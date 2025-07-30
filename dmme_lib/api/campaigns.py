# --- dmme_lib/api/campaigns.py ---
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint("campaigns", __name__)


@bp.route("/", methods=["GET"])
def get_campaigns():
    """Gets all campaigns."""
    campaigns = current_app.storage.get_all_campaigns()
    return jsonify([dict(c) for c in campaigns])


@bp.route("/<int:campaign_id>", methods=["GET"])
def get_campaign(campaign_id):
    """Gets a single campaign by ID."""
    campaign = current_app.storage.get_campaign(campaign_id)
    if campaign is None:
        return jsonify({"error": "Campaign not found"}), 404
    return jsonify(dict(campaign))


@bp.route("/", methods=["POST"])
def create_campaign():
    """Creates a new campaign."""
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Missing 'name' in request body"}), 400

    name = data["name"]
    desc = data.get("description", "")
    campaign_id = current_app.storage.create_campaign(name, desc)

    new_campaign = current_app.storage.get_campaign(campaign_id)
    return jsonify(dict(new_campaign)), 201


@bp.route("/<int:campaign_id>", methods=["PUT"])
def update_campaign(campaign_id):
    """Updates an existing campaign."""
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Missing 'name' in request body"}), 400

    name = data["name"]
    desc = data.get("description", "")

    if not current_app.storage.update_campaign(campaign_id, name, desc):
        return jsonify({"error": "Campaign not found or update failed"}), 404

    updated_campaign = current_app.storage.get_campaign(campaign_id)
    return jsonify(dict(updated_campaign))


@bp.route("/<int:campaign_id>", methods=["DELETE"])
def delete_campaign(campaign_id):
    """Deletes a campaign."""
    if not current_app.storage.delete_campaign(campaign_id):
        return jsonify({"error": "Campaign not found"}), 404
    return "", 204
