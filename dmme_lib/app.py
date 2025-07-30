# --- dmme_lib/app.py ---
import os
import logging
import configparser

from flask import Flask, send_from_directory
from .services.storage_service import StorageService
from .services.vector_store_service import VectorStoreService
from .services.ingestion_service import IngestionService

ASSETS_DIR = os.path.join(os.path.expanduser("~"), ".dmme", "assets")


def create_app(config_overrides=None):
    """
    Creates and configures an instance of the Flask application.
    """
    app = Flask(
        __name__,
        instance_relative_config=True,
        static_folder="frontend",
        static_url_path="",
    )
    log = logging.getLogger("dmme.app")

    # --- Configuration ---
    app.config.from_mapping(
        SECRET_KEY="dev",
        DATABASE=os.path.join(os.path.expanduser("~"), ".dmme", "dmme.db"),
        CHROMA_PATH=os.path.join(os.path.expanduser("~"), ".dmme", "chroma"),
        ASSETS_PATH=ASSETS_DIR,
        OLLAMA_URL="http://localhost:11434",
        OLLAMA_MODEL="llama3.1:latest",
        EMBEDDING_MODEL="mxbai-embed-large",
    )

    if config_overrides:
        app.config.from_mapping(config_overrides)
        log.info("Applied runtime configuration overrides.")

    # --- Initialize Services ---
    log.info("Initializing application services...")
    try:
        app.storage = StorageService(app.config["DATABASE"])
        app.vector_store = VectorStoreService(
            app.config["CHROMA_PATH"], app.config["OLLAMA_URL"], app.config["EMBEDDING_MODEL"]
        )
        app.ingestion_service = IngestionService(
            app.vector_store, app.config["OLLAMA_URL"], app.config["OLLAMA_MODEL"]
        )
        with app.app_context():
            app.storage.init_db()
        log.info("All services initialized successfully.")
    except Exception as e:
        log.error("Failed to initialize services: %s", e, exc_info=True)
        raise

    # --- Register Blueprints (APIs) ---
    log.info("Registering API blueprints...")
    from .api import campaigns, parties, knowledge

    app.register_blueprint(campaigns.bp, url_prefix="/api/campaigns")
    app.register_blueprint(parties.bp, url_prefix="/api/parties")
    app.register_blueprint(knowledge.bp, url_prefix="/api/knowledge")
    log.info("Registered blueprints: /api/campaigns, /api/parties, /api/knowledge")

    # --- Static File Serving ---
    @app.route("/")
    def serve_index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/assets/<path:filename>")
    def serve_assets(filename):
        """Serves extracted assets like images."""
        return send_from_directory(app.config["ASSETS_PATH"], filename)

    @app.route("/health")
    def health_check():
        return "OK"

    return app
