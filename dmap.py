# --- dmap.py ---
import argparse
import os
import logging

from dmap_lib import rendering, schema
from dmap_lib.analysis import analyze_image
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
    p.add_argument(
        "-i", "--input", help="Path to the input PNG or JSON file."
    )
    p.add_argument(
        "-o", "--output", required=True, help="Base name for output files."
    )
    p.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip analysis and render directly from an existing JSON file "
             " (e.g., <output>.json).",
    )
    p.add_argument("--rooms", help="Comma-separated list of room numbers to render.")
    p.add_argument(
        "--hatching",
        action="store_true",
        help="Enables the procedural exterior border hatching.",
    )
    p.add_argument(
        "--no-features",
        action="store_true",
        help="Disables the rendering of all Feature objects.",
    )
    # Logging arguments
    g_log = p.add_argument_group("Logging & Output")
    g_log.add_argument("-v", "--verbose", action="store_true", help="Enable INFO logging.")
    g_log.add_argument(
        "--save-intermediate",
        metavar="DIR",
        help="Save intermediate analysis images to a directory.",
    )
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

    # --- New Logic for Skipping Analysis ---
    map_data = None
    unified_geometry = None
    json_path = f"{args.output}.json"

    if args.skip_analysis:
        log.info("Skipping analysis. Loading data from '%s'...", json_path)
        try:
            map_data = schema.load_json(json_path)
            # Unified geometry is not saved in JSON, so it will be None
            unified_geometry = None
            log.info("Successfully loaded map data.")
        except FileNotFoundError:
            log.critical("JSON file not found for --skip-analysis: %s", json_path)
            return
        except Exception as e:
            log.critical("Failed to load or parse JSON file: %s", e, exc_info=True)
            return

    # --- Original Analysis Workflow ---
    else:
        if not args.input:
            log.critical("--input is required unless --skip-analysis is used.")
            return

        if args.input.endswith(".json"):
            log.info("Input is a JSON file. Loading data and skipping analysis.")
            try:
                map_data = schema.load_json(args.input)
                unified_geometry = None
            except Exception as e:
                log.critical("Failed to load or parse JSON file: %s", e, exc_info=True)
                return
        else:
            if args.save_intermediate:
                try:
                    os.makedirs(args.save_intermediate, exist_ok=True)
                    log.info("Will save intermediate images to: %s", args.save_intermediate)
                except OSError as e:
                    log.error("Could not create intermediate image directory: %s", e)
                    args.save_intermediate = None

            try:
                map_data, unified_geometry = analyze_image(
                    args.input,
                    ascii_debug=args.ascii_debug,
                    save_intermediate_path=args.save_intermediate,
                )
                log.info("Saving analysis to '%s'...", json_path)
                schema.save_json(map_data, json_path)

            except Exception as e:
                log.critical("An unexpected error occurred during analysis: %s", e, exc_info=True)
                return

    # --- Common Rendering Path ---
    if map_data:
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


        if args.ascii_debug:
            log.info("--- ASCII Debug Output (Post-Transformation) ---")
            renderer = rendering.ASCIIRenderer()
            renderer.render_from_json(map_data)
            log.info("\n%s", renderer.get_output(), extra={"raw": True})
            log.info("--- End ASCII Debug Output ---")

        render_opts = {
            "rooms": args.rooms.split(",") if args.rooms else None,
            "hatching": args.hatching,
            "no_features": args.no_features,
        }
        run_rendering(map_data, unified_geometry, args.output, render_opts)
        log.info("--- Processing complete. ---")


if __name__ == "__main__":
    main()
