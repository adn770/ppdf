# --- dmme_lib/api/knowledge.py ---
import json
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint("knowledge", __name__)


@bp.route("/import", methods=["POST"])
def import_knowledge():
    """
    Handles the file upload and metadata for knowledge base ingestion.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        metadata_str = request.form.get("metadata")
        if not metadata_str:
            return jsonify({"error": "Missing metadata for the knowledge base"}), 400

        metadata = json.loads(metadata_str)
        metadata["filename"] = file.filename

        # For this milestone, we only handle Markdown
        if not file.filename.lower().endswith(".md"):
            return (
                jsonify(
                    {"error": "Only Markdown (.md) files are supported in this milestone."}
                ),
                400,
            )

        file_content = file.read().decode("utf-8")

        # Delegate to the IngestionService
        current_app.ingestion_service.ingest_markdown(file_content, metadata)

        return (
            jsonify(
                {
                    "success": True,
                    "message": f"Knowledge base '{metadata['kb_name']}' created successfully.",
                }
            ),
            201,
        )

    except Exception as e:
        current_app.logger.error("Ingestion failed: %s", e, exc_info=True)
        return (
            jsonify({"error": f"An unexpected error occurred during ingestion: {str(e)}"}),
            500,
        )
