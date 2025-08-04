# --- dmme_lib/api/knowledge.py ---
import json
import os
import shutil
import logging
import uuid
from flask import Blueprint, request, jsonify, current_app, Response
from ppdf_lib.api import analyze_pdf_structure

bp = Blueprint("knowledge", __name__)
log = logging.getLogger("dmme.api")
log_ingest = logging.getLogger("dmme.ingest")

TEMP_DIR = os.path.join(os.path.expanduser("~"), ".dmme", "temp")


def _ensure_temp_dir_exists():
    """Creates the temporary directory if it doesn't exist."""
    os.makedirs(TEMP_DIR, exist_ok=True)


@bp.route("/", methods=["GET"])
def list_knowledge_bases():
    """Lists all available knowledge bases (ChromaDB collections)."""
    try:
        collections = current_app.vector_store.list_collections()
        kbs = []
        for c in collections:
            if not c.name.endswith("_reviewing"):
                kbs.append(
                    {
                        "name": c.name,
                        "count": c.count(),
                        "metadata": c.metadata or {},  # Ensure metadata is always a dict
                    }
                )
        log.debug("Returning knowledge bases: %s", kbs)
        return jsonify(kbs)
    except Exception as e:
        log.error("Failed to list knowledge bases: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/explore/<kb_name>", methods=["GET"])
def explore_knowledge_base(kb_name):
    """Retrieves all documents and assets for a given knowledge base."""
    try:
        # 1. Get all text documents from the vector store
        documents = current_app.vector_store.get_all_from_kb(kb_name)

        # 2. Get all assets from the filesystem
        assets = []
        assets_path = current_app.config["ASSETS_PATH"]
        kb_asset_dir = os.path.join(assets_path, "images", kb_name)
        if os.path.isdir(kb_asset_dir):
            for filename in sorted(os.listdir(kb_asset_dir)):
                if filename.endswith(".json") and filename != "assets.json":
                    try:
                        with open(os.path.join(kb_asset_dir, filename), "r") as f:
                            meta = json.load(f)
                        thumb_path = meta.get("thumbnail_filename")
                        if thumb_path:
                            assets.append(
                                {
                                    "url": f"assets/images/{kb_name}/{thumb_path}",
                                    "caption": meta.get("description", "No caption"),
                                    "classification": meta.get("classification", "other"),
                                }
                            )
                    except (IOError, json.JSONDecodeError) as e:
                        log.warning("Could not read asset metadata %s: %s", filename, e)

        return jsonify({"documents": documents, "assets": assets})
    except Exception as e:
        log.error("Failed to explore knowledge base '%s': %s", kb_name, e, exc_info=True)
        return jsonify({"error": f"Could not explore knowledge base: {e}"}), 500


