# --- ppdf.py ---
#!/usr/bin/env python3
"""
ppdf: An advanced PDF text and structure extraction tool.

This script provides a comprehensive solution for extracting, understanding, and
reformatting content from PDF files. It uses a multi-stage analysis pipeline
(handled by the PDFTextExtractor class) to identify the document's logical
structure and an LLM to produce a clean, readable Markdown file.
"""

import argparse
import copy
import json
import logging
import os
import re
import statistics
import sys
import time

# --- Dependency Imports ---
try:
    import requests
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
    from rich.theme import Theme
except ImportError as e:
    print(f"Error: Missing required library. -> {e}")
    print("Please install all core dependencies with:")
    print("pip install requests rich")
    sys.exit(1)

# --- Local Application Imports ---
from ppdf_lib.constants import (
    PROMPT_PRESETS,
    PROMPT_ANALYZE_PROMPT,
    PROMPT_DESCRIBE_TABLE_PURPOSE,
)
from ppdf_lib.api import process_pdf_text, process_pdf_images
from ppdf_lib.extractor import PDFTextExtractor

from core.tts import TTSManager, PIPER_AVAILABLE
from ppdf_lib.renderer import ASCIIRenderer
from core.log_utils import ContextFilter, setup_logging


# --- LOGGING SETUP ---
log_llm = logging.getLogger("ppdf.llm")


# --- CUSTOM ARGPARSE FORMATTER ---
class CustomHelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter, argparse.RawTextHelpFormatter
):
    """
    A custom argparse formatter that combines showing default values with
    preserving newline formatting in help text.
    """

    pass


