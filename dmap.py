# --- dmap.py ---
import argparse
import os

from dmap_lib import analysis, schema


def run_rendering(map_data, output_name: str, options: dict):
    """Placeholder for the SVG rendering logic."""
    if map_data:
        print(f"Rendering SVG for '{output_name}'... (not yet implemented)")
    else:
        print("Skipping rendering because no map data was generated.")


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
        map_data = analysis.analyze_image(args.input)
        print("\n--- Analysis Results ---")
        print(f"Source Image:     {map_data.meta.sourceImage}")
        print(f"Detected Grid Size: {map_data.meta.gridSizePx}px")
        print(f"Found {len(map_data.mapObjects)} potential rooms.")

        if map_data.mapObjects:
            print("Sample of detected rooms:")
            for room in map_data.mapObjects[:3]:
                if isinstance(room, schema.Room):
                    print(f"  - Room ID: {room.id}, Vertices: {len(room.gridVertices)}")

        json_output_path = f"{args.output}.json"
        print(f"\nSaving analysis with room data to '{json_output_path}'...")
        schema.save_json(map_data, json_output_path)
        print("Save complete.")

        rendering_options = {} # To be implemented
        run_rendering(map_data, args.output, rendering_options)

    except (FileNotFoundError, IOError) as e:
        print(f"\nERROR: {e}")


if __name__ == "__main__":
    main()
