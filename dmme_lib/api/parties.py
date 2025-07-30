# --- dmme_lib/api/parties.py ---
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint("parties", __name__)


@bp.route("/", methods=["GET"])
def get_parties():
    """Gets all parties."""
    parties = current_app.storage.get_all_parties()
    return jsonify([dict(p) for p in parties])


@bp.route("/<int:party_id>", methods=["GET"])
def get_party(party_id):
    """Gets a single party by ID."""
    party = current_app.storage.get_party(party_id)
    if party is None:
        return jsonify({"error": "Party not found"}), 404
    return jsonify(dict(party))


@bp.route("/", methods=["POST"])
def create_party():
    """Creates a new party."""
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Missing 'name' in request body"}), 400

    name = data["name"]
    party_id = current_app.storage.create_party(name)

    if party_id is None:
        return jsonify({"error": f"Party name '{name}' already exists"}), 409

    new_party = current_app.storage.get_party(party_id)
    return jsonify(dict(new_party)), 201


@bp.route("/<int:party_id>", methods=["PUT"])
def update_party(party_id):
    """Updates an existing party."""
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Missing 'name' in request body"}), 400

    name = data["name"]

    if not current_app.storage.update_party(party_id, name):
        return jsonify({"error": "Party not found or name is already taken"}), 404

    updated_party = current_app.storage.get_party(party_id)
    return jsonify(dict(updated_party))


@bp.route("/<int:party_id>", methods=["DELETE"])
def delete_party(party_id):
    """Deletes a party."""
    if not current_app.storage.delete_party(party_id):
        return jsonify({"error": "Party not found"}), 404
    return "", 204
