
# Project: dmap (Dungeon Map Processor)

---

## 0. AI Assistant Procedures

This section outlines the collaborative workflows between the developer and the AI
assistant. The core principle is **Confirmation-Based Structuring**: the developer
can use natural language, and the assistant is responsible for structuring the
request into a formal plan that requires developer approval before execution.

### 0.1. Main Rules
-   **Developer-Led Workflow**: The developer always initiates the activity.
-   **Providing Context**: The developer will provide the relevant project context.
-   **Confirmation and Readiness**: The assistant will confirm its understanding and
    signal its readiness.

### 0.2. Code & Document Generation
-   **Complete Code**: All source code must be complete and self-contained. "Self-contained"
    means the code must execute without errors assuming all necessary libraries are
    installed. All required `import` statements must be present.
-   **File Content Presentation**: All generated source code for a specific file **must**
    begin with a single header line in the format: `# --- path/to/your/file.ext ---`.
-   **Asymmetric Guard Convention**: The developer may use multi-file guards (e.g.,
    `--- START FILE: ... ---`) for uploading source code context. These guards are
    for input only. The assistant's generated code **must not** contain these guards.
-   **Line Length & Formatting**: Code and text should be formatted to a maximum of 95
    characters per line, with no trailing whitespace.
-   **Document Integrity**: Design documents must be presented in their complete form.
-   **Milestone Detail**: Milestones must include a `Goal`, `Description`, `Key
    Tasks`, and `Outcome`.
-   **Copy-Friendly Markdown**: Documents in Markdown must be delivered as a raw
    markdown code block adhering to the GitHub Flavored Markdown (GFM) specification.
-   **Citation-Free Output**: Generated source code and markdown documents must not
    contain any inline citations (e.g., ``). All necessary information
    should be self-contained.

### 0.3. Bug Fixing Workflow
1.  **Initiation**: The developer reports a bug using natural language.
2.  **Plan Proposal**: The assistant interprets the request, analyzes the issue, and
    proposes a structured, mandatory `Bug-Fix Plan` for approval.
3.  **Approval**: The developer provides a simple confirmation (e.g., "Yes, proceed,"
    "Approved").
4.  **Execution**: Only after approval does the assistant generate the necessary code to
    implement the fix.

### 0.4. Idea Development Workflow
This workflow governs the creation of new features and has two distinct modes.

