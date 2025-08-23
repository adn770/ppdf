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
-   **Confirmation and Readiness**: the assistant will confirm its understanding and
    signal its readiness.

### 0.2. Code & Document Generation
-   **Complete Code**: All source code must be complete and self-contained.
    "Self-contained" means the code must execute without errors assuming all necessary
    libraries are installed. All required `import` statements must be present.
-   **File Content Presentation**: All generated source code for a specific file **must**
    begin with a single header line in the format: `# --- path/to/your/file.ext ---`.
-   **File-Level Code Blocks**: All generated content for a specific file, whether source
    code or a markdown document, **must** be enclosed within a single, top-level
    markdown code block.
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

The analysis engine employs a sophisticated, **region-first** multi-stage pipeline.
It first isolates the primary dungeon area from the surrounding canvas and any text
blocks. Only then does it perform a **multi-pass semantic color analysis** on the
isolated region to identify the functional role of each color (e.g., `floor`,
`stroke`, `shadow`, `glow`). This allows for intelligent pre-processing and robust,
score-based wall detection that combines stroke thickness, shadow, and glow cues.

The pipeline cleanly separates the detection of the core, grid-aligned structure
from the detection of non-grid-aligned **enhancement layers**. These enhancement
features are captured using a high-precision (1/10th grid unit) coordinate system
and assigned a `z-order` to ensure correct rendering. This layered, semantic
approach allows `dmap` to produce a deeply structured and accurate representation of
complex dungeon maps.

---

## 2. File System Structure

The project is organized into a library package and a command-line script.
This structure promotes code reuse and clean separation of concerns.

