import base64
import json
import logging
from typing import Dict, Any, Optional

import cv2
import numpy as np
import requests

log_llm = logging.getLogger("dmap.llm")


def query_llava(
    ollama_url: str, model: str, image: np.ndarray, prompt: str
) -> Optional[Dict[str, Any]]:
    """
    Queries a LLaVA model via the Ollama API with an image and a prompt.

    Args:
        ollama_url: The base URL of the Ollama server.
        model: The name of the LLaVA model to use.
        image: The image to analyze (as a NumPy array).
        prompt: The text prompt to send with the image.

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
    }

    try:
        log_llm.debug("Sending request to LLaVA at %s with model %s.", ollama_url, model)
        response = requests.post(
            f"{ollama_url}/api/generate", json=payload, timeout=60
        )
        response.raise_for_status()
        response_data = response.json()
        raw_json = response_data.get("response", "{}")
        log_llm.debug("Raw LLaVA response:\n%s", raw_json)
        return json.loads(raw_json)
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