@bp.route("/<kb_name>", methods=["DELETE"])
def delete_knowledge_base(kb_name):
    """Deletes a knowledge base and its associated assets."""
    try:
        # Delete the ChromaDB collection
        current_app.vector_store.delete_kb(kb_name)

        # Delete the associated asset directory
        assets_path = current_app.config["ASSETS_PATH"]
        kb_asset_dir = os.path.join(assets_path, "images", kb_name)
        if os.path.isdir(kb_asset_dir):
            shutil.rmtree(kb_asset_dir)
            log.info("Deleted asset directory: %s", kb_asset_dir)

        return jsonify({"success": True, "message": f"Knowledge base '{kb_name}' deleted."})
    except Exception as e:
        log.error("Failed to delete knowledge base '%s': %s", kb_name, e, exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route("/upload-temp-file", methods=["POST"])
def upload_temp_file():
    """Saves an uploaded file to a temporary directory for later processing."""
    _ensure_temp_dir_exists()
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    try:
        ext = os.path.splitext(file.filename)[1]
        temp_filename = f"{uuid.uuid4().hex}{ext}"
        temp_file_path = os.path.join(TEMP_DIR, temp_filename)
        file.save(temp_file_path)
        log.info("Uploaded file saved to temporary path: %s", temp_file_path)
        return jsonify({"temp_file_path": temp_file_path})
    except Exception as e:
        log.error("Failed to save temporary file: %s", e, exc_info=True)
        return jsonify({"error": "Failed to save temporary file"}), 500


@bp.route("/analyze", methods=["POST"])
def analyze_document():
    """Analyzes a document's structure without performing full ingestion."""
    data = request.get_json()
    tmp_path = data.get("temp_file_path")
    pages_str = data.get("pages", "all")

    if not tmp_path or not os.path.exists(tmp_path) or not tmp_path.startswith(TEMP_DIR):
        log.warning("Invalid or non-existent temp_file_path for analysis: %s", tmp_path)
        return jsonify({"error": "A valid temporary file path is required"}), 400

    try:
        # Analysis is currently only supported for PDF files
        if not tmp_path.lower().endswith(".pdf"):
            log.info("Analysis requested for non-PDF file, returning empty structure.")
            return jsonify([])

        log.info("Starting structural analysis for: %s", tmp_path)
        sections = analyze_pdf_structure(tmp_path, pages_str)
        log.info("Analysis complete, found %d sections.", len(sections))
        return jsonify(sections)
    except Exception as e:
        log.error("Document analysis failed for '%s': %s", tmp_path, e, exc_info=True)
        return jsonify({"error": "Failed to analyze document structure."}), 500


@bp.route("/ingest-document", methods=["POST"])
def ingest_document():
    """
    Processes a previously uploaded temporary file.
    """
    data = request.get_json()
    metadata = data.get("metadata")
    tmp_path = data.get("temp_file_path")
    pages_str = data.get("pages", "all")
    sections_to_include = data.get("sections_to_include")

    if not metadata or not tmp_path:
        return jsonify({"error": "Missing metadata or temp_file_path"}), 400
    if not os.path.exists(tmp_path) or not tmp_path.startswith(TEMP_DIR):
        log.warning("Invalid or non-existent temp_file_path provided: %s", tmp_path)
        return jsonify({"error": "Invalid temp_file_path"}), 400

    app = current_app._get_current_object()
    filename = metadata.get("filename", "unknown")

    def stream_ingestion():
        with app.app_context():
            try:
                is_pdf = filename.lower().endswith(".pdf")
                yield f"data: {json.dumps({'message': '✔ Beginning processing...'})}\n\n"
                ingestion_service = app.ingestion_service

                # --- Text Ingestion ---
                if filename.lower().endswith(".md"):
                    with open(tmp_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    for msg in ingestion_service.ingest_markdown(content, metadata):
                        yield f"data: {json.dumps({'message': msg})}\n\n"
                elif is_pdf:
                    for msg in ingestion_service.ingest_pdf_text(
                        tmp_path, metadata, pages_str, sections_to_include
                    ):
                        yield f"data: {json.dumps({'message': msg})}\n\n"

                # --- Image Extraction (for PDFs only) ---
                if is_pdf:
                    assets_path = app.config["ASSETS_PATH"]
                    for msg in ingestion_service.process_and_extract_images(
                        tmp_path, assets_path, metadata, pages_str=pages_str
                    ):
                        yield f"data: {json.dumps({'message': msg})}\n\n"

            except Exception as e:
                log.error("Document ingestion stream failed: %s", e, exc_info=True)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    return Response(stream_ingestion(), mimetype="text/event-stream")


@bp.route("/review-images/<kb_name>", methods=["GET"])
def get_review_images(kb_name):
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
    data = request.json
    assets_path = current_app.config["ASSETS_PATH"]
    review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
    json_path = os.path.join(review_dir, image_filename.replace(".png", ".json"))
    if not os.path.exists(json_path):
        return jsonify({"error": "Metadata file not found"}), 404
    with open(json_path, "r") as f:
        metadata = json.load(f)
    metadata["description"] = data["description"]
    metadata["classification"] = data["classification"]
    with open(json_path, "w") as f:
        json.dump(metadata, f, indent=4)
    return jsonify({"success": True, "message": "Image metadata updated."})


@bp.route("/review-images/<kb_name>/<image_filename>", methods=["DELETE"])
def delete_review_image(kb_name, image_filename):
    assets_path = current_app.config["ASSETS_PATH"]
    review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
    img_path = os.path.join(review_dir, image_filename)
    json_path = os.path.join(review_dir, image_filename.replace(".png", ".json"))
    try:
        if os.path.exists(img_path):
            os.remove(img_path)
        if os.path.exists(json_path):
            os.remove(json_path)
        return "", 204
    except OSError as e:
        log.error("Error deleting review image files: %s", e, exc_info=True)
        return jsonify({"error": "Failed to delete files"}), 500


@bp.route("/ingest-images", methods=["POST"])
def ingest_images():
    data = request.json
    kb_name = data.get("kb_name")
    if not kb_name:
        return jsonify({"error": "Missing kb_name"}), 400
    try:
        current_app.ingestion_service.ingest_images(kb_name, current_app.config["ASSETS_PATH"])
        return jsonify({"success": True, "message": "Image ingestion complete."})
    except Exception as e:
        log.error(
            "Image ingestion finalization failed for KB '%s': %s", kb_name, e, exc_info=True
        )
        return jsonify({"error": str(e)}), 500
