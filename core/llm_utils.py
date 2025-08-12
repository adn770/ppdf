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
    if len(single_line_text) > 240:
        return f'"{single_line_text[:115]}...{single_line_text[-115:]}"'
    return f'"{single_line_text}"'


def _extract_json_from_llm_response(text: str) -> dict | list | None:
    """Finds and parses the first valid JSON object or array in a string."""
    # Find the first potential JSON object or array
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not match:
        log_llm.warning("No JSON object or array found in LLM response.")
        return None

    json_str = match.group(0)

    # Attempt to fix common errors, like trailing commas
    json_str = re.sub(r",\s*([\]}])", r"\1", json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        log_llm.warning(
            "Failed to parse extracted JSON string. Error: %s\nString: %s",
            e,
            json_str,
        )
        return None


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
    context_window: int = None,
    raw_response_log: bool = False,
):
    """
    Sends a standard text prompt to an Ollama model with a retry mechanism.
    Can operate in both streaming and non-streaming modes.
    """
    MAX_RETRIES = 3
    RETRY_DELAY_S = 2
    last_exception = None

    log_llm.debug(
        "Querying LLM:\n  - Model: %s (Stream: %s)\n  - System: %s\n  - User: %s",
        model,
        stream,
        _format_text_for_log(prompt),
        _format_text_for_log(user_content),
    )
    start_time = time.monotonic()
    payload = {}

    # --- Conditional Gemma Prompt Formatting ---
    if "gemma" in model.lower():
        log_llm.debug("Applying Gemma-specific prompt formatting for model '%s'.", model)
        # For Gemma, the system prompt is included within the user turn.
        formatted_prompt = (
            f"<start_of_turn>user\n{prompt}\n\n{user_content}<end_of_turn>\n"
            f"<start_of_turn>model\n"
        )
        payload = {
            "model": model,
            "prompt": formatted_prompt,
            "stream": stream,
        }
    else:
        # Standard formatting for Llama, Mixtral, Qwen, etc.
        payload = {
            "model": model,
            "system": prompt,
            "prompt": user_content,
            "stream": stream,
            "format": "json" if "json" in prompt.lower() else "",
        }

    # Add options to the payload
    options = {}
    if temperature is not None:
        options["temperature"] = temperature
    if context_window is not None:
        options["num_ctx"] = context_window
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

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                f"{ollama_url}/api/generate", json=payload, stream=stream, timeout=60
            )
            response.raise_for_status()

            if stream:
                return _stream_generator(response)
            else:
                data = response.json()
                if raw_response_log:
                    log_llm.debug(
                        "--- Raw LLM Response Text ---\n%s",
                        data.get("response", "[No response text found]"),
                    )
                eval_ns = data.get("eval_duration", 0)
                eval_count = data.get("eval_count", 0)
                eval_sec = eval_ns / 1_000_000_000
                tps = (eval_count / eval_sec) if eval_sec > 0 else 0
                duration_sec = data.get("total_duration", 0) / 1_000_000_000
                log_llm.debug(
                    "LLM Query OK: model=%s duration=%.2fs prompt_tk=%d response_tk=%d "
                    "tps=%.1f response=%s",
                    model,
                    duration_sec,
                    data.get("prompt_eval_count", 0),
                    eval_count,
                    tps,
                    _format_text_for_log(data.get("response", "").strip()),
                )
                return data

        except requests.exceptions.RequestException as e:
            last_exception = e
            log_llm.warning(
                "LLM query failed on attempt %d/%d: %s", attempt + 1, MAX_RETRIES, e
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_S)
            else:
                log_llm.error("Failed to query text LLM after %d retries.", MAX_RETRIES)

    # This part is reached only after all retries have failed
    if stream:
        return (chunk for chunk in [{"error": str(last_exception)}])
    else:
        return {"error": str(last_exception)}


def query_multimodal_llm(
    prompt: str,
    image_bytes: bytes,
    ollama_url: str,
    model: str,
    temperature: float = None,
) -> str:
    """Sends a prompt and an image to an Ollama multimodal model with a retry mechanism."""
    MAX_RETRIES = 3
    RETRY_DELAY_S = 2
    last_exception = None

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

    for attempt in range(MAX_RETRIES):
        try:
            start_time = time.monotonic()
            response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=90)
            response.raise_for_status()
            data = response.json()
            duration = time.monotonic() - start_time
            response_text = data.get("response", "").strip()
            log_llm.debug(
                "Multimodal LLM response received:\n  - Model: %s\n  - Duration: %.2fs\n"
                "  - Response: %s",
                model,
                duration,
                _format_text_for_log(response_text),
            )
            return response_text
        except requests.exceptions.RequestException as e:
            last_exception = e
            log_llm.warning(
                "Multimodal LLM query failed on attempt %d/%d: %s",
                attempt + 1,
                MAX_RETRIES,
                e,
            )
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_S)
            else:
                log_llm.error("Failed to query multimodal LLM after %d retries.", MAX_RETRIES)

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
            "Successfully generated %d embeddings in %.2f seconds.",
            len(chunks),
            duration,
        )
        return embeddings
    except requests.exceptions.RequestException as e:
        log_llm.error("Failed to generate embeddings via Ollama: %s", e)
        raise


def get_semantic_tags(
    chunk: str,
    prompt: str,
    ollama_url: str,
    model: str,
    context_window: int = None,
    raw_response_log: bool = False,
) -> list[str]:
    """Gets a list of semantic tags for a text chunk, handling various LLM JSON outputs."""
    response_data = query_text_llm(
        prompt,
        chunk,
        ollama_url,
        model,
        temperature=0.1,
        context_window=context_window,
        raw_response_log=raw_response_log,
    )
    response_str = response_data.get("response", "").strip()

    if not response_str:
        return ["type:prose"]

    parsed_json = _extract_json_from_llm_response(response_str)
    if isinstance(parsed_json, list) and all(isinstance(t, str) for t in parsed_json):
        return parsed_json if parsed_json else ["type:prose"]

    log_llm.warning("Could not parse a valid tag list from LLM response: %s", response_str)
    return ["type:prose"]


def generate_character_json(
    description: str,
    rules_context: str,
    lang: str,
    ollama_url: str,
    model: str,
    context_window: int = None,
    raw_response_log: bool = False,
) -> dict:
    """
    High-level function to generate a character JSON from a description.
    Encapsulates prompt construction, LLM call, and JSON parsing.
    """
    prompt_template = _get_prompt_from_registry("GENERATE_CHARACTER", lang)
    prompt = prompt_template.format(description=description, rules_context=rules_context)

    # For this specific task, the complex prompt is the user content
    response_data = query_text_llm(
        "",
        prompt,
        ollama_url,
        model,
        context_window=context_window,
        raw_response_log=raw_response_log,
    )
    response_str = response_data.get("response", "").strip()

    if not response_str:
        raise ValueError("LLM returned an empty response.")

    char_data = _extract_json_from_llm_response(response_str)
    if isinstance(char_data, dict):
        log_llm.debug(
            "Successfully parsed generated character JSON for '%s'.",
            char_data.get("name"),
        )
        return char_data

    log_llm.error(
        "LLM returned invalid or un-extractable JSON for character generation: %s",
        response_str,
    )
    raise ValueError("LLM returned invalid JSON. Please try again.")
