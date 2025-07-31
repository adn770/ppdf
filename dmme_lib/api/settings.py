# --- dmme_lib/api/settings.py ---
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint("settings", __name__)


@bp.route("/", methods=["GET"])
def get_settings():
    """Gets all settings from the config file."""
    settings = current_app.config_service.get_settings()
    return jsonify(settings)


@bp.route("/", methods=["POST"])
def save_settings():
    """Saves settings to the config file."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Missing request body"}), 400

    try:
        current_app.config_service.save_settings(data)
        return jsonify({"success": True, "message": "Settings saved."})
    except Exception as e:
        current_app.logger.error("Failed to save settings: %s", e, exc_info=True)
        return jsonify({"error": "Failed to save settings."}), 500
