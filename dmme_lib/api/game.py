# --- dmme_lib/api/game.py ---
import json
import logging
from flask import Blueprint, request, jsonify, current_app
from core.llm_utils import generate_character_json

bp = Blueprint("game", __name__)
log = logging.getLogger("dmme.api")

# Simple in-memory cache for conversation history (replace with DB persistence later)
conversation_history = []


@bp.route("/start", methods=["POST"])
def start_game():
    """Handles the start of a game, generating the initial narration."""
    global conversation_history
    conversation_history = []  # Reset history for a new game
    data = request.get_json()
    game_config = data.get("config")
    log.debug("Game start requested with config: %s", game_config)

    if not game_config:
        return jsonify({"error": "Missing 'config' in request"}), 400

    rag_service = current_app.rag_service

    def stream_kickoff():
        try:
            # The RAG service is now responsible for handling language
            response_generator = rag_service.generate_kickoff_narration(game_config)
            full_narrative = ""
            for chunk in response_generator:
                if chunk.get("type") == "narrative_chunk":
                    full_narrative += chunk.get("content", "")
                yield json.dumps(chunk) + "\n"

            if full_narrative:
                conversation_history.append({"role": "assistant", "content": full_narrative})
        except Exception as e:
            log.error("Error in RAG kickoff stream: %s", e, exc_info=True)
            error_chunk = json.dumps({"type": "error", "content": str(e)})
            yield error_chunk + "\n"

    return Response(stream_kickoff(), mimetype="application/x-ndjson")


@bp.route("/command", methods=["POST"])
def handle_command():
    """Handles a player command by using the RAG service and streaming the response."""
    global conversation_history
    data = request.get_json()
    player_command = data.get("command")
    game_config = data.get("config")

    if not player_command or not game_config:
        return jsonify({"error": "Missing 'command' or 'config' in request"}), 400

    rag_service = current_app.rag_service
    conversation_history.append({"role": "user", "content": player_command})
    conversation_history = conversation_history[-10:]  # Limit history

    def stream_response():
        try:
            response_generator = rag_service.generate_response(
                player_command, game_config, conversation_history
            )
            full_narrative = ""
            for chunk in response_generator:
                if chunk.get("type") == "narrative_chunk":
                    full_narrative += chunk.get("content", "")
                yield json.dumps(chunk) + "\n"

            if full_narrative:
                conversation_history.append({"role": "assistant", "content": full_narrative})
        except Exception as e:
            log.error("Error in RAG stream: %s", e, exc_info=True)
            error_chunk = json.dumps({"type": "error", "content": str(e)})
            yield error_chunk + "\n"

    return Response(stream_response(), mimetype="application/x-ndjson")


@bp.route("/generate-character", methods=["POST"])
def generate_character():
    """Generates a character using an LLM based on a user description."""
    data = request.get_json()
    description = data.get("description")
    rules_kb = data.get("rules_kb")
    lang = data.get("language", "en")

    if not description or not rules_kb:
        return jsonify({"error": "Description and rules_kb are required."}), 400

    try:
        query = "Core rules for character creation, attributes, classes, and levels."
        rules_docs, _ = current_app.vector_store.query(rules_kb, query, n_results=5)
        rules_context = "\n\n".join(rules_docs)
        if not rules_context:
            rules_context = f"No specific rules found. Use general knowledge for '{rules_kb}'."

        char_data = generate_character_json(
            description=description,
            rules_context=rules_context,
            lang=lang,
            ollama_url=current_app.config["OLLAMA_URL"],
            model=current_app.config["OLLAMA_MODEL"],
        )
        return jsonify(char_data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        current_app.logger.error("Character generation failed: %s", e, exc_info=True)
        return jsonify({"error": "An unexpected server error occurred."}), 500
