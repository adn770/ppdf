# --- dmap_lib/prompts.py ---
LLAVA_PROMPT_CLASSIFIER = """
Analyze the provided image of a single dungeon map tile.
Classify the primary feature it contains.
Respond with a single JSON object with one key: "feature_type".
Possible values are "door", "secret_door", "iron_bar_door", "double_door", "stairs", "column",
"altar", "statue", "pit", "rubble", or null if it's just an empty floor tile.
Example Response:
{ "feature_type": "stairs" }
"""

LLAVA_PROMPT_ORACLE = """
Analyze the provided image of a dungeon map region.
Identify all distinct features present.
Respond with a single JSON object with one key: "features".
The value should be a list of objects, where each object has two keys:
1. "feature_type": A string classifying the feature.
   Possible values: "door", "secret_door", "iron_bar_door", "double_door", "stairs", "column",
   "altar", "statue", "pit", "rubble".
2. "bounding_box": An object with "x", "y", "width", and "height" keys,
   representing the feature's location in pixels.

Example Response:
{
  "features": [
    {
      "feature_type": "stairs",
      "bounding_box": {"x": 120, "y": 250, "width": 40, "height": 80}
    },
    {
      "feature_type": "column",
      "bounding_box": {"x": 300, "y": 400, "width": 30, "height": 30}
    }
  ]
}
"""
