# --- dmme_lib/api/characters.py ---
import json
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint("characters", __name__)
log = logging.getLogger("dmme.api")


def _character_to_dict(row):
    """
    Helper to convert a character row to a serializable dictionary.
    This handles parsing the JSON string in 'stats' and formatting dates.
    """
    if not row:
        return None
    char_dict = dict(row)
    char_id = char_dict.get("id", "UNKNOWN")
    log.debug("Serializing character data for character_id: %s", char_id)

    # Parse the 'stats' field
    stats_json = char_dict.get("stats")
    if stats_json:
        try:
            char_dict["stats"] = json.loads(stats_json)
        except (json.JSONDecodeError, TypeError):
            # Explicitly log the data corruption error
            log.error(
                "Failed to parse corrupt JSON for character_id: %s. Data: %s",
                char_id,
                stats_json,
            )
            char_dict["stats"] = {}  # Default to empty on malformed data
    else:
        char_dict["stats"] = {}

    # Format datetime objects to ISO strings
    for key in ["created_at", "updated_at"]:
        if key in char_dict and isinstance(char_dict[key], datetime):
            char_dict[key] = char_dict[key].isoformat()

    return char_dict


@bp.route("/parties/<int:party_id>/characters", methods=["GET"])
def get_characters(party_id):
    """Gets all characters for a given party."""
    log.info("Request received to get characters for party_id: %d", party_id)
    try:
        character_rows = current_app.storage.get_characters_for_party(party_id)
        log.info(
            "Found %d character record(s) for party_id: %d", len(character_rows), party_id
        )
        characters_list = [_character_to_dict(row) for row in character_rows]
        return jsonify(characters_list)
    except Exception as e:
        log.error(
            "Unexpected error fetching characters for party_id: %d. Error: %s",
            party_id,
            e,
            exc_info=True,
        )
        return jsonify({"error": "Failed to retrieve character data."}), 500


@bp.route("/characters/<int:character_id>", methods=["GET"])
def get_character(character_id):
    """Gets a single character by their ID."""
    character_row = current_app.storage.get_character(character_id)
    if not character_row:
        return jsonify({"error": "Character not found"}), 404
    return jsonify(_character_to_dict(character_row))


@bp.route("/parties/<int:party_id>/characters", methods=["POST"])
def create_character(party_id):
    """Creates a new character and adds it to a party."""
    data = request.get_json()
    if not data or "name" not in data or "class" not in data:
        return jsonify({"error": "Missing required fields"}), 400

    char_id = current_app.storage.create_character(
        party_id,
        data["name"],
        data.get("class"),
        data.get("level", 1),
        data.get("description", ""),
        data.get("stats", {}),
    )

    new_char_row = current_app.storage.get_character(char_id)
    return jsonify(_character_to_dict(new_char_row)), 201


@bp.route("/characters/<int:character_id>", methods=["PUT"])
def update_character(character_id):
    """Updates an existing character."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid request body"}), 400

    if not current_app.storage.update_character(character_id, data):
        return jsonify({"error": "Character not found or update failed"}), 404

    updated_char_row = current_app.storage.get_character(character_id)
    return jsonify(_character_to_dict(updated_char_row))


@bp.route("/characters/<int:character_id>", methods=["DELETE"])
def delete_character(character_id):
    """Deletes a character."""
    if not current_app.storage.delete_character(character_id):
        return jsonify({"error": "Character not found"}), 404
    return "", 204
