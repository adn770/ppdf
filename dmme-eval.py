#!/usr/bin/env python3
"""dmme_eval: Main entry point for the prompt evaluation tool."""

import argparse
import logging
import sys
import os
import tempfile
import shutil
import json
from datetime import datetime

from core.log_utils import setup_logging
from ppdf_lib.api import process_pdf_images
from dmme_lib.constants import PROMPT_REGISTRY


def handle_ingest_command(args):
    """Handler for the 'ingest' subcommand."""
    log = logging.getLogger("dmme_eval.ingest")
    if args.task != "extract-images":
        log.error("Task '%s' is not yet implemented.", args.task)
        return

    os.makedirs(args.output_dir, exist_ok=True)
    pdf_name = os.path.splitext(os.path.basename(args.pdf_file))[0]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"report_{pdf_name}_{ts}.md"
    report_path = os.path.join(args.output_dir, report_filename)
    assets_dir = os.path.join(args.output_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    temp_dir = tempfile.mkdtemp(prefix="dmme_eval_")
    log.info("Using temporary directory: %s", temp_dir)

    try:
        log.info("Starting image extraction task for '%s'...", args.pdf_file)
        describe_prompt = PROMPT_REGISTRY["DESCRIBE_IMAGE"][args.lang]
        classify_prompt = PROMPT_REGISTRY["CLASSIFY_IMAGE"][args.lang]

        progress_generator = process_pdf_images(
            pdf_path=args.pdf_file,
            output_dir=temp_dir,
            ollama_url=args.url,
            vision_model=args.vision_model,
            utility_model=args.utility_model,
            describe_prompt=describe_prompt,
            classify_prompt=classify_prompt,
        )
        for message in progress_generator:
            log.info(message)

        log.info("Generating Markdown report...")
        report_content = [f"# Image Extraction Report: `{pdf_name}`"]
        report_content.append(f"**Generated on:** {datetime.now().isoformat()}")
        report_content.append("\n---\n")

        json_files = sorted([f for f in os.listdir(temp_dir) if f.endswith(".json")])
        if not json_files:
            report_content.append("## No images were extracted from this document.")

        for json_file in json_files:
            with open(os.path.join(temp_dir, json_file), "r") as f:
                meta = json.load(f)

            img_file = meta.get("image_filename")
            thumb_file = meta.get("thumbnail_filename")

            if img_file:
                shutil.copy(os.path.join(temp_dir, img_file), assets_dir)
            if thumb_file:
                shutil.copy(os.path.join(temp_dir, thumb_file), assets_dir)

            report_content.append(
                f"## Image: `{img_file}` (Page: {meta.get('page_number', 'N/A')})"
            )
            report_content.append(f"![{img_file}](./assets/{thumb_file})")
            report_content.append("\n**Classification:**")
            report_content.append(f"`{meta.get('classification', 'N/A')}`")
            report_content.append("\n**AI-Generated Description:**")
            report_content.append(f"> {meta.get('description', 'N/A')}")
            report_content.append("\n---\n")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_content))
        log.info("Report successfully generated at: %s", report_path)

    finally:
        log.info("Cleaning up temporary directory...")
        shutil.rmtree(temp_dir)


def handle_prompt_command(args):
    """Handler for the 'prompt' subcommand."""
    log = logging.getLogger("dmme_eval.prompt")
    is_comparison = len(args.test_suite_dirs) == 2
    if is_comparison:
        log.info("Running Prompt Comparison...")
        log.info("  - Suite 1: %s", args.test_suite_dirs[0])
        log.info("  - Suite 2: %s", args.test_suite_dirs[1])
        #
        # --- Implementation for Milestone 43 will go here ---
        #
        log.warning("Prompt comparison logic is not yet implemented.")
    else:
        log.info("Running Single Prompt Evaluation...")
        log.info("  - Suite: %s", args.test_suite_dirs[0])
        #
        # --- Implementation for Milestone 42 will go here ---
        #
        log.warning("Single prompt evaluation logic is not yet implemented.")

    log.info("  - DM Model: %s", args.dm_model)
    log.info("  - Utility Model: %s", args.utility_model)