-   **🧠 Brainstorm Mode (Divergent)**:
    -   **Goal**: To generate a wide array of diverse, high-level possibilities.
    -   **Process**: The developer starts with a broad topic (e.g., "Let's brainstorm a
        music system"). The assistant provides a list of creative, distinct concepts.

-   **🛠️ Design Mode (Convergent)**:
    -   **Goal**: To refine a single concept into a detailed, actionable plan.
    -   **Process**: The developer starts with a specific idea or selects an option from
        Brainstorm Mode. The assistant uses the Confirmation-Based Structuring approach
        to create and refine a formal `Design Proposal` until it is approved.

### 0.5. Milestone Implementation Workflow
-   The assistant presents the next milestone from the `Implementation Plan`.
-   Upon developer approval, the assistant generates the **complete source code** required
    to fulfill that milestone.

### 0.6. Append-Only Design & Implementation
-   **Immutable History**: The design document is the single source of truth for the
    project's history and intent. Completed or superseded phases and milestones
    **must not be removed or altered**. The document functions as an append-only log.
-   **Fine-Grained Milestones**: Every new feature must be broken down into a series of
    incremental, fine-grained milestones.
-   **Workflow for Extension**: At the conclusion of an **Idea Development** session, the
    assistant's final output will be a new, fully-formatted `Phase` containing these
    milestones, ready to be appended to the `Implementation Plan`.

### 0.7. Session Initialization & Code Review
-   **Step 1: Context Upload**: At the start of a session, the developer will first
    upload the latest design document, followed by the complete source code.
-   **Step 2: AI Acknowledgment**: The assistant will confirm receipt of both the
    design document and the source code files.
-   **Step 3: Automated Analysis**: The assistant's first action is to perform a
    comprehensive analysis, comparing the provided source code against the design
    document.
-   **Step 4: Report Generation**: The assistant will produce a concise report
    detailing its findings on alignment, completeness, and deviations.
-   **Step 5: Proceed with Task**: After presenting the analysis, the assistant will
    signal its readiness to proceed with the developer's next instruction.

---

## 1. Core Concept

`dmap` is a Python-based utility for converting raster dungeon map images (e.g.,
`.png`) into a structured, machine-readable JSON format and a stylized,
procedurally generated SVG format.

The project is architected as a core library (`dmap_lib`) and a command-line
interface (`dmap.py`) that uses it. This modular design allows the core logic to
be integrated into other applications, such as the AI Dungeon Master Engine
(`dmme`), while providing a powerful standalone tool for map conversion.

The pipeline uses **OpenCV** for robust image analysis to identify rooms, doors,
and other features, including complex polygonal shapes. It leverages the
**EasyOCR** library for accurate recognition of room numbers, which are stored as
labels in the intermediate JSON. The rendering engine can then use this JSON to
recreate the full map as an SVG or generate partial maps showing only a
user-specified list of rooms and their direct connections.

---

## 2. File System Structure

The project will be organized into a library package and a command-line script.
This structure promotes code reuse and clean separation of concerns.

`ppdf/`
├── **dmap_lib/**: The installable library package.
│   ├── `__init__.py`
│   ├── `analysis.py`: Image analysis, feature detection, and number recognition.
│   ├── `schema.py`: Data structures (dataclasses) and JSON serialization.
│   └── `rendering.py`: Procedural SVG generation logic.
│
├── **dmap.py**: The command-line executable script.
│
└── **docs/**: Project documentation.
    ├── `design-dmme.md`
    └── `design-dmap.md`

---

## 3. Library Design (`dmap_lib`)

The core logic is encapsulated within the `dmap_lib` package, exposing a clean
API for analysis and rendering.

### 3.1. `analysis` Module
-   **Purpose**: To handle all image processing and map feature recognition.
-   **Key Function**: `analyze_image(image_path: str) -> MapData`
    -   Performs image preprocessing (grayscale, thresholding, noise reduction).
    -   Detects the grid to establish a coordinate system.
    -   Uses OpenCV to find contours and `cv2.approxPolyDP` to simplify them into
        polygonal shapes for rooms and caverns.
    -   For each identified room, it isolates the area and uses **EasyOCR** to
        recognize a numerical label. It will also analyze room fill patterns to
        detect environmental layers like water.
    -   Classifies smaller, interior contours as specific features (stairs,
        columns, etc.) based on shape analysis and heuristics.
    -   Returns a structured `MapData` object representing the full map.

### 3.2. `schema` Module
-   **Purpose**: To define the canonical data structures and handle serialization.
-   **Key Components**:
    -   Python `dataclasses` for `MapData`, `MapObject`, `Room`, `Door`, etc.
    -   `save_json(map_data: MapData, output_path: str)`: Serializes a `MapData`
        object to a `.json` file.
    -   `load_json(input_path: str) -> MapData`: Deserializes a `.json` file into a
        `MapData` object.

### 3.3. `rendering` Module
-   **Purpose**: To handle the procedural generation of the SVG file.
-   **Key Function**: `render_svg(map_data: MapData, style_options: dict,
    room_labels_to_render: list[str] = None) -> str`
    -   Accepts a `MapData` object, style parameters, and an optional list of room
        labels to render.
    -   If a list of labels is provided, it filters the `mapObjects` to include only
        the specified rooms and any doors connecting them.
    -   Procedurally draws the filtered set of map objects, including environmental
        layers (like water) and stylized features according to the style
        specification.
    -   Returns the complete SVG content as a string.

#### 3.3.1. Render Style Specification
This section defines the target visual style for the SVG output, based on an
analysis of the `stronghold.svg` example.

-   **Color Palette**:
    -   **Background**: `#EDE0CE` (A light parchment color).
    -   **Room Fill**: `#F7EEDE` (A slightly lighter parchment/off-white).
    -   **Wall & Detail Lines**: `#000000` (Black).
    -   **Shadow/Offset**: `#999999` (A dark gray for the drop shadow effect).
    -   **Glow/Underlayer**: `#C9C1B1` (A light gray-brown for a soft border effect).

-   **Layering and Effects**: The final look is achieved through three distinct layers
    rendered from bottom to top:
    1.  **Shadow Layer**: A copy of the room polygons is rendered first, offset
        slightly down and to the right (e.g., by `3px`). It is filled and stroked
        with the shadow color (`#999999`) to create a drop shadow.
    2.  **Glow/Underlayer**: A copy of the room polygons is rendered with a very
        thick, semi-transparent stroke (`#C9C1B1`, `stroke-opacity="0.4"`) to
        create a soft, thick border underneath the main walls.
    3.  **Main Layer**: The primary room polygons are rendered with their fill color
        (`#F7EEDE`) and a thick, black outline (`#000000`, `stroke-width: 7`).

-   **Border Hatching**:
    -   The "earth" texture around the rooms is not a simple pattern. It is a series
        of procedurally generated, slightly randomized, short black lines (`stroke:
        #000000`, `stroke-width: 1.2`).
    -   The hatching should be drawn around the exterior perimeter of all rendered
        room and corridor polygons, extending outwards. The density can be
        controlled by the `--hatch-density` CLI flag.

-   **Internal Details**:
    -   **Grid**: The internal grid should be rendered as a pattern of small dots,
        not lines.
    -   **Features**: Simple features like columns or doors should be rendered with a
        thinner black line (`stroke-width: 1.5` to `3.5`) to distinguish them from
        the main walls.

### 3.4. Supported Feature Types
This section details the features to be identified and rendered.

-   **Columns/Pillars**: Identified as small, simple geometric shapes (circles,
    squares). Rendered as filled shapes with a black outline.
-   **Statues**: Identified as more complex, often symmetrical shapes. Rendered as
    stylized outlines. Can have a `facing` direction.
-   **Stairs**: Identified by a series of parallel lines within a rectangular boundary.
    Rendered as a rectangle with evenly spaced lines indicating steps.
-   **Thrones**: Identified as a prominent, often ornate, chair-like shape. Rendered
    as a stylized, high-backed chair.
-   **Curtains/Drapes**: Identified by wavy, parallel lines, often near an opening.
    Rendered with flowing, slightly randomized curves.
-   **Fountains/Pools**: Identified by circular or geometric shapes with internal
    patterns suggesting water. These will be handled by the `water` layer.
-   **Water Layer**: Identified by a distinct fill pattern (e.g., wavy lines) inside
    a room's polygon. Rendered as a semi-transparent blue fill (`#77AADD`,
    `fill-opacity="0.5"`) with procedural wave lines on top. This layer is drawn
    above the room fill but below other features like columns or statues.

---

## 4. Data Format (JSON Schema)

The intermediate JSON format is designed to be extensible and resolution-independent
by using grid-based coordinates. It support specific feature types and environmental
layers.

-   **Version**: 1.0.0
-   **Example**:
    ```json
    {
      "dmapVersion": "1.0.0",
      "meta": {
        "title": "Tomb of the Serpent Kings",
        "sourceImage": "tomb2.png",
        "gridSizePx": 20
      },
      "mapObjects": [
        {
          "id": "room_uuid_1",
          "type": "room",
          "label": "38",
          "shape": "polygon",
          "gridVertices": [
            {"x": 10, "y": 10},
            {"x": 20, "y": 10},
            {"x": 20, "y": 15},
            {"x": 10, "y": 15}
          ],

          "properties": {
            "layer": "water"
          },
          "contents": ["feature_01"]
        },
        {
          "id": "door_uuid_1",
          "type": "door",
          "gridPos": {"x": 20, "y": 12},
          "orientation": "vertical",
          "connects": ["room_uuid_1", "room_uuid_2"]
        },
        {
          "id": "feature_01",
          "type": "feature",
          "featureType": "statue",
          "shape": "polygon",
          "gridVertices": [ ... ],
          "properties": {
            "facing": "north"
          }
        }
      ]
    }
    ```

---

## 5. Command-Line Interface (`dmap.py`)

The CLI provides a user-friendly way to interact with the `dmap_lib` library.

-   **Usage**: `python dmap.py -i <input.png> -o <output_name> [OPTIONS]`
-   **Arguments & Flags**:
    -   `--input` / `-i`: **(Required)** Path to the input PNG file.
    -   `--output` / `-o`: **(Required)** The base name for the output `.json` and
        `.svg` files.
    -   `--rooms`: A comma-separated list of room numbers to render (e.g.,
        `--rooms 38,40,41`). If omitted, the entire map is rendered.
    -   `--bg-color`: SVG background color (hex).
    -   `--wall-color`: Color for room outlines and hatching (hex).
    -   `--room-color`: Fill color for rooms (hex).
    -   `--line-thickness`: A float multiplier for line thickness.
    -   `--hatch-density`: A float multiplier for border hatching density.
    -   `--no-grid`: A boolean flag to disable rendering the grid inside rooms.

---

## 6. Implementation Plan

This plan breaks down the development of `dmap` into incremental, low-complexity
milestones.

### Phase 1: Library and Schema Foundation

-   **Milestone 1: Project Scaffolding and Schema Definition**
    -   **Goal**: Create the project's directory structure and define the core data
        models.
    -   **Description**: This milestone establishes the foundational file structure and
        the data classes that will be used throughout the project, ensuring a solid
        base for future development.
    -   **Key Tasks**:
        1.  Create the `dmap_lib/` directory and the empty `.py` files within it.
        2.  Create the `dmap.py` script file.
        3.  In `dmap_lib/schema.py`, define all necessary Python `dataclasses` for
            the JSON schema (e.g., `MapData`, `MapObject`, `Room`).
    -   **Outcome**: A complete project structure and a fully defined, importable set
        of data models for representing a map.

-   **Milestone 2: Implement JSON Serialization and CLI Stubs**
    -   **Goal**: Implement the logic to save/load the data models and create a basic,
        runnable CLI.
    -   **Description**: This milestone makes the schema functional by adding JSON
        conversion logic and sets up the command-line interface to handle arguments,
        even though it won't perform any real processing yet.
    -   **Key Tasks**:
        1.  In `dmap_lib/schema.py`, implement the `save_json` and `load_json`
            functions.
        2.  In `dmap.py`, use `argparse` to implement the full CLI argument
            specification (`--input`, `--output`, etc.).
        3.  Add placeholder functions for the main execution logic.
    -   **Outcome**: A runnable `dmap.py` script that accepts all specified command-line
        arguments and can serialize/deserialize hardcoded `MapData` objects.

### Phase 2: Core Image Analysis

-   **Milestone 3: Basic Image Processing and Grid Detection**
    -   **Goal**: Implement the initial image analysis steps to prepare an image and
        determine the map's scale.
    -   **Description**: This milestone focuses on the foundational computer vision
        tasks required before any features can be identified.
    -   **Key Tasks**:
        1.  In `dmap_lib/analysis.py`, begin the `analyze_image` function.
        2.  Implement image loading, conversion to grayscale, and binary thresholding
            using OpenCV.
        3.  Add a heuristic-based function to detect the grid size in pixels.
    -   **Outcome**: The `analyze_image` function can successfully load an image and
        calculate the `gridSizePx` value for the `meta` section of the JSON.

-   **Milestone 4: Room Detection and Polygonal Approximation**
    -   **Goal**: Identify all room shapes in the processed image.
    -   **Description**: This milestone implements the core logic for finding room
        contours and converting them into the simplified polygonal format for our
        schema.
    -   **Key Tasks**:
        1.  In `analyze_image`, use `cv2.findContours` to get all shapes.
        2.  Filter the contours by area to isolate potential rooms.
        3.  Use `cv2.approxPolyDP` to simplify the room contours into vertices.
        4.  Populate `Room` objects with the calculated `gridVertices`.
    -   **Outcome**: The `analyze_image` function can produce a `MapData` object
        containing a list of all rooms found in the image, represented as polygons.

### Phase 3: SVG Rendering

-   **Milestone 5: Basic SVG Rendering of Rooms**
    -   **Goal**: Implement the initial SVG rendering logic to draw the identified rooms.
    -   **Description**: This milestone creates the first visual output, drawing the
        polygonal room shapes based on the generated JSON data.
    -   **Key Tasks**:
        1.  In `dmap_lib/rendering.py`, begin the `render_svg` function.
        2.  Add logic to create an SVG canvas and iterate through the `mapObjects`.
        3.  For each `Room` object, draw an SVG `<polygon>` element using its
            `gridVertices`.
        4.  Connect this function to the `dmap.py` CLI.
    -   **Outcome**: The `dmap.py` tool can now take a PNG, analyze it, and output a basic
        SVG file showing the outlines of the detected rooms.

-   **Milestone 6: Implement Stylistic Rendering**
    -   **Goal**: Add the stylized border hatching and custom colors to the SVG output.
    -   **Description**: This milestone implements the key aesthetic features that define
        the map's style.
    -   **Key Tasks**:
        1.  In `render_svg`, implement a function to procedurally generate the "sketchy"
            hatching lines around the exterior of each room polygon.
        2.  Integrate the `style_options` dictionary to control colors, line
            thickness, and hatch density.
    -   **Outcome**: The generated SVG now closely matches the target artistic style,
        with colored rooms and textured borders.

### Phase 4: Feature Recognition and Filtering

-   **Milestone 7: Implement Number Recognition**
    -   **Goal**: Integrate EasyOCR to identify and label the rooms.
    -   **Description**: This milestone adds the number recognition capability to the
        analysis pipeline.
    -   **Key Tasks**:
        1.  In `dmap_lib/analysis.py`, add the EasyOCR library.
        2.  For each identified room, create a masked image of its interior.
        3.  Run the masked image through EasyOCR to find numbers.
        4.  Add the recognized number to the `Room` object's `label` field.
    -   **Outcome**: The generated JSON now includes the correct numerical labels for
        each room.

-   **Milestone 8: Implement Door Detection and Linking**
    -   **Goal**: Identify doors and establish their connections between rooms.
    -   **Description**: This milestone completes the core map structure by finding doors
        and logically linking the rooms they connect.
    -   **Key Tasks**:
        1.  In `analyze_image`, after identifying rooms, process the remaining smaller
            contours to find potential doors.
        2.  For each door, determine which two rooms it connects based on proximity.
        3.  Populate `Door` objects with their `connects` data.
    -   **Outcome**: The JSON now contains a complete representation of the map's
        topology, with rooms and their connections fully defined.

-   **Milestone 9: Implement Partial Map Rendering**
    -   **Goal**: Enable the rendering of a user-specified subset of rooms.
    -   **Description**: This milestone implements the `--rooms` CLI flag, allowing
        users to generate SVGs of single rooms or small sections of the map.
    -   **Key Tasks**:
        1.  In `dmap_lib/rendering.py`, implement the filtering logic in the
            `render_svg` function.
        2.  In `dmap.py`, parse the comma-separated `--rooms` argument and pass the
            resulting list to the `render_svg` function.
    -   **Outcome**: The `dmap.py` tool is now fully functional, capable of generating
        complete or partial maps with all specified styling and features.

### Phase 5: Advanced Feature Rendering

-   **Milestone 10: Implement Advanced Feature and Layer Detection**
    -   **Goal**: Enhance the analysis engine to identify specific feature types and
        environmental layers.
    -   **Description**: This milestone expands the computer vision logic to classify
        the generic "feature" contours into specific types and to detect patterns
        indicating a water layer.
    -   **Key Tasks**:
        1.  In `dmap_lib/analysis.py`, create a classifier function that takes a
            contour and uses shape analysis (e.g., number of vertices, symmetry,
            aspect ratio) to return a `featureType` string (e.g., "column", "stairs").
        2.  Integrate this classifier into the `analyze_image` pipeline.
        3.  Add logic to `analyze_image` to detect fill patterns (like wavy lines)
            within room contours and assign the "water" value to the `layer` property.
    -   **Outcome**: The generated JSON is now populated with specific `featureType`
        and `layer` properties based on the visual content of the map.

-   **Milestone 11: Implement Advanced Feature and Layer Rendering**
    -   **Goal**: Enhance the rendering engine to draw the newly identified features
        and layers according to the style guide.
    -   **Description**: This milestone adds the drawing logic for each supported
        feature type and implements the rendering of the water layer.
    -   **Key Tasks**:
        1.  In `dmap_lib/rendering.py`, expand the `render_svg` function to handle the
            new `featureType` and `layer` properties.
        2.  Create separate helper functions to draw each feature type (e.g.,
            `draw_stairs`, `draw_statue`).
        3.  Implement the water layer rendering, which should be drawn on top of the
            room fill but beneath all other objects contained in that room.
    -   **Outcome**: The `dmap.py` tool can now produce highly detailed SVGs that
        faithfully represent complex map features like stairs, statues, and water.

### Phase 6: High-Fidelity Rendering and Analysis

-   **Milestone 12: Implement Polygon Union for Unified Geometry**
    -   **Goal**: Create a single, unified polygon representing the entire map's floor space.
    -   **Description**: This is a critical prerequisite for advanced rendering. It involves merging all individual room polygons into one complex shape using a robust geometry library, which is essential for creating the unified exterior border.
    -   **Key Tasks**:
        1.  Integrate the `shapely` library into the project for computational geometry operations.
        2.  In `analysis.py`, convert all detected room contours into `shapely` Polygon objects.
        3.  Use `shapely.ops.unary_union` to merge all room polygons into a single geometry object.
        4.  Create a helper function to convert the unified `shapely` geometry back into a list of vertex contours usable by the rendering engine.
    -   **Outcome**: The analysis pipeline will produce a single, unified geometry representing the entire map's exterior boundary, in addition to the individual room objects.

-   **Milestone 13: Implement Advanced Exterior Hatching**
    -   **Goal**: Replicate the target SVG's unified, sketchy exterior hatching.
    -   **Description**: This milestone replaces the per-room hatching with a new algorithm that operates on the unified geometry from the previous milestone, providing a more professional and aesthetically pleasing result.
    -   **Key Tasks**:
        1.  In `rendering.py`, create a new `_generate_unified_hatching` function that accepts the unified map geometry.
        2.  Adapt the existing hatching logic (generating randomized short lines along an edge) to trace the `exterior` boundary of the unified shape.
        3.  Ensure the hatching is drawn correctly around complex shapes and does not appear in the interior of the dungeon.
    -   **Outcome**: The generated SVG will feature a single, continuous field of hatching around the entire dungeon complex, matching the target style.

-   **Milestone 14: Replicate Target Style and Door Rendering**
    -   **Goal**: Precisely match the visual aesthetic of the `stronghold.svg` example.
    -   **Description**: This milestone updates the default style parameters and adds specific drawing logic for doors to fully conform to the target style guide.
    -   **Key Tasks**:
        1.  In `rendering.py`, update the default `styles` dictionary to use the exact color palette and line weights from the `Render Style Specification`.
        2.  Modify the door rendering logic to draw doors as rectangles filled with the room color and a thin black outline.
        3.  Fine-tune the three-layer rendering effect (shadow, glow, main) to work seamlessly with the new style parameters.
    -   **Outcome**: The SVG output's colors, line weights, and feature appearance will be visually indistinguishable from the target `stronghold.svg` example.

-   **Milestone 15: Improve Door Detection Heuristics**
    -   **Goal**: Reliably detect doors in maps where they are represented as gaps in walls.
    -   **Description**: This milestone replaces the simple contour-based door detector with a more robust, geometry-based approach that can identify narrow passages between rooms.
    -   **Key Tasks**:
        1.  In `analysis.py`, create a new door detection function that operates *after* rooms have been identified.
        2.  For every pair of rooms, calculate the intersection of their slightly "dilated" shapes (using `shapely.buffer`).
        3.  If the intersection is a small, compact area, classify it as a door connection.
        4.  The centroid of this intersection area becomes the position of the detected `Door` object.
    -   **Outcome**: The tool can accurately detect and place doors on a wider variety of map styles, including those like `stronghold.png` where doors are not distinct objects.

### Phase 7: Observability and Refinement

* **Milestone 16: Implement Advanced Logging System**
    * **Goal**: Integrate a sophisticated, topic-based logging system to improve the tool's observability and ease of debugging.
    * **Description**: This comprehensive milestone introduces a new logging utility inspired by the `ppdf` project. It will replace all `print()` statements with structured, topic-based log messages, add command-line flags for controlling log verbosity and output, and provide a clear, color-coded format for console output.
    * **Key Tasks**:
        1.  Create a new `dmap_lib/log_utils.py` module to house the `setup_logging` function and a custom `RichLogFormatter` class.
        2.  Define the logging topics for `dmap`: `main`, `analysis`, `grid`, `ocr`, `geometry`, and `render`.
        3.  Add `--debug`, `--color-logs`, and `--log-file` arguments to `dmap.py`.
        4.  Call `setup_logging` at startup in `dmap.py` and replace all `print` calls with structured logging.
        5.  Instrument `dmap_lib/analysis.py` with detailed `log.info` and `log.debug` calls using topic-specific loggers.
        6.  Instrument `dmap_lib/rendering.py` with `log.info` and `log.debug` calls using the `dmap.render` logger.
    * **Outcome**: The `dmap` tool will have a comprehensive and configurable logging system. Developers can easily enable detailed debug output for specific components, and all output will be structured and informative, significantly improving the development and debugging experience.

### Phase 8: Final Polish and Heuristics

* **Milestone 17: High-Fidelity Shape Extraction**
    * **Goal**: Restore the sharp, angular geometry of the rooms by replacing the distorting morphological operations.
    * **Description**: This milestone replaces the "blobby" shape generation with a more precise "hole-filling" algorithm. It will digitally remove grid dots from the floor plan without distorting the room's original shape, resulting in a crisp final render.
    * **Key Tasks**:
        1.  In `analysis.py`, remove the `cv2.morphologyEx` call.
        2.  Change the initial `cv2.findContours` mode to `cv2.RETR_TREE` to find all shapes, including holes.
        3.  Create a new function to iterate through all found contours. If a contour is very small (like a grid dot), "paint" it over on the binary image.
        4.  Run a final `cv2.findContours` call on the cleaned image to get the final, crisp room polygons.
    * **Outcome**: The generated room polygons will accurately match the sharp corners and straight lines of the source map, eliminating the distorted appearance.

* **Milestone 18: Wall Mask Generation and OCR**
    * **Goal**: Correctly extract room numbers by scanning the wall areas of the map.
    * **Description**: This milestone implements a new strategy to perform OCR on the walls of the dungeon instead of the empty floor space. It will generate a "wall mask" image containing only the wall pixels and scan it for numbers.
    * **Key Tasks**:
        1.  In `analysis.py`, create the "wall mask" image by taking the unified room polygon, making it slightly larger, and then subtracting the original shape.
        2.  Run the `easyocr` engine on this new wall mask.
        3.  For each number found, associate it with the closest room polygon.
        4.  Update the corresponding `Room` object with the correct `label`.
    * **Outcome**: The tool will successfully read numbers from the wall areas and correctly label the rooms in the final JSON output.
