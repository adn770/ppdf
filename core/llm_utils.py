# --- core/llm_utils.py ---
import logging
import requests
import json
import base64
import time
import re

# Local Application Imports
from dmme_lib.constants import PROMPT_REGISTRY

log_llm = logging.getLogger("dmme.llm")


def _format_text_for_log(text: str) -> str:
    """Formats a long text block into a concise, single-line summary for logging."""
    single_line_text = str(text).replace("\n", " ").strip()
    if len(single_line_text) > 120:
        return f'"{single_line_text[:55]}...{single_line_text[-55:]}"'
    return f'"{single_line_text}"'


def _get_prompt_from_registry(key: str, lang: str) -> str:
    """Safely retrieves a prompt, falling back to English."""
    return PROMPT_REGISTRY.get(key, {}).get(lang, PROMPT_REGISTRY.get(key, {}).get("en"))


def get_model_details(ollama_url: str, model: str) -> dict:
    """Queries the Ollama /api/show endpoint for model details."""
    log_llm.info("Querying details for model: %s...", model)
    try:
        response = requests.post(f"{ollama_url}/api/show", json={"name": model}, timeout=10)
        if response.status_code == 404:
            log_llm.error("Model '%s' not found.", model)
            return {}  # Return empty dict on not found
        response.raise_for_status()
        model_info = response.json()
        details = model_info.get("details", {})
        context_length = 0
        for line in model_info.get("modelfile", "").split("\n"):
            if "num_ctx" in line.lower():
                try:
                    context_length = int(line.split()[1])
                    break
                except (ValueError, IndexError):
                    continue

        result = {
            "family": details.get("family", "N/A"),
            "parameter_size": details.get("parameter_size", "N/A"),
            "quantization_level": details.get("quantization_level", "N/A"),
            "context_length": context_length,
        }
        log_llm.info("Model details retrieved: %s", result)
        return result
    except requests.exceptions.RequestException as e:
        log_llm.error("Could not connect to Ollama at %s: %s", ollama_url, e)
        return {}


def query_text_llm(
    prompt: str,
    user_content: str,
    ollama_url: str,
    model: str,
    stream: bool = False,
    temperature: float = None,
):
    """
    Sends a standard text prompt to an Ollama model.
    Can operate in both streaming and non-streaming modes.
    In streaming mode, it yields the raw JSON chunk from the API.
    In non-streaming mode, it returns the full JSON response dictionary.
    """
    log_llm.debug(
        "Querying LLM:\n  - Model: %s (Stream: %s)\n  - System: %s\n  - User: %s",
        model,
        stream,
        _format_text_for_log(prompt),
        _format_text_for_log(user_content),
    )
    start_time = time.monotonic()
    payload = {
        "model": model,
        "system": prompt,
        "prompt": user_content,
        "stream": stream,
    }
    options = {}
    if temperature is not None:
        options["temperature"] = temperature
    if options:
        payload["options"] = options

    def _stream_generator(response):
        """Inner generator to handle the streaming response."""
        for line in response.iter_lines():
            if line:
                try:
                    chunk_data = json.loads(line.decode("utf-8"))
                    yield chunk_data
                except (json.JSONDecodeError, UnicodeDecodeError):
                    log_llm.warning("Failed to decode stream chunk: %s", line)
                    continue
        duration = time.monotonic() - start_time
        log_llm.debug("LLM stream finished for model '%s' in %.2f seconds.", model, duration)

    try:
        response = requests.post(
            f"{ollama_url}/api/generate", json=payload, stream=stream, timeout=60
        )
        response.raise_for_status()

        if stream:
            return _stream_generator(response)
        else:
            data = response.json()
            # Performance Metrics Calculation
            eval_ns = data.get("eval_duration", 0)
            eval_count = data.get("eval_count", 0)
            eval_sec = eval_ns / 1_000_000_000
            tps = (eval_count / eval_sec) if eval_sec > 0 else 0
            duration_sec = data.get("total_duration", 0) / 1_000_000_000
            # Log rich performance data in a single line
            log_llm.debug(
                "LLM Query OK: model=%s duration=%.2fs prompt_tk=%d response_tk=%d tps=%.1f response=%s",
                model,
                duration_sec,
                data.get("prompt_eval_count", 0),
                eval_count,
                tps,
                _format_text_for_log(data.get("response", "").strip()),
            )
            return data

    except requests.exceptions.RequestException as e:
        log_llm.error("Failed to query text LLM: %s", e)
        if stream:
            return (chunk for chunk in [{"error": str(e)}])
        else:
            return {"error": str(e)}