`ppdf/`
├── **dmap_lib/**: The installable library package.
│   ├── `__init__.py`
│   ├── `analysis/`: The core analysis engine, split into modules.
│   │   ├── `__init__.py`
│   │   ├── `analyzer.py`: Main `MapAnalyzer` orchestrator class.
│   │   ├── `color.py`: `ColorAnalyzer` class for semantic color analysis.
│   │   ├── `context.py`: Internal dataclasses for the analysis pipeline.
│   │   ├── `features.py`: `FeatureExtractor` for high-res layers.
│   │   ├── `regions.py`: Logic for Stage 1 region and text detection.
│   │   ├── `structure.py`: `StructureAnalyzer` for grid and wall detection.
│   │   └── `transformer.py`: `MapTransformer` for final entity generation.
│   ├── `llm.py`: Ollama/LLaVA API communication and prompting.
│   ├── `log_utils.py`: Utilities for configuring the logging system.
│   ├── `prompts.py`: Constant definitions for LLM system prompts.
│   ├── `rendering/`: Procedural SVG generation logic.
│   │   ├── `__init__.py`
│   │   ├── `ascii_renderer.py`
│   │   ├── `constants.py`
│   │   ├── `geometry.py`
│   │   ├── `hatching.py`
│   │   ├── `svg_renderer.py`
│   │   └── `water.py`
│   └── `schema.py`: Data structures (dataclasses) and JSON serialization.
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
    -   Implements the full multi-stage analysis pipeline detailed in Section 4.
    -   Accepts an image path and returns the final, structured `MapData` object.
    -   Orchestrates the flow of data between specialized analyzer classes for each
        identified region.

### 3.2. `schema` Module
-   **Purpose**: To define the canonical data structures and handle serialization.
-   **Key Components**:
    -   Python `dataclasses` for the entire data model: `MapData`, `Meta`, `Region`,
        `Room`, `Door`, `Feature`, `EnvironmentalLayer`.
    -   The `properties` dictionary on `Feature` and `EnvironmentalLayer` objects is
        used to store metadata like the `z-order` for rendering.
    -   `save_json(map_data: MapData, output_path: str)`: Serializes a `MapData`
        object to a `.json` file.
    -   `load_json(input_path: str) -> MapData`: Deserializes a `.json` file into a
        `MapData` object.

### 3.3. `rendering` Module
-   **Purpose**: To handle the procedural generation of the SVG file.
-   **Key Function**: `render_svg(map_data: MapData, style_options: dict) -> str`
-   **Architecture**: The rendering engine is an object-oriented system orchestrated
    by the main `SVGRenderer` class. This class manages the overall rendering
    process, including canvas setup, style management, and the sequential drawing of
    SVG layers (shadows, glows, room fills, walls, doors, and other contents). It
    delegates specialized, procedural rendering tasks to helper classes.

#### 3.3.1. Specialized Renderers
-   **`HatchingRenderer`**: Encapsulates the logic for generating the organic,
    sketchy exterior border hatching. It uses a tile-based approach combined with
    Perlin noise to displace line cluster anchors, avoiding mechanical repetition
    for a hand-drawn aesthetic.
-   **`WaterRenderer`**: Handles the rendering of water layers. It uses a two-stage
    process to generate smooth, natural shorelines. First, the raw water polygon is
    simplified using the Douglas-Peucker algorithm to remove high-frequency noise.
    Then, a Catmull-Rom spline is used to interpolate the simplified points into a
    final, organic curve.

#### 3.3.2. Render Style Specification
-   **Color Palette**:
    -   **Background**: `#EDE0CE` (A light parchment color).
    -   **Room Fill**: `#FFFFFF` (White).
    -   **Wall & Detail Lines**: `#000000` (Black).
    -   **Shadow/Offset**: `#999999` (A dark gray for the drop shadow effect).
    -   **Glow/Underlayer**: `#C0C0C0` (A light gray for a soft border effect).

#### 3.3.3. Pre-Rendering Merge Step
-   Before rendering, the engine performs a merge pass on all `Room` objects.
-   It uses a **Disjoint Set Union (DSU)** algorithm to identify all rooms that are
    geometrically adjacent and are not separated by a `Door` object.
-   These adjacent, open rooms are merged into a single, complex `_RenderableShape`
    object. This ensures that open archways are correctly rendered and that exterior
    effects like hatching are applied to a single, unified dungeon perimeter.

---

## 4. The Analysis Pipeline

The `dmap` analysis engine is an object-oriented, **region-first** pipeline,
orchestrated by the `MapAnalyzer` class. It isolates the main
dungeon area(s) before performing a detailed, multi-pass color analysis. This
ensures that the analysis is focused only on relevant map data, leading to much
higher accuracy.

### Stage 1: Region Detection and Metadata Parsing
-   **Input**: Source Image
-   **Output**: A list of `Region` contexts, `Metadata` object.
-   **Process**: The `analyze_image` orchestrator first identifies all distinct content
    areas on the canvas using `detect_content_regions`. Areas with a high density
    of lines are classified as 'dungeon', while others are treated as 'text'. OCR is
    run on text regions by `parse_text_metadata` to extract the map's title and
    notes. The rest of the pipeline then runs on each 'dungeon' region.

### The Per-Region Pipeline (Orchestrated by `MapAnalyzer`)

For each detected 'dungeon' region, the following pipeline is executed:

### Stage 2: Multi-Pass Semantic Color Analysis
-   **Component**: `ColorAnalyzer`
-   **Input**: An isolated Dungeon Region Image
-   **Output**: `color_profile` (map of colors to semantic roles), `KMeans` model
-   **Process**: This stage performs a sophisticated, multi-pass analysis on the
    region's color palette to assign semantic meaning.
    1.  **Anchor Identification**: The `floor` color is identified as the most
        common color in the center of the region.
    2.  **Stroke Identification**: The system finds the perimeter of the `floor` to
        identify the most common non-floor color as the `stroke`.
    3.  **Border Identification**: The area adjacent to `stroke` pixels is searched
        to identify the lighter `glow` and darker `shadow` colors.
    4.  **Environmental Layer Identification**: Large patches of color inside `floor`
        areas are identified (e.g., `water`).
    5.  **Alias Classification**: Remaining colors are classified as aliases of
        their nearest primary color.

### Stage 3: Structural Image Preparation
-   **Component**: `MapAnalyzer`
-   **Input**: Dungeon Region Image, `color_profile`
-   **Output**: `structural_image`, `floor_only_image`, `stroke_only_image`
-   **Process**: The `MapAnalyzer` generates several single-purpose, temporary images
    in memory. This includes a clean, two-color image with only `stroke` on `floor`
    pixels, and binary masks for floor and stroke areas. These filtered images are
    crucial for robust geometric analysis in subsequent stages.

### Stage 4: Grid Discovery
-   **Component**: `StructureAnalyzer`
-   **Input**: `structural_image`, `room_bounds`
-   **Output**: `GridInfo` (size and offset)
-   **Process**: Heuristics are run on the `structural_image` to detect the grid size
    in pixels via peak-finding on pixel projections. The grid offset is calculated
    from the bounding boxes of the main room shapes.

### Stage 5: High-Resolution Feature & Layer Pre-Classification
-   **Component**: `FeatureExtractor`
-   **Input**: *Original* Dungeon Region Image, `color_profile`, `room_contours`
-   **Output**: `enhancement_layers` (a dictionary of high-res feature lists)
-   **Process**: This stage operates on the original region image to find features
    that do not align with the main grid.
    1.  **Heuristic Pre-classification**: It uses simple geometric heuristics to
        perform a pre-classification. For example, small circular or square shapes are
        pre-classified as `"column"`, while long, rectangular shapes are pre-classified as
        `"stairs"`. Environmental layers like water are also detected.
    2.  **Feature Consolidation**: A `_consolidate_features` pass is performed to
        intelligently merge raw feature polygons that are overlapping or very close,
        cleaning up noisy detections into single, unified features.
    3.  **Coordinate Storage**: All found items are converted into high-resolution polygons
        using a **1/10th grid unit** coordinate system and stored with a `z-order`
        attribute, ready for LLM refinement.

### Stage 6: Core Structure and Passage Detection
-   **Component**: `StructureAnalyzer`
-   **Input**: `structural_image`, `feature_cleaned_image`, `GridInfo`
-   **Output**: `tile_grid` (a grid of `_TileData` objects)
-   **Process**: This is the heart of the structural analysis.
    1.  A grid is overlaid on a `feature_cleaned_image` (the floor plan with
        features digitally removed).
    2.  Each tile is first classified as `floor` or `empty`.
    3.  **Score-Based Wall Detection**: The pipeline analyzes the boundaries between
        `floor` and `empty` grid cells. It uses a **dual area-based sampling**
        method (`_calculate_boundary_scores`), checking both the centered and exterior
        sides of a potential wall line to improve accuracy and reduce false positives
        from grid lines. A boundary is classified as a `wall` if its confidence score
        exceeds a threshold.
    4.  **Passageway Door Detection**: A dedicated pass (`_detect_passageway_doors`)
        analyzes narrow (1-tile wide) passageways. Tiles in these corridors containing
        any non-floor pixels are identified as potential doors. These are
        pre-classified with a generic `"door"` type and added to the
        `enhancement_layers` for later refinement by the LLM.
    5.  The `tile_grid` is populated with the core structure: `wall` and `floor`
        information.

### Stage 7: Transformation & Entity Generation
-   **Component**: `MapTransformer`
-   **Input**: `_RegionAnalysisContext` (containing `tile_grid`, `enhancement_layers`)
-   **Output**: The final list of `MapObject` entities for the region.
-   **Process**: This final stage transforms the intermediate `tile_grid` into the final
    schema-compliant objects.
    1.  **Floor Tile Classification**: It first classifies all `floor` tiles into either
        `chamber` or `passageway` categories based on their neighbors.
    2.  **Corridor Generation**: It creates 1x1 `Room` objects with a `corridor` roomType
        for each passageway tile.
    3.  **Chamber Merging**: It uses `shapely.unary_union` to merge all adjacent
        `chamber` tiles into complex, unified polygons, creating `Room` objects for them.
    4.  **Grid Shifting**: A `grid_shift` is applied to normalize the final coordinates.
    5.  **Feature Integration**: It extracts door information from the tile grid and
        integrates them with the high-resolution features from the `enhancement_layers`
        for a unified feature list.

---

## 5. Data Format (JSON Schema)

The intermediate JSON format is designed to be extensible and resolution-independent.

-   **Version**: 2.0.0
-   **Example** (Illustrating a z-ordered feature with 1/10th precision):
    ```json
    {
      "dmapVersion": "2.0.0",
      "meta": {
        "title": "The Wizard's Spire",
        "sourceImage": "wizard_spire.png"
      },
      "regions": [
        {
          "id": "region_floor_1",
          "label": "Ground Floor",
          "gridSizePx": 20,
          "bounds": [],
          "mapObjects": [
            {
              "id": "room_uuid_1",
              "type": "room",
              "shape": "polygon",
              "roomType": "chamber",
              "label": "1",
              "gridVertices": [{"x": 10, "y": 10}, ...],
              "contents": ["feature_column_1"]
            },
            {
              "id": "feature_column_1",
              "type": "feature",
              "featureType": "column",
              "shape": "polygon",
              "gridVertices": [{"x": 15.5, "y": 15.2}, ...],
              "properties": {
                "z-order": 1
              }
            }
          ]
        }
      ]
    }
    ```

---

## 6. Command-Line Interface (`dmap.py`)

The CLI provides a user-friendly way to interact with the `dmap_lib` library.

-   **Usage**: `python dmap.py -i <input.png> -o <output_name> [OPTIONS]`
-   **Arguments & Flags**:
    -   `--input` / `-i`: Path to the input PNG or JSON file. Required unless
        `--skip-analysis` is used.
    -   `--output` / `-o`: **(Required)** The base name for the output `.json` and
        `.svg` files.
    -   `--skip-analysis`: Skip analysis and render directly from an existing
        `<output>.json` file.
    -   `--rooms`: A comma-separated list of room numbers to render. If omitted,
        the entire map is rendered.
    -   `--hatching`: Enables and selects the style of procedural exterior border
        hatching (`sketch` or `stipple`).
    -   `--no-features`: Disables the rendering of all `Feature` objects.
    -   `--save-intermediate`: Save intermediate analysis images (e.g.,
        `pass1_layers`, `pass2_features`, `wall_detection`) to a directory for debugging.
    -   `--ascii-debug`: Render an ASCII map of the final structure for debugging.
    -   `--debug`: Enable detailed DEBUG logging for specific topics (e.g., `analysis`,
        `grid`, `render`).
-   **LLM Feature Enhancement**:
    -   `--llava`: Enable feature enhancement with LLaVA (`classifier` or `oracle`).
    -   `-M, --llm-model`: The LLaVA model to use (default: `llava:latest`).
    -   `-U, --llm-url`: The base URL of the Ollama server (default:
        `http://localhost:11434`).
    -   `--llm-temp`: Set the temperature for the LLaVA model (default: 0.3).
    -   `--llm-ctx-size`: Set the context window size for the LLaVA model (default: 8192).

---

## 7. Implementation Plan

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
    -   **Goal**: Create a single, unified polygon representing the entire map's floor
        space.
    -   **Description**: This is a critical prerequisite for advanced rendering. It
        involves merging all individual room polygons into one complex shape using a
        robust geometry library, which is essential for creating the unified exterior
        border.
    -   **Key Tasks**:
        1.  Integrate the `shapely` library into the project for computational geometry
            operations.
        2.  In `analysis.py`, convert all detected room contours into `shapely` Polygon
            objects.
        3.  Use `shapely.ops.unary_union` to merge all room polygons into a single
            geometry object.
        4.  Create a helper function to convert the unified `shapely` geometry back
            into a list of vertex contours usable by the rendering engine.
    -   **Outcome**: The analysis pipeline will produce a single, unified geometry
        representing the entire map's exterior boundary, in addition to the
        individual room objects.

-   **Milestone 13: Implement Advanced Exterior Hatching**
    -   **Goal**: Replicate the target SVG's unified, sketchy exterior hatching.
    -   **Description**: This milestone replaces the per-room hatching with a new
        algorithm that operates on the unified geometry from the previous milestone,
        providing a more professional and aesthetically pleasing result.
    -   **Key Tasks**:
        1.  In `rendering.py`, create a new `_generate_unified_hatching` function that
            accepts the unified map geometry.
        2.  Adapt the existing hatching logic (generating randomized short lines along
            an edge) to trace the `exterior` boundary of the unified shape.
        3.  Ensure the hatching is drawn correctly around complex shapes and does not
            appear in the interior of the dungeon.
    -   **Outcome**: The generated SVG will feature a single, continuous field of
        hatching around the entire dungeon complex, matching the target style.

-   **Milestone 14: Replicate Target Style and Door Rendering**
    -   **Goal**: Precisely match the visual aesthetic of the `stronghold.svg` example.
    -   **Description**: This milestone updates the default style parameters and adds
        specific drawing logic for doors to fully conform to the target style guide.
    -   **Key Tasks**:
        1.  In `rendering.py`, update the default `styles` dictionary to use the exact
            color palette and line weights from the `Render Style Specification`.
        2.  Modify the door rendering logic to draw doors as rectangles filled with
            the room color and a thin black outline.
        3.  Fine-tune the three-layer rendering effect (shadow, glow, main) to work
            seamlessly with the new style parameters.
    -   **Outcome**: The SVG output's colors, line weights, and feature appearance will
        be visually indistinguishable from the target `stronghold.svg` example.

-   **Milestone 15: Improve Door Detection Heuristics**
    -   **Goal**: Reliably detect doors in maps where they are represented as gaps in
        walls.
    -   **Description**: This milestone replaces the simple contour-based door detector
        with a more robust, geometry-based approach that can identify narrow passages
        between rooms.
    -   **Key Tasks**:
        1.  In `analysis.py`, create a new door detection function that operates *after*
            rooms have been identified.
        2.  For every pair of rooms, calculate the intersection of their slightly
            "dilated" shapes (using `shapely.buffer`).
        3.  If the intersection is a small, compact area, classify it as a door
            connection.
        4.  The centroid of this intersection area becomes the position of the detected
            `Door` object.
    -   **Outcome**: The tool can accurately detect and place doors on a wider variety
        of map styles, including those like `stronghold.png` where doors are not
        distinct objects.

### Phase 7: Observability and Refinement

* **Milestone 16: Implement Advanced Logging System**
    * **Goal**: Integrate a sophisticated, topic-based logging system to improve the
        tool's observability and ease of debugging.
    * **Description**: This comprehensive milestone introduces a new logging utility
        inspired by the `ppdf` project. It will replace all `print()` statements with
        structured, topic-based log messages, add command-line flags for controlling
        log verbosity and output, and provide a clear, color-coded format for console
        output.
    * **Key Tasks**:
        1.  Create a new `dmap_lib/log_utils.py` module to house the `setup_logging`
            function and a custom `RichLogFormatter` class.
        2.  Define the logging topics for `dmap`: `main`, `analysis`, `grid`, `ocr`,
            `geometry`, and `render`.
        3.  Add `--debug`, `--color-logs`, and `--log-file` arguments to `dmap.py`.
        4.  Call `setup_logging` at startup in `dmap.py` and replace all `print` calls
            with structured logging.
        5.  Instrument `dmap_lib/analysis.py` with detailed `log.info` and `log.debug`
            calls using topic-specific loggers.
        6.  Instrument `dmap_lib/rendering.py` with `log.info` and `log.debug` calls
            using the `dmap.render` logger.
    * **Outcome**: The `dmap` tool will have a comprehensive and configurable logging
        system. Developers can easily enable detailed debug output for specific
        components, and all output will be structured and informative, significantly
        improving the development and debugging experience.

### Phase 8: Final Polish and Heuristics

* **Milestone 17: High-Fidelity Shape Extraction**
    * **Goal**: Restore the sharp, angular geometry of the rooms by replacing the
        distorting morphological operations.
    * **Description**: This milestone replaces the "blobby" shape generation with a
        more precise "hole-filling" algorithm. It will digitally remove grid dots
        from the floor plan without distorting the room's original shape, resulting
        in a crisp final render.
    * **Key Tasks**:
        1.  In `analysis.py`, remove the `cv2.morphologyEx` call.
        2.  Change the initial `cv2.findContours` mode to `cv2.RETR_TREE` to find all
            shapes, including holes.
        3.  Create a new function to iterate through all found contours. If a contour
            is very small (like a grid dot), "paint" it over on the binary image.
        4.  Run a final `cv2.findContours` call on the cleaned image to get the
            final, crisp room polygons.
    * **Outcome**: The generated room polygons will accurately match the sharp corners
        and straight lines of the source map, eliminating the distorted appearance.

* **Milestone 18: Wall Mask Generation and OCR**
    * **Goal**: Correctly extract room numbers by scanning the wall areas of the map.
    * **Description**: This milestone implements a new strategy to perform OCR on the
        walls of the dungeon instead of the empty floor space. It will generate a
        "wall mask" image containing only the wall pixels and scan it for numbers.
    * **Key Tasks**:
        1.  In `analysis.py`, create the "wall mask" image by taking the unified room
            polygon, making it slightly larger, and then subtracting the original
            shape.
        2.  Run the `easyocr` engine on this new wall mask.
        3.  For each number found, associate it with the closest room polygon.
        4.  Update the corresponding `Room` object with the correct `label`.
    * **Outcome**: The tool will successfully read numbers from the wall areas and
        correctly label the rooms in the final JSON output.

### Phase 9: Semantic Redesign and Pipeline Refactoring

* **Milestone 19: Semantic Schema Update**
    * **Goal**: To update the core data structures to support regional maps and richer
        feature representation.
    * **Description**: This is the foundational step for the new architecture. It
        refactors the dataclasses in `dmap_lib/schema.py` to match the approved
        "Revision 3" of the semantic schema design.
    * **Key Tasks**:
        1.  In `schema.py`, modify `MapData` to contain a `regions: List[Region]`
            instead of `mapObjects`.
        2.  Create the new `Region` dataclass with a `label` and `mapObjects` list.
        3.  Expand the `Meta` dataclass to include optional `legend` and `notes`
            fields.
        4.  Create the new `EnvironmentalLayer` dataclass.
        5.  Modify the `Room` dataclass to include a `roomType: str` field (e.g.,
            "chamber", "corridor").
    * **Outcome**: The `dmap_lib/schema.py` module fully reflects the new, more
        expressive data model, ready to be used by the redesigned analysis and
        rendering engines.

* **Milestone 20: Optional Hatching Implementation**
    * **Goal**: To make the exterior SVG border hatching an optional,
        disabled-by-default feature.
    * **Description**: This milestone implements the approved design for optional
        hatching, providing more control over the final visual style of the SVG
        output.
    * **Key Tasks**:
        1.  In `dmap.py`, add a `--hatching` boolean flag to the CLI arguments,
            disabled by default.
        2.  Pass the state of this flag into the `render_svg` function via the
            `style_options`.
        3.  In `rendering.py`, make the generation and inclusion of the hatching SVG
            group conditional on this flag being true.
    * **Outcome**: The `dmap` tool no longer produces hatching unless explicitly
        requested via the `--hatching` flag.

* **Milestone 21: Analysis Pipeline Scaffolding**
    * **Goal**: To replace the existing analysis logic with the structure of the new
        multi-stage pipeline.
    * **Description**: This milestone completely rewrites `dmap_lib/analysis.py`,
        creating the skeleton of the new analysis engine. It will contain placeholder
        functions for each stage but will not yet have the full implementation logic.
    * **Key Tasks**:
        1.  Define a series of placeholder functions for each of the 8 pipeline stages
            (e.g., `_stage1_detect_regions`, `_stage6_classify_tiles`).
        2.  Rewrite the main `analyze_image` function to call these stage functions in
            the correct order.
        3.  Ensure the function returns a valid, empty `MapData` object based on the
            new schema.
    * **Outcome**: A new `analysis.py` file with a clean, well-defined structure that
        is ready for the detailed implementation of each analysis stage.

* **Milestone 22: Implement Region and Metadata Analysis**
    * **Goal**: To implement the initial stages of the pipeline that identify map
        regions and parse textual metadata.
    -   **Description**: This milestone breathes life into the pipeline scaffolding,
        enabling `dmap` to understand complex layouts with multiple map areas and text
        blocks.
    -   **Key Tasks**:
        1.  Implement the logic for Stage 1 (`_stage1_detect_regions`) to find all
            distinct map areas on the source image.
        2.  Implement the logic for Stage 4 (`_stage4_analyze_text`) to perform OCR
            on non-dungeon regions.
        3.  Populate the `MapData` object with a `Region` for each dungeon area and
            populate the `Meta` object with any text found.
    -   **Outcome**: The `analyze_image` function can now correctly parse a source image
        like `lost_basilica_title.jpg` and produce a `MapData` object containing
        correctly labeled `Region`s and populated `meta` fields.

* **Milestone 23: Implement Room and Corridor Detection**
    -   **Goal**: To implement the core logic for identifying and classifying all
        navigable floor space within a region.
    -   **Description**: This milestone focuses on identifying the primary shapes of
        the dungeon, distinguishing between rooms and the passages that connect them.
    -   **Key Tasks**:
        1.  Implement Stage 5 (`_stage5_identify_rooms`) using a greedy algorithm to
            find room boundaries.
        2.  Implement Stage 7 (`_stage7_discover_corridors`) to find the connecting
            passages.
        3.  For each discovered space, create a `Room` object and set its `roomType`
            to either "chamber" or "corridor".
    -   **Outcome**: The pipeline now populates each `Region`'s `mapObjects` list with
        `Room` objects representing the complete floor plan.

* **Milestone 24: Implement Detailed Feature Classification**
    -   **Goal**: To populate the map with fine-grained features and environmental
        layers.
    -   **Description**: This milestone implements the tile-based classification stage,
        which is the heart of the new pipeline's high-fidelity analysis.
    -   **Key Tasks**:
        1.  Implement Stage 6 (`_stage6_classify_tiles`) to iterate through each grid
            cell of a room and identify its contents.
        2.  For each identified item, create the appropriate `Feature` or
            `EnvironmentalLayer` object.
        3.  Populate the `contents` list of the parent `Room` object with the IDs of
            the newly created features.
    -   **Outcome**: The generated `MapData` object is now fully detailed, containing all
        specific features like columns, altars, rubble, and water layers.

* **Milestone 25: Update Rendering Engine for New Schema**
    -   **Goal**: To make the SVG rendering engine compatible with the new region-based
        and feature-rich data schema.
    -   **Description**: This final milestone updates the renderer to understand the new
        `MapData` structure, enabling it to draw complex, multi-part maps with all
        the newly detected details.
    -   **Key Tasks**:
        1.  Modify `render_svg` to iterate through the `MapData.regions` list,
            potentially rendering each as a separate group.
        2.  Add specific drawing logic to render `EnvironmentalLayer` objects
            correctly (e.g., a semi-transparent fill with a pattern).
        3.  Expand the rendering logic to draw all the new, standardized `Feature`
            types.
    -   **Outcome**: The `dmap.py` tool is once again fully functional, capable of
        analyzing a complex map and rendering a complete, detailed, and stylistically
        correct SVG based on the new, semantically rich schema.

### Phase 10: Debugging and Visualization

* **Milestone 26: Implement ASCII Renderer Class and CLI Flag**
    -   **Goal**: Create the foundational `ASCIIRenderer` class and the CLI flag to
        control it.
    -   **Description**: This milestone establishes the core components for the new
        debugging feature. It creates the renderer class with placeholder methods and
        adds the necessary command-line argument to `dmap.py`.
    -   **Key Tasks**:
        1.  In `dmap_lib/rendering.py`, create the new `ASCIIRenderer` class with an
            `__init__` method and empty stubs for `render_from_json`,
            `render_from_tiles`, and `get_output`.
        2.  In `dmap.py`, add the `--ascii-debug` boolean flag to the `argparse`
            configuration.
    -   **Outcome**: The project structure is updated with the new class and CLI flag,
        ready for the rendering logic to be implemented.

* **Milestone 27: Implement Post-Transformation (JSON) ASCII Rendering**
    -   **Goal**: Enable ASCII rendering of the final `MapData` JSON structure.
    -   **Description**: This milestone implements the logic to visualize the final
        output of the analysis pipeline. It reads the structured `MapData` object
        and draws an ASCII representation of its rooms, doors, and features.
    -   **Key Tasks**:
        1.  In `dmap_lib/rendering.py`, implement the `render_from_json` method. This
            includes logic for drawing polygon walls (`#`), floors (`.`), doors (`+`),
            features (`O`), and environmental layers (`~`).
        2.  In `dmap.py`, add logic to check for the `--ascii-debug` flag after
            analysis. If present, instantiate the renderer, call `render_from_json`,
            and print the result.
    -   **Outcome**: The `dmap` tool can now produce a complete ASCII map of the final
        JSON data when the `--ascii-debug` flag is used.

* **Milestone 28: Implement Pre-Transformation (Tile-Based) ASCII Rendering**
    -   **Goal**: Enable ASCII rendering of the intermediate tile-based model for deep
        debugging.
    -   **Description**: This provides a direct view into the results of the tile
        classification stage, allowing for precise debugging of the core analysis
        algorithms before they are transformed into the final entity structure.
    -   **Key Tasks**:
        1.  In `dmap_lib/analysis.py`, modify the pipeline after Stage 6 to generate
            an intermediate `tile_grid` mapping coordinates to tile types.
        2.  In `dmap_lib/rendering.py`, implement the `render_from_tiles` method to
            draw the map based on this `tile_grid`.
        3.  In `dmap_lib/analysis.py`, modify `analyze_image` to accept a debug flag.
            If true, it will call the `render_from_tiles` method and print the
            result before proceeding to Stage 7.
    -   **Outcome**: Developers can use the `--ascii-debug` flag to see a direct,
        character-based visualization of the tile classification results, greatly
        aiding in the debugging of the analysis pipeline.

### Phase 11: Advanced Analysis Engine Refactoring

* **Milestone 29: Define Internal Tile Dataclass**
    -   **Goal**: Establish the new core data structure for the tile-based analysis.
    -   **Description**: This milestone creates the new internal `Tile` dataclass
        within the analysis module. This structure is central to the new tile-edge
        wall representation and must be defined before the logic that populates it.
    -   **Key Tasks**:
        1.  In `dmap_lib/analysis.py`, define a new internal dataclass (e.g.,
            `_TileData`) with fields for `feature_type` and `north_wall`, `east_wall`,
            `south_wall`, `west_wall`.
        2.  Update the `_stage6_classify_features` function signature to reflect that
            it will now produce a grid of these new objects.
    -   **Outcome**: A new internal data model for a tile is defined, and the pipeline
        structure is updated to reflect its future use.

* **Milestone 30: Implement Tile Feature Classification**
    -   **Goal**: Rewrite the feature classification stage to identify the primary
        content of each grid tile.
    -   **Description**: This milestone implements the first half of the new Stage 6
        logic. It focuses on analyzing the area *within* each grid cell to determine
        what it contains, populating the `feature_type` of each `_TileData` object
        in the intermediate grid.
    -   **Key Tasks**:
        1.  In `_stage6_classify_features`, create a loop that iterates over every
            `(x, y)` coordinate of a region's grid.
        2.  For each coordinate, analyze the corresponding pixel area in the source
            image.
        3.  Implement heuristics to classify the area as `floor`, `column`, `pit`,
            etc., and create a `_TileData` object with the correct `feature_type`.
        4.  Store these objects in the `tile_grid`. The wall attributes will remain
            `None`.
    -   **Outcome**: Stage 6 can now produce a complete `tile_grid` where every tile
        has its primary feature correctly identified.

* **Milestone 31: Implement Tile-Edge Wall Detection**
    -   **Goal**: Enhance the classification stage to detect walls on the boundaries
        between tiles.
    -   **Description**: This milestone implements the second half of the Stage 6
        logic. It analyzes the pixel lines *between* grid cells to identify and
        classify walls, doors, and other edge-based features.
    -   **Key Tasks**:
        1.  In `_stage6_classify_features`, add logic to analyze the boundaries of
            each tile.
        2.  For each tile at `(x, y)`, analyze the pixels between it and its neighbors
            (e.g., `(x, y-1)` for the north wall).
        3.  Implement heuristics to classify these boundaries as `stone`, `door`,
            `window`, or `None` (open space).
        4.  Update the `north_wall`, `east_wall`, `south_wall`, and `west_wall`
            attributes of the `_TileData` objects in the `tile_grid`.
    -   **Outcome**: The intermediate `tile_grid` is now fully populated, containing
        both the feature type of each tile and the wall types on all its edges.

### Phase 12: Wall-Tracing Transformation and Entity Generation

* **Milestone 32: Implement Room Area Discovery and Feature Extraction**
    -   **Goal**: To identify all contiguous room areas and extract simple,
        self-contained features from the `tile_grid`.
    -   **Description**: This first step focuses on finding *what* and *where* the
        rooms and features are, without yet calculating their precise polygonal
        shape. It lays the groundwork for the more complex tracing and linking steps.
    -   **Key Tasks**:
        1.  In `_stage7_transform_to_mapdata`, implement a Flood Fill (or BFS)
            algorithm to find all unique, contiguous groups of `floor` tiles. Each
            group represents a single room area.
        2.  For each room area, create a placeholder `Room` object. Store the set of
            tile coordinates belonging to that room in a temporary property.
        3.  Create a `coord_to_room_id` map to easily find which room a given tile
            belongs to.
        4.  Implement the logic to iterate through the `tile_grid`, find all tiles
            with `feature_type = 'column'`, create `schema.Feature` objects for
            them, and use the `coord_to_room_id` map to link them to the correct
            parent room's `contents` list.
    -   **Outcome**: The `_stage7` function can now produce `Feature` objects and a
        list of placeholder `Room` objects, each associated with a set of its
        constituent tiles. The "Found 0 rooms" message will be resolved, though the
        room shapes will be inaccurate.

* **Milestone 33: Implement Perimeter Wall Tracing**
    -   **Goal**: To implement the core wall-following algorithm that generates a
        precise polygon for a single room area.
    -   **Description**: This milestone develops the most complex part of the
        transformation: the algorithm that traces the perimeter of a room by
        following the `wall` attributes in the `tile_grid`.
    -   **Key Tasks**:
        1.  Create a new helper function, e.g., `_trace_room_perimeter`, that takes a
            set of a room's tiles and the `tile_grid` as input.
        2.  Inside this function, find a consistent starting point (e.g., the
            top-leftmost tile).
        3.  Implement a "right-hand rule" wall-following algorithm. It will start at
            a corner of the starting tile and trace along connected wall segments,
            adding a vertex to a path every time the direction changes.
        4.  The algorithm must continue until it returns to the starting vertex.
        5.  Return the completed list of `gridVertices`.
    -   **Outcome**: A robust, reusable function that can accurately trace the
        perimeter of any given room area from the `tile_grid`.

* **Milestone 34: Integrate Tracing for a Single Room**
    -   **Goal**: To integrate the wall-tracing function for the *first discovered
        room only* and add extensive debugging output.
    -   **Description**: This milestone focuses on verifying the
        `_trace_room_perimeter` function's output on a single, controlled case. It
        replaces the bounding box for just the first room and adds logging to inspect
        the generated path, making the complex tracing algorithm easier to debug.
    -   **Key Tasks**:
        1.  In `_stage7_transform_to_mapdata`, modify the loop over `room_areas`. For
            the *first* area only, call the `_trace_room_perimeter` function.
        2.  Add a `DEBUG` log line to print the returned `gridVertices` path from the
            tracer.
        3.  Create a `Room` object for this first room using the traced vertices.
        4.  For all *other* room areas, continue to use the old placeholder bounding
            box logic.
    -   **Outcome**: The tool will generate a map where one room has its precise shape,
        and the rest are simple boxes. The log will contain the detailed vertex path
        for the traced room, allowing for easy debugging of the algorithm.

* **Milestone 35: Apply Wall Tracing to All Rooms**
    -   **Goal**: To apply the now-verified wall-tracing algorithm to all discovered
        room areas.
    -   **Description**: This milestone expands the integration from the previous step
        to all rooms, replacing all remaining placeholder shapes with high-fidelity
        polygons.
    -   **Key Tasks**:
        1.  In `_stage7_transform_to_mapdata`, remove the "first room only" condition
            from the loop.
        2.  Call `_trace_room_perimeter` for *every* room area found.
        3.  Create all `Room` objects using their accurately traced vertices.
        4.  Remove all temporary properties from the final `Room` objects.
    -   **Outcome**: The `dmap` tool generates `MapData` with `Room` objects that have
        precise polygons for *all* rooms. The SVG and ASCII renderings will show
        correct shapes for the entire map.

* **Milestone 36: Implement Door Extraction and Linking**
    -   **Goal**: To extract door information from the `tile_grid` and link adjacent
        rooms correctly.
    -   **Description**: This final milestone completes the transformation by
        identifying all doors and establishing the topological connections between
        the newly traced rooms.
    -   **Key Tasks**:
        1.  Create and implement the `_extract_doors_from_grid` helper function.
        2.  This function will find `'door'` attributes in the `tile_grid` and use the
            `coord_to_room_id` map to find the rooms they connect.
        3.  Create `schema.Door` objects with the correct `gridPos`, `orientation`,
            and `connects` data.
        4.  Integrate this function into `_stage7_transform_to_mapdata`.
    -   **Outcome**: The `MapData` is now fully complete, with accurate rooms,
        features, and doors that are all correctly linked.

### Phase 13: Semantic Color Analysis & Filtering

* **Milestone 37: Implement Stage 0 - Palette & Semantic Analysis**
    * **Goal**: To enable the pipeline to understand the functional role of colors in the
        source image.
    * **Description**: This milestone introduces the first stage of the new analysis
        pipeline. It implements logic to quantize the image's colors and use
        heuristics to assign semantic meaning to them, such as 'floor' or 'shadow'.
    * **Key Tasks**:
        1.  Create a new `_stage0_analyze_colors` function in `analysis.py`.
        2.  Integrate a color quantization library (e.g., scikit-learn) to derive a
            representative color palette from the source image.
        3.  Implement heuristic logic to classify these colors into roles (e.g.,
            `background`, `floor`, `stroke`, `shadow`) and return a `color_profile`.
        4.  Update the main `analyze_image` function to call this stage first.
    * **Outcome**: The pipeline can analyze a source image and produce a `color_profile`
        dictionary that guides all subsequent analysis stages.

* **Milestone 38: Implement Stage 3 - Structural Analysis Filtering**
    * **Goal**: To create a clean, two-color version of the map for robust structural
        analysis.
    * **Description**: This milestone adds the image pre-processing step. It uses the
        `color_profile` from Stage 0 to generate a new `filtered_image` in memory
        that contains only the core structural elements (walls and floor).
    * **Key Tasks**:
        1.  Create a `_stage3_create_filtered_image` helper function.
        2.  This function will iterate over the source image pixels. If a pixel's color
            is mapped to `stroke` in the `color_profile`, it is preserved. All other
            pixels are changed to the `floor` color.
        3.  Update the main `analyze_image` function to generate this `filtered_image`
            and pass it to the stages responsible for structural analysis.
    * **Outcome**: The analysis pipeline now produces a clean `filtered_image`, free
        of shadows and other patterns, for use in wall and floor detection.

### Phase 14: High-Resolution Feature Layer Implementation

* **Milestone 39: Refactor Intermediate Data Model**
    * **Goal**: To refactor the internal data model to separate the core structure
        from high-resolution, non-grid-aligned features.
    * **Description**: This milestone introduces the `RegionAnalysisContext` object and
        simplifies the `_TileData` grid. This prepares the pipeline for the new
        enhancement layer system.
    * **Key Tasks**:
        1.  In `analysis.py`, create a new internal `RegionAnalysisContext` dataclass
            to hold `tile_grid`, `enhancement_layers`, and other stage data.
        2.  Modify the `_stage6_classify_features` logic to no longer detect `column`
            features. The `tile_grid` will now only contain `floor`, `wall`, and
            `door` information.
        3.  Temporarily remove the `_extract_features` logic from Stage 7; it will
            be replaced by the new enhancement layer processing.
    * **Outcome**: The internal data model is successfully refactored. The `tile_grid`
        is now responsible only for the map's core structure.

* **Milestone 40: Implement High-Resolution Feature Detection (Columns)**
    * **Goal**: To re-implement column detection using the new high-resolution
        enhancement layer system.
    * **Description**: This milestone adds the first part of the new Stage 5 logic.
        It scans the original image for column-like shapes and stores them as
        high-precision polygons.
    * **Key Tasks**:
        1.  Create a new `_stage5_detect_enhancement_features` function.
        2.  Using the *original* image, find contours inside room areas that match
            the `stroke` color and have simple geometry (e.g., small circles/squares).
        3.  Convert these contours to polygons, scale their vertices to the 1/10th
            grid unit system, and assign a `z-order` of 1.
        4.  Store the resulting feature data in the `enhancement_layers` dictionary
            within the `RegionAnalysisContext`.
    * **Outcome**: The pipeline can detect columns as non-grid-aligned,
        high-resolution features and store them separately from the core map structure.

* **Milestone 41: Implement High-Resolution Layer Detection (Water)**
    * **Goal**: To implement the detection of environmental layers using the new
        high-resolution system.
    * **Description**: This milestone extends the Stage 5 logic to identify areas
        with specific fill patterns, such as water, and store them as high-precision
        polygons.
    * **Key Tasks**:
        1.  Extend the `_stage5_detect_enhancement_features` function.
        2.  Add logic to scan the *original* image for contiguous areas of the
            `water_pattern` color defined in the `color_profile`.
        3.  Convert these areas to polygons, scale them to the 1/10th grid unit
            system, assign a `z-order` of 0, and store them in the
            `enhancement_layers` dictionary.
    * **Outcome**: The pipeline can now detect and represent environmental layers like
        water with high precision, assigning them a base z-order.

* **Milestone 42: Integrate Enhancement Layers into Transformation**
    * **Goal**: To update the final transformation stage to process and include data
        from the `enhancement_layers`.
    * **Description**: This milestone makes the high-resolution features part of the
        final output. It modifies Stage 7 to convert the enhancement layer data into
        the final schema objects.
    * **Key Tasks**:
        1.  Modify `_stage7_transform_to_mapdata` to accept the full
            `RegionAnalysisContext`.
        2.  After creating rooms and doors from the `tile_grid`, iterate through the
            features in the `enhancement_layers`.
        3.  For each feature, scale its high-resolution vertices back to the standard
            grid system.
        4.  Create the appropriate `schema.Feature` or `schema.EnvironmentalLayer`
            object, storing its `z-order` in the `properties` field.
        5.  Link the new objects to their parent rooms.
    * **Outcome**: The final `MapData` object now correctly includes all features and
        layers detected by the high-resolution system.

### Phase 15: Advanced Wall Detection & Rendering

* **Milestone 43: Implement Advanced Wall Detection**
    * **Goal**: To make wall detection more robust by using a combination of color,
        thickness, and shadow information.
    * **Description**: This milestone replaces the simple wall detection heuristic with a
        more advanced method that is less likely to be confused by thin grid lines or
        other non-wall details.
    * **Key Tasks**:
        1.  Modify the wall detection logic in `_stage6_classify_features`.
        2.  When analyzing a boundary between tiles, the new logic will check for a
            line of `stroke` color in the `filtered_image` that exceeds a minimum
            thickness threshold.
        3.  It will then cross-reference with the *original* image to verify that
            `shadow` colored pixels are adjacent to the line on its exterior side.
        4.  Only if both conditions are met is the boundary classified as a `wall`.
    * **Outcome**: Wall detection is significantly more accurate and robust.

* **Milestone 44: Implement Z-Order Rendering**
    * **Goal**: To ensure the final SVG output correctly layers all visual elements
        based on their `z-order`.
    * **Description**: This milestone updates the rendering engine to read and respect
        the `z-order` property assigned to features and layers during analysis.
    * **Key Tasks**:
        1.  In `dmap_lib/rendering.py`, modify the `render_svg` function.
        2.  Before rendering the contents of a room, sort the associated `Feature`
            and `EnvironmentalLayer` objects based on the `z-order` value stored
            in their `properties` dictionary.
        3.  Render the objects in ascending order of their `z-order`.
    * **Outcome**: The final SVG correctly layers all map elements, for example,
        drawing a column on top of a water layer, as intended by the design.

### Phase 16: Granular Region-First Pipeline Refactoring

* **Milestone 45: Encapsulate the Core Pipeline**
    * **Goal**: To perform a pure refactoring by renaming the main analysis function.
    * **Description**: This is a preparatory, zero-risk step. We will rename
        `analyze_image` to better reflect its future role as a pipeline that runs on
        a single, pre-defined image area. All calls to this function will be updated.
    * **Key Tasks**:
        1.  Rename the `analyze_image` function in `analysis.py` to
            `_run_analysis_on_region`.
        2.  Update the call site in `dmap.py` to use the new function name.
    * **Outcome**: The code is functionally identical, but the main analysis logic is
        now clearly named and encapsulated.

* **Milestone 46: Introduce the Orchestrator Scaffolding**
    * **Goal**: To create the new top-level `analyze_image` function as a simple
        pass-through.
    * **Description**: This milestone introduces the new orchestrator function that will
        eventually manage the region loop. For now, it will simply load the image
        and immediately delegate to the encapsulated pipeline function from the
        previous milestone.
    * **Key Tasks**:
        1.  Create a new `analyze_image` function in `analysis.py`.
        2.  This function will accept the `image_path` and load the `img`.
        3.  It will immediately call `_run_analysis_on_region`, passing the `img` to it.
        4.  Update the call site in `dmap.py` to point to this new `analyze_image`
            function.
    * **Outcome**: The new orchestrator is wired in place. The program's behavior
        remains unchanged, but the structural scaffolding is now present.

* **Milestone 47: Implement and Verify Region Detection**
    * **Goal**: To activate region-detection logic and log its output without altering
        the pipeline flow.
    * **Description**: In this step, we will execute the region-finding stages.
        However, instead of acting on the results, we will simply log them. This
        allows us to verify that region detection is working correctly before we
        start feeding regions into the pipeline.
    * **Key Tasks**:
        1.  In the `analyze_image` orchestrator, call `_stage1_detect_regions`.
        2.  Add a `log.debug` statement to report the number of regions found.
        3.  The orchestrator will still pass the original, full `img` to
            `_run_analysis_on_region`.
    * **Outcome**: The console log will now show that regions are being detected. The
        core analysis pipeline is still unaffected and runs only once on the full
        image.

* **Milestone 48: Process a Single Cropped Region**
    * **Goal**: To make the pipeline process a single, automatically cropped dungeon
        region for the first time.
    * **Description**: This is the first functional change to the pipeline's input.
        The orchestrator will now select the largest detected dungeon region, crop
        the source image to its bounds, and pass only that cropped image to the
        pipeline runner.
    * **Key Tasks**:
        1.  In `analyze_image`, get the list of dungeon regions from the detection
            stage.
        2.  Identify the largest region based on its contour.
        3.  Create a new, cropped `region_img` from the source `img` using the
            region's bounding box.
        4.  Pass this `region_img` to the `_run_analysis_on_region` function.
    * **Outcome**: The tool now analyzes only the main dungeon area, ignoring all text
        and secondary regions. This verifies that the pipeline can run successfully on
        a cropped image.

* **Milestone 49: Activate the Multi-Region Processing Loop**
    * **Goal**: To wrap the single-region logic in a loop to process all detected
        dungeon areas.
    * **Description**: This milestone expands the logic from the previous step to
        handle all dungeon regions. It will loop through each detected region, run
        the pipeline, and aggregate the results into a single `MapData` object.
    * **Key Tasks**:
        1.  In `analyze_image`, create a loop to iterate over all detected dungeon
            regions.
        2.  Move the cropping and pipeline-calling logic inside this loop.
        3.  Implement logic to collect the results from each pipeline run and append
            them to the final `MapData` object's list of `regions`.
    * **Outcome**: The tool now correctly analyzes maps with multiple, separate dungeon
        areas. The analysis is still inefficient but is now structurally complete.

* **Milestone 50: Relocate the Color Analysis Call**
    * **Goal**: To move the color analysis function call from the global scope into
        the per-region pipeline.
    * **Description**: This is a critical step to make the analysis context-aware. We
        will move the function call that performs the color analysis so that it
        executes inside the loop for each region.
    * **Key Tasks**:
        1.  Cut the `_stage0_analyze_colors` call from the `analyze_image` orchestrator.
        2.  Paste the call at the beginning of the `_run_analysis_on_region` function.
    * **Outcome**: Color analysis is now performed for each region. It is more
        accurate but is now called `_stage0` inside a per-region context, which is
        semantically incorrect and will be fixed next.

* **Milestone 51: Finalize the Per-Region Color Analysis**
    * **Goal**: To semantically finalize the color analysis stage, making it truly
        per-region.
    * **Description**: This final milestone cleans up the color analysis stage. We will
        rename the function to match its new role in the pipeline and remove the
        now-obsolete `background` detection heuristic, which is a source of errors
        when run on cropped images.
    * **Key Tasks**:
        1.  Rename `_stage0_analyze_colors` to `_stage2_analyze_region_colors`.
        2.  Update its call site inside `_run_analysis_on_region`.
        3.  Modify the function's internal logic to remove the code that identifies a
            `background` color role.
    * **Outcome**: The refactoring is complete. The pipeline is now a true region-first
        system, and the color analysis is more robust, accurate, and correctly
        implemented.

### Phase 17: Structural Scaffolding

-   **Milestone 52: Create Class Skeletons**
    -   **Goal**: To introduce the new class structure into `dmap_lib/analysis.py`
        without implementing any new logic.
    -   **Description**: This initial step creates the empty class definitions for
        each major component of the analysis pipeline. This provides the
        structural foundation for all subsequent refactoring work.
    -   **Key Tasks**:
        1.  Create the empty `ColorAnalyzer`, `StructureAnalyzer`, `FeatureExtractor`,
            and `MapTransformer` classes.
        2.  Create the main `MapAnalyzer` orchestrator class with placeholder methods.
        3.  The existing free-standing functions will remain untouched.
    -   **Outcome**: The `analysis.py` file will contain the new, empty class
        definitions alongside the existing functions, ready for the logic to be moved.

-   **Milestone 53: Lift and Shift Functions into Methods**
    -   **Goal**: To move the existing analysis functions into the new classes as
        methods with minimal changes.
    -   **Description**: This is a pure "lift and shift" operation. Each global
        function will be moved into the most appropriate class and converted to a
        method. This step isolates the logic within its future home without yet
        refactoring its internal workings.
    -   **Key Tasks**:
        1.  Move color analysis logic into the `ColorAnalyzer` class.
        2.  Move grid discovery and feature classification logic into the
            `StructureAnalyzer` class.
        3.  Move enhancement detection logic into the `FeatureExtractor` class.
        4.  Move transformation logic into the `MapTransformer` class.
        5.  Update the main `_run_analysis_on_region` function to instantiate these
            new classes and call their methods, replacing the direct function calls.
    -   **Outcome**: The code is now structured within classes, but the internal logic
        and the overall data flow remain unchanged. The application should function
        exactly as before.

### Phase 18: Implementation Refactoring

-   **Milestone 54: Refactor `ColorAnalyzer`**
    -   **Goal**: To refactor the internal implementation of the `ColorAnalyzer`
        class for clarity and encapsulation.
    -   **Description**: This milestone focuses on cleaning up the first stage of the
        pipeline. The methods within `ColorAnalyzer` will be reviewed to ensure they
        are self-contained.
    -   **Key Tasks**:
        1.  Refactor the `analyze` method of `ColorAnalyzer` to be a pure function
            that accepts an image and returns a `color_profile`.
        2.  Ensure no global state is being used within the class.
    -   **Outcome**: A fully encapsulated `ColorAnalyzer` class that is easier to test
        and understand.

-   **Milestone 55: Refactor `StructureAnalyzer`**
    -   **Goal**: To refactor the internal implementation of the `StructureAnalyzer`.
    -   **Description**: We will break down the large classification method into
        smaller, more manageable helper methods within the `StructureAnalyzer`
        class, improving its readability.
    -   **Key Tasks**:
        1.  Create private helper methods for tasks like boundary classification and
            wall scoring.
        2.  Ensure the main `analyze` method of the class clearly shows the sequence
            of operations.
    -   **Outcome**: A refactored `StructureAnalyzer` class where the complex logic is
        broken down into smaller, well-named methods.

-   **Milestone 56: Refactor `FeatureExtractor` and `MapTransformer`**
    -   **Goal**: To refactor the internal implementations of the final two stages.
    -   **Description**: This milestone cleans up the remaining classes, ensuring they
        follow the same principles of encapsulation and clarity as the others.
    -   **Key Tasks**:
        1.  Refactor the `FeatureExtractor` class to ensure its `extract` method is
            a pure function.
        2.  Refactor the `MapTransformer` class, cleaning up the wall-tracing and
            door-linking logic into clearer helper methods.
    -   **Outcome**: The entire analysis pipeline is now composed of fully refactored,
        single-responsibility classes.

### Phase 19: Final Integration and Cleanup

-   **Milestone 57: Finalize Orchestrator and Remove Old Functions**
    -   **Goal**: To clean up `analysis.py` by finalizing the orchestrator and removing
        all the old, now-redundant, free-standing functions.
    -   **Description**: This final step completes the refactoring. The `MapAnalyzer`
        class will be finalized, and all the old procedural code will be deleted,
        leaving only the new, clean object-oriented structure.
    -   **Key Tasks**:
        1.  Review the `MapAnalyzer` class and its main `analyze_region` method to
            ensure the data flow between components is correct and efficient.
        2.  Delete all the old `_stageX...` and helper functions from the module.
        3.  Update the top-level `analyze_image` function to be a clean, simple
            entry point that uses the `MapAnalyzer`.
    -   **Outcome**: The `dmap_lib/analysis.py` file now contains only the new,
        refactored class-based implementation. The codebase is significantly
        cleaner, more organized, and easier to maintain.

### Phase 20: LLaVA Integration for Feature Enhancement

-   **Milestone 58: API and CLI Scaffolding**
    -   **Goal**: To create the API communication layer and integrate the new CLI
        arguments.
    -   **Description**: This milestone establishes the foundational components for
        communicating with an Ollama server and exposes the necessary controls to the
        user through the command-line interface.
    -   **Key Tasks**:
        1.  In `dmap.py`, add the `--llava`, `-M/--llm-model`, and `-U/--llm-url`
            arguments using `argparse`.
        2.  Create the new `dmap_lib/llm.py` file.
        3.  Implement the `query_llava` function, including image encoding, request
            logic, and robust error handling.
        4.  In `dmap_lib/log_utils.py`, add a new logging topic for `llm` to
            `PROJECT_TOPICS`.
    -   **Outcome**: A runnable CLI that accepts the new arguments and a functional API
        module capable of sending an image and prompt to an Ollama server.

-   **Milestone 59: Create LLaVA Enhancer Class Skeleton**
    -   **Goal**: To introduce the new `LLaVAFeatureEnhancer` class and its prompt into
        the codebase without functional logic.
    -   **Description**: This milestone creates the structural placeholder for the LLaVA
        logic and defines the prompt that will be used for classification, ensuring the
        core components are in place before adding complex behavior.
    -   **Key Tasks**:
        1.  In `dmap_lib/analysis/features.py`, create the new `LLaVAFeatureEnhancer`
            class.
        2.  Add an empty `enhance` method to the class.
        3.  Create a new `dmap_lib/prompts.py` module to define the
            `LLAVA_PROMPT_CLASSIFIER` constant containing the text prompt for the LLM.
    -   **Outcome**: The new `LLaVAFeatureEnhancer` class and its associated prompt are
        defined and importable, ready for integration into the pipeline.

-   **Milestone 60: Integrate Enhancer into Analysis Pipeline**
    -   **Goal**: To modify the main analysis pipeline to conditionally call the new
        enhancer.
    -   **Description**: This step wires the new enhancer into the `MapAnalyzer`. The call
        will be guarded by the new `--llava` CLI flag, but for now, the call will not
        perform any action. This verifies the data flow and control logic.
    -   **Key Tasks**:
        1.  In `dmap.py`, pass the `llava_mode`, `llm_url`, and `llm_model` arguments
            into the `analyze_image` function.
        2.  In `dmap_lib/analysis/analyzer.py`, update `analyze_image` and
            `MapAnalyzer.analyze_region` to accept the new LLM parameters.
        3.  In `analyze_region`, after the `FeatureExtractor` runs, add a conditional
            block that checks if `llava_mode` is 'classifier'.
        4.  Inside the block, instantiate `LLaVAFeatureEnhancer` and call its empty
            `enhance` method, logging a debug message indicating it was called.
    -   **Outcome**: The `dmap` tool, when run with `--llava classifier`, will correctly
        enter the enhancement step and log that the process was initiated, though no
        features will be modified.

-   **Milestone 61: Implement Feature Image Cropping**
    -   **Goal**: To implement the logic for extracting individual feature images from
        the main region image.
    -   **Description**: This milestone focuses on the computer vision task of cropping
        the precise pixel data for each feature detected by the `FeatureExtractor`. This
        is a critical prerequisite for sending targeted images to the LLM.
    -   **Key Tasks**:
        1.  In the `LLaVAFeatureEnhancer.enhance` method, iterate through the features
            passed in the `enhancement_layers`.
        2.  For each feature, calculate its bounding box from its `high_res_vertices`.
        3.  Use the bounding box to crop the feature's image from the
            `original_region_img`.
        4.  For debugging, add a `log.debug` statement to report the dimensions of each
            cropped image.
    -   **Outcome**: The enhancer can now isolate the image data for every detected
        feature.

-   **Milestone 62: Implement and Verify Single LLaVA API Call**
    -   **Goal**: To send one cropped feature image to the LLaVA API and log the raw
        response.
    -   **Description**: This milestone connects the pipeline to the Ollama API for the
        first time in a controlled manner. It will process only the *first* feature it
        finds, send it for classification, and log the output without attempting to
        parse or merge it. This isolates the API call for easy debugging.
    -   **Key Tasks**:
        1.  In `LLaVAFeatureEnhancer.enhance`, modify the feature loop to process only
            the first feature and then break.
        2.  Call the `llm.query_llava` function with the cropped image and the
            classifier prompt.
        3.  Add a `log_llm.debug` statement to print the raw JSON or error message
            returned from the API call.
    -   **Outcome**: The tool, when run, will send a single feature to the LLaVA model
        and print the model's raw classification response to the debug log, verifying
        the end-to-end API connection.

-   **Milestone 63: Implement Full Feature Enhancement and Merging**
    -   **Goal**: To process all features through LLaVA, parse the results, and merge
        them back into the final map data.
    -   **Description**: This final milestone fully enables the feature enhancement
        pipeline. It removes the single-feature limitation, adds JSON parsing for the
        LLM's response, and updates the feature objects with the new, more descriptive
        `featureType`.
    -   **Key Tasks**:
        1.  In `LLaVAFeatureEnhancer.enhance`, remove the `break` to allow the loop to
            process all features.
        2.  Add logic to parse the JSON response from `query_llava`.
        3.  If a valid `featureType` is returned by the LLM, update the corresponding
            feature dictionary in the `enhancement_layers` with the new type.
        4.  Ensure the method returns the modified `enhancement_layers` object.
        5.  In `MapAnalyzer`, correctly receive and use the returned, modified context
            for the final transformation stage.
    -   **Outcome**: When `--llava classifier` is used, the final JSON and SVG output
        will contain features with semantically rich types (e.g., "stairs", "altar") as
        classified by the LLaVA model.

### Phase 21: LLaVA Oracle Mode Enhancement

-   **Milestone 64: Add Oracle Mode to CLI and Prompts**
    -   **Goal**: To prepare the project for the oracle mode implementation by adding
        the necessary CLI options and the new, more complex prompt.
    -   **Description**: This milestone updates the user-facing controls and defines
        the sophisticated prompt required to instruct the LLM to perform a full-region
        analysis.
    -   **Key Tasks**:
        1.  In `dmap.py`, update the `--llava` argument's choices to include `oracle`.
        2.  In `dmap_lib/prompts.py`, create the new `LLAVA_PROMPT_ORACLE` constant.
            This prompt will ask the LLM to return a JSON object with a list of all
            features it identifies, including their `featureType` and bounding box.
    -   **Outcome**: The CLI accepts `--llava oracle`, and the new prompt is available
        for use by the enhancer.

-   **Milestone 65: Implement Oracle Mode API Call**
    -   **Goal**: To implement the logic for sending the entire region image to the
        LLaVA model.
    -   **Description**: This step adds the 'oracle' branch to the `LLaVAFeatureEnhancer`.
        It will send the full image of a dungeon region for analysis and log the raw
        response for debugging.
    -   **Key Tasks**:
        1.  In `dmap_lib/analysis/features.py`, add logic to the `LLaVAFeatureEnhancer`
            to handle the `oracle` mode.
        2.  This logic will call `llm.query_llava` using the *entire*
            `original_region_img` and the new `LLAVA_PROMPT_ORACLE`.
        3.  Add a `log_llm.debug` statement to print the raw JSON response from the
            model.
    -   **Outcome**: When run with `--llava oracle`, the tool sends the full region
        image to the LLM and logs the complete, unprocessed response, verifying the API
        call.

-   **Milestone 66: Implement Oracle Response Parsing and Reconciliation**
    -   **Goal**: To parse the LLM's response and merge its findings with the
        geometrically detected features.
    -   **Description**: This is the core of the oracle mode. It implements the logic
        to interpret the LLM's JSON output and reconciles it with the
        `FeatureExtractor`'s baseline results. This ensures the semantic richness of
        the LLM without losing the geometric precision of the original extractor.
    -   **Key Tasks**:
        1.  In `LLaVAFeatureEnhancer.enhance`, add logic to parse the JSON list of
            features returned by the oracle prompt.
        2.  For each feature identified by the LLM, find the closest corresponding
            feature (by centroid distance) in the `enhancement_layers`.
        3.  If a close match is found, update the geometrically-sound feature's
            `featureType` with the semantically richer one from the LLM.
    -   **Outcome**: The `--llava oracle` mode produces a final `MapData` object that
        combines the geometric accuracy of the `FeatureExtractor` with the advanced
        semantic classification from the LLaVA oracle pass.

### Phase 22: LLM-First Feature Classification Refactoring

-   **Milestone 67: Remove CV-based Heuristics**
    -   **Goal**: To eliminate the complex CV-based heuristics for identifying specific
        door types and stairs.
    -   **Description**: This milestone streamlines the `StructureAnalyzer` by removing
        the brittle, pattern-matching logic that attempted to classify features
        based on their visual signature. This logic will be replaced by a simpler
        geometric pre-classification followed by LLaVA-based refinement.
    -   **Key Tasks**:
        1.  In `dmap_lib/analysis/structure.py`, delete the `_is_stair_tile_fft` and
            `_classify_door_type` methods.
        2.  In the `classify_features` method, remove the call to `_is_stair_tile_fft`.
        3.  Update the `_detect_passageway_doors` method to use a simple pixel count
            (`cv2.countNonZero`) to identify a passageway as a generic `"door"`,
            removing the call to `_classify_door_type`.
    -   **Outcome**: The `StructureAnalyzer` is simplified to focus on core structure
        (walls, floors) and identifying potential feature locations (passageways)
        without attempting to classify their specific type.

-   **Milestone 68: Implement Stair Pre-classification Heuristic**
    -   **Goal**: To add a simple, geometry-based heuristic to pre-classify potential
        staircases.
    -   **Description**: This milestone adds a pre-classification step to the
        `FeatureExtractor`, allowing it to identify shapes that are likely to be
        stairs based on their geometry, preparing them for LLaVA refinement.
    -   **Key Tasks**:
        1.  In `dmap_lib/analysis/features.py`, update the `extract` method to find
            contours with a high aspect ratio that are roughly rectangular.
        2.  Pre-classify these identified contours with the `featureType` of `"stairs"`.
    -   **Outcome**: The pipeline can now geometrically identify and pre-classify both
        columns and potential staircases before they are sent to the LLM.

-   **Milestone 69: Expand LLaVA Prompts for Refinement**
    -   **Goal**: To update the LLaVA prompts to include the full taxonomy of features
        it is now responsible for classifying.
    -   **Description**: This final step ensures the LLM is aware of the new feature
        types it needs to distinguish between.
    -   **Key Tasks**:
        1.  In `dmap_lib/prompts.py`, update both the `LLAVA_PROMPT_CLASSIFIER` and
            `LLAVA_PROMPT_ORACLE` constants.
        2.  Add `"stairs"`, `"door"`, `"secret_door"`, `"iron_bar_door"`, and
            `"double_door"` to the list of possible `feature_type` values in both
            prompts.
    -   **Outcome**: The LLaVA model will be correctly prompted, enabling it to
        accurately refine the generic "door" and "stairs" pre-classifications into
        their final, specific types.

### Phase 23: Rendering Engine Refactoring
* **Milestone 70: Modularize Rendering Logic**
    * **Goal**: To refactor the monolithic `rendering.py` module into a structured
        package of single-responsibility modules.
    * **Description**: This milestone improves maintainability by separating concerns.
        The core rendering orchestration, geometric calculations, and specialized
        procedural generation for features like water and hatching are moved into their
        own dedicated files.
    * **Key Tasks**:
        1.  Create the `dmap_lib/rendering/` package directory.
        2.  Create the `svg_renderer.py`, `geometry.py`, `hatching.py`, `water.py`, and
            `constants.py` modules.
        3.  Move the main `render_svg` orchestration logic into an `SVGRenderer` class
            within `svg_renderer.py`.
        4.  Relocate geometric helper functions and the `_RenderableShape` class to
            `geometry.py`.
        5.  Isolate all hatching and water generation logic into `HatchingRenderer` and
            `WaterRenderer` classes in their respective modules.
    * **Outcome**: A clean, organized rendering package where each module has a clear and
        distinct purpose, making the system easier to extend and debug.

* **Milestone 71: Implement Class-Based Rendering Orchestration**
    * **Goal**: To convert the rendering pipeline from a procedural function to an
        object-oriented process orchestrated by the `SVGRenderer` class.
    * **Description**: This milestone finalizes the refactoring by implementing a
        class-based approach. The `SVGRenderer` becomes the central point for
        managing styles, orchestrating the drawing of layers, and delegating
        specialized tasks to helper classes.
    * **Key Tasks**:
        1.  Implement the `SVGRenderer` class to manage the rendering lifecycle,
            including style initialization, canvas setup, and layer ordering.
        2.  Instantiate `HatchingRenderer` and `WaterRenderer` within the
            `SVGRenderer` to handle their specific tasks.
        3.  Update the main `dmap.py` script to instantiate and call the
            `SVGRenderer` class instead of the old procedural function.
    * **Outcome**: A fully object-oriented rendering engine that is more robust,
        extensible, and aligns better with the design of the analysis pipeline.

### Phase 24: Advanced Rendering and Bug Fixes
* **Milestone 72: Implement Catmull-Rom Spline Algorithm**
    * **Goal**: To create the core mathematical implementation for the spline generation.
    * **Description**: This milestone replaces the Chaikin smoothing algorithm with a
        Catmull-Rom spline interpolation to create more fluid and organic curves for
        features like water shorelines.
    * **Key Tasks**:
        1.  In `dmap_lib/rendering/water.py`, create a new private helper function
            `_catmull_rom_spline`.
        2.  This function will take a list of points, a tension value, and the number
            of points to generate between each control point.
        3.  Implement the Catmull-Rom formula to calculate the interpolated points.
        4.  Replace the existing `_chaikin_smoothing` function with this new
            implementation in the `_create_curvy_path` helper.
    * **Outcome**: The rendering engine can now produce higher-quality, smoother curves,
        significantly improving the visual appeal of natural features.

* **Milestone 73: Integrate Polygon Simplification**
    * **Goal**: To add a preparatory simplification step to the water rendering
        pipeline to prevent visual artifacts.
    * **Description**: This milestone introduces a crucial pre-processing step for the
        Catmull-Rom spline. By simplifying the source polygon before interpolation,
        we can avoid self-intersections, loops, and other artifacts that can occur
        when applying splines to complex, noisy geometries.
    * **Key Tasks**:
        1.  In `WaterRenderer.render`, before the polygon is passed to the spline
            function, apply the `polygon.simplify()` method from the `shapely`
            library.
        2.  Add a new style option, `water_simplification_factor`, to the
            `_initialize_styles` method in `svg_renderer.py` to make the
            simplification tolerance configurable.
        3.  Update the design document to reflect the new Shapely simplification +
            Catmull-Rom spline process.
    * **Outcome**: The water rendering pipeline is now more robust and produces
        consistently high-quality results without rendering artifacts.

* **Milestone 74: Implement Water Layer Clipping**
    * **Goal**: To prevent the procedural water effect from rendering outside the
        bounds of its containing room.
    * **Description**: This milestone introduces a clipping step into the water
        rendering process. The parent room's polygon is used to perform a geometric
        intersection with the water layer's polygon, ensuring the final smoothed
        path is perfectly contained.
    * **Key Tasks**:
        1.  Update the `WaterRenderer.render` method to accept an optional
            `clip_polygon`.
        2.  Implement the `intersection` logic within the `WaterRenderer`.
        3.  Modify the `SVGRenderer` to identify the parent room of each water layer
            and pass its polygon to the `WaterRenderer`.
    * **Outcome**: The water effect is correctly clipped to the room's interior,
        preventing any visual "spilling" and producing a cleaner, more accurate map.

* **Milestone 75: Fix Content-to-Room Linking Logic**
    * **Goal**: To correctly associate features and layers with their parent rooms
        *after* rooms have been merged.
    * **Description**: This milestone fixes a critical logical flaw where content was
        linked to rooms before the pre-rendering merge pass. This caused content in
        merged areas to be orphaned and not rendered correctly. The fix moves the
        linking logic into the renderer, ensuring it runs on the final, merged room
        shapes.
    * **Key Tasks**:
        1.  Remove the content-linking logic from `dmap_lib/analysis/transformer.py`.
        2.  In `dmap_lib/rendering/svg_renderer.py`, implement a new step after room
            merging that correctly associates each feature and layer with its final
            parent `_RenderableShape`.
        3.  Ensure the `contents` list of each `_RenderableShape` is populated
            correctly before the main rendering loop.
    * **Outcome**: All features and layers, including water, are now correctly
        associated with their final parent rooms, enabling accurate clipping and
        rendering.
