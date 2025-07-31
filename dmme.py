#!/usr/bin/env python3
"""dmme: Main entry point for the game driver."""

import os
import logging
import sys
import argparse

from dmme_lib.app import create_app
from core.log_utils import setup_logging

# --- CONSTANTS ---
APP_DIR = os.path.join(os.path.expanduser("~"), ".dmme")
DB_PATH = os.path.join(APP_DIR, "dmme.db")


def main():
    """Initializes and runs the DMme Flask application."""
    # --- Basic Setup ---
    os.makedirs(APP_DIR, exist_ok=True)
    setup_logging(level=logging.INFO, color_logs=True)
    log = logging.getLogger("dmme")

    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="DMme Game Driver.")
    parser.add_argument(
        "--ollama-url",
        type=str,
        default=None,
        help="Ollama server URL. Default: http://localhost:11434",
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        default=None,
        help="Main text generation model. Default: llama3.1:latest",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default=None,
        help="Model for generating embeddings. Default: mxbai-embed-large",
    )
    args = parser.parse_args()

    config_overrides = {
        key: value
        for key, value in {
            "OLLAMA_URL": args.ollama_url,
            "OLLAMA_MODEL": args.ollama_model,
            "EMBEDDING_MODEL": args.embedding_model,
        }.items()
        if value is not None
    }

    # --- App Creation ---
    try:
        app = create_app(config_overrides)
        log.info("DMme application created successfully.")
        log.info("Database is located at: %s", DB_PATH)
        log.info("Using Ollama server at: %s", app.config["OLLAMA_URL"])
    except Exception as e:
        log.critical("Failed to create the DMme application: %s", e, exc_info=True)
        sys.exit(1)

    # --- Run Server ---
    try:
        log.info("Starting DMme Flask server at http://127.0.0.1:5000...")
        log.info("Press CTRL+C to stop the server.")
        app.run(host="127.0.0.1", port=5000, debug=False)
    except KeyboardInterrupt:
        log.info("\nServer stopped by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        log.critical("The Flask server failed to run: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