def query_multimodal_llm(
    prompt: str, image_bytes: bytes, ollama_url: str, model: str, temperature: float = None
) -> str:
    """Sends a prompt and a single image to an Ollama multimodal model."""
    if not image_bytes:
        log_llm.error("No image bytes provided for multimodal query.")
        return ""

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")
    log_llm.debug(
        "Querying Multimodal LLM:\n  - Model: %s\n  - Prompt: %s\n  - Image: %d bytes",
        model,
        _format_text_for_log(prompt),
        len(image_bytes),
    )
    start_time = time.monotonic()

    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "images": [encoded_image],
            "stream": False,
        }
        options = {}
        if temperature is not None:
            options["temperature"] = temperature
        if options:
            payload["options"] = options

        response = requests.post(
            f"{ollama_url}/api/generate",
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        duration = time.monotonic() - start_time
        response_text = data.get("response", "").strip()
        log_llm.debug(
            "Multimodal LLM response received:\n  - Model: %s\n  - Duration: %.2fs\n  - Response: %s",
            model,
            duration,
            _format_text_for_log(response_text),
        )
        return response_text
    except requests.exceptions.RequestException as e:
        log_llm.error("Failed to query multimodal LLM: %s", e)
        return ""


def generate_embeddings_ollama(
    chunks: list[str], ollama_url: str, model: str
) -> list[list[float]]:
    """Generates embeddings for a list of text chunks using Ollama."""
    log_llm.debug("Generating embeddings for %d chunks with model '%s'.", len(chunks), model)
    start_time = time.monotonic()
    embeddings = []
    try:
        for i, chunk in enumerate(chunks):
            log_llm.debug("  - Embedding chunk %d/%d...", i + 1, len(chunks))
            response = requests.post(
                f"{ollama_url}/api/embeddings",
                json={"model": model, "prompt": chunk},
                timeout=30,
            )
            response.raise_for_status()
            embeddings.append(response.json()["embedding"])
        duration = time.monotonic() - start_time
        log_llm.debug(
            "Successfully generated %d embeddings in %.2f seconds.", len(chunks), duration
        )
        return embeddings
    except requests.exceptions.RequestException as e:
        log_llm.error("Failed to generate embeddings via Ollama: %s", e)
        raise


def get_semantic_label(chunk: str, prompt: str, ollama_url: str, model: str) -> str:
    """Gets a single semantic label for a text chunk using a provided prompt."""
    # FIX: Synchronized with SEMANTIC_LABELER prompt in constants.py
    valid_labels = [
        "read_aloud_kickoff",
        "adventure_hook",
        "stat_block",
        "read_aloud_text",
        "item_description",
        "location_description",
        "mechanics",
        "lore",
        "dialogue",
        "prose",
    ]
    response_data = query_text_llm(prompt, chunk, ollama_url, model, temperature=0.1)
    # FIX: More robust cleaning of the model's response
    label = re.sub(r"[`'\"]", "", response_data.get("response", "").strip())
    if label in valid_labels:
        return label
    log_llm.warning("LLM returned invalid semantic label '%s'. Defaulting to 'prose'.", label)
    return "prose"  # Default fallback


def generate_character_json(
    description: str,
    rules_context: str,
    lang: str,
    ollama_url: str,
    model: str,
) -> dict:
    """
    High-level function to generate a character JSON from a description.
    Encapsulates prompt construction, LLM call, and JSON parsing.
    """
    prompt_template = _get_prompt_from_registry("GENERATE_CHARACTER", lang)
    prompt = prompt_template.format(description=description, rules_context=rules_context)

    # For this specific task, the complex prompt is the user content
    response_data = query_text_llm("", prompt, ollama_url, model)
    response_str = response_data.get("response", "").strip()

    if not response_str:
        raise ValueError("LLM returned an empty response.")

    try:
        # Use regex to find the JSON object, ignoring surrounding text
        json_match = re.search(r"\{.*\}", response_str, re.DOTALL)
        if not json_match:
            log_llm.error("Could not find a JSON object in the LLM's response.")
            raise ValueError("LLM did not return a valid JSON object.")

        json_str = json_match.group(0)
        char_data = json.loads(json_str)
        log_llm.debug(
            "Successfully parsed generated character JSON for '%s'.", char_data.get("name")
        )
        return char_data
    except json.JSONDecodeError:
        log_llm.error("LLM returned invalid JSON for character generation: %s", response_str)
        raise ValueError("LLM returned invalid JSON. Please try again.")
