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
    log = logging.getLogger("dmme")

    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(description="DMme Game Driver.")
    g_ollama = parser.add_argument_group("Ollama Configuration")
    g_ollama.add_argument(
        "--ollama-url",
        type=str,
        default=None,
        help="Ollama server URL. Default: http://localhost:11434",
    )
    g_ollama.add_argument(
        "--ollama-model",
        type=str,
        default=None,
        help="Main text generation model. Default: llama3.1:latest",
    )
    g_ollama.add_argument(
        "--embedding-model",
        type=str,
        default=None,
        help="Model for generating embeddings. Default: mxbai-embed-large",
    )

    g_log = parser.add_argument_group("Logging & Output")
    g_log.add_argument(
        "-v", "--verbose", action="store_true", help="Enable INFO logging for progress."
    )
    g_log.add_argument(
        "--color-logs", action="store_true", help="Enable colored logging output."
    )
    g_log.add_argument(
        "--log-file",
        metavar="FILE",
        default=None,
        help="Redirect all logging output to a specified file.",
    )
    g_log.add_argument(
        "-d",
        "--debug",
        dest="debug_topics",
        metavar="TOPICS",
        help="Enable DEBUG logging (all,api,rag,ingest,storage,config,llm).",
    )
    g_log.add_argument(
        "--raw-llm-response",
        action="store_true",
        help="Print the full, raw JSON response from the LLM for debugging.",
    )
    args = parser.parse_args()

    # --- Logging Setup ---
    setup_logging(
        project_name="dmme",
        level=logging.INFO if args.verbose else logging.WARNING,
        color_logs=args.color_logs,
        debug_topics=args.debug_topics,
        include_projects=["ppdf"],  # Activate ppdf logs as well
        log_file=args.log_file,
    )

    config_overrides = {
        key: value
        for key, value in {
            "OLLAMA_URL": args.ollama_url,
            "OLLAMA_MODEL": args.ollama_model,
            "EMBEDDING_MODEL": args.embedding_model,
            "RAW_LLM_RESPONSE": args.raw_llm_response,
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
        # Use waitress or another production-ready server in a real deployment
        from waitress import serve

        serve(app, host="127.0.0.1", port=5000, channel_timeout=600)
    except KeyboardInterrupt:
        log.info("\nServer stopped by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        log.critical("The Flask server failed to run: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
