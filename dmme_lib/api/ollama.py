# --- dmme_lib/api/ollama.py ---
import requests
import logging
from flask import Blueprint, jsonify, current_app

bp = Blueprint("ollama", __name__)
log = logging.getLogger("dmme.api")


@bp.route("/models", methods=["GET"])
def get_ollama_models():
    """Gets all available local models from the Ollama service."""
    try:
        ollama_url = current_app.config.get("OLLAMA_URL", "http://localhost:11434")
        api_endpoint = f"{ollama_url}/api/tags"
        log.debug("Fetching models from Ollama at %s", api_endpoint)

        response = requests.get(api_endpoint, timeout=5)
        response.raise_for_status()

        models_data = response.json().get("models", [])
        model_names = sorted([model["name"] for model in models_data])
        return jsonify(model_names)

    except requests.exceptions.RequestException as e:
        log.warning("Could not connect to Ollama to fetch models: %s", e)
        # Return empty list so the UI doesn't break
        return jsonify([])
    except Exception as e:
        log.error("Failed to get Ollama models: %s", e, exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500
