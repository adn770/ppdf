LLM_PROMPT_CLASSIFIER = """
Analyze the provided image, which shows a small area of a TTRPG dungeon map.
Your task is to classify the single, primary feature in the CENTER of the image.

**IMPORTANT**: Pay close attention to context. First, determine if the feature
is freestanding within a room or part of a wall. Then, find the description that
best matches its specific shape.

Your response MUST be a single word from the list of possible feature types.

--- Feature Descriptions ---

**Freestanding Features:**
- "column": A freestanding, solid circle or square with NO internal details.
- "statue": A five-pointed star enclosed within a circle. MUST have the star.
- "throne": A U-shaped or high-backed chair symbol.
- "altar": A rectangular shape with an arrow symbol pointing out from one side. MUST have the arrow.
- "chest": A freestanding rectangle, often with small lines or squares on its edge representing latches.
- "table": A simple freestanding rectangle.
- "bed": A simple freestanding rectangle, often with a smaller shape for a pillow.
- "fountain": A circle that MUST contain a dot or smaller circle in the center.
- "pit": A circle or square with lines radiating inward. MUST have the radiating lines.
- "rubble": An area with a scattered, irregular pattern of small shapes and dots.
- "trap": Often marked with a 'T' inside a circle or square on the floor. MUST have the 'T'.
- "dais": A solid rectangular or circular shape indicating a raised platform.

**Wall-Based Features:**
- "door": A thin rectangle that interrupts or is placed within a solid wall line.
- "secret_door": Usually marked with an 'S' inside a section of solid wall. MUST have the 'S'.
- "portcullis": A rectangle with a grid/crosshatch pattern, placed in a wall opening.
- "iron_bar_door": A rectangle with a grid/crosshatch pattern, placed in a wall opening.
- "double_door": Two thin rectangles side-by-side in a wall opening.
- "archway": An opening in a wall, often wider than a door and shown with dotted lines.
- "fireplace": A U-shape or semi-circle inset into a solid wall.
- "shelf": A rectangle containing several parallel lines, typically against a wall.

**Other:**
- "stairs": A set of parallel lines within a rectangular boundary. MUST have parallel lines.
- "null": Empty floor space with no distinct features.

Example Response:
column
"""

LLM_PROMPT_ORACLE = """
Analyze the provided image of a dungeon map region.
Identify all distinct features present.
Respond with raw, headerless CSV data, with one feature per line.
The format for each line MUST be: feature_type,x1,y1,x2,y2

The bounding box values (x1, y1, x2, y2) MUST be normalized floats (0.0 to 1.0),
representing the top-left and bottom-right corners of the box, relative to the
image dimensions.

Your response MUST NOT contain any markdown formatting or headers.

--- Feature Descriptions ---

**Freestanding Features:**
- "column": A freestanding, solid circle or square with NO internal details.
- "statue": A five-pointed star enclosed within a circle. MUST have the star.
- "throne": A U-shaped or high-backed chair symbol.
- "altar": A rectangular shape with an arrow symbol pointing out from one side. MUST have the arrow.
- "chest": A freestanding rectangle, often with small lines or squares on its edge representing latches.
- "table": A simple freestanding rectangle.
- "bed": A simple freestanding rectangle, often with a smaller shape for a pillow.
- "fountain": A circle that MUST contain a dot or smaller circle in the center.
- "pit": A circle or square with lines radiating inward. MUST have the radiating lines.
- "rubble": An area with a scattered, irregular pattern of small shapes and dots.
- "trap": Often marked with a 'T' inside a circle or square. MUST have the 'T'.
- "dais": A solid rectangular or circular shape indicating a raised platform.

**Wall-Based Features:**
- "door": A thin rectangle that interrupts or is placed within a solid wall line.
- "secret_door": Usually marked with an 'S' inside a section of solid wall. MUST have the 'S'.
- "portcullis": A rectangle with a grid/crosshatch pattern, placed in a wall opening.
- "iron_bar_door": A rectangle with a grid/crosshatch pattern, placed in a wall opening.
- "double_door": Two thin rectangles side-by-side in a wall opening.
- "archway": An opening in a wall, often wider than a door and shown with dotted lines.
- "fireplace": A U-shape or semi-circle inset into a solid wall.
- "shelf": A rectangle containing several parallel lines, typically against a wall.

**Other:**
- "stairs": A set of parallel lines within a rectangular boundary. MUST have parallel lines.

Example Response:
column,0.7,0.8,0.78,0.88
"""
