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
interface (`dmap.py`) that uses it.

The analysis engine employs a multi-stage pipeline to interpret the source image.
It first identifies distinct **Regions** on the map, allowing it to process complex
layouts with multiple floors or sections on a single canvas. Within each region, it
establishes a grid-based coordinate system and uses a series of greedy algorithms
to perform a tile-by-tile analysis. This high-fidelity approach identifies not
only rooms and corridors but also a rich set of specific features (columns, stairs,
altars) and environmental layers (water, rubble). Textual elements like titles or
legends are parsed and stored as metadata.

The final output is a semantically rich JSON file that can be used to generate
stylized SVG maps, including partial maps showing only user-specified rooms.

---

## 2. File System Structure

The project will be organized into a library package and a command-line script.
This structure promotes code reuse and clean separation of concerns.

`ppdf/`
├── **dmap_lib/**: The installable library package.
│   ├── `__init__.py`
│   ├── `analysis.py`: Image analysis, feature detection, and number recognition.
│   ├── `log_utils.py`: Utilities for configuring the logging system.
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
    -   Implements a multi-stage analysis pipeline.
    -   **Stage 1: Region Detection**: Identifies distinct map areas (e.g.,
        different floors) on the source image.
    -   **Stage 2: Text Analysis**: Parses textual blocks to populate metadata fields
        like the map's title and notes.
    -   **Stage 3: Grid Discovery**: Establishes a grid-based coordinate system for
        each region.
    -   **Stage 4 & 5: Room and Corridor Detection**: Uses greedy algorithms to
        identify all navigable floor space, classifying it as a "chamber" or "corridor".
    -   **Stage 6: Tile Classification**: Performs a cell-by-cell analysis to
        identify specific `Feature` objects (e.g., columns, altars, stairs) and
        `EnvironmentalLayer` objects (e.g., water, rubble).
    -   **Stage 7: Transformation**: Converts the detailed internal model into the
        final `MapData` object, which is returned.

### 3.2. `schema` Module
-   **Purpose**: To define the canonical data structures and handle serialization.
-   **Key Components**:
    -   Python `dataclasses` for the entire data model: `MapData`, `Meta`, `Region`,
        `Room`, `Door`, `Feature`, `EnvironmentalLayer`.
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
    -   Iterates through the `regions` in the `MapData` object to draw each map area.
    -   Procedurally draws all `mapObjects`, including `EnvironmentalLayer`s and
        stylized `Feature`s according to the style specification.
    -   Returns the complete SVG content as a string.

#### 3.3.1. Render Style Specification
This section defines the target visual style for the SVG output.

-   **Color Palette**:
    -   **Background**: `#EDE0CE` (A light parchment color).
    -   **Room Fill**: `#F7EEDE` (A slightly lighter parchment/off-white).
    -   **Wall & Detail Lines**: `#000000` (Black).
    -   **Shadow/Offset**: `#999999` (A dark gray for the drop shadow effect).
    -   **Glow/Underlayer**: `#C9C1B1` (A light gray-brown for a soft border effect).

-   **Layering and Effects**: The final look is achieved through three distinct layers
    rendered from bottom to top: Shadow, Glow/Underlayer, and Main.

-   **Border Hatching**:
    -   An **optional** feature, disabled by default, controlled by the `--hatching`
        CLI flag.
    -   When enabled, a series of procedurally generated, slightly randomized, short
        black lines are drawn around the exterior perimeter of all rendered polygons.

### 3.4. Supported Feature Types
This section details the features to be identified and rendered.

-   **Room Types**: `chamber`, `corridor`, `hallway`.
-   **Feature Types**: `column`, `pillar`, `statue`, `stairs`, `throne`,
    `curtain`, `drapes`, `altar`, `sarcophagus`, `chest`, `furniture`, `rubble`.
-   **Environmental Layers**: `water`, `chasm`, `difficult_terrain`.

---

## 4. Data Format (JSON Schema)

The intermediate JSON format is designed to be extensible, resolution-independent,
and support multiple map regions.

-   **Version**: 2.0.0
-   **Example** (Illustrating a map with two floors):
    ```json
    {
      "dmapVersion": "2.0.0",
      "meta": {
        "title": "The Wizard's Spire",
        "sourceImage": "wizard_spire.png",
        "legend": "Each square is 5ft.",
        "notes": "A two-story tower overlooking the sea."
      },
      "regions": [
        {
          "id": "region_floor_1",
          "label": "Ground Floor",
          "gridSizePx": 20,
          "bounds": [{"x": 10, "y": 10}, ...],
          "mapObjects": [
            {
              "id": "room_uuid_1",
              "type": "room",
              "roomType": "chamber",
              "label": "1",
              "gridVertices": [...],
              "contents": ["feature_altar_1"]
            },
            {
              "id": "door_uuid_1",
              "type": "door",
              "gridPos": {"x": 20, "y": 12},
              "connects": ["room_uuid_1", "room_uuid_2"]
            },
            {
              "id": "feature_altar_1",
              "type": "feature",
              "featureType": "altar",
              "gridVertices": [...]
            }
          ]
        },
        {
          "id": "region_floor_2",
          "label": "Upper Floor",
          "gridSizePx": 20,
          "bounds": [...],
          "mapObjects": [
            // ... rooms, doors, and features for the upper floor
          ]
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
    -   `--rooms`: A comma-separated list of room numbers to render. If omitted,
        the entire map is rendered.
    -   `--hatching`: A boolean flag to enable procedural exterior border hatching.
        Disabled by default.
    -   `--hatch-density`: A float multiplier for border hatching density.
    -   `--bg-color`: SVG background color (hex).
    -   `--wall-color`: Color for room outlines and details (hex).
    -   `--room-color`: Fill color for rooms (hex).
    -   `--line-thickness`: A float multiplier for line thickness.
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

### Phase 9: Semantic Redesign and Pipeline Refactoring

* **Milestone 19: Semantic Schema Update**
    * **Goal**: To update the core data structures to support regional maps and richer feature representation.
    * **Description**: This is the foundational step for the new architecture. It refactors the dataclasses in `dmap_lib/schema.py` to match the approved "Revision 3" of the semantic schema design.
    * **Key Tasks**:
        1.  In `schema.py`, modify `MapData` to contain a `regions: List[Region]` instead of `mapObjects`.
        2.  Create the new `Region` dataclass with a `label` and `mapObjects` list.
        3.  Expand the `Meta` dataclass to include optional `legend` and `notes` fields.
        4.  Create the new `EnvironmentalLayer` dataclass.
        5.  Modify the `Room` dataclass to include a `roomType: str` field (e.g., "chamber", "corridor").
    * **Outcome**: The `dmap_lib/schema.py` module fully reflects the new, more expressive data model, ready to be used by the redesigned analysis and rendering engines.

* **Milestone 20: Optional Hatching Implementation**
    * **Goal**: To make the exterior SVG border hatching an optional, disabled-by-default feature.
    * **Description**: This milestone implements the approved design for optional hatching, providing more control over the final visual style of the SVG output.
    * **Key Tasks**:
        1.  In `dmap.py`, add a `--hatching` boolean flag to the CLI arguments, disabled by default.
        2.  Pass the state of this flag into the `render_svg` function via the `style_options`.
        3.  In `rendering.py`, make the generation and inclusion of the hatching SVG group conditional on this flag being true.
    * **Outcome**: The `dmap` tool no longer produces hatching unless explicitly requested via the `--hatching` flag.

* **Milestone 21: Analysis Pipeline Scaffolding**
    * **Goal**: To replace the existing analysis logic with the structure of the new multi-stage pipeline.
    * **Description**: This milestone completely rewrites `dmap_lib/analysis.py`, creating the skeleton of the new analysis engine. It will contain placeholder functions for each stage but will not yet have the full implementation logic.
    * **Key Tasks**:
        1.  Define a series of placeholder functions for each of the 8 pipeline stages (e.g., `_stage1_detect_regions`, `_stage6_classify_tiles`).
        2.  Rewrite the main `analyze_image` function to call these stage functions in the correct order.
        3.  Ensure the function returns a valid, empty `MapData` object based on the new schema.
    * **Outcome**: A new `analysis.py` file with a clean, well-defined structure that is ready for the detailed implementation of each analysis stage.

* **Milestone 22: Implement Region and Metadata Analysis**
    * **Goal**: To implement the initial stages of the pipeline that identify map regions and parse textual metadata.
    * **Description**: This milestone breathes life into the pipeline scaffolding, enabling `dmap` to understand complex layouts with multiple map areas and text blocks.
    * **Key Tasks**:
        1.  Implement the logic for Stage 1 (`_stage1_detect_regions`) to find all distinct map areas on the source image.
        2.  Implement the logic for Stage 4 (`_stage4_analyze_text`) to perform OCR on non-dungeon regions.
        3.  Populate the `MapData` object with a `Region` for each dungeon area and populate the `Meta` object with any text found.
    * **Outcome**: The `analyze_image` function can now correctly parse a source image like `lost_basilica_title.jpg` and produce a `MapData` object containing correctly labeled `Region`s and populated `meta` fields.

* **Milestone 23: Implement Room and Corridor Detection**
    * **Goal**: To implement the core logic for identifying and classifying all navigable floor space within a region.
    * **Description**: This milestone focuses on identifying the primary shapes of the dungeon, distinguishing between rooms and the passages that connect them.
    * **Key Tasks**:
        1.  Implement Stage 5 (`_stage5_identify_rooms`) using a greedy algorithm to find room boundaries.
        2.  Implement Stage 7 (`_stage7_discover_corridors`) to find the connecting passages.
        3.  For each discovered space, create a `Room` object and set its `roomType` to either "chamber" or "corridor".
    * **Outcome**: The pipeline now populates each `Region`'s `mapObjects` list with `Room` objects representing the complete floor plan.

* **Milestone 24: Implement Detailed Feature Classification**
    * **Goal**: To populate the map with fine-grained features and environmental layers.
    * **Description**: This milestone implements the tile-based classification stage, which is the heart of the new pipeline's high-fidelity analysis.
    * **Key Tasks**:
        1.  Implement Stage 6 (`_stage6_classify_tiles`) to iterate through each grid cell of a room and identify its contents.
        2.  For each identified item, create the appropriate `Feature` or `EnvironmentalLayer` object.
        3.  Populate the `contents` list of the parent `Room` object with the IDs of the newly created features.
    * **Outcome**: The generated `MapData` object is now fully detailed, containing all specific features like columns, altars, rubble, and water layers.

* **Milestone 25: Update Rendering Engine for New Schema**
    * **Goal**: To make the SVG rendering engine compatible with the new region-based and feature-rich data schema.
    * **Description**: This final milestone updates the renderer to understand the new `MapData` structure, enabling it to draw complex, multi-part maps with all the newly detected details.
    * **Key Tasks**:
        1.  Modify `render_svg` to iterate through the `MapData.regions` list, potentially rendering each as a separate group.
        2.  Add specific drawing logic to render `EnvironmentalLayer` objects correctly (e.g., a semi-transparent fill with a pattern).
        3.  Expand the rendering logic to draw all the new, standardized `Feature` types.
    * **Outcome**: The `dmap.py` tool is once again fully functional, capable of analyzing a complex map and rendering a complete, detailed, and stylistically correct SVG based on the new, semantically rich schema.
