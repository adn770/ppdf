# --- dmme_lib/app.py ---
import os
import logging

from flask import Flask
from .services.storage_service import StorageService


def create_app(test_config=None):
    """
    Creates and configures an instance of the Flask application.
    This follows the Application Factory pattern.
    """
    app = Flask(__name__, instance_relative_config=True)
    log = logging.getLogger("dmme.app")

    # --- Configuration ---
    # Set default configuration
    app.config.from_mapping(
        SECRET_KEY="dev",  # Change for production
        DATABASE=os.path.join(app.instance_path, "dmme.db"),
    )

    if test_config is None:
        # Load the instance config, if it exists, when not testing
        app.config.from_pyfile("dmme.cfg", silent=True)
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    # Ensure the instance folder exists
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
    # Example:
    # from .api import campaigns
    # app.register_blueprint(campaigns.bp)

    @app.route("/health")
    def health_check():
        return "OK"

    return app
