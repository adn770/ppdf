# --- dmap.py ---
import argparse
import os

from dmap_lib import analysis, rendering, schema


def run_rendering(map_data: schema.MapData, output_name: str, options: dict):
    """Generates and saves an SVG from a MapData object."""
    if not map_data:
        print("Skipping rendering because no map data was generated.")
        return

    print(f"Rendering SVG for '{output_name}'...")
    svg_content = rendering.render_svg(map_data, options)

    output_path = f"{output_name}.svg"
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        print(f"Successfully saved SVG to '{output_path}'")
    except IOError as e:
        print(f"ERROR: Could not write SVG file. {e}")


def get_cli_args():
    """Configures and parses command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Converts raster dungeon maps to structured JSON and SVG."
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        help="Path to the input PNG file."
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="The base name for the output .json and .svg files."
    )
    parser.add_argument(
        "--rooms",
        help="A comma-separated list of room numbers to render (e.g., '38,40,41')."
    )
    parser.add_argument("--bg-color", help="SVG background color (hex).")
    parser.add_argument("--wall-color", help="Color for outlines and hatching (hex).")
    parser.add_argument("--room-color", help="Fill color for rooms (hex).")
    parser.add_argument(
        "--line-thickness", type=float, help="A float multiplier for line thickness."
    )
    parser.add_argument(
        "--hatch-density", type=float, help="Multiplier for border hatching density."
    )
    parser.add_argument(
        "--no-grid", action="store_true", help="Disable rendering the grid in rooms."
    )
    return parser.parse_args()


def main():
    """Main entry point for the dmap CLI."""
    args = get_cli_args()

    print("--- DMAP CLI ---")
    try:
        # 1. Analysis Step
        map_data = analysis.analyze_image(args.input)
        print("\n--- Analysis Results ---")
        print(f"Found {len(map_data.mapObjects)} potential rooms.")

        # 2. Save Analysis to JSON
        json_output_path = f"{args.output}.json"
        print(f"Saving analysis to '{json_output_path}'...")
        schema.save_json(map_data, json_output_path)

        # 3. Rendering Step
        rendering_options = {}  # Not used yet, but passed for future compatibility
        run_rendering(map_data, args.output, rendering_options)

    except (FileNotFoundError, IOError) as e:
        print(f"\nERROR: {e}")


if __name__ == "__main__":
    main()
