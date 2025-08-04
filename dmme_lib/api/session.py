# --- dmme_lib/api/session.py ---
import os
import json
import logging
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint("session", __name__)
log = logging.getLogger("dmme.api")

AUTOSAVE_FILENAME = "autosave.json"


def _get_autosave_path():
    """Constructs the full path to the autosave file."""
    app_dir = os.path.dirname(current_app.config["DATABASE"])
    return os.path.join(app_dir, AUTOSAVE_FILENAME)


@bp.route("/autosave", methods=["POST"])
def autosave_session():
    """Saves the current game state to a temporary recovery file."""
    state = request.get_json()
    if not state or not state.get("config"):
        return jsonify({"error": "No valid game state provided"}), 400

    autosave_path = _get_autosave_path()
    log.debug("Autosaving session state to: %s", autosave_path)

    try:
        with open(autosave_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
        return jsonify({"success": True, "message": "Session state saved."})
    except IOError as e:
        log.error("Failed to write to autosave file: %s", e, exc_info=True)
        return jsonify({"error": "Could not save session state."}), 500


@bp.route("/autosave", methods=["DELETE"])
def delete_autosave():
    """Deletes the autosave file."""
    autosave_path = _get_autosave_path()
    log.debug("Deleting autosave file at: %s", autosave_path)
    if os.path.exists(autosave_path):
        try:
            os.remove(autosave_path)
            return "", 204  # No Content
        except OSError as e:
            log.error("Failed to delete autosave file: %s", e, exc_info=True)
            return jsonify({"error": "Could not delete autosave file."}), 500
    return "", 204  # File didn't exist, which is also a success


@bp.route("/recover", methods=["GET"])
def recover_session():
    """Recovers the last game state from the temporary recovery file."""
    autosave_path = _get_autosave_path()
    if not os.path.exists(autosave_path):
        log.info("No autosave file found at %s to recover from.", autosave_path)
        return jsonify({})  # Return empty object if no save file exists

    log.debug("Recovering session state from: %s", autosave_path)
    try:
        with open(autosave_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        # Ensure the recovered state is not empty
        if not state or not state.get("config"):
            log.warning("Autosave file is empty or invalid. Discarding.")
            os.remove(autosave_path)
            return jsonify({})
        return jsonify(state)
    except (IOError, json.JSONDecodeError) as e:
        log.error("Failed to read or parse autosave file: %s", e, exc_info=True)
        return jsonify({"error": "Could not recover session state."}), 500


@bp.route("/summarize", methods=["POST"])
def summarize_session():
    """Summarizes a session log and saves it as a journal recap."""
    data = request.get_json()
    campaign_id = data.get("campaign_id")
    narrative_log = data.get("session_log") # The full HTML log
    language = data.get("language", "en")

    if not campaign_id or not narrative_log:
        return jsonify({"error": "Missing campaign_id or session_log"}), 400

    try:
        # Step 1: Create a new session record in the database
        session_id = current_app.storage.create_session(campaign_id)
        log.info(
            "Created new session record (ID: %d) for campaign %d.", session_id, campaign_id
        )

        # Step 2: Use the RAG service to generate the summary
        summary = current_app.rag_service.generate_journal_recap(narrative_log, language)
        if not summary:
            raise Exception("LLM failed to generate a summary.")

        # Step 3: Save the summary and the full log to the new session record
        current_app.storage.save_session_end_data(session_id, summary, narrative_log)
        log.info("Saved journal recap and narrative log for session %d.", session_id)

        return jsonify({"session_id": session_id, "recap": summary}), 201

    except Exception as e:
        log.error(
            "Failed to summarize session for campaign %d: %s", campaign_id, e, exc_info=True
        )
        return jsonify({"error": "Failed to create session summary."}), 500
