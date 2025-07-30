# --- dmme.py ---
#!/usr/bin/env python3
"""dmme: Main entry point for the game driver."""

import os
import logging
import sys

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

    # --- App Creation ---
    try:
        app = create_app({"DATABASE": DB_PATH})
        log.info("DMme application created successfully.")
        log.info("Database is located at: %s", DB_PATH)
    except Exception as e:
        log.critical("Failed to create the DMme application: %s", e, exc_info=True)
        sys.exit(1)

    # --- Run Server ---
    # Note: For development, Flask's built-in server is used. For production,
    # this should be run behind a proper WSGI server like Gunicorn or Waitress.
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
