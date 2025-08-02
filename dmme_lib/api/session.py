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
    if not state:
        return jsonify({"error": "No game state provided in request body"}), 400

    autosave_path = _get_autosave_path()
    log.debug("Autosaving session state to: %s", autosave_path)

    try:
        with open(autosave_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)
        return jsonify({"success": True, "message": "Session state saved."})
    except IOError as e:
        log.error("Failed to write to autosave file: %s", e, exc_info=True)
        return jsonify({"error": "Could not save session state."}), 500


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
        return jsonify(state)
    except (IOError, json.JSONDecodeError) as e:
        log.error("Failed to read or parse autosave file: %s", e, exc_info=True)
        return jsonify({"error": "Could not recover session state."}), 500
