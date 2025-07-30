#!/usr/bin/env python3
"""dmme_eval: Main entry point for the prompt evaluation tool."""

import argparse
import logging
import sys

from core.log_utils import setup_logging


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="DMme Prompt Evaluation Tool.")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable INFO logging."
    )
    parser.add_argument(
        "--color-logs", action="store_true", help="Enable colored logging."
    )
    parser.add_argument(
        "-d",
        "--debug",
        dest="debug_topics",
        help="Enable DEBUG logging for specific topics.",
    )
    args = parser.parse_args()

    setup_logging(
        level=logging.INFO if args.verbose else logging.WARNING,
        color_logs=args.color_logs,
        debug_topics=args.debug_topics,
    )

    logging.getLogger("dmme_eval").info("DMme Eval starting up...")


if __name__ == "__main__":
    main()
