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


def demonstrate_serialization(output_name: str):
    """Creates a dummy MapData object and tests saving/loading it."""
    print("\n--- Testing Serialization ---")
    dummy_map_data = schema.MapData(
        dmapVersion="1.0.0-test",
        meta=schema.Meta("Test Map", "test.png", 20),
        mapObjects=[
            schema.Room(
                id="room_1", label="1", shape="polygon",
                gridVertices=[schema.GridPoint(0, 0), schema.GridPoint(5, 5)]
            )
        ]
    )
    temp_json_path = f"{output_name}_temp_test.json"
    schema.save_json(dummy_map_data, temp_json_path)
    loaded_map_data = schema.load_json(temp_json_path)
    if dummy_map_data == loaded_map_data:
        print("SUCCESS: Serialization and deserialization test passed.")
    else:
        print("FAILURE: Deserialized data does not match original.")
    os.remove(temp_json_path)


def main():
    """Main entry point for the dmap CLI."""
    args = get_cli_args()

    print("--- DMAP CLI ---")
    demonstrate_serialization(args.output)

    print("\n--- Main Execution Flow ---")
    try:
        map_data = analysis.analyze_image(args.input)
        print("\n--- Analysis Results ---")
        print(f"Source Image:     {map_data.meta.sourceImage}")
        print(f"Detected Grid Size: {map_data.meta.gridSizePx}px")

        # In a later milestone, this map_data object will be saved
        json_output_path = f"{args.output}.json"
        print(f"Saving analysis to '{json_output_path}'...")
        schema.save_json(map_data, json_output_path)
        print("Save complete.")

        rendering_options = {} # To be implemented
        run_rendering(map_data, args.output, rendering_options)

    except (FileNotFoundError, IOError) as e:
        print(f"\nERROR: {e}")


if __name__ == "__main__":
    main()
