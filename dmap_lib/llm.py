# --- dmap_lib/llm.py ---
import base64
import json
import logging
from typing import Dict, Any, Optional

import cv2
import numpy as np
import requests

log_llm = logging.getLogger("dmap.llm")


def query_llm(
    ollama_url: str,
    model: str,
    image: np.ndarray,
    prompt: str,
    temperature: float = 0.3,
    context_size: int = 8192,
) -> Optional[str]:
    """
    Queries an LLM model via the Ollama API with an image and a prompt.

    Args:
        ollama_url: The base URL of the Ollama server.
        model: The name of the LLM model to use.
        image: The image to analyze (as a NumPy array).
        prompt: The text prompt to send with the image.
        temperature: The temperature for the model's generation.
        context_size: The context window size for the model.

    Returns:
        A string containing the raw response from the model, or None if
        an error occurred.
    """
    _, buffer = cv2.imencode(".png", image)
    img_base64 = base64.b64encode(buffer).decode("utf-8")

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "images": [img_base64],
        "options": {"temperature": temperature, "num_ctx": context_size},
    }
    response = None
    try:
        log_llm.debug("Sending request to LLM (prompt length: %d chars).", len(prompt))
        response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=60)
        response.raise_for_status()
        response_data = response.json()
        raw_response = response_data.get("response", "")
        log_llm.debug("Raw LLM response:\n%s", raw_response)

        cleaned_response = raw_response.strip()
        if cleaned_response.startswith("```"):
            # Handles cases where the model might still wrap output in markdown
            lines = cleaned_response.split("\n")
            if len(lines) > 1 and lines[0].strip() != "```":
                cleaned_response = "\n".join(lines[1:])  # Assumes language hint like ```csv
            else:
                cleaned_response = "\n".join(lines[1:-1])  # Assumes ``` wrapping
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
        cleaned_response = cleaned_response.strip()

        if not cleaned_response:
            log_llm.warning("LLM returned an empty response after cleaning.")
            if response:
                log_llm.warning("HTTP Status Code: %d", response.status_code)
            return None

        return cleaned_response
    except requests.exceptions.RequestException as e:
        log_llm.error("Failed to connect to Ollama API at %s: %s", ollama_url, e)
        if response is not None:
            log_llm.error("HTTP Status Code: %s", response.status_code)
            log_llm.error("Raw Response Body: %s", response.text)
        return None
    except json.JSONDecodeError as e:
        # This is less likely now but kept for robustness
        log_llm.error("Failed to parse JSON from API endpoint: %s", e)
        if response is not None:
            log_llm.error("Raw LLM response was: %s", response.text)
            log_llm.error("HTTP Status Code: %s", response.status_code)
        return None
    except Exception as e:
        log_llm.error("An unexpected error occurred during LLM query: %s", e, exc_info=True)
        if response is not None:
            log_llm.error("HTTP Status Code: %s", response.status_code)
            log_llm.error("Raw Response Body: %s", response.text)
        return None
