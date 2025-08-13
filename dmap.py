# --- dmap.py ---
import argparse
import os

from dmap_lib import analysis, rendering, schema


def run_rendering(map_data: schema.MapData, output_name: str, options: dict):
    """Generates and saves an SVG from a MapData object."""
    if not map_data:
        print("Skipping rendering because no map data was generated.")
        return
    print(f"\nRendering stylized SVG for '{output_name}'...")
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
    p = argparse.ArgumentParser(description="Converts raster dungeon maps to JSON and SVG.")
    p.add_argument("-i", "--input", required=True, help="Path to the input PNG file.")
    p.add_argument("-o", "--output", required=True, help="Base name for output files.")
    p.add_argument("--rooms", help="Comma-separated list of room numbers to render.")
    p.add_argument("--bg-color", help="SVG background color (hex).")
    p.add_argument("--wall-color", help="Color for outlines and hatching (hex).")
    p.add_argument("--room-color", help="Fill color for rooms (hex).")
    p.add_argument("--line-thickness", type=float, help="Multiplier for line thickness.")
    p.add_argument("--hatch-density", type=float, help="Multiplier for border hatching.")
    p.add_argument("--no-grid", action="store_true", help="Disable rendering the grid.")
    return p.parse_args()


def main():
    """Main entry point for the dmap CLI."""
    args = get_cli_args()
    print("--- dmap CLI ---")
    try:
        map_data = analysis.analyze_image(args.input)
        num_r = sum(1 for o in map_data.mapObjects if isinstance(o, schema.Room))
        num_d = sum(1 for o in map_data.mapObjects if isinstance(o, schema.Door))
        num_f = sum(1 for o in map_data.mapObjects if isinstance(o, schema.Feature))
        print(f"\n--- Analysis Results ---\nFound {num_r} rooms, {num_d} doors, and {num_f} features.")

        json_path = f"{args.output}.json"
        print(f"Saving analysis to '{json_path}'...")
        schema.save_json(map_data, json_path)

        render_opts = {
            "rooms": args.rooms.split(',') if args.rooms else None,
            "bg_color": args.bg_color, "wall_color": args.wall_color,
            "room_color": args.room_color, "line_thickness": args.line_thickness,
            "hatch_density": args.hatch_density, "no_grid": args.no_grid
        }
        run_rendering(map_data, args.output, render_opts)
        print("\nProcessing complete.")

    except (FileNotFoundError, IOError) as e:
        print(f"\nERROR: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
