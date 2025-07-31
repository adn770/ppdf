# --- dmme_lib/api/knowledge.py ---
import json
import os
import shutil
import tempfile
from flask import Blueprint, request, jsonify, current_app
from ppdf_lib.api import process_pdf_images, process_pdf_text

bp = Blueprint("knowledge", __name__)


@bp.route("/", methods=["GET"])
def list_knowledge_bases():
    """Lists all available knowledge bases (ChromaDB collections)."""
    try:
        collections = current_app.vector_store.list_collections()
        kbs = [
            {"name": c.name, "count": c.count()}
            for c in collections
            if not c.name.endswith("_reviewing")
        ]
        return jsonify(kbs)
    except Exception as e:
        current_app.logger.error("Failed to list knowledge bases: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/import-text", methods=["POST"])
def import_knowledge_text():
    """Handles file upload and metadata for knowledge base TEXT ingestion."""
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
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                file.save(tmp.name)
                tmp_path = tmp.name
            try:
                current_app.ingestion_service.ingest_pdf_text(tmp_path, metadata)
            finally:
                os.remove(tmp_path)
        else:
            return (
                jsonify({"error": "Unsupported file type. Please upload a .md or .pdf file."}),
                400,
            )

        return (
            jsonify(
                {"success": True, "message": f"Text for KB '{metadata['kb_name']}' ingested."}
            ),
            201,
        )
    except Exception as e:
        current_app.logger.error("Text ingestion failed: %s", e, exc_info=True)
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500


@bp.route("/start-image-extraction", methods=["POST"])
def start_image_extraction():
    """Extracts images from a PDF to a temporary review directory."""
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files["file"]
    kb_name = request.form.get("kb_name")
    if not kb_name:
        return jsonify({"error": "Missing kb_name"}), 400

    assets_path = current_app.config["ASSETS_PATH"]
    review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
    if os.path.exists(review_dir):
        shutil.rmtree(review_dir)
    os.makedirs(review_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        file.save(tmp.name)
        tmp_path = tmp.name

    try:
        process_pdf_images(
            tmp_path,
            review_dir,
            current_app.config["OLLAMA_URL"],
            current_app.config["OLLAMA_MODEL"],
        )
        return jsonify({"success": True, "message": "Image extraction complete."})
    except Exception as e:
        current_app.logger.error("Image extraction failed: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        os.remove(tmp_path)


@bp.route("/review-images/<kb_name>", methods=["GET"])
def get_review_images(kb_name):
    """Lists all images and their metadata from a review directory."""
    assets_path = current_app.config["ASSETS_PATH"]
    review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
    if not os.path.isdir(review_dir):
        return jsonify({"error": "Review directory not found"}), 404

    images_data = []
    files = sorted(os.listdir(review_dir))
    for filename in files:
        if filename.endswith(".json"):
            image_filename = filename.replace(".json", ".png")
            if image_filename in files:
                with open(os.path.join(review_dir, filename), "r") as f:
                    metadata = json.load(f)
                images_data.append(
                    {
                        "url": f"assets/images/{kb_name}_reviewing/{image_filename}",
                        "filename": image_filename,
                        "metadata": metadata,
                    }
                )
    return jsonify(images_data)


@bp.route("/review-images/<kb_name>/<image_filename>", methods=["PUT"])
def update_review_image(kb_name, image_filename):
    """Updates the metadata for a single image under review."""
    data = request.json
    if not data or "description" not in data or "classification" not in data:
        return jsonify({"error": "Invalid data"}), 400

    assets_path = current_app.config["ASSETS_PATH"]
    review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
    json_filename = image_filename.replace(".png", ".json")
    json_path = os.path.join(review_dir, json_filename)

    if not os.path.exists(json_path):
        return jsonify({"error": "Metadata file not found"}), 404

    with open(json_path, "r") as f:
        metadata = json.load(f)

    metadata["description"] = data["description"]
    metadata["classification"] = data["classification"]

    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=4)

    return jsonify({"success": True, "message": "Image metadata updated."})


@bp.route("/ingest-images", methods=["POST"])
def ingest_images():
    """Finalizes the image ingestion process."""
    data = request.json
    kb_name = data.get("kb_name")
    if not kb_name:
        return jsonify({"error": "Missing kb_name"}), 400

    try:
        current_app.ingestion_service.ingest_images(kb_name, current_app.config["ASSETS_PATH"])
        return jsonify({"success": True, "message": "Image ingestion complete."})
    except Exception as e:
        current_app.logger.error("Image ingestion finalization failed: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500
