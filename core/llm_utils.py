# --- core/llm_utils.py ---
import logging
import requests
import json
import base64

log = logging.getLogger("dmme.llm_utils")


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
    """
    try:
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

        response = requests.post(
            f"{ollama_url}/api/generate", json=payload, stream=stream, timeout=60
        )
        response.raise_for_status()

        if not stream:
            data = response.json()
            log.debug("LLM response received: %s", data.get("response", "").strip())
            return data.get("response", "").strip()
        else:
            # In streaming mode, this function becomes a generator
            def generator():
                for line in response.iter_lines():
                    if line:
                        chunk_data = json.loads(line.decode("utf-8"))
                        yield chunk_data.get("response", "")

            return generator()

    except requests.exceptions.RequestException as e:
        log.error("Failed to query text LLM: %s", e)
        if stream:
            return iter([])  # Return an empty iterator on error
        return ""


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
    # We only want the single most relevant label
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
    label = query_text_llm(prompt, chunk, ollama_url, model, temperature=0.1)
    if label in valid_labels:
        return label
    return "prose"  # Default fallback
