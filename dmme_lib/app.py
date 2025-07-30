# --- dmme_lib/app.py ---
import os
import logging

from flask import Flask, send_from_directory
from .services.storage_service import StorageService


def create_app(test_config=None):
    """
    Creates and configures an instance of the Flask application.
    This follows the Application Factory pattern.
    """
    # Adjust the static folder to point to our new frontend directory
    app = Flask(
        __name__,
        instance_relative_config=True,
        static_folder="frontend",
        static_url_path="",
    )
    log = logging.getLogger("dmme.app")

    # --- Configuration ---
    app.config.from_mapping(
        SECRET_KEY="dev",  # Change for production
        DATABASE=os.path.join(app.instance_path, "dmme.db"),
    )

    if test_config is None:
        app.config.from_pyfile("dmme.cfg", silent=True)
    else:
        app.config.from_mapping(test_config)

    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # --- Initialize Services ---
    log.info("Initializing application services...")
    try:
        storage = StorageService(app.config["DATABASE"])
        with app.app_context():
            storage.init_db()
        app.storage = storage
        log.info("StorageService initialized successfully.")
    except Exception as e:
        log.error("Failed to initialize StorageService: %s", e, exc_info=True)
        raise

    # --- Register Blueprints (APIs) ---
    log.info("Registering API blueprints...")
    from .api import campaigns, parties

    app.register_blueprint(campaigns.bp, url_prefix="/api/campaigns")
    app.register_blueprint(parties.bp, url_prefix="/api/parties")
    log.info("Registered blueprints: /api/campaigns, /api/parties")

    # --- Frontend Serving ---
    @app.route("/")
    def serve_index():
        return send_from_directory(app.static_folder, "index.html")

    @app.route("/health")
    def health_check():
        return "OK"

    return app
