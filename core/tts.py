#!/usr/bin/env python3
"""
core/tts.py: Manages real-time text-to-speech synthesis and playback.

This module provides the TTSManager class, which uses the Piper library for
high-quality offline TTS and PyAudio for streaming audio playback. It handles
voice model downloading and caching, and uses a threaded queue to process text
and play audio without blocking the main application.
"""

import logging
import os
import queue
import re
import threading
import requests

# Gracefully handle optional TTS dependencies
try:
    import pyaudio
    from piper import PiperVoice

    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False

log_tts = logging.getLogger("ppdf.tts")


class TTSManager:
    """
    Manages real-time text-to-speech synthesis and playback using Piper/PyAudio.

    This class handles voice model loading, audio stream setup, and processing
    text chunks into audible speech in a separate thread.

    Args:
        lang (str): The language code for the voice model (e.g., 'en', 'es').

    Raises:
        RuntimeError: If the Piper TTS engine fails to initialize.
    """

    _SENTENCE_END = re.compile(r"(?<=[.!?])\s")

    def __init__(self, lang: str):
        self.app_log = logging.getLogger("ppdf")
        if not PIPER_AVAILABLE:
            raise RuntimeError(
                "TTS dependencies (piper-tts, pyaudio) are not installed."
            )

        self.voice = self._get_piper_engine(lang)
        if not self.voice:
            raise RuntimeError("Failed to initialize Piper TTS engine.")

        self.pyaudio_instance = pyaudio.PyAudio()

        # Safely get audio parameters with sensible fallbacks.
        sample_rate = getattr(self.voice.config, "sample_rate", 22050)
        num_channels = getattr(self.voice.config, "num_channels", 1)
        sample_width = getattr(self.voice.config, "sample_width", 2)

        log_tts.debug(
            "Initializing PyAudio stream with: Rate=%d, Channels=%d, Width=%d",
            sample_rate,
            num_channels,
            sample_width,
        )

        self.stream = self.pyaudio_instance.open(
            format=self.pyaudio_instance.get_format_from_width(sample_width),
            channels=num_channels,
            rate=sample_rate,
            output=True,
        )

        self.text_queue = queue.Queue()
        self.processing_thread = threading.Thread(
            target=self._process_queue, daemon=True
        )
        self.processing_thread.start()
        self.text_buffer = ""

    def _get_piper_engine(self, lang: str):
        """
        Checks for a cached Piper TTS model and downloads it if not found.

        Models are cached in ~/.cache/ppdf/models/.

        Args:
            lang (str): The language code ('en', 'es', 'ca') for the model.

        Returns:
            PiperVoice | None: The loaded voice engine, or None on failure.
        """
        MODELS_CONFIG = {
            "en": {
                "model": "en_US-lessac-medium.onnx",
                "url_base": (
                    "https://huggingface.co/rhasspy/piper-voices"
                    "/resolve/main/en/en_US/lessac/medium/"
                ),
            },
            "es": {
                "model": "es_ES-sharvard-medium.onnx",
                "url_base": (
                    "https://huggingface.co/rhasspy/piper-voices"
                    "/resolve/main/es/es_ES/sharvard/medium/"
                ),
            },
            "ca": {
                "model": "ca_ES-upc_ona-medium.onnx",
                "url_base": (
                    "https://huggingface.co/rhasspy/piper-voices"
                    "/resolve/main/ca/ca_ES/upc_ona/medium/"
                ),
            },
        }
        config = MODELS_CONFIG.get(lang)
        if not config:
            self.app_log.error(
                "Language '%s' is not supported for speech synthesis.", lang
            )
            return None

        cache_dir = os.path.expanduser("~/.cache/ppdf/models")
        os.makedirs(cache_dir, exist_ok=True)

        for path_suffix in [config["model"], f"{config['model']}.json"]:
            path = os.path.join(cache_dir, path_suffix)
            if not os.path.exists(path):
                filename = os.path.basename(path)
                self.app_log.info("Performing one-time download for '%s'...", filename)
                try:
                    url = config["url_base"] + path_suffix
                    with requests.get(url, stream=True) as r:
                        r.raise_for_status()
                        with open(path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    self.app_log.info("Successfully downloaded %s", filename)
                except requests.exceptions.RequestException as e:
                    self.app_log.error(
                        "Failed to download voice model component: %s", e
                    )
                    if os.path.exists(path):
                        os.remove(path)
                    return None
        return PiperVoice.load(os.path.join(cache_dir, config["model"]))

    def add_text(self, text: str):
        """
        Adds a chunk of text to the buffer, processing complete sentences.

        Cleans markdown and other artifacts before adding to the synthesis queue.

        Args:
            text (str): The text chunk to add.
        """
        clean_text = re.sub(r"#+\s*|[\*_`]|<[^>]+>", "", text, flags=re.DOTALL)
        self.text_buffer += clean_text

        while True:
            match = self._SENTENCE_END.search(self.text_buffer)
            if match:
                sentence = self.text_buffer[: match.end()]
                self.text_buffer = self.text_buffer[match.end() :]
                if sentence.strip():
                    log_tts.debug("Queueing sentence: '%s'", sentence.strip())
                    self.text_queue.put(sentence)
            else:
                break

    def _process_queue(self):
        """Worker thread to process sentences from the queue and play audio."""
        while True:
            try:
                sentence = self.text_queue.get()
                if sentence is None:  # Sentinel to stop the thread
                    log_tts.debug("Sentinel received, shutting down TTS worker thread.")
                    self.text_queue.task_done()
                    break

                audio_generator = self.voice.synthesize(sentence)
                for audio_chunk in audio_generator:
                    self.stream.write(audio_chunk.audio_int16_bytes)
                self.text_queue.task_done()
            except Exception as e:
                log_tts.error(
                    "Fatal error in TTS processing thread, stopping TTS: %s", e
                )
                break

    def finalize(self):
        """
        Processes any remaining text in the buffer.

        This should be called when no more text will be added to ensure the last
        fragments of speech are played.
        """
        if self.text_buffer.strip():
            log_tts.debug("Queueing final buffer: '%s'", self.text_buffer.strip())
            self.text_queue.put(self.text_buffer)
            self.text_buffer = ""

    def cleanup(self):
        """
        Shuts down the TTS system gracefully.

        Waits for the queue to finish, stops the worker thread, and closes the
        audio stream.
        """
        log_tts.info("Finalizing TTS, waiting for audio queue to finish...")
        self.finalize()
        self.text_queue.join()  # Wait for all sentences to be processed

        self.text_queue.put(None)  # Send sentinel to stop the thread
        self.processing_thread.join(timeout=2)

        if self.stream.is_active():
            self.stream.stop_stream()
        self.stream.close()
        self.pyaudio_instance.terminate()
        log_tts.info("TTS Manager cleaned up successfully.")
