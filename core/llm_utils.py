# --- core/llm_utils.py ---
import logging
import requests

from ppdf_lib.constants import PROMPT_SEMANTIC_LABELER

log = logging.getLogger("dmme.llm_utils")


def query_text_llm(prompt: str, user_content: str, ollama_url: str, model: str) -> str:
    """Sends a standard text prompt to an Ollama model."""
    try:
        log.debug("Querying text LLM '%s'...", model)
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "system": prompt,
                "prompt": user_content,
                "stream": False,
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        log.debug("LLM response received: %s", data.get("response", "").strip())
        return data.get("response", "").strip()
    except requests.exceptions.RequestException as e:
        log.error("Failed to query text LLM: %s", e)
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


def get_semantic_label(chunk: str, ollama_url: str, model: str) -> str:
    """Gets a single semantic label for a text chunk."""
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
    label = query_text_llm(PROMPT_SEMANTIC_LABELER, chunk, ollama_url, model)
    if label in valid_labels:
        return label
    return "prose"  # Default fallback