def parse_arguments(args=None):
    """Parses command-line arguments for the script."""
    parser = argparse.ArgumentParser(
        description="DMme Evaluation & Testing Tool.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    # --- Global arguments ---
    g_log = parser.add_argument_group("Logging & Output")
    g_log.add_argument(
        "-v", "--verbose", action="store_true", help="Enable INFO logging for progress."
    )
    g_log.add_argument(
        "--color-logs", action="store_true", help="Enable colored logging output."
    )
    g_log.add_argument(
        "-d",
        "--debug",
        dest="debug_topics",
        metavar="TOPICS",
        help="Enable DEBUG logging (e.g., all, api, llm).",
    )
    g_log.add_argument(
        "--log-file",
        metavar="FILE",
        default=None,
        help="Redirect all logging output to a specified file.",
    )
    # --- Subparsers ---
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- Ingest Sub-parser ---
    p_ingest = subparsers.add_parser(
        "ingest", help="Test ingestion pipelines.", description="Test ingestion pipelines."
    )
    p_ingest.add_argument("pdf_file", help="Path to the input PDF file to test.")
    p_ingest.add_argument(
        "-t",
        "--task",
        default="extract-images",
        choices=["extract-images"],
        help="The specific ingestion task to run.",
    )
    p_ingest.add_argument(
        "-o",
        "--output-dir",
        default="./eval_reports",
        help="Directory to save the output report.",
    )
    p_ingest.add_argument(
        "--vision-model",
        default="llava:latest",
        help="Ollama model for image description.",
    )
    p_ingest.add_argument(
        "--utility-model",
        default="llama3.1:latest",
        help="Ollama model for image classification.",
    )
    p_ingest.add_argument(
        "--lang", default="en", choices=["en", "es", "ca"], help="Language for prompts."
    )
    p_ingest.set_defaults(func=handle_ingest_command)

    # --- Prompt Sub-parser ---
    p_prompt = subparsers.add_parser(
        "prompt",
        help="Evaluate prompt performance.",
        description=(
            "Evaluate prompt performance. "
            "Provide one directory for a single suite evaluation, or two directories "
            "to run a side-by-side comparison."
        ),
    )
    p_prompt.add_argument(
        "test_suite_dirs",
        nargs="+",
        metavar="TEST_SUITE_DIR",
        help="Path to one or two prompt test suite directories.",
    )
    p_prompt.add_argument(
        "--dm-model", default="llama3.1:latest", help="Main model for generating responses."
    )
    p_prompt.add_argument(
        "--utility-model",
        default="llama3.1:latest",
        help="Model for judging/scoring prompt outputs.",
    )
    p_prompt.set_defaults(func=handle_prompt_command)

    # --- LLM Config (common to both) ---
    for p in [p_ingest, p_prompt]:
        g_llm = p.add_argument_group("Ollama Configuration")
        g_llm.add_argument(
            "-U", "--url", default="http://localhost:11434", help="Ollama API URL."
        )
    parsed_args = parser.parse_args(args)
    if parsed_args.command == "prompt" and len(parsed_args.test_suite_dirs) > 2:
        parser.error("The 'prompt' command accepts a maximum of two directories.")

    return parsed_args


def main():
    """Main entry point for the script."""
    try:
        args = parse_arguments(sys.argv[1:])
        setup_logging(
            project_name="dmme_eval",
            level=logging.INFO if args.verbose else logging.WARNING,
            color_logs=args.color_logs,
            debug_topics=args.debug_topics,
            log_file=args.log_file,
            include_projects=["ppdf", "dmme"],
        )
        logging.getLogger("dmme_eval").info("DMme Eval starting up...")
        args.func(args)

    except Exception as e:
        logging.getLogger("dmme_eval").critical(
            "An unexpected error occurred: %s", e, exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
