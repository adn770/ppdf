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
    # Add other arguments...
    return parser.parse_args()


def main():
    """Main entry point for the dmap CLI."""
    args = get_cli_args()

    print("--- DMAP CLI ---")
    try:
        map_data = analysis.analyze_image(args.input)
        print("\n--- Analysis Results ---")
        print(f"Found {len(map_data.mapObjects)} potential rooms.")

        if map_data.mapObjects:
            print("Sample of detected rooms (with labels):")
            for room in map_data.mapObjects[:5]: # Print first 5
                if isinstance(room, schema.Room):
                    label = room.label if room.label else "N/A"
                    print(
                        f"  - Room ID: {room.id}, Label: {label}, "
                        f"Vertices: {len(room.gridVertices)}"
                    )

        json_output_path = f"{args.output}.json"
        print(f"\nSaving analysis with labels to '{json_output_path}'...")
        schema.save_json(map_data, json_output_path)

        rendering_options = { "rooms": args.rooms.split(',') if args.rooms else None }
        run_rendering(map_data, args.output, rendering_options)

    except (FileNotFoundError, IOError) as e:
        print(f"\nERROR: {e}")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
