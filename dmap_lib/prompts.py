# --- dmap_lib/prompts.py ---
LLM_PROMPT_CLASSIFIER = """
Analyze the provided image, which shows a 3x3 grid area of a TTRPG dungeon map.
Your task is to classify the single, primary feature in the CENTER tile and provide its
bounding box.

Your response MUST be a single line of raw, headerless CSV.
The format MUST be: feature_type,x,y,width,height

The bounding box values (x, y, width, height) MUST be normalized floats (0.0 to 1.0),
relative to the dimensions of the image provided.

Possible feature types: "door", "secret_door", "iron_bar_door", "double_door",
"stairs", "column", "altar", "statue", "pit", "rubble", or "null" if it's empty floor.

Example Response:
stairs,0.25,0.1,0.5,0.8
"""

LLM_PROMPT_ORACLE = """
Analyze the provided image of a dungeon map region.
Identify all distinct features present.
Respond with raw, headerless CSV data, with one feature per line.
The format for each line MUST be: feature_type,x,y,width,height

The bounding box values (x, y, width, height) MUST be normalized floats (0.0 to 1.0),
relative to the image dimensions.

Your response MUST NOT contain any markdown formatting or headers.

Possible feature types: "door", "secret_door", "iron_bar_door", "double_door", "stairs", "column",
"altar", "statue", "pit", "rubble".

Example Response:
stairs,0.25,0.5,0.1,0.2
column,0.7,0.8,0.08,0.08
"""
