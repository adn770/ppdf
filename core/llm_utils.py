# --- core/llm_utils.py ---
import logging
import requests
import json
import base64

# Local Application Imports
from dmme_lib.constants import PROMPT_REGISTRY

log = logging.getLogger("dmme.llm_utils")


def _get_prompt_from_registry(key: str, lang: str) -> str:
    """Safely retrieves a prompt, falling back to English."""
    return PROMPT_REGISTRY.get(key, {}).get(lang, PROMPT_REGISTRY.get(key, {}).get("en"))


def get_model_details(ollama_url: str, model: str) -> dict:
    """Queries the Ollama /api/show endpoint for model details."""
    log.info("Querying details for model: %s...", model)
    try:
        response = requests.post(f"{ollama_url}/api/show", json={"name": model}, timeout=10)
        if response.status_code == 404:
            log.error("Model '%s' not found.", model)
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
        log.info("Model details retrieved: %s", result)
        return result
    except requests.exceptions.RequestException as e:
        log.error("Could not connect to Ollama at %s: %s", ollama_url, e)
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
    log.debug("Querying text LLM '%s' (Stream: %s)...", model, stream)
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
                    log.warning("Failed to decode stream chunk: %s", line)
                    continue

    try:
        response = requests.post(
            f"{ollama_url}/api/generate", json=payload, stream=stream, timeout=60
        )
        response.raise_for_status()

        if stream:
            return _stream_generator(response)
        else:
            data = response.json()
            log.debug("LLM response received: %s", data.get("response", "").strip())
            return data

    except requests.exceptions.RequestException as e:
        log.error("Failed to query text LLM: %s", e)
        if stream:
            # Return a generator expression that yields a single error chunk.
            # This avoids using 'yield' in the main function's scope.
            return (chunk for chunk in [{"error": str(e)}])
        else:
            # Return a dictionary for the non-streaming error case.
            return {"error": str(e)}


def query_multimodal_llm(
    prompt: str, image_bytes: bytes, ollama_url: str, model: str, temperature: float = None
) -> str:
    """Sends a prompt and a single image to an Ollama multimodal model."""
    if not image_bytes:
        log.error("No image bytes provided for multimodal query.")
        return ""

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    try:
        log.debug("Querying multimodal LLM '%s'...", model)
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
        log.debug("LLM response received: %s", data.get("response", "").strip())
        return data.get("response", "").strip()
    except requests.exceptions.RequestException as e:
        log.error("Failed to query multimodal LLM: %s", e)
        return ""


def generate_embeddings_ollama(
    chunks: list[str], ollama_url: str, model: str
) -> list[list[float]]:
    """Generates embeddings for a list of text chunks using Ollama."""
    embeddings = []
    try:
        for chunk in chunks:
            response = requests.post(
                f"{ollama_url}/api/embeddings",
                json={"model": model, "prompt": chunk},
                timeout=30,
            )
            response.raise_for_status()
            embeddings.append(response.json()["embedding"])
        return embeddings
    except requests.exceptions.RequestException as e:
        log.error("Failed to generate embeddings via Ollama: %s", e)
        raise


def get_semantic_label(chunk: str, prompt: str, ollama_url: str, model: str) -> str:
    """Gets a single semantic label for a text chunk using a provided prompt."""
    valid_labels = [
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
    label = response_data.get("response", "").strip()
    if label in valid_labels:
        return label
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
        # Clean the response to remove markdown code block delimiters
        clean_str = response_str.replace("```json", "").replace("```", "").strip()
        char_data = json.loads(clean_str)
        return char_data
    except json.JSONDecodeError:
        log.error("LLM returned invalid JSON for character generation: %s", response_str)
        raise ValueError("LLM returned invalid JSON. Please try again.")
