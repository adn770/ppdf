# --- dmme_lib/api/knowledge.py ---
import json
import os
import tempfile
from flask import Blueprint, request, jsonify, current_app

bp = Blueprint("knowledge", __name__)


@bp.route("/import", methods=["POST"])
def import_knowledge():
    """
    Handles the file upload and metadata for knowledge base ingestion.
    Supports both Markdown and PDF files.
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

        filename_lower = file.filename.lower()

        if filename_lower.endswith(".md"):
            file_content = file.read().decode("utf-8")
            current_app.ingestion_service.ingest_markdown(file_content, metadata)

        elif filename_lower.endswith(".pdf"):
            # The ppdf library requires a file path, so we save to a temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name

            try:
                current_app.ingestion_service.ingest_pdf(tmp_path, metadata)
            finally:
                # Ensure the temporary file is always cleaned up
                os.remove(tmp_path)
        else:
            return (
                jsonify({"error": "Unsupported file type. Please upload a .md or .pdf file."}),
                400,
            )

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
