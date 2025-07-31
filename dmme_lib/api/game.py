# --- dmme_lib/api/game.py ---
import json
from flask import Blueprint, request, jsonify, current_app
from dmme_lib.constants import PROMPT_GENERATE_CHARACTER
from core.llm_utils import query_text_llm

bp = Blueprint("game", __name__)

# Simple in-memory cache for conversation history (replace with DB persistence later)
conversation_history = []


@bp.route("/command", methods=["POST"])
def handle_command():
    """Handles a player command by using the RAG service."""
    global conversation_history
    data = request.get_json()
    player_command = data.get("command")
    game_config = data.get("config")

    if not player_command or not game_config:
        return jsonify({"error": "Missing 'command' or 'config' in request"}), 400

    # Add player's turn to history
    conversation_history.append({"role": "user", "content": player_command})

    # Limit history to the last 10 turns to keep context size manageable
    conversation_history = conversation_history[-10:]

    try:
        response_data = current_app.rag_service.generate_response(
            player_command, game_config, conversation_history
        )
        # Add AI's turn to history
        conversation_history.append({"role": "assistant", "content": response_data["content"]})
        return jsonify(response_data)
    except Exception as e:
        current_app.logger.error("Error in RAG service: %s", e, exc_info=True)
        return jsonify({"error": "Failed to generate response from RAG service."}), 500


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
