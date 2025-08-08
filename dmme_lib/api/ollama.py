# --- dmme_lib/api/ollama.py ---
import requests
import logging
from flask import Blueprint, jsonify, current_app

bp = Blueprint("ollama", __name__)
log = logging.getLogger("dmme.api")


@bp.route("/models", methods=["GET"])
def get_ollama_models():
    """
    Gets all available local models from the Ollama service, including a type hint
    for each to aid in frontend filtering.
    """
    try:
        ollama_url = current_app.config.get("OLLAMA_URL", "http://localhost:11434")
        api_endpoint = f"{ollama_url}/api/tags"
        log.debug("Fetching models from Ollama at %s", api_endpoint)

        response = requests.get(api_endpoint, timeout=5)
        response.raise_for_status()

        models_data = response.json().get("models", [])
        model_details = []
        vision_keywords = ["llava", "bakllava", "vision", "vl", "minicpm-v"]

        for model in models_data:
            name = model.get("name")
            if not name:
                continue

            name_lower = name.lower()
            type_hint = "text"
            if any(keyword in name_lower for keyword in vision_keywords):
                type_hint = "vision"
            elif "embed" in name_lower:
                type_hint = "embedding"

            model_details.append({"name": name, "type_hint": type_hint})

        return jsonify(sorted(model_details, key=lambda x: x["name"]))

    except requests.exceptions.RequestException as e:
        log.warning("Could not connect to Ollama to fetch models: %s", e)
        return jsonify([])
    except Exception as e:
        log.error("Failed to get Ollama models: %s", e, exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500
