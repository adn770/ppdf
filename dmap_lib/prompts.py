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
