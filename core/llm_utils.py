# --- core/llm_utils.py ---
import logging
import requests
import json

log = logging.getLogger("dmme.llm_utils")


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
