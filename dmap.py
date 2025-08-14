# --- dmap.py ---
import argparse
import os

from dmap_lib import analysis, rendering, schema


def run_rendering(map_data: schema.MapData, unified_geo: list | None, output_name: str, options: dict):
    """Generates and saves an SVG from a MapData object and unified geometry."""
    print(f"\nRendering stylized SVG for '{output_name}'...")
    svg_content = rendering.render_svg(map_data, unified_geo, options)

    output_path = f"{output_name}.svg"
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        print(f"Successfully saved SVG to '{output_path}'")
    except IOError as e:
        print(f"ERROR: Could not write SVG file. {e}")


def get_cli_args():
    """Configures and parses command-line arguments."""
    p = argparse.ArgumentParser(description="Converts raster dungeon maps to JSON and SVG.")
    p.add_argument("-i", "--input", required=True, help="Path to the input PNG file.")
    p.add_argument("-o", "--output", required=True, help="Base name for output files.")
    p.add_argument("--rooms", help="Comma-separated list of room numbers to render.")
    return p.parse_args()


def main():
    """Main entry point for the dmap CLI."""
    args = get_cli_args()
    print("--- DMAP CLI ---")
    try:
        map_data, unified_geometry = analysis.analyze_image(args.input)

        num_r = sum(1 for o in map_data.mapObjects if isinstance(o, schema.Room))
        print(f"\n--- Analysis Results ---\nFound {num_r} rooms.")
        if unified_geometry:
            print(f"Successfully generated a unified geometry with {len(unified_geometry)} outer contours.")

        json_path = f"{args.output}.json"
        print(f"Saving analysis to '{json_path}'...")
        schema.save_json(map_data, json_path)

        render_opts = { "rooms": args.rooms.split(',') if args.rooms else None }
        run_rendering(map_data, unified_geometry, args.output, render_opts)
        print("\nProcessing complete.")

    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
