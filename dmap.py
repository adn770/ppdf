import argparse
import os
import logging

from dmap_lib import analysis, rendering, schema
from dmap_lib.log_utils import setup_logging


def run_rendering(
    map_data: schema.MapData, unified_geo: list | None, output_name: str, options: dict
):
    """Generates and saves an SVG from a MapData object and unified geometry."""
    log = logging.getLogger("dmap.main")
    log.info("Rendering stylized SVG for '%s'...", output_name)
    svg_content = rendering.render_svg(map_data, unified_geo, options)

    output_path = f"{output_name}.svg"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        log.info("Successfully saved SVG to '%s'", output_path)
    except IOError as e:
        log.error("Could not write SVG file: %s", e)


def get_cli_args():
    """Configures and parses command-line arguments."""
    p = argparse.ArgumentParser(description="Converts raster dungeon maps to JSON and SVG.")
    p.add_argument("-i", "--input", required=True, help="Path to the input PNG file.")
    p.add_argument("-o", "--output", required=True, help="Base name for output files.")
    p.add_argument("--rooms", help="Comma-separated list of room numbers to render.")
    p.add_argument(
        "--hatching",
        action="store_true",
        help="Enables the procedural exterior border hatching.",
    )
    # Logging arguments
    g_log = p.add_argument_group("Logging & Output")
    g_log.add_argument("-v", "--verbose", action="store_true", help="Enable INFO logging.")
    g_log.add_argument("--color-logs", action="store_true", help="Enable colored logging.")
    g_log.add_argument("--log-file", metavar="FILE", help="Redirect log output to a file.")
    g_log.add_argument(
        "--ascii-debug",
        action="store_true",
        help="Render an ASCII map of the final structure for debugging.",
    )
    g_log.add_argument(
        "-d",
        "--debug",
        nargs="?",
        const="all",
        dest="debug_topics",
        metavar="TOPICS",
        help="Enable DEBUG logging (all,analysis,grid,ocr,geometry,render).",
    )
    return p.parse_args()


def main():
    """Main entry point for the dmap CLI."""
    args = get_cli_args()
    log_level = logging.INFO if args.verbose else logging.WARNING
    if args.debug_topics:
        log_level = logging.DEBUG

    setup_logging(log_level, args.color_logs, args.debug_topics, args.log_file)
    log = logging.getLogger("dmap.main")

    log.info("--- DMAP CLI Initialized ---")
    log.debug("Arguments received: %s", vars(args))

    try:
        map_data, unified_geometry = analysis.analyze_image(
            args.input, ascii_debug=args.ascii_debug
        )

        num_r = sum(
            1 for r in map_data.regions for o in r.mapObjects if isinstance(o, schema.Room)
        )
        num_d = sum(
            1 for r in map_data.regions for o in r.mapObjects if isinstance(o, schema.Door)
        )
        log.info("--- Analysis Results ---")
        log.info("Found %d rooms and %d doors.", num_r, num_d)
        if unified_geometry:
            log.info(
                "Generated a unified geometry with %d outer contours.", len(unified_geometry)
            )

        json_path = f"{args.output}.json"
        log.info("Saving analysis to '%s'...", json_path)
        schema.save_json(map_data, json_path)

        if args.ascii_debug:
            log.info("--- ASCII Debug Output (Post-Transformation) ---")
            renderer = rendering.ASCIIRenderer()
            renderer.render_from_json(map_data)
            log.info("\n%s", renderer.get_output(), extra={"raw": True})
            log.info("--- End ASCII Debug Output ---")

        render_opts = {
            "rooms": args.rooms.split(",") if args.rooms else None,
            "hatching": args.hatching,
        }
        run_rendering(map_data, unified_geometry, args.output, render_opts)
        log.info("--- Processing complete. ---")

    except Exception as e:
        log.critical("An unexpected error occurred: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