class Application:
    """Orchestrates the PDF processing workflow based on command-line arguments."""

    DEFAULT_FILENAME_SENTINEL = "__DEFAULT_FILENAME__"
    DEFAULT_CHUNK_SIZE = 4000

    def __init__(self, args):
        self.args = args
        self.stats = {"chunk_sizes": []}
        self.extractor = PDFTextExtractor(
            args.pdf_file, args.columns, args.remove_footers, args.keep_style
        )
        self.tts_manager = None

    def run(self):
        """Main entry point for the application logic."""
        self.stats["start_time"] = time.monotonic()
        setup_logging(
            level=logging.INFO if self.args.verbose else logging.WARNING,
            color_logs=self.args.color_logs,
            debug_topics=self.args.debug_topics,
        )

        try:
            # Handle image extraction mode first, as it's an exclusive action
            if self.args.extract_images:
                logging.getLogger("ppdf").info("--- Running in Image Extraction Mode ---")
                process_pdf_images(
                    self.args.pdf_file,
                    self.args.extract_images,
                    self.args.url,
                    self.args.model,
                )
                return

            self._smart_preset_override()
            presets_to_run = self._get_presets_to_run()

            if self.args.analyze_prompts:
                self._run_stage0_prompt_analysis(presets_to_run)

            context_size = self._get_model_details()
            if context_size and self.args.chunk_size == self.DEFAULT_CHUNK_SIZE:
                self.args.chunk_size = int(context_size * 0.8)
                logging.getLogger("ppdf").info(
                    "Auto-adjusting chunk size to %d.", self.args.chunk_size
                )

            pages = self._parse_page_selection()
            if pages is None and self.args.pages.lower() != "all":
                sys.exit(1)

            pdf_start = time.monotonic()
            extraction_options = {
                "num_cols": self.args.columns,
                "rm_footers": self.args.remove_footers,
                "style": self.args.keep_style,
            }
            sections, page_models = process_pdf_text(
                self.args.pdf_file,
                extraction_options,
                self.args.url,
                self.args.model,
                apply_labeling=self.args.semantic_labeling,
            )
            self.stats["pdf_analysis_duration"] = time.monotonic() - pdf_start
            self.stats["pages_processed"] = len(page_models)
            self.stats["sections_reconstructed"] = len(sections)

            if not sections:
                logging.getLogger("ppdf").error("No content could be extracted.")
                self._display_performance_epilogue(self.stats, "N/A")
                return

            for preset in presets_to_run:
                self._run_for_preset(preset, sections)

        except Exception as e:
            logging.getLogger("ppdf").critical(
                "\nAn unexpected error occurred: %s", e, exc_info=True
            )
            if self.tts_manager:
                self.tts_manager.cleanup()
            sys.exit(1)

    def _smart_preset_override(self):
        """Automatically selects a prompt preset based on other flags."""
        if self.args.prompt_preset != "auto":
            return
        app_log = logging.getLogger("ppdf")
        if self.args.speak:
            self.args.prompt_preset = "tts"
            app_log.info("--speak flag detected. Auto-selecting 'tts' preset.")
        elif self.args.rich_stream:
            self.args.prompt_preset = "creative"
            app_log.info("--rich-stream flag detected. Auto-selecting 'creative' preset.")
        else:
            self.args.prompt_preset = "strict"  # Default fallback

    def _get_presets_to_run(self):
        """Determines which prompt presets to execute based on arguments."""
        if not self.args.batch_presets:
            return [self.args.prompt_preset]

        if self.args.batch_presets == "all":
            return list(PROMPT_PRESETS.keys())

        prefix = self.args.batch_presets
        presets_to_run = [p for p in PROMPT_PRESETS.keys() if p.startswith(prefix)]
        if not presets_to_run:
            logging.getLogger("ppdf").error("No presets found with prefix: '%s'", prefix)
            sys.exit(1)
        return presets_to_run

    def _run_stage0_prompt_analysis(self, presets_to_analyze):
        """
        [STAGE 0] Analyzes each system prompt using the LLM to get feedback for
        iterative refinement.
        """
        app_log = logging.getLogger("ppdf")
        app_log.info("\n--- STAGE 0: Analyzing System Prompts with LLM ---")

        for preset_name in presets_to_analyze:
            preset_data = PROMPT_PRESETS[preset_name]
            app_log.info("Analyzing preset: '%s'...", preset_name)
            user_content = preset_data["prompt"]

            analysis_response, _ = self._query_llm_api(
                system=PROMPT_ANALYZE_PROMPT,
                user=user_content,
                is_analysis=True,
            )

            if analysis_response:
                log_llm.info(
                    "\n--- LLM Analysis of Prompt Preset: [%s] ---\n%s\n"
                    "--- End of Analysis ---",
                    preset_name,
                    analysis_response.strip(),
                )
            else:
                log_llm.warning("LLM analysis failed for preset: %s", preset_name)

        app_log.info("\n--- STAGE 0: Prompt Analysis Complete ---\n")

    def _preprocess_table_summaries(self, sections, preset_name):
        """
        Finds tables and uses an LLM to describe their purpose if the preset
        has table_summaries enabled.
        """
        preset_data = PROMPT_PRESETS.get(preset_name, {})
        if not preset_data.get("table_summaries", False):
            return sections

        log_tables = logging.getLogger("ppdf.tables")
        log_tables.info("\n--- Preprocessing Stage: Describing Table Purposes ---")

        processed_sections = copy.deepcopy(sections)

        for section in processed_sections:
            for p_idx, p in enumerate(section.paragraphs):
                if not p.is_table:
                    continue

                plain_text_table = p.get_text()
                log_tables.debug(
                    "Found table to describe in section '%s':\n%s",
                    section.title,
                    plain_text_table,
                )
                prev_p = section.paragraphs[p_idx - 1] if p_idx > 0 else None
                next_p = (
                    section.paragraphs[p_idx + 1]
                    if p_idx < len(section.paragraphs) - 1
                    else None
                )

                context_parts = [
                    section.title or "Untitled",
                    prev_p.get_text() if prev_p else "",
                    plain_text_table,
                    next_p.get_text() if next_p else "",
                ]
                user_context = "\n\n".join(part for part in context_parts if part)

                summary_text, _ = self._query_llm_api(
                    system=PROMPT_DESCRIBE_TABLE_PURPOSE, user=user_context
                )

                if summary_text:
                    log_tables.debug("LLM-generated description:\n%s", summary_text)
                    section.paragraphs[p_idx].lines = [summary_text]
                    section.paragraphs[p_idx].is_table = False
                else:
                    log_tables.warning(
                        "Failed to get description for table in section '%s'",
                        section.title,
                    )
        return processed_sections

    def _run_for_preset(self, preset_name, sections):
        """Executes the processing pipeline for a single prompt preset."""
        run_stats = {"start_time": time.monotonic()}
        self.stats["chunk_sizes"] = []
        original_output = self.args.output_file
        original_extracted = self.args.extracted_file

        log_filter = ContextFilter(preset_name)
        root_logger = logging.getLogger()
        root_logger.addFilter(log_filter)

        is_batch_run = self.args.batch_presets is not None

        if is_batch_run:
            logging.getLogger("ppdf").info(
                "\n--- Running Batch Mode: Processing with preset '%s' ---",
                preset_name,
            )
            pdf_base = os.path.splitext(os.path.basename(self.args.pdf_file))[0]
            if original_output:
                self.args.output_file = f"{pdf_base}_{preset_name}.md"
            if original_extracted:
                self.args.extracted_file = f"{pdf_base}_{preset_name}.extracted"

        try:
            self._resolve_output_filenames(is_batch_run)

            preset_data = PROMPT_PRESETS[preset_name]
            system_prompt = preset_data["prompt"]
            produces_markdown = preset_data.get("markdown_output", False)

            self._log_run_conditions(system_prompt, preset_name)
            processed_sections = self._preprocess_table_summaries(sections, preset_name)
            self._save_extracted_text(processed_sections)

            if self.args.dry_run:
                self._display_dry_run_summary(processed_sections)
            else:
                if self.args.speak:
                    self._initialize_tts()

                llm_start = time.monotonic()
                final_md = self._generate_output_with_llm(
                    processed_sections,
                    system_prompt,
                    run_stats,
                    produces_markdown,
                )
                run_stats["llm_wall_duration"] = time.monotonic() - llm_start

                self._save_llm_output(final_md)
        finally:
            if self.tts_manager:
                self.tts_manager.cleanup()
                self.tts_manager = None
            self._display_performance_epilogue(run_stats, preset_name)
            # Restore original filenames for the next loop iteration
            self.args.output_file = original_output
            self.args.extracted_file = original_extracted
            root_logger.removeFilter(log_filter)

    def _initialize_tts(self):
        """Initializes the TTSManager if the --speak flag is used."""
        if not PIPER_AVAILABLE:
            logging.warning("TTS dependencies not installed. --speak flag will be ignored.")
            logging.warning('To enable speech, run: pip install "piper-tts==1.3.0" pyaudio')
            self.args.speak = None
            return
        try:
            self.tts_manager = TTSManager(lang=self.args.speak)
            logging.getLogger("ppdf.tts").info(
                "TTS Manager initialized for language: '%s'", self.args.speak
            )
        except Exception as e:
            logging.getLogger("ppdf.tts").error(
                "Failed to initialize TTS Manager: %s", e, exc_info=True
            )
            self.tts_manager = None
            self.args.speak = None

    def _get_model_details(self):
        """Queries the Ollama /api/show endpoint for model details."""
        app_log = logging.getLogger("ppdf")
        app_log.info("Querying details for model: %s...", self.args.model)
        try:
            response = requests.post(
                f"{self.args.url}/api/show", json={"name": self.args.model}
            )
            if response.status_code == 404:
                app_log.error("Model '%s' not found.", self.args.model)
                tags_resp = requests.get(f"{self.args.url}/api/tags")
                if tags_resp.status_code == 200:
                    models = tags_resp.json().get("models", [])
                    names = "\n".join(
                        f"  - {m['name']}" for m in sorted(models, key=lambda x: x["name"])
                    )
                    app_log.error(f"Available models:\n{names if names else '  (None)'}")
                sys.exit(1)
            response.raise_for_status()
            model_info = response.json()
            details = model_info.get("details", {})
            app_log.info(
                "Ollama Model: Family=%s, Size=%s, Quantization=%s",
                details.get("family", "N/A"),
                details.get("parameter_size", "N/A"),
                details.get("quantization_level", "N/A"),
            )
            for line in model_info.get("modelfile", "").split("\n"):
                if "num_ctx" in line.lower():
                    try:
                        return int(line.split()[1])
                    except (ValueError, IndexError):
                        continue
            return None
        except requests.exceptions.RequestException as e:
            app_log.error("Could not connect to Ollama at %s: %s", self.args.url, e)
            sys.exit(1)

    def _display_performance_epilogue(self, run_stats, preset_name):
        """Displays a summary of performance statistics."""
        app_log = logging.getLogger("ppdf")
        total_dur = time.monotonic() - run_stats.get("start_time", time.monotonic())
        self.stats.update(run_stats)

        eval_dur_s = self.stats.get("llm_eval_duration", 0) / 1e9
        eval_count = self.stats.get("llm_eval_count", 0)
        tps = (eval_count / eval_dur_s) if eval_dur_s > 0 else 0

        pdf_analysis_dur = self.stats.get("pdf_analysis_duration", 0)
        pages = self.stats.get("pages_processed", 0)
        sections = self.stats.get("sections_reconstructed", 0)
        report = [
            f"\n--- Performance Epilogue (Preset: {preset_name}) ---",
            f"Total Execution Time: {total_dur:.1f} seconds",
            f"PDF Analysis: {pdf_analysis_dur:.1f}s ({pages} pages, {sections} sections)",
        ]
        if not self.args.dry_run and not self.args.extract_images:
            llm_wall_dur = self.stats.get("llm_wall_duration", 0)
            llm_eval_count = self.stats.get("llm_eval_count", 0)
            report.extend(
                [
                    f"LLM Wall Clock: {llm_wall_dur:.1f}s",
                    f"LLM Generation: {tps:.1f} tokens/sec ({llm_eval_count:,} tokens)",
                ]
            )
            chunk_sizes = self.stats.get("chunk_sizes", [])
            if chunk_sizes:
                min_s, max_s = min(chunk_sizes), max(chunk_sizes)
                avg_s = statistics.mean(chunk_sizes)
                stdev_s = statistics.stdev(chunk_sizes) if len(chunk_sizes) > 1 else 0
                report.append(
                    f"LLM Chunk Stats:  {len(chunk_sizes):,} chunks "
                    f"(min: {min_s:,}, max: {max_s:,}, avg: {avg_s:,.0f}, "
                    f"stddev: {stdev_s:,.0f})"
                )
        app_log.info("\n".join(report))

    def _log_run_conditions(self, system_prompt, preset_name):
        """If debugging is enabled, logs script arguments and system prompt."""
        if self.args.debug_topics:
            args_copy = vars(self.args).copy()
            args_copy["prompt_preset"] = preset_name
            log_llm.debug(
                "--- Script Running Conditions ---\n%s",
                "\n".join([f"  - {k:<16} : {v}" for k, v in args_copy.items()]),
            )
        logging.getLogger("ppdf").info(
            "---\nLLM System Prompt (Preset: '%s'):\n%s\n---",
            preset_name,
            system_prompt,
        )

    def _resolve_output_filenames(self, is_batch_run):
        """Sets default output filenames based on the input PDF name."""
        S = self.DEFAULT_FILENAME_SENTINEL
        pdf_base = os.path.splitext(os.path.basename(self.args.pdf_file))[0]

        if not is_batch_run:
            if self.args.output_file == S:
                self.args.output_file = f"{pdf_base}.md"
            if self.args.extracted_file == S:
                self.args.extracted_file = f"{pdf_base}.extracted"
        elif self.args.output_file:
            logging.getLogger("ppdf").info(
                "Output for this run will be saved to '%s'",
                self.args.output_file,
            )

    def _parse_page_selection(self):
        """Parses the --pages argument string (e.g., '1,3,5-7') into a set."""
        if self.args.pages.lower() == "all":
            return None
        pages = set()
        try:
            for p in self.args.pages.split(","):
                part = p.strip()
                if "-" in part:
                    s, e = map(int, part.split("-"))
                    pages.update(range(s, e + 1))
                else:
                    pages.add(int(part))
            return pages
        except ValueError:
            logging.getLogger("ppdf").error("Invalid --pages format: %s.", self.args.pages)
            return None

    def _display_dry_run_summary(self, sections):
        """Prints a detailed summary of the extracted document structure."""
        print("\n--- Document Structure Summary (Dry Run) ---")

        print("\n--- Page Layout Analysis ---")
        renderer = ASCIIRenderer(self.extractor)
        for page in self.extractor.page_models:
            print(f"\n[ Page {page.page_num} Layout ]")
            print(renderer.render(page))
        if sections:
            print("\n--- Reconstructed Sections Summary ---")
            for i, s in enumerate(sections):
                title = s.title or "Untitled"
                print(
                    f"\nSection {i + 1}:\n  Title: {title}\n"
                    f"  Pages: {s.page_start}-{s.page_end}"
                )
                num_tables = sum(1 for p in s.paragraphs if p.is_table)
                num_paras = len(s.paragraphs)
                num_lines = sum(len(p.lines) for p in s.paragraphs)
                num_chars = len(s.get_text())
                print(
                    f"  Stats: {num_paras} paras ({num_tables} tables), "
                    f"{num_lines} lines, {num_chars} chars"
                )
                if num_tables > 0:
                    print("  --- Formatted Table(s) ---")
                    for p in s.paragraphs:
                        if p.is_table:
                            print("\n".join([f"    {line}" for line in p.lines]))
        print("\n--- End of Dry Run Summary ---")

    def _save_extracted_text(self, sections):
        """Saves the raw, reconstructed text to a file if requested."""
        if not self.args.extracted_file or not sections:
            return
        content = []
        for s in sections:
            s_header = f"--- Page {s.page_start}-{s.page_end} (Title: {s.title or 'N/A'}) ---"
            s_content = []
            for p in s.paragraphs:
                p_text = p.get_text()
                p_header = ""
                if p.labels:
                    p_header = f"[{', '.join(p.labels).upper()}]"
                elif p.is_table:
                    p_header = "[TABLE]"
                s_content.append(f"{p_header}\n{p_text}" if p_header else p_text)
            content.append(f"{s_header}\n{'\n\n'.join(s_content)}")
        try:
            with open(self.args.extracted_file, "w", encoding="utf-8") as f:
                f.write("\n\n\n".join(content))
            logging.getLogger("ppdf").info(
                "Raw extracted text saved to: '%s'",
                self.args.extracted_file,
            )
        except IOError as e:
            logging.getLogger("ppdf").error("Error saving raw text: %s", e)

    def _save_llm_output(self, markdown_text):
        """Saves the final LLM-generated markdown to a file."""
        if not self.args.output_file:
            return
        try:
            with open(self.args.output_file, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            logging.getLogger("ppdf").info(
                "\nLLM output saved to: '%s'", self.args.output_file
            )
        except IOError as e:
            logging.getLogger("ppdf").error("Error saving LLM output: %s", e)

    def _chunk_text_by_paragraphs(self, text, max_size):
        """
        Splits text into chunks of a maximum size without breaking paragraphs.
        Yields each chunk as a string.
        """
        paragraphs = re.split(r"\n{2,}", text.strip())
        current_chunk_parts = []
        current_chunk_size = 0

        for para in paragraphs:
            para_size = len(para)
            if current_chunk_parts and current_chunk_size + para_size + 2 > max_size:
                yield "\n\n".join(current_chunk_parts)
                current_chunk_parts = [para]
                current_chunk_size = para_size
            else:
                current_chunk_parts.append(para)
                current_chunk_size += para_size + 2

        if current_chunk_parts:
            yield "\n\n".join(current_chunk_parts)

    def _generate_output_with_llm(self, sections, system_prompt, run_stats, produces_markdown):
        """Orchestrates section-by-section, chunk-aware processing with the LLM."""
        all_markdown, agg_stats = [], {"eval_count": 0, "eval_duration": 0}
        chars_sent, chars_received = 0, 0

        for i, section in enumerate(sections):
            s_page, e_page = section.page_start, section.page_end
            logging.getLogger("ppdf").info(
                "\nProcessing section %d/%d (Pages: %s-%s): '%s'",
                i + 1,
                len(sections),
                s_page,
                e_page,
                section.title or "Untitled",
            )
            section_markdown_parts = []
            section_text = section.get_llm_text()
            chunks = list(self._chunk_text_by_paragraphs(section_text, self.args.chunk_size))

            for j, chunk_text in enumerate(chunks):
                self.stats["chunk_sizes"].append(len(chunk_text))
                logging.getLogger("ppdf").info(
                    "  -> Processing chunk %d/%d for section %d (%d chars)...",
                    j + 1,
                    len(chunks),
                    i + 1,
                    len(chunk_text),
                )

                title = section.title or "Untitled"
                if not self.args.no_fmt_titles:
                    title = title.upper()

                user_content = (
                    f"# {title}\n\n{chunk_text}"
                    if produces_markdown
                    else f"{title}\n\n{chunk_text}"
                )

                # Add a stop sequence to the very last chunk to prevent rambling
                stop_sequences = None
                is_final_chunk = i == len(sections) - 1 and j == len(chunks) - 1
                if is_final_chunk:
                    stop_sequences = ["||END||"]
                    lure = "The next document begins:"
                    user_content += stop_sequences[0] + lure

                full_response, chunk_stats = self._query_llm_api(
                    system_prompt,
                    user_content,
                    self.tts_manager,
                    stop_sequences=stop_sequences,
                )
                if full_response:
                    if is_final_chunk and stop_sequences:
                        full_response = full_response.split(stop_sequences[0])[0]
                        full_response = full_response.rstrip()

                    response = full_response
                    if (
                        produces_markdown
                        and j > 0
                        and response.strip().startswith(f"# {title}")
                    ):
                        response = re.sub(rf"^# {re.escape(title)}\s*", "", response.strip())

                    section_markdown_parts.append(response)
                    for key in agg_stats:
                        agg_stats[key] += chunk_stats.get(key, 0)
                    chars_sent += len(system_prompt) + len(user_content)
                    chars_received += len(full_response)
                else:
                    err_msg = f"\n[ERROR: Could not process chunk {j + 1} of section {i + 1}]"
                    section_markdown_parts.append(err_msg)

            all_markdown.append("\n\n".join(section_markdown_parts))

        run_stats.update({f"llm_{k}": v for k, v in agg_stats.items()})
        run_stats["llm_chars_sent"] = chars_sent
        run_stats["llm_chars_received"] = chars_received
        return "\n\n".join(all_markdown)

    def _query_llm_api(
        self,
        system,
        user,
        tts_manager=None,
        is_analysis=False,
        stop_sequences=None,
    ):
        """Queries the Ollama /api/generate endpoint and streams response."""
        options = {"temperature": self.args.temperature}
        if stop_sequences:
            options["stop"] = stop_sequences

        payload = {
            "model": self.args.model,
            "system": system,
            "prompt": user,
            "stream": True,
            "options": options,
        }

        full_content, stats = "", {}
        thought_content, is_thinking = "", False

        if not is_analysis and self.args.debug_topics and "llm" in self.args.debug_topics:
            log_llm.debug("User content for chunk:\n%s", payload["prompt"])
            if "options" in payload:
                log_llm.debug("API options: %s", payload["options"])

        try:
            r = requests.post(f"{self.args.url}/api/generate", json=payload, stream=True)
            r.raise_for_status()

            if is_analysis:
                for line in r.iter_lines():
                    j, chunk = self._process_stream_line(line, None)
                    if chunk is not None:
                        full_content += chunk
                    if j and j.get("done"):
                        stats = j
                return full_content.strip(), stats

            def process_chunk(chunk):
                nonlocal thought_content, is_thinking
                output_chunk = ""
                while chunk:
                    if is_thinking:
                        if "</think>" in chunk:
                            part, rest = chunk.split("</think>", 1)
                            thought_content += part
                            is_thinking = False
                            chunk = rest
                        else:
                            thought_content += chunk
                            chunk = ""
                    else:
                        if "<think>" in chunk:
                            part, rest = chunk.split("<think>", 1)
                            output_chunk += part
                            is_thinking = True
                            chunk = rest
                        else:
                            output_chunk += chunk
                            chunk = ""
                return output_chunk

            if self.args.rich_stream:
                full_content = self._stream_to_rich(r, process_chunk, stats)
            else:
                full_content = self._stream_to_stdout(r, process_chunk, stats)

            if thought_content:
                log_llm.info(
                    "\n--- LLM Thought Process ---\n%s\n--- End of Thought ---",
                    thought_content.strip(),
                )

            return full_content.strip(), stats
        except requests.exceptions.RequestException as e:
            log_llm.error("Ollama API request failed: %s", e)
            return None, {}

    def _stream_to_rich(self, response, processor, stats):
        """Helper for streaming LLM response to a `rich` live display."""
        content = ""
        custom_theme = Theme(
            {
                "table.header": "bold sky_blue2",
                "markdown.h1": "bold sky_blue2",
                "markdown.strong": "bold sky_blue2",
                "markdown.em": "italic turquoise2",
                "markdown.code": "grey74",
                "markdown.link": "underline bright_blue",
                "markdown.text": "grey93",
            }
        )
        console = Console(theme=custom_theme)
        live = Live(console=console, auto_refresh=False, vertical_overflow="visible")
        with live:
            for line in response.iter_lines():
                j, raw_chunk = self._process_stream_line(line, self.tts_manager)
                if raw_chunk is not None:
                    display_chunk = processor(raw_chunk)
                    if display_chunk:
                        content += display_chunk
                        live.update(Markdown(content), refresh=True)
                if j and j.get("done"):
                    stats.update(j)
        return content

    def _stream_to_stdout(self, response, processor, stats):
        """Helper for streaming LLM response directly to stdout."""
        content = ""
        print()
        for line in response.iter_lines():
            j, raw_chunk = self._process_stream_line(line, self.tts_manager)
            if raw_chunk is not None:
                display_chunk = processor(raw_chunk)
                if display_chunk:
                    content += display_chunk
                    print(display_chunk, end="", flush=True)
            if j and j.get("done"):
                stats.update(j)
        print()
        return content

    def _process_stream_line(self, line, tts_manager):
        """Helper to process a single line from the Ollama stream."""
        if not line:
            return None, None
        try:
            j = json.loads(line.decode("utf-8"))
            chunk = j.get("response", "")
            if chunk and tts_manager:
                tts_manager.add_text(chunk)
            return j, chunk
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, None

    @staticmethod
    def parse_arguments(args=None):
        """Parses command-line arguments for the script."""
        examples = [
            "\nExamples:",
            '  python ppdf.py document.pdf -o "output.md"',
            '  python ppdf.py document.pdf --extract-images "assets/images/my_module"',
            "  python ppdf.py document.pdf --semantic-labeling -e out.txt",
            "  python ppdf.py document.pdf -d llm,struct --color-logs",
        ]
        presets_details = ["\nPrompt Preset Details:"]
        for name in sorted(PROMPT_PRESETS.keys()):
            presets_details.append(f"  {name}: {PROMPT_PRESETS[name]['desc']}")

        parser = argparse.ArgumentParser(
            description="An advanced PDF text and structure extraction tool.",
            formatter_class=CustomHelpFormatter,
            add_help=False,
            epilog="\n".join(presets_details + examples),
        )
        S = Application.DEFAULT_FILENAME_SENTINEL

        g_opts = parser.add_argument_group("Main Options")
        g_opts.add_argument("pdf_file", help="Path to the input PDF file.")
        g_opts.add_argument(
            "-h",
            "--help",
            action="help",
            help="Show this help message and exit.",
        )

        g_proc = parser.add_argument_group("Processing Control")
        g_proc.add_argument(
            "-p",
            "--pages",
            default="all",
            metavar="PAGES",
            help="Pages to process (e.g., '1,3,5-7'). (default: %(default)s)",
        )
        g_proc.add_argument(
            "-C",
            "--columns",
            default="auto",
            metavar="COUNT",
            help="Force column count (e.g., '2', 'auto'). (default: %(default)s)",
        )
        g_proc.add_argument(
            "--no-remove-footers",
            action="store_false",
            dest="remove_footers",
            help="Disable footer removal logic. (default: Enabled)",
        )
        g_proc.add_argument(
            "-K",
            "--keep-style",
            action="store_true",
            help="Preserve bold/italic formatting from PDF. (default: %(default)s)",
        )
        g_proc.add_argument(
            "--no-fmt-titles",
            action="store_true",
            help="Disable automatic uppercasing of section titles. (default: %(default)s)",
        )

        g_llm = parser.add_argument_group("LLM Configuration")
        g_llm.add_argument(
            "-M",
            "--model",
            default="llama3.1:latest",
            help="Ollama model to use. (default: %(default)s)",
        )
        g_llm.add_argument(
            "-U",
            "--url",
            default="http://localhost:11434",
            help="Ollama API URL. (default: %(default)s)",
        )
        g_llm.add_argument(
            "-z",
            "--chunk-size",
            type=int,
            default=Application.DEFAULT_CHUNK_SIZE,
            help="Max characters per LLM chunk. (default: %(default)s)",
        )
        g_llm.add_argument(
            "-t",
            "--temperature",
            type=float,
            default=0.2,
            help="Set the model's temperature. (default: %(default)s)",
        )

        preset_choices = ["auto"] + sorted(PROMPT_PRESETS.keys())
        preset_group = g_llm.add_mutually_exclusive_group()
        preset_group.add_argument(
            "--prompt-preset",
            default="auto",
            choices=preset_choices,
            help=("System prompt preset to use. " "(default: %(default)s)"),
        )
        preset_group.add_argument(
            "--batch-presets",
            nargs="?",
            const="all",
            default=None,
            metavar="PREFIX",
            help="Run all presets, or only those with a specific prefix.",
        )

        g_out = parser.add_argument_group("Script Output & Actions")
        g_out.add_argument(
            "-o",
            "--output-file",
            nargs="?",
            const=S,
            default=None,
            metavar="FILE",
            help="Save final output. Defaults to PDF name.",
        )
        g_out.add_argument(
            "-e",
            "--extracted-file",
            nargs="?",
            const=S,
            default=None,
            metavar="FILE",
            help="Save raw extracted text. Defaults to PDF name.",
        )
        g_out.add_argument(
            "--extract-images",
            metavar="DIR",
            default=None,
            help="Extract images to a directory and exit.",
        )
        g_out.add_argument(
            "--semantic-labeling",
            action="store_true",
            help="Apply semantic labels to text chunks (requires LLM).",
        )
        g_out.add_argument(
            "--rich-stream",
            action="store_true",
            help="Render live LLM output as Markdown in terminal. (default: %(default)s)",
        )
        g_out.add_argument(
            "--color-logs",
            action="store_true",
            help="Enable colored logging output. (default: %(default)s)",
        )
        g_out.add_argument(
            "-S",
            "--speak",
            nargs="?",
            const="en",
            choices=["en", "es", "ca"],
            help="Stream output to speech (en, es, ca).",
        )
        g_out.add_argument(
            "-D",
            "--dry-run",
            action="store_true",
            help="Analyze structure without calling LLM. (default: %(default)s)",
        )
        g_out.add_argument(
            "--analyze-prompts",
            action="store_true",
            help="Enable Stage 0 to have the LLM analyze the selected presets."
            " (default: %(default)s)",
        )
        g_out.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="Enable INFO logging for detailed progress. (default: %(default)s)",
        )
        g_out.add_argument(
            "-d",
            "--debug",
            nargs="?",
            const="all",
            dest="debug_topics",
            metavar="TOPICS",
            help="Enable DEBUG logging (all,layout,struct,llm,tts,tables,api).",
        )

        return parser.parse_args(args)


def main():
    """Main entry point for the script."""
    core_dir = os.path.join(os.path.dirname(__file__), "core")
    os.makedirs(core_dir, exist_ok=True)
    init_path = os.path.join(core_dir, "__init__.py")
    if not os.path.exists(init_path):
        with open(init_path, "w") as _:  # noqa: E701
            pass

    # Basic logging config for early errors before full setup
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    try:
        args = Application.parse_arguments(sys.argv[1:])
        app = Application(args)
        app.run()
    except FileNotFoundError as e:
        logging.getLogger("ppdf").critical(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logging.getLogger("ppdf").info("\nProcess interrupted by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        logging.getLogger("ppdf").critical(
            "\nAn unexpected error occurred: %s", e, exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
