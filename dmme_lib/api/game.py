# --- dmme_lib/api/game.py ---
import json
from flask import Blueprint, request, jsonify, current_app
from dmme_lib.constants import PROMPT_GENERATE_CHARACTER
from core.llm_utils import query_text_llm

bp = Blueprint("game", __name__)


@bp.route("/command", methods=["POST"])
def handle_command():
    """
    Handles a player command. (STUB for Milestone 12)
    This is a hardcoded response and does not use the RAG system yet.
    """
    # We can log the incoming data to show it's being received, but we ignore it.
    player_input = request.get_json()
    current_app.logger.info("Received player command: %s", player_input)

    # Return a fixed, predictable JSON response for the frontend to render.
    stub_response = {
        "type": "narrative",
        "content": (
            "You stand at the edge of a dark forest. A narrow path winds its way "
            "into the oppressive gloom. The air is still, and an unnatural silence "
            "hangs over the woods. This is a hardcoded response from the backend stub."
        ),
        "dm_insight": "The backend stub is working correctly.",
    }
    return jsonify(stub_response)


@bp.route("/generate-character", methods=["POST"])
def generate_character():
    """Generates a character using an LLM based on a user description."""
    data = request.get_json()
    description = data.get("description")
    rules_kb = data.get("rules_kb")  # Name of the rules knowledge base

    if not description or not rules_kb:
        return jsonify({"error": "Description and rules_kb are required."}), 400

    try:
        # A future RAG implementation would query the KB for relevant rules.
        rules_context = f"The game is based on the '{rules_kb}' rule system."
        prompt = PROMPT_GENERATE_CHARACTER.format(
            description=description, rules_context=rules_context
        )

        response_str = query_text_llm(
            "",  # System prompt is built into the main prompt
            prompt,
            current_app.config["OLLAMA_URL"],
            current_app.config["OLLAMA_MODEL"],
        )

        # Clean and parse the JSON response from the LLM
        response_str = response_str.strip().replace("```json", "").replace("```", "")
        char_data = json.loads(response_str)

        return jsonify(char_data)

    except json.JSONDecodeError:
        err = "LLM returned invalid JSON. Please try again."
        return jsonify({"error": err}), 500
    except Exception as e:
        current_app.logger.error("Character generation failed: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500
