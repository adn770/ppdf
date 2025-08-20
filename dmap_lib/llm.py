# --- dmap_lib/llm.py ---
import base64
import json
import logging
from typing import Dict, Any, Optional

import cv2
import numpy as np
import requests

log_llm = logging.getLogger("dmap.llm")


def query_llava(
    ollama_url: str,
    model: str,
    image: np.ndarray,
    prompt: str,
    temperature: float = 0.3,
    context_size: int = 8192,
) -> Optional[Dict[str, Any]]:
    """
    Queries a LLaVA model via the Ollama API with an image and a prompt.

    Args:
        ollama_url: The base URL of the Ollama server.
        model: The name of the LLaVA model to use.
        image: The image to analyze (as a NumPy array).
        prompt: The text prompt to send with the image.
        temperature: The temperature for the model's generation.
        context_size: The context window size for the model.

    Returns:
        A dictionary containing the parsed JSON response from the model, or None if
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
    raw_json = ""  # Initialize raw_json to ensure it's available for logging
    try:
        log_llm.debug("Sending request to LLaVA (prompt length: %d chars).", len(prompt))
        response = requests.post(f"{ollama_url}/api/generate", json=payload, timeout=60)
        response.raise_for_status()
        response_data = response.json()
        raw_json = response_data.get("response", "{}")
        log_llm.debug("Raw LLaVA response:\n%s", raw_json)

        # Clean the response to handle markdown code blocks
        cleaned_json = raw_json.strip()
        if cleaned_json.startswith("```json"):
            cleaned_json = cleaned_json[7:]
        if cleaned_json.endswith("```"):
            cleaned_json = cleaned_json[:-3]
        cleaned_json = cleaned_json.strip()

        return json.loads(cleaned_json)
    except requests.exceptions.RequestException as e:
        log_llm.error("Failed to connect to Ollama API at %s: %s", ollama_url, e)
        return None
    except json.JSONDecodeError as e:
        log_llm.error("Failed to parse JSON response from LLaVA: %s", e)
        log_llm.error("Raw LLaVA response was: %s", raw_json)
        return None
    except Exception as e:
        log_llm.error("An unexpected error occurred during LLaVA query: %s", e)
        return None
