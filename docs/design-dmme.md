# Project: DMme (AI Dungeon Master Engine)

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

DMme is an AI-powered engine for playing tabletop role-playing games (TTRPGs).
The project is an evolution and extension of **`ppdf`**, a pre-existing, advanced
tool for PDF structure analysis and reformatting. The full system adds a game
driver (`dmme`) to leverage the knowledge bases created by `ppdf`.

The system uses a Retrieval-Augmented Generation (RAG) approach, drawing from
four distinct types of knowledge sources to ground the Large Language Model (LLM).
All components are designed to run locally using Ollama.

The application is architected around three distinct, top-level views: **Game**,
**Library**, and **Party**. This organizes management tasks into dedicated hubs,
streamlines workflows, and creates a more professional, application-like user
experience.

### 1.1. Knowledge Source Types

The RAG system is built upon four types of knowledge bases:

1.  **Rules:** Contains the core mechanics of a specific TTRPG system (e.g., D&D 5e).
2.  **Setting:** Contains the lore, locations, and characters of a game world
    (e.g., Forgotten Realms), independent of a specific adventure.
3.  **Module:** A specific, pre-written adventure, which may optionally be linked
    to a particular `Setting`.
4.  **Adapter:** A reusable knowledge base that translates mechanics from a source
    rule system to a target rule system (e.g., D&D 5e to Pathfinder 2e).

### 1.2. Game Modes

`dmme` supports two primary modes of play, selectable via a "New Game" wizard:

1.  **Adventure Module Mode:** The standard playstyle where the user selects a
    `Rules` system and a specific `Module` to play through.
2.  **Freestyle Mode:** A sandbox mode where the user selects a `Rules` system and
    a `Setting`. The LLM generates a unique adventure on the fly, using the
    `Setting` for context and potentially drawing inspiration from the entire
    corpus of available modules.

### 1.3. Campaign and Session Structure

-   **Campaign**: This is the primary, persistent save object. A campaign encompasses
    the party, their inventory, and the entire history of their adventure. Users
    will save and load *Campaigns*.
-   **Session**: A single instance of gameplay within a campaign (e.g., a single
    evening's play).
-   **Journal Recap**: An LLM-generated, shareable summary of a single **Session**.
    When a campaign is loaded, the recap of the *previous* session will be
    displayed to remind players of what happened.

### 1.4. `ppdf` Feature Set

-   **Implemented Features**:
    -   **Advanced PDF Parsing**: A multi-stage pipeline that analyzes page layouts,
        detects columns, reconstructs logical reading order, and identifies
        structural elements like titles, paragraphs, tables, and boxed notes.
    -   **LLM-Powered Reformatting**: Uses LLM prompts to clean and reformat
        extracted text into styled Markdown or plain text.
    -   **Rich CLI**: A comprehensive command-line interface with options for page
        selection, column forcing, style preservation, and output control.
    -   **Prompt Engineering Suite**: Includes features for running in batch mode
        across multiple prompt presets and a unique `--analyze-prompts` mode to have
        an LLM critique system prompts.
    -   **Real-time TTS Output**: Can stream the final, processed text to a
        local, high-quality text-to-speech engine using Piper TTS.
    -   **Debugging Tools**: A `--dry-run` mode with an ASCII layout renderer to
        visualize the detected structure without calling the LLM.
    -   **Library Refactoring**: The core processing logic has been refactored into a
        `ppdf_lib.api` module, allowing its functions to be imported and called
        directly by other Python applications like the `dmme` backend.
    -   **Image Extraction Mode**: A complete pipeline dedicated to extracting graphical
        assets from PDFs. It uses a multimodal LLM to generate descriptions and a
        separate utility model to classify each image (e.g., `art`, `map`, `cover`,
        `handout`).
    -   **Semantic Labeling**: An enhancement to the text processing pipeline that
        uses an LLM to add semantic labels (e.g., `stat_block`,
        `read_aloud_text`, `dm_knowledge`) to text chunks before ingestion.

### 1.5. `dmme` Feature Set

-   **Implemented Features**:
    -   **Campaign & Party Management**: Full CRUD functionality for creating, saving,
        and loading persistent campaigns and parties of characters.
    -   **Interactive Gameplay UI**: A two-column interface featuring a narrative log,
        player input, a dynamically populated party status panel, and an interactive
        dice roller.
    -   **Advanced RAG System**: A sophisticated Retrieval-Augmented Generation
        system that leverages semantically labeled text chunks for precise,
        context-aware responses. It employs a two-stage retrieval process to prevent
        DM-only knowledge from being shown to the player while still using it for
        context.
    -   **Multiple Game Modes**: Support for both pre-defined `Module` play and
        LLM-generated `Freestyle` play, selectable from a "New Game" wizard.
    -   **Optional Game Aids**: User-selectable aids including an "AI Art Historian" for
        inline visual aids (with thumbnails and lightbox) and an "ASCII Scene Renderer"
        for rogue-like maps.
    -   **Library Hub**: A dedicated hub for all Knowledge Base (KB) management,
        replacing modal-based workflows. It features a KB list, a
        content/asset explorer with thumbnail views, and an integrated, multi-step
        **Ingestion Wizard**.
    -   **Party Hub**: A dedicated hub for creating and managing all parties and their
        characters. It features a multi-pane character sheet editor and includes an
        **LLM-Powered Character Creator** that uses RAG from a selected ruleset to
        generate character sheets.
    -   **Advanced Ingestion Workflow**: An enhanced workflow that allows for
        section-level review of a PDF document *before* ingestion. The system first
        analyzes the document's structure, then presents a list of sections to the user,
        who can exclude sections from the final import process.
    -   **Custom Asset Upload**: A feature within the Library Hub's asset explorer
        allowing users to add their own images to a KB via drag-and-drop. The
        system automatically generates a description, classification, and thumbnail for
        the uploaded asset.
    -   **Tiered LLM Configuration Panel**: An advanced settings panel that allows
        for fine-grained control over LLM configurations. It enables users to assign
        different models and Ollama server endpoints for distinct workloads (e.g.,
        Game vs. Ingestion).

---

## 2. File System Structure

The application will create and manage a hidden directory at `~/.dmme/` to store all
generated data. A single SQLite file will serve as the primary database for all
application data besides the vector stores.

`~/.dmme/`
├── assets/
│   └── images/
│       └── <collection_name>/
│           ├── assets.json      (*Asset manifest*)
│           ├── ...              (*Extracted image files*)
│           └── ...              (*Extracted thumbnail files*)
├── chroma/
│   └── ...                  (*ChromaDB persistent vector storage*)
├── dmme.db                    (*SQLite database for campaigns, sessions, etc.*)
└── dmme.cfg                   (*INI file for user settings, including LLM configs*)

---

## 3. Backend Design

### 3.1. `ppdf` - The Document Analysis & Reformatting Utility

`ppdf` is a powerful Python script designed for extracting, understanding, and
reformatting content from PDF files, especially those with complex, multi-column
layouts. It goes beyond simple text extraction by performing a multi-stage
analysis to identify the document's logical structure, then leverages a Large
Language Model (LLM) via Ollama to produce clean, readable, and stylistically
enhanced Markdown.

For the `dmme` project, `ppdf` has been refactored into an importable
library (`ppdf_lib`), exposing distinct modes for content and image
processing that are used by the main application's ingestion service.

#### 3.1.1. Detailed Processing Pipeline

The script processes the PDF in a series of stages, transforming the raw file
into structured, readable output.

1.  **Stage 1: Page Layout Analysis**: The engine analyzes each page to
    classify its type (e.g., `art`, `credits`, `content`), detect column
    counts, and identify distinct layout zones. Footers and page
    numbers are automatically detected and removed.
2.  **Stage 2: Content Structuring**: Within each column, the engine segments
    content into logical blocks like `ProseBlock`, `TableBlock`, `Title`, and
    `BoxedNoteBlock` based on structure and styling cues.
3.  **Stage 3: Logical Document Reconstruction**: The tool walks the structured
    page models to rebuild the document into a final, linear sequence of
    logical `Section` objects. This process correctly merges paragraphs that
    span columns and pages, representing the true reading order.

#### 3.1.2. Detailed Data Model

`ppdf` employs a sophisticated, hierarchical data model to represent the PDF's
content, transforming raw layout elements into logically structured sections.

-   **`BoundedElement`**: The base class for any layout element that has a computed
    bounding box.
-   **`ContentBlock`**: A generic block of content lines from the PDF. It serves as a
    base for more specific content types and holds the raw line objects and bounding
    box.
-   **`ProseBlock`, `TableBlock`, `BoxedNoteBlock`**: Specific subclasses of
    `ContentBlock` that represent standard text, structured tables, or sidebars.
-   **`Title`**: Represents a title or heading element found on a page or within a
    column.
-   **`PageModel`**: A structured representation of a single PDF page's physical
    layout, including its zones, columns, and detected elements.
-   **`Paragraph`**: Represents a logical paragraph of text, reconstructed from
    various `ContentBlock` types. This is the unit used for LLM processing.
-   **`Section`**: Represents a logical section of a document, such as a chapter or
    topic, composed of multiple `Paragraph` objects.

### 3.2. `dmme` - The Game Driver (Python / Flask)

The `dmme` backend is a Flask server that orchestrates knowledge ingestion, manages
game state, and interacts with the LLM.

-   **Data Persistence**: All application data is stored in a unified **SQLite
    database** (`dmme.db`) with tables for `campaigns`, `sessions`, `parties`, and
    `characters`.
-   **Configuration Persistence**: User settings are stored in an INI file at
    `~/.dmme/dmme.cfg`. A dedicated **`ConfigService`** is responsible for reading and
    writing these settings, including the tiered Game/Ingestion LLM configurations.
-   **Knowledge Ingestion**: Provides an API to support the frontend's **Library
    Hub**. It will invoke `ppdf_lib` for a two-stage process: first to
    `analyze` a document's structure, and second to perform the final `ingestion`
    based on user-provided section configurations.
-   **RAG & LLM Logic**: The core RAG service will query the ChromaDB collections,
    leveraging semantic labels for precision. It will request its model configuration
    (e.g., for the 'DM Narration' task) from the `ConfigService` before making any
    LLM calls.
-   **REST API (Enhanced)**:
    -   **Campaigns**: Full CRUD APIs for managing campaigns.
    -   **Parties**: Full CRUD APIs for managing saved parties.
    -   **Knowledge**: APIs to orchestrate the multi-step ingestion process,
        including `POST /api/knowledge/analyze` and
        `POST /api/knowledge/<kb_name>/upload-asset`.
        -   `GET /api/knowledge/dashboard/<kb_name>` for aggregated KB stats.
        -   `GET /api/knowledge/entities/<kb_name>` for a list of all unique entities.
    -   **Gameplay**: `POST /api/game/command` (streams structured JSON with text,
        images, and maps).
    -   **Settings**: `GET` and `POST` APIs for the `ConfigService` to manage the
        `dmme.cfg` file.
    -   **Ollama**: `GET /api/ollama/models` to list available models, which will be
        enhanced to return a `type_hint` for each model to aid frontend filtering.
    -   **Search**: `GET /api/search` with `q` and `scope` parameters to perform
        vector searches across one or all knowledge bases.

### 3.3. `dmme-eval` - The Evaluation Utility

`dmme-eval` is a command-line utility for the systematic testing and evaluation of
both LLM prompts and core backend ingestion pipelines.

#### 3.3.1. CLI Structure
The tool uses a subcommand structure implemented with `argparse`:
-   **`prompt`**: All functionality related to testing and evaluating system prompts.
-   **`ingest`**: All functionality related to testing parts of the ingestion pipeline.

#### 3.3.2. Prompt Evaluation Mode
This mode operates on **Test Suites**. A test suite is a directory containing a
`prompt.txt` file, a `config.json` file, and a subdirectory of `scenarios` containing
individual test cases as `.txt` files. Key features include an
"LLM-as-a-Judge" evaluation using a dedicated prompt (`PROMPT_LLM_AS_JUDGE`) and a
`--compare` mode for side-by-side analysis of two different prompt suites.
The output for all evaluations is a detailed, self-contained Markdown report.

#### 3.3.3. Ingestion Test Mode
This mode allows for isolated testing of backend services. The primary implemented
task is `extract-images`, which runs the full image processing pipeline on a PDF and
generates a visual Markdown report, including thumbnails, for easy analysis.

---

## 4. Frontend Design (HTML/CSS/JavaScript)

The `dmme` frontend is a single-page application built using a modern, modular
**ES6 JavaScript** structure. It features a modern, component-based design with
a dark, themeable interface.

### 4.1. Detailed Style Guide

To ensure a consistent and professional look and feel, the UI will adhere to the
following style guide.

-   **Primary Color Palette**: The default theme will use the following colors:
    -   `--bg-color`: `#1a1a1a`
    -   `--panel-bg`: `#2a2a2e`
    -   `--border-color`: `#444`
    -   `--text-color`: `#e0e0e0`
    -   `--accent-color`: `#007acc`
    -   `--danger-color`: `#e53935`

-   **Typography**:
    -   The main UI will use a standard sans-serif font stack for readability
        (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto...`).
    -   All views displaying narrative text, code, or log-like content will use a
        monospace font (`"Courier New", Courier, monospace`).

-   **Theming System**: The application is themeable. The settings panel will
    allow users to choose from several pre-defined themes, which are implemented in
    `base.css`:
    -   Default
    -   Vibrant Focus
    -   High Contrast
    -   CRT Green Phosphorus
    -   Ocean Blue
    -   Forest Green
    -   Warm Sepia
    -   Cyberpunk

### 4.2. UI/UX Paradigm

The application is organized around three distinct views, a contextual header, and
status bar navigation.

-   **Main Views:**
    1.  **Game View:** The immersive environment for active gameplay.
    2.  **Library View:** A dedicated hub for all Knowledge Base (KB) management.
    3.  **Party View:** A dedicated hub for creating and managing all parties and
        characters.

-   **Status Bar Navigation:** The primary method for switching between views is
    a set of icons on the left side of the bottom status bar.

-   **Contextual Header:** The main header buttons will change based on the active view,
    a behavior managed in `main.js`.
    -   **Game View Header:** `New Game` | `Load Game` | `Settings`
    -   **Library View Header:** `+ New Knowledge Base` | `Settings`
    -   **Party View Header:** `+ New Party` | `Settings`

### 4.3. Core Layouts

#### 4.3.1. Game View

The main gameplay interface is a **two-column layout**:

-   **Left Panel (approx. 1/4 width):** A fixed-width side panel containing:
    -   An upper, scrollable **Party Status Panel** with an accordion view for character
        details.
    -   A lower, fixed **Dice Roller** component anchored to the bottom.
-   **Right Panel (approx. 3/4 width):** The main interaction area containing:
    -   **Knowledge Source Panel:** Displays active KBs for the session.
    -   **Narrative View:** The main log displaying the game's story.
    -   **Input Panel:** The text area for user commands.

#### 4.3.2. Library Hub (Enhanced)

A two-panel layout for all KB-related tasks.

-   **Left Panel (Split View):**
    -   **Top Section**: Contains the **Global Search Utility** with a search bar and scope
        selector, positioned above the main, searchable list of all created
        Knowledge Bases.
    -   **Bottom Section**: Contains the master **Entity List** for the selected KB,
        complete with its own filter input. This allows for Browse all unique
        entities found in a document.

-   **Right Panel (KB Inspector / Search Results):** This panel is dynamic.
    -   **Default State (Inspector):** A multi-tab interface for the selected KB:
        -   **Dashboard:** An overview with stats, an entity distribution chart, and a
            key terms word cloud.
        -   **Content Explorer:** A view of all text chunks, presented in enhanced
            cards that display semantic labels and key terms. It features a toggle for
            a linear "Section Flow" view.
        -   **Entities:** A detail view that displays all text chunks related to a
            single entity selected from the master list in the left panel.
        -   **Mind Map:** A graphical visualization of the document's structure,
            showing sections and their entity-based relationships.
        -   **Asset Explorer:** The grid view for visual assets, featuring a
            drag-and-drop area for custom asset uploads.
    -   **Search State:** When a search is performed, this panel displays a list of
        rich result cards, each showing a content snippet, source KB, and other
        metadata.

#### 4.3.3. Party Hub

A two-panel layout for all party and character management:

-   **Left Panel:** A searchable list of all created Parties.
-   **Right Panel (Party Inspector):** Displays the selected party's character
    roster and contains all UI for adding and editing characters.

### 4.4. Modals and Wizards

-   **New Game Wizard:** A modal launched from the Game View to guide the user
    through selecting a Game Mode and the required knowledge bases.
-   **DM's Insight Modal**: Triggered by a toolbar button, this
    modal displays the raw RAG context used for that specific generation.
-   **Image Lightbox Modal**: A simple, reusable modal overlay that displays a
    full-resolution image when a thumbnail in the narrative view is clicked.

#### 4.4.1. Settings Panel (Granular LLM Configuration)

The main settings modal is a multi-pane interface for application configuration,
featuring a powerful tab-based system for granular LLM control. It is implemented with
**three** tabs that group the configuration sections.

-   **General Tab**: This tab combines two functional groups:
    -   **Game Configuration**: Contains application-level settings, such as the "Default
        Preferred Ruleset" for the AI Character Creator.
    -   **Appearance**: Contains all theming and language selection options.

-   **Game LLM Tab**:
    -   **Ollama Server URL**: A text input for the endpoint serving gameplay models.
    -   **DM Model Group**:
        -   **Model**: A text input with a datalist for model selection.
        -   **Temperature**: A slider for tuning creativity.
        -   **Context Window**: A dropdown with options (2K through 128K).
    -   **Character Creation Model Group**:
        -   Contains the same three controls (Model, Temperature, Context Window).

-   **Ingestion LLM Tab**:
    -   **Ollama Server URL**: A separate text input for the endpoint serving
        ingestion and utility models.
    -   **PDF Formatting Model Group**: Controls for Model, Temperature, and Context Window.
    -   **Classification & Labeling Model Group**: Controls for Model, Temperature, and
        Context Window.
    -   **Image Analysis Model Group**: Controls for Model, Temperature, and Context Window.
    -   **Embedding Model Group**: A single Model selection input.

---

## 5. Source Code Structure

The project is organized into a monorepo containing the main scripts at the
root, a shared `core` library, and dedicated libraries for each application.

`dmme_project/`
├── **ppdf.py**: Main entry point for the PDF utility CLI.
├── **dmme.py**: Main entry point to launch the Game Driver Flask server.
├── **dmme-eval.py**: A command-line utility for prompt and pipeline evaluation.
|
├── **core/**: A library for utilities shared across all scripts.
│   ├── `log_utils.py`: `RichLogFormatter` for consistent, colored console logging.
│   ├── `llm_utils.py`: Centralized functions for querying Ollama models.
│   └── `tts.py`: The Text-to-Speech engine manager using Piper TTS.
│
├── **ppdf_lib/**: All internal logic for the `ppdf` utility's pipeline.
│   ├── `api.py`: The public API for invoking `ppdf` functionality from other scripts.
│   ├── `scanner.py`: `MarginScanner` for header/footer detection.
│   ├── `analyzer.py`: `PageLayoutAnalyzer` for Stage 1 analysis.
│   ├── `segmenter.py`: `ContentSegmenter` for Stage 2 analysis.
│   ├── `reconstructor.py`: `DocumentReconstructor` for Stage 3 analysis.
│   ├── `models.py`: Data models for the structured PDF document representation.
│   ├── `renderer.py`: `ASCIIRenderer` for visualizing page layout.
│   └── `constants.py`: Stores presets and system prompts for reformatting.
│
└── **dmme_lib/**: A self-contained package for the `dmme` web server.
    ├── `app.py`: The Flask app factory (`create_app`) and service initialization.
    ├── `constants.py`: Stores DM persona presets and all internationalized prompts.
    ├── `api/`: Contains all Flask Blueprints for the REST API (e.g., `game.py`, `knowledge.py`).
    ├── `services/`: Contains all backend business logic (`storage_service.py`, `rag_service.py`, `config_service.py`, etc.).
    └── `frontend/`: All frontend code for the web UI, built with ES6 modules.
        ├── `js/`: Main application logic (`main.js`), handlers, and core utilities.
        │   ├── `components/`: Reusable UI components (e.g., `DiceRoller.js`).
        │   ├── `hubs/`: Logic for the main views (e.g., `LibraryHub.js`).
        │   └── `wizards/`: Logic for modal wizards (e.g., `ImportWizard.js`).
        ├── `css/`: All stylesheets, including base styles and component modules.
        └── `locales/`: JSON files for internationalization (`en.json`, `es.json`, etc.).

---

## 6. Implementation Plan

This implementation plan details the incremental steps to build the `dmme` application.

### Phase 1: Foundational `ppdf` Enhancements

-   **Milestone 1: Refactor `ppdf` for Library Usage**
    -   **Goal**: Make the core `ppdf` logic easily importable and callable from other
        Python scripts.
    -   **Description**: This architectural change will allow the `dmme` backend to use
        `ppdf`'s functionality directly, which is more robust than relying solely
        on a subprocess CLI.
    -   **Key Tasks**: Refactor `ppdf.py`'s `Application` class and its methods so that
        the core text and image processing pipelines can be imported and called with
        Python arguments.
    -   **Outcome**: The `dmme` backend can `import ppdf_lib` and use its functions
        directly.

-   **Milestone 2: Implement `ppdf` Image Extraction Mode**
    -   **Goal**: Add the dedicated image processing pipeline to the `ppdf` library.
    -   **Description**: Implements the functionality to extract images, generate AI
        descriptions and classifications, and save them with JSON metadata.
    -   **Key Tasks**: Create a new function in `ppdf_lib.extractor` that performs the
        image extraction. Add logic to call a multimodal LLM. Write the image and
        JSON files to a specified output directory.
    -   **Outcome**: `ppdf` can now be called in a mode that processes a PDF and
        outputs a folder of images and their corresponding metadata files.

-   **Milestone 3: Implement `ppdf` Semantic Labeling**
    -   **Goal**: Add the LLM-powered metadata enhancement step to the text pipeline.
    -   **Description**: Enhances the existing text extraction process to include the
        semantic labeling required for powerful RAG.
    -   **Key Tasks**: In the text processing pipeline, add a step that takes each text
        chunk, sends it to an LLM with a classification prompt, and attaches the
        resulting labels to the chunk's data.
    -   **Outcome**: The data structure returned by the `ppdf` text processing
        function now includes semantic labels for each text chunk.

### Phase 2: `dmme` Backend Foundation

-   **Milestone 4: Create `dmme` Flask Server & Database Schema**
    -   **Goal**: Establish a runnable Flask server and the complete SQLite database.
    -   **Description**: Builds the core backend application and data model,
        incorporating all entities we've designed.
    -   **Key Tasks**: Create the `dmme_lib` app factory. Define the full SQLite schema
        with tables for `campaigns`, `sessions`, `parties`, and `characters`.
        Implement a `StorageService`.
    -   **Outcome**: A runnable Flask server that can manage a complete, relational
        SQLite database for the application.

-   **Milestone 5: Implement Campaign & Party Management APIs**
    -   **Goal**: Build the backend APIs for managing campaigns and parties.
    -   **Description**: Creates the endpoints necessary for the frontend to handle
        saving, loading, and creating campaigns and parties.
    -   **Key Tasks**: Implement full CRUD API endpoints in Flask for `campaigns` and
        `parties`.
    -   **Outcome**: The backend provides a complete API for campaign and party
        management.

### Phase 3: Knowledge Ingestion

-   **Milestone 6: Build Static Import Wizard UI**
    -   **Goal**: Create the frontend modal for the Import Knowledge Wizard.
    -   **Description**: Builds the complete visual component for the wizard without yet
        wiring it up to the backend.
    -   **Key Tasks**: Create the HTML/CSS for a multi-step modal. Implement UI for file
        upload, type selection, and placeholder metadata forms.
    -   **Outcome**: A user can see and interact with a non-functional Import Wizard.

-   **Milestone 7: Implement Markdown Ingestion**
    -   **Goal**: Create the backend endpoint and service logic for Markdown ingestion.
    -   **Description**: This milestone implements the simplest ingestion path. The backend
        will call the enhanced `ppdf` library's semantic labeling function.
    -   **Key Tasks**: Implement the `POST /api/knowledge/import` endpoint. Add logic in
        an `IngestionService` to handle `.md` files, chunk text, call the semantic
        labeling function, and store in ChromaDB.
    -   **Outcome**: A functional API endpoint that can create a semantically enriched
        knowledge base from an uploaded Markdown file.

-   **Milestone 8: Implement PDF Content Ingestion**
    -   **Goal**: Add the capability to ingest text content from PDF files.
    -   **Description**: The backend ingestion service will be extended to call the `ppdf`
        library's text processing function when a PDF is uploaded.
    -   **Key Tasks**: In the `IngestionService`, add logic to detect PDF files. Call
        the refactored `ppdf` text processing library function. Ensure the output
        (including semantic labels) is correctly stored in ChromaDB.
    -   **Outcome**: The import API now fully supports text ingestion from PDF files.

-   **Milestone 9: Implement Image Review Workflow**
    -   **Goal**: Implement the full "human-in-the-loop" workflow for image ingestion.
    -   **Description**: Builds the complete pipeline for extracting, reviewing, and
        ingesting image-based knowledge.
    -   **Key Tasks**: Create a new API to trigger `ppdf`'s image extraction mode. Build
        the "Image Review" UI with a slideshow and editing forms. Implement APIs to
        list reviewable images and save the user's edits. Create the final API to
        ingest the approved image metadata into ChromaDB.
    -   **Outcome**: A user can create a high-quality, curated knowledge base of visual
        aids from a PDF.

### Phase 4: Core Gameplay (Revised)

-   **Milestone 10: Build Party and Game Creation Wizards**
    -   **Goal**: Build the UI and connect the backend for creating a party and
        starting a new game.
    -   **Description**: Implements the final setup steps before gameplay can begin.
    -   **Key Tasks**: Build the "Party Creation Wizard" UI. Implement the LLM
        character generation API. Build the "New Game Wizard" UI, allowing selection
        of game mode, knowledge bases, and a saved party.
    -   **Outcome**: A user can create a party of characters and configure a new game
        session using all the designed options.

-   **Milestone 11: Build Static Gameplay UI**
    -   **Goal**: Create the static HTML and CSS for the main two-column gameplay
        interface.
    -   **Description**: This milestone focuses on building the complete visual layout for
        the game screen without any backend interaction. It establishes the foundational
        structure for all subsequent gameplay functionality.
    -   **Key Tasks**: Implement the two-column layout using HTML and CSS. Create the
        static Party Status Panel, Dice Roller, Knowledge Source Panel, Narrative View,
        and Player Input components.
    -   **Outcome**: A non-interactive but visually complete gameplay screen is rendered
        in the browser, matching the design specifications.

-   **Milestone 12: Implement Backend Gameplay Stub**
    -   **Goal**: Create the backend API endpoint for handling player commands with a
        hardcoded, non-streaming response.
    -   **Description**: This step creates the necessary backend infrastructure for the
        gameplay loop. The endpoint will accept a player command but return a fixed,
        predictable JSON response, allowing for frontend development without a
        functioning RAG system.
    -   **Key Tasks**: Implement the `POST /api/game/command` endpoint in Flask. The
        endpoint logic will ignore the input and immediately return a hardcoded JSON
        object representing a sample AI response.
    -   **Outcome**: The backend has a testable `/api/game/command` endpoint that the
        frontend can successfully call and receive a valid, albeit static, response from.

-   **Milestore 13: Connect UI to Gameplay Stub**
    -   **Goal**: Wire up the frontend player input to the backend stub and display the
        returned data.
    -   **Description**: This connects the two halves of the application. The user will be
        able to type a command, press enter, and see the hardcoded response from the
        backend appear in the Narrative View.
    -   **Key Tasks**: Write JavaScript to capture the user's input from the text area.
        Implement the `fetch` call to the `POST /api/game/command` endpoint. Write the
        logic to render the received JSON data into the Narrative View.
    -   **Outcome**: A user can type a command, send it to the backend, and see the
        static, hardcoded response render correctly in the main narrative log.

-   **Milestone 14: Implement Full RAG Logic**
    -   **Goal**: Implement the complete, non-streaming RAG and LLM logic on the backend.
    -   **Description**: This milestone replaces the backend stub with the full
        Retrieval- Augmented Generation system. It will now query the vector store based
        on the player's command and generate a unique response from the LLM.
    -   **Key Tasks**: Implement the RAG service logic to query the ChromaDB collections.
        Integrate the LLM call using the retrieved context. Replace the stub logic in
        the `/api/game/command` endpoint with the new RAG service call.
    -   **Outcome**: The backend now processes player commands dynamically, generating a
        contextually relevant response from the LLM, though the response is not yet
        streamed.

-   **Milestone 15: Integrate Streaming Response**
    -   **Goal**: Upgrade the backend endpoint and frontend logic to support real-time,
        streaming responses.
    -   **Description**: The final step in core gameplay implementation. This changes the
        interaction from a simple request-response to a streaming connection, allowing
        the AI's response to appear token-by-token in the UI.
    -   **Key Tasks**: Modify the Flask endpoint to return a streaming response. Update
        the frontend JavaScript to handle the streaming data and append it
        progressively to the Narrative View, creating a "live typing" effect.
    -   **Outcome**: A user can type a command and receive an AI-generated response that
        streams into the narrative log in real-time, completing the core gameplay loop.

### Phase 5: UI/UX & Internationalization

-   **Milestone 16: Implement Settings Panel & Configuration Persistence**
    -   **Goal**: Create a UI for application settings and save user choices persistently.
    -   **Description**: This milestone introduces a settings modal where users can
        configure various application options. These settings will be saved to and loaded
        from a `dmme.cfg` file in the user's `~/.dmme/` directory, making them
        persistent across sessions.
    -   **Key Tasks**: Build the HTML/CSS for the multi-pane Settings Panel modal.
        Implement frontend JavaScript to manage the modal's state. Add backend API
        endpoints (e.g., `GET /api/settings`, `POST /api/settings`) to read and write
        key-value pairs to `dmme.cfg`. Implement the logic for theme switching.
    -   **Outcome**: A functional settings panel where a user can, at a minimum, select a
        theme, and that choice will persist the next time they launch the application.

-   **Milestone 17: Implement DM's Insight Modal**
    -   **Goal**: Allow the user to view the raw RAG context that the LLM used for a
        specific response.
    -   **Description**: To improve transparency and aid in debugging, each AI-generated
        narrative block will have an icon. Clicking this icon will open a modal window
        displaying the exact context retrieved from the vector store that was used to
        generate that specific piece of narrative.
    -   **Key Tasks**: Modify the `GameplayHandler.js` to store the `dm_insight` content
        received from the stream. Add a '🔍' icon button to each AI response in the
        narrative log. Create the HTML/CSS for the "DM's Insight" modal. Write
        JavaScript to show the stored context in the modal when an icon is clicked.
    -   **Outcome**: A user can click an icon next to any AI response in the game log and
        see the underlying RAG context that informed that response.

-   **Milestone 18: Frontend Internationalization (i18n)**
    -   **Goal**: Refactor the frontend UI to support multiple languages for all static
        text elements.
    -   **Description**: This milestone introduces a framework for internationalization.
        All hardcoded text in the UI (buttons, labels, titles) will be replaced with
        keys that are translated at runtime based on the user's selected language.
    -   **Key Tasks**: Create JSON language files (e.g., `en.json`, `es.json`) containing
        key-value pairs for all UI text. Write a JavaScript helper to load the
        appropriate language file. Refactor all HTML and JS to use this helper function
        instead of hardcoded strings. Add a language selector dropdown to the Settings
        Panel.
    -   **Outcome**: The entire user interface can be switched between English and Spanish
        (or other added languages) dynamically from the settings panel.

-   **Milestone 19: Backend Multi-language LLM Support**
    -   **Goal**: Enable the LLM to understand context and generate narrative responses
        in the user's selected language.
    -   **Description**: This extends the multi-language support to the AI itself. The
        backend will use a system prompt translated into the target language to ensure
        the LLM's entire "personality" and response framing match the user's selection.
    -   **Key Tasks**: Create translated versions of the core system prompts (e.g.,
        `PROMPT_GAME_MASTER`) in `dmme_lib/constants.py`. Modify the `RAGService` to
        accept a language parameter. The service will then select the appropriate system
        prompt before querying the LLM.
    -   **Outcome**: When a user selects a language in the settings, the AI Dungeon
        Master's responses will be generated in that language.

### Phase 6: Gameplay Features & Enhancements

-   **Milestone 20: Implement Interactive Dice Roller**
    -   **Goal**: Make the Dice Roller component in the left panel fully interactive.
    -   **Description**: Transforms the static dice buttons into a functional "dice
        expression builder." Users can click multiple dice, see the expression being
        built, and click a "Roll" button to submit the expression as a command to the
        game.
    -   **Key Tasks**: Add a display, "Roll" button, and backspace button to the Dice
        Roller HTML. Create a `DiceRoller.js` module to manage state. Add event
        listeners to build a dice expression array, render it to the display, and
        submit the final expression as a natural language command to the backend.
    -   **Outcome**: The Dice Roller is fully functional. A user can click to build an
        expression like `3d6`, click "Roll," and see the command appear in the narrative
        log.

-   **Milestone 21: Implement Backend Autosave Service**
    -   **Goal**: Create the backend mechanism for saving and retrieving the current game
        state to a temporary recovery file.
    -   **Description**: This provides the core safety net for in-progress games. The
        backend will manage a dedicated `autosave.json` file.
    -   **Key Tasks**: Implement `POST /api/session/autosave` to write the game state
        to `autosave.json`. Implement `GET /api/session/recover` to read from it.
    -   **Outcome**: The backend has a functional API for saving and retrieving a
        temporary game session state.

-   **Milestone 22: Implement Frontend Autosave and Recovery Logic**
    -   **Goal**: Implement the frontend logic to periodically autosave and to
        automatically recover the state on application startup.
    -   **Description**: This makes the autosave feature functional from the user's
        perspective.
    -   **Key Tasks**: Implement a `setInterval` to post the game state to the autosave
        endpoint. On startup, call the recover endpoint. If data exists, load the game
        view directly and show a banner with "Save", "Load Other", or "New Game" options.
    -   **Outcome**: A user who accidentally closes their browser can reload the
        application and find their game state exactly as it was.

-   **Milestone 23: Implement Backend Journaling Service**
    -   **Goal**: Create the backend service to summarize a session's raw log into a
        narrative "Journal Recap."
    -   **Description**: This service will take a session's history and use an LLM to
        create a concise, story-like summary.
    -   **Key Tasks**: Create a `POST /api/sessions/summarize` endpoint. The service
        will take a session log, use an LLM with a specific summarization prompt, and
        save the result to the `sessions` table in the database.
    -   **Outcome**: The backend can generate and persist narrative summaries of gameplay
        sessions.

### Phase 6 (Refined): Campaign Continuation

-   **Milestone 24.1: Enhance Campaign Persistence**
    -   **Goal:** Enhance the backend to save the initial `gameConfig` when a campaign
        is created.
    -   **Description:** To properly resume a game, the system needs to know which
        knowledge bases and settings were used to start it. This milestone adds the
        necessary persistence logic.
    -   **Key Tasks:** Add a `game_config_json` TEXT column to the `campaigns` table
        in `storage_service.py`. Modify the `create_campaign` API and service
        method to accept and store the JSON representation of the `gameConfig`.
    -   **Outcome:** New campaigns saved in the database now include the configuration
        required to restart them.

-   **Milestone 24.2: Implement Campaign State API**
    -   **Goal:** Create a backend endpoint to retrieve all data needed to resume a
        campaign.
    -   **Description:** This API will provide the frontend with the saved `gameConfig`
        and the full narrative history from the last session.
    -   **Key Tasks:** Create a new endpoint, `GET /api/campaigns/<id>/state`. The
        service logic will fetch the campaign's `game_config_json` and combine it
        with the narrative log of the most recent session.
    -   **Outcome:** A functional API endpoint that the frontend can call to get all
        necessary data to reconstruct and continue a saved game.

-   **Milestone 24.3: Implement Frontend Campaign Continuation**
    -   **Goal:** Wire the "Continue Campaign" button to fully load and resume a saved
        game.
    -   **Description:** This completes the user-facing feature by replacing the
        placeholder logic with a call to the new state API and initializing the game
        view.
    -   **Key Tasks:** In `LoadCampaignWizard.js`, modify the `recapContinueBtn`'s
        event listener. It should now call the `/api/campaigns/<id>/state` endpoint.
        On success, it will call the main application's `startGame()` method, passing
        in the retrieved game config and the historical narrative log.
    -   **Outcome:** A user can load a saved campaign, view the recap, and click
        "Continue" to seamlessly resume their adventure exactly where they left off.

### Phase 7: Optional Game Aids

-   **Milestone 25: Implement RAG and API for Visual Aids**
    -   **Goal**: Enhance the backend to retrieve and stream relevant visual aid data.
    -   **Description**: This milestone makes the backend "aware" of the curated images
        in the knowledge base and enables it to send them to the frontend.
    -   **Key Tasks**: Modify the `RAGService` to retrieve `image_description`
        documents. Update the `game` API to stream a new JSON object type: `{"type":
        "visual_aid", "image_url": "...", "caption": "..."}`.
    -   **Outcome**: The backend API can now send structured data to the frontend,
        instructing it to display a specific visual aid.

-   **Milestone 26: Implement Frontend Rendering of Visual Aids**
    -   **Goal**: Update the Narrative View to render the images sent by the backend,
        respecting a user setting.
    -   **Description**: The frontend will listen for the `visual_aid` object and, if
        the feature is enabled, display the image directly in the game log.
    -   **Key Tasks**: Add a "Show Visual Aids" toggle to the Settings Panel. In the
        `GameplayHandler.js`, check for the `visual_aid` chunk type and the user
        setting, then dynamically create and append the `<img>` element to the log.
    -   **Outcome**: When relevant, and if the user has the feature enabled, images
        appear directly in the narrative log during gameplay.

-   **Milestone 27: Implement Backend ASCII Scene Generation**
    -   **Goal**: Integrate the ASCII map generation prompt into the backend game loop.
    -   **Description**: After a narrative response is generated, it will be used as
        input for a second LLM call to create the ASCII map.
    -   **Key Tasks**: Design and test the ASCII map generation prompt. In the
        `RAGService`, after generating the narrative, make a second LLM call with the
        new prompt. Modify the `game` API to stream a new JSON object type: `{"type":
        "ascii_map", "content": "..."}`.
    -   **Outcome**: The backend can now generate both a narrative response and a
        corresponding ASCII map for a player command.

-   **Milestone 28: Implement Frontend Rendering of ASCII Scene**
    -   **Goal**: Update the Narrative View to render the ASCII map sent by the backend.
    -   **Description**: The frontend will listen for the `ascii_map` object and, if
        the feature is enabled, display the map correctly formatted.
    -   **Key Tasks**: Add a "Show ASCII Scene" toggle to the Settings Panel. In the
        `GameplayHandler.js`, check for the `ascii_map` chunk type and the user
        setting, then render the content inside a `<pre><code>` block.
    -   **Outcome**: When enabled, a rogue-like ASCII map of the scene appears in the
        narrative log after the descriptive text for a turn.

### Phase 8: UI/UX Refinements

-   **Milestone 29: Refine Visual Aids with Thumbnails and Lightbox**
    -   **Goal**: Improve the visual aids feature by generating thumbnails to keep the
        narrative log tidy and adding a "lightbox" modal to view full-size images.
    -   **Description**: This refactors the visual aids implementation. The ingestion
        process will generate a smaller JPEG thumbnail for each image, saved with a
        `thumb_` prefix. The gameplay API will provide URLs for both. The frontend
        will display the thumbnail and allow the user to click it to view the full
        image in a modal.
    -   **Key Tasks**:
        -   **Backend**: Modify `ppdf_lib/api.py` to generate and save a prefixed JPEG
            thumbnail during image extraction. Update `ingestion_service.py` to include
            the thumbnail path in the vector store metadata. Modify `rag_service.py` to
            stream a `visual_aid` object containing both `thumb_url` and `full_url`.
        -   **Frontend**: Add a new `Image Lightbox` modal to `index.html`. Update
            `GameplayHandler.js` to render thumbnails using `thumb_url`, making them
            clickable to open the `full_url` in the lightbox. Add CSS to constrain
            thumbnail size and style the lightbox.
    -   **Outcome**: Visual aids appear as clean, clickable thumbnails in the log.
        Clicking a thumbnail opens the full-resolution image in a modal overlay,
        improving usability and reducing initial load.

-   **Milestone 30: Implement Cover Mosaic Kickoff**
    -   **Goal**: Create a more immersive start for Adventure Modules by displaying a
        mosaic of cover art before the initial narration.
    -   **Description**: This feature enhances the start of "Adventure Module" games. The
        backend will find the first four images classified as 'cover' and send their
        thumbnail URLs to the frontend. The UI will display these in a responsive,
        horizontal row before the first narrative text appears.
    -   **Key Tasks**:
        -   **Backend**: Modify the `/api/game/start` endpoint. Add logic to the
            `RAGService` to query the module's KB for the first four `cover` images.
            Stream a new `cover_mosaic` JSON object containing an array of image URLs
            before streaming the narrative text.
        -   **Frontend**: Update `GameplayHandler.js` to handle the new `cover_mosaic`
            stream type. Implement a new UI component to render the images in a
            responsive horizontal row at the top of the narrative view.
    -   **Outcome**: Users playing an Adventure Module are greeted with a visually
        striking mosaic of cover art, creating a strong thematic opening for the game
        session.

### Phase 9: Core UI & Hub Foundations

-   **Milestone 31: Implement Multi-View Architecture**
    -   **Goal:** Refactor the core UI to support the new multi-view paradigm.
    -   **Key Tasks:**
        -   Create the main containers for the Game, Library, and Party views.
        -   Implement the status bar with icons to switch between the three views.
        -   Implement the logic for the contextual header, showing different
            buttons based on the active view.
    -   **Outcome:** A functional application shell where the user can navigate
        between three distinct (but still empty) views.

-   **Milestone 32: Build Library & Party Hub UIs**
    -   **Goal:** Create the static two-panel layouts for the new management hubs.
    -   **Key Tasks:**
        -   Build the Library Hub's layout: KB list on the left, tabbed inspector
            panel on the right.
        -   Build the Party Hub's layout: Party list on the left, character roster/
            editor panel on the right.
        -   Populate the lists by fetching data from the existing backend APIs.
    -   **Outcome:** The Library and Party hubs are visually complete and display
        existing KBs and Parties.

### Phase 10 (Refined): Advanced Ingestion Workflow

-   **Milestone 33: Implement Content Explorer**
    -   **Goal:** Allow users to view the indexed content of a Knowledge Base.
    -   **Key Tasks:**
        -   Create a new backend endpoint `GET /api/knowledge/<kb_name>/explore`.
        -   Implement the frontend logic to fetch and render the "Text View" and
            "Asset View" in the Library Hub.
    -   **Outcome:** A user can select a KB and browse all of its indexed content.

-   **Milestone 34.1: Backend - Create Analysis Endpoint**
    -   **Goal:** Create a backend API that analyzes a document's structure without full
        ingestion.
    -   **Description:** This is the first stage of the two-stage ingestion process. This
        endpoint will invoke `ppdf` to get a high-level structural overview (list of
        sections) of a document.
    -   **Key Tasks:** Implement `POST /api/knowledge/analyze`. This should call a
        refactored `ppdf_lib` function that returns a JSON list of logical sections
        (e.g., `[{title: "Chapter 1", page_start: 5}, ...]`).
    -   **Outcome:** A functional API endpoint that returns a document's structure for
        review.

-   **Milestone 34.2: Frontend - Build Section Review UI**
    -   **Goal:** Create the user interface for the new "Section Review" step in the
        Import Wizard.
    -   **Description:** This new UI pane will display the list of sections returned by
        the analysis endpoint, allowing the user to select which ones to include or
        exclude.
    -   **Key Tasks:** Add a new pane to the Import Wizard in `index.html`. Write the
        JavaScript in `ImportWizard.js` to display the section list with checkboxes.
    -   **Outcome:** A user can upload a document and see a list of its logical
        sections in a new wizard step.

-   **Milestone 34.3: Backend - Refactor Ingestion Endpoint**
    -   **Goal:** Modify the final ingestion endpoint to accept user configurations.
    -   **Description:** The main ingestion service will be updated to process only the
        sections specified by the user in the new review step.
    -   **Key Tasks:** Update the `/api/knowledge/ingest-document` endpoint. It will
        now accept an additional parameter: a list of section configurations (e.g.,
        which titles to include/exclude). The service logic must be updated to
        respect these configurations.
    -   **Outcome:** The backend can now perform a targeted ingestion based on
        user-provided section selections.

-   **Milestone 34.4: Frontend - Integrate Two-Stage Workflow**
    -   **Goal:** Connect the new Section Review UI to the backend, completing the
        workflow.
    -   **Description:** This milestone wires the frontend and backend together for the
        advanced ingestion feature.
    -   **Key Tasks:** In `ImportWizard.js`, on the "Next" click from the file upload
        step, call the new `/analyze` endpoint. Populate the review UI with the
        response. On the "Next" click from the review step, call the modified
        `/ingest-document` endpoint, passing the user's section selections.
    -   **Outcome:** A user can upload a file, review its sections, deselect unwanted
        parts, and then finalize the ingestion process.

### Phase 11 (Refined): Character & Asset Management Hubs

-   **Milestone 35.1: UI - Migrate Character Editor to Party Hub**
    -   **Goal:** Move the character creation and editing UI from the modal into the main
        Party Hub view.
    -   **Description:** This refactors the UI to match the hub-based design paradigm,
        making character management a more integrated experience.
    -   **Key Tasks:** Copy the HTML form structure for adding a character (manual and
        AI) from the `party-wizard-modal` into the right-hand panel of the `party-view`
        in `index.html`.
    -   **Outcome:** The character editor form is now visually present within the Party
        Hub's main interface.

-   **Milestone 35.2: Frontend - Implement Party Hub State Management**
    -   **Goal:** Make the Party Hub's right panel dynamic, showing either a character
        list, an editor, or a welcome message.
    -   **Description:** This adds the necessary JavaScript logic to manage the state of
        the Party Hub's inspector panel.
    -   **Key Tasks:** In `PartyHub.js`, add logic to handle clicks on parties in the
        left-hand list. On selection, display that party's character roster in the
        right panel. Add logic for a "+ New Character" button that shows the
        character editor form.
    -   **Outcome:** The Party Hub is now interactive. Users can select a party to view
        its members and can switch to a form for adding a new character.

-   **Milestone 35.3: Frontend - Port Character Management Logic**
    -   **Goal:** Move all character-related business logic from the old modal to the
        new hub.
    -   **Description:** This finalizes the feature migration by moving the JavaScript
        that calls the backend APIs into the `PartyHub.js` module.
    -   **Key Tasks:** Move the functions for creating (manual and AI) and deleting
        characters from `PartyWizard.js` to `PartyHub.js`. Ensure they correctly
        interact with the new UI and call the existing backend APIs. Deprecate the
        old modal.
    -   **Outcome:** The Party Hub is a fully self-contained and functional interface for
        creating, viewing, and managing all parties and characters.

-   **Milestone 36.1: Backend - Create Asset Upload Endpoint**
    -   **Goal:** Create a backend API to allow users to upload their own images to a
        Knowledge Base.
    -   **Description:** This endpoint will handle file storage, thumbnail generation,
        and LLM-powered metadata creation for user-provided images.
    -   **Key Tasks:** Implement a new `POST /api/knowledge/<kb_name>/upload-asset`
        endpoint. The logic should save the uploaded file to the correct assets
        directory, create a thumbnail, call a multimodal LLM to generate a description
        and classification, and save the metadata to a corresponding `.json` file.
    -   **Outcome:** A functional API endpoint that can add a new, fully processed image
        asset to an existing Knowledge Base.

-   **Milestone 36.2: Frontend - Build Drag-and-Drop UI**
    -   **Goal:** Create the user interface for uploading custom assets in the Library Hub.
    -   **Description:** This will add a clear, interactive area in the Library Hub's
        "Asset View" where users can drop their image files.
    -   **Key Tasks:** In `index.html`, add an "Upload Asset" dropzone element to the
        Library Hub's asset view. Add CSS to style it, including visual feedback for
        when a user is dragging a file over it.
    -   **Outcome:** A visible and styled drag-and-drop area is present in the Library Hub.

-   **Milestone 36.3: Frontend - Implement Upload Logic**
    -   **Goal:** Connect the new UI to the backend, completing the custom asset upload
        feature.
    -   **Description:** This milestone implements the client-side logic to handle the
        file upload process and refresh the UI upon completion.
    -   **Key Tasks:** In `LibraryHub.js`, add event listeners for drag-and-drop events
        on the new UI element. When a file is dropped, use the Fetch API to send it
        to the `/upload-asset` endpoint. Upon a successful response, automatically
        refresh the asset view to show the newly added image.
    -   **Outcome:** A user can drag and drop an image file onto the Library Hub to add
        it to the selected Knowledge Base.

### Phase 12: Refactor LLM Configuration and Usage

-   **Milestone 37: Backend Configuration Refactor**
    -   **Goal**: Update all backend configuration files and service initializations to use the
        new four-model role system (`dm_model`, `vision_model`, `utility_model`,
        `embedding_model`).
    -   **Description**: This milestone standardizes how the application manages and accesses
        the different Ollama models, making the system more robust and easier to
        configure.
    -   **Key Tasks**: Rename keys in `config_service.py` defaults. Update `app.py` to
        load all four model settings. Update `IngestionService` and `RAGService`
        constructors to accept the specific model names they require.
    -   **Outcome**: The backend application initializes correctly with the new
        configuration scheme, passing the correct model names to each service.

-   **Milestone 38: Backend Logic Refactor**
    -   **Goal**: Refactor the service methods to use the correct, explicitly-configured
        model for each specific LLM task.
    -   **Description**: This ensures that each task (e.g., creative writing,
        classification, reformatting) uses the most appropriate and efficient model,
        preventing mismatches like using a vision model for text tasks.
    -   **Key Tasks**: Modify `rag_service.py` to use `dm_model` for narration and
        `utility_model` for ASCII maps. Update `ingestion_service.py` to use
        `utility_model` for PDF reformatting. Implement the two-stage "See then
        Classify" logic for image classification.
    -   **Outcome**: All backend LLM calls use the correct model for the task at hand,
        improving performance and accuracy.

-   **Milestone 39: Frontend Settings UI Update**
    -   **Goal**: Update the user-facing settings panel to reflect the new, clearer model
        role names.
    -   **Description**: This makes the application's configuration intuitive for the user,
        allowing them to easily assign specific models to the "DM Model" and
        "Utility Model" roles.
    -   **Key Tasks**: In `index.html`, update the `id` and `data-key` attributes for
        the model inputs. Update all `locales/*.json` files with new translation
        keys and text for the updated labels.
    -   **Outcome**: The settings panel correctly displays, loads, and saves the new
        model role configurations.

### Phase 13: `dmme-eval` Utility

-   **Milestone 40: `dmme-eval` Foundation and CLI Structure**
    -   **Goal**: Create the basic scaffolding for the `dmme_eval.py` script, including
        the subcommand-based CLI.
    -   **Description**: This milestone builds the entry point and command-line
        argument parsing for the new tool, providing a foundation for all subsequent
        functionality.
    -   **Key Tasks**: Create the `dmme_eval.py` file. Use `argparse` to implement the
        `prompt` and `ingest` subcommands and their respective arguments. Integrate
        the existing `core/log_utils.py` for logging.
    -   **Outcome**: A runnable script that correctly parses all designed commands and is
        ready for the implementation of its core logic.

-   **Milestone 41: Implement Ingestion Test Mode (`extract-images`)**
    -   **Goal**: Implement the full logic for the `ingest --task extract-images`
        feature.
    -   **Description**: This provides the first piece of useful functionality, allowing
        for targeted testing and refinement of the `ppdf` image extraction and
        analysis pipeline.
    -   **Key Tasks**: Write the core logic for the `extract-images` task. Implement
        temporary directory creation. Import and call the `process_pdf_images`
        function from `ppdf_lib.api`. Generate the visual Markdown report.
    -   **Outcome**: A user can run the tool on a PDF and receive a complete, visual
        report on all extracted images and their AI-generated metadata.

-   **Milestone 42: Implement Prompt Evaluation Logic (Single Run)**
    -   **Goal**: Implement the core logic for the `prompt` subcommand for a single
        test suite.
    -   **Description**: This builds the main prompt evaluation engine, allowing a
        developer to benchmark a prompt's performance against multiple scenarios.
    -   **Key Tasks**: Implement Test Suite parsing. Loop through scenarios, calling the
        `dm_model`. Implement the "LLM-as-a-Judge" feature using the `utility_model`
        to score and critique the output. Generate the Markdown report.
    -   **Outcome**: A user can run the tool on a single prompt test suite and get a
        full, objective evaluation report.

-   **Milestone 43: Implement Prompt Comparison Mode**
    -   **Goal**: Add the `--compare` functionality to the `prompt` subcommand.
    -   **Description**: This provides the key feature for rapid iteration, allowing for
        direct, side-by-side comparison of two prompt versions.
    -   **Key Tasks**: Modify the `prompt` subcommand to handle two input directories.
        Run the same scenarios against both prompts. Generate the side-by-side
        comparison report in Markdown.
    -   **Outcome**: A user can easily compare two different prompts to see which one
        performs better on a given set of test cases.

### Phase 14: Enhanced Image Interactivity

-   **Milestone 44: Refactor Lightbox into a Reusable Component**
    -   **Goal**: Decouple the lightbox logic from `GameplayHandler.js` into a
        standalone, reusable component.
    -   **Description**: This architectural improvement will make the lightbox
        available to any part of the application, reducing code duplication. It
        is a prerequisite for implementing the feature in new areas.
    -   **Key Tasks**: Create a new `dmme_lib/frontend/js/components/Lightbox.js`
        file. Migrate all lightbox-related DOM selectors, methods, and event
        listeners from `GameplayHandler.js` into the new `Lightbox` class.
        Refactor `GameplayHandler.js` to import and use the new component.
    -   **Outcome**: A self-contained `Lightbox.js` module exists and is used by
        the Game View, with no loss of the original functionality.

-   **Milestone 45: Update RAG Service for Mosaic URLs**
    -   **Goal**: Modify the backend to provide full-resolution image URLs for the
        kickoff cover mosaic.
    -   **Description**: The frontend requires both thumbnail and full-size URLs to
        implement the lightbox. This task updates the RAG service to provide
        this necessary data structure.
    -   **Key Tasks**: In `dmme_lib/services/rag_service.py`, modify the
        `_find_and_yield_cover_mosaic` function. Change the yielded object's
        payload from an array of strings to an array of objects, where each
        object contains `thumb_url` and `full_url`.
    -   **Outcome**: The `/api/game/start` endpoint streams all data required for the
        frontend to render the kickoff mosaic with lightbox functionality.

-   **Milestone 46: Implement Kickoff Mosaic Lightbox**
    -   **Goal**: Make the cover images in the kickoff mosaic clickable, opening them
        in the lightbox.
    -   **Description**: This task connects the newly refactored `Lightbox`
        component to the cover mosaic UI, completing the user-facing feature
        for Adventure Module kickoffs.
    -   **Key Tasks**: In `GameplayHandler.js`, update the `_renderCoverMosaic`
        function to handle the new data from the backend. Add a click event
        listener to each rendered mosaic image that calls `lightbox.open()` with
        the corresponding `full_url`.
    -   **Outcome**: A user can click any cover image at the start of an adventure to
        view the full-size version in a modal overlay.

-   **Milestone 47: Implement Library Hub Lightbox**
    -   **Goal**: Make asset thumbnails in the Library Hub's asset grid clickable
        to open in a lightbox.
    -   **Description**: This task implements the lightbox feature in the asset
        explorer, allowing users to easily view their uploaded or extracted
        images at full resolution.
    -   **Key Tasks**: In `dmme_lib/frontend/js/hubs/LibraryHub.js`, import and
        instantiate the new `Lightbox` component. In the `_addAssetToGrid`
        function, add a click listener to each asset card that opens the
        asset's `full_url` in the lightbox. This will require ensuring the
        full asset object is passed to the function.
    -   **Outcome**: A user can click any asset in the Library Hub's asset viewer to
        see the full-resolution image in the lightbox modal.

### Phase 15: Advanced RAG Strategy - Chunking, Security & Context

-   **Milestone 48: Implement Advanced Chunking Heuristics**
    -   **Goal**: Refactor the ingestion service to produce more contextually
        complete RAG documents by keeping related content together.
    -   **Description**: This milestone replaces the simple paragraph recovery logic
        with an intelligent system that avoids splitting small sections and groups
        tables with their introductory text, creating a better foundation for
        retrieval.
    -   **Key Tasks**: Modify `ingestion_service.py` to: 1) Ingest sections
        below a character threshold as a single document. 2) Ingest
        table-only sections as a single document. 3) Redefine chunks as the
        content between the start of one paragraph and the start of the next.
    -   **Outcome**: Documents in the vector store are more contextually rich and
        cohesive, improving the raw material used by the RAG system.

-   **Milestone 49: Enhance Semantic Labeling for Security & Kickoffs**
    -   **Goal**: Improve the labeling process to distinguish DM-only information
        and more accurately identify adventure kickoff text.
    -   **Description**: This milestone introduces a new label for secret
        information and adds both automated heuristics and a user-driven "cue"
        system for pinpointing the start of an adventure during ingestion.
    -   **Key Tasks**: Add a `dm_knowledge` label to the `SEMANTIC_LABELER` prompt
        in `constants.py`. Add a "Kickoff Cue" text area to the Import Wizard
        UI. Update the ingestion API to accept this cue and pass it to the LLM
        labeler. Add a rule to `ingestion_service.py` to limit the
        `read_aloud_kickoff` label to the first 10 pages of a document.
    -   **Outcome**: The ingestion pipeline can create more secure and accurately
        labeled documents, separating player-facing text and correctly
        identifying complex adventure introductions.

-   **Milestone 50: Implement Two-Stage RAG with Defragmentation**
    -   **Goal**: Refactor the core RAG retrieval process to prevent information
        leaks and fix the context fragmentation bug.
    -   **Description**: This implements the core security and context improvements
        for gameplay, ensuring the LLM only sees player-safe information while
        also providing the full, coherent context for the section it's
        discussing.
    -   **Key Tasks**: Refactor the `generate_response` method in `rag_service.py`.
        Implement a two-stage query: first, a query excluding `dm_knowledge`
        chunks, followed by a call to `_get_full_section` to defragment the
        context for the LLM. Second, a broader query *including*
        `dm_knowledge` and its defragmented results to populate the "DM's
        Insight" modal.
    -   **Outcome**: A secure and robust RAG retrieval system that prevents secret
        information leaks and eliminates fragmented context, leading to
        higher-quality AI responses.

-   **Milestone 51: Implement Kickoff Sequence Grouping**
    -   **Goal**: Enable the RAG system to handle multi-part adventure
        introductions that combine narrative and mechanics.
    -   **Description**: This task updates the kickoff narration logic to recognize
        and group a sequence of related chunks (e.g., read-aloud text
        followed by a rumors table) into a single, comprehensive kickoff context.
    -   **Key Tasks**: Modify the `generate_kickoff_narration` function in
        `rag_service.py`. After finding the primary `read_aloud_kickoff` chunk,
        add logic to search for and append any subsequent, contiguous chunks from
        the same section that are labeled `mechanics`.
    -   **Outcome**: The application delivers a more accurate kickoff experience for
        adventures that begin with both narrative and mechanical elements,
        presenting them together as a single unit.

### Phase 16: Advanced Ingestion & Metadata

-   **Milestone 52: Implement Markdown Structural Pre-Analysis**
    -   **Goal**: Improve the contextual integrity of chunks ingested from Markdown files.
    -   **Description**: This milestone replaces the naive newline-based chunking for
        Markdown files with a more intelligent, structure-aware approach. The system will
        first parse the document's hierarchy using its Markdown headers (#, ##, etc.) to
        identify logical sections.
    -   **Key Tasks**: Modify the `ingest_markdown` function in `ingestion_service.py`.
        Implement a pre-processing step that splits the document into sections based on
        header levels. Pass these complete sections to the chunking logic.
    -   **Outcome**: Chunks from Markdown files are far more contextually complete, keeping
        headers grouped with their associated paragraphs and tables, which significantly
        improves the quality of data for subsequent processing and RAG.

-   **Milestone 53: Implement Basic Style Ingestion and Keyword Extraction**
    -   **Goal**: Make stylistic data from the PDF available to the ingestion service
        and perform a first-pass keyword extraction.
    -   **Description**: This is the foundational step. We will modify the pipeline to
        pass styled (Markdown) text from `ppdf_lib` to the `IngestionService` and
        implement a simple rule to extract all bolded text into a new metadata
        field.
    -   **Key Tasks**:
        -   In `ingestion_service.py`, update the call to `process_pdf_text` to
            enable style preservation.
        -   In `ingestion_service.py`, implement a function that parses a chunk's
            styled text, extracts all phrases wrapped in `**...**`, and saves
            them to the new `key_terms` metadata field.
    -   **Outcome**: All new chunks ingested from PDFs will have a populated
        `key_terms` field containing all bolded text, and styled text is available
        for subsequent milestones.

-   **Milestone 54: Implement Context-Aware Italic Handling for Semantic Labeling**
    -   **Goal**: Improve semantic labeling accuracy by interpreting italics
        differently based on the knowledge base type.
    -   **Description**: This step refines the semantic labeling process by introducing
        specialized prompts. It addresses the issue that italics mean different
        things in adventure modules versus rulebooks.
    -   **Key Tasks**:
        -   Create two new prompts in `dmme_lib/constants.py`:
            `SEMANTIC_LABELER_ADVENTURE` (treats italics as `read_aloud_text`).
            `SEMANTIC_LABELER_RULES` (treats italics as `mechanics` or emphasis).
        -   Modify the semantic labeling step in `ingestion_service.py` to accept the
            styled text and select the appropriate prompt based on the `kb_type`
            metadata.
    -   **Outcome**: Semantic labeling becomes significantly more accurate. The system
        can now reliably distinguish descriptive read-aloud text from emphasized
        rule terms, improving the quality of the data foundation.

-   **Milestone 55: Implement Special Handling for Stat Blocks**
    -   **Goal**: Refine the keyword extraction logic to correctly handle the unique
        structure of creature stat blocks.
    -   **Description**: This milestone fixes the "metadata pollution" problem we
        identified. It adds a condition to the logic from Milestone 53, preventing
        generic labels like **CA** and **DC** from overwriting the more important
        creature name as the primary key term.
    -   **Key Tasks**:
        -   In `ingestion_service.py`, modify the keyword extraction function.
        -   Add a check: if a chunk's semantic label is `stat_block`, do *not*
            extract all bolded phrases.
        -   Instead, for `stat_block` chunks, extract only the title of the stat
            block (the creature's name) and make that the sole entry in the
            `key_terms` field.
    -   **Outcome**: The `key_terms` metadata for stat blocks becomes clean and highly
        relevant, containing only the creature's name. This makes finding specific
        creatures via search or filtering much more reliable.

-   **Milestone 56: Implement Deep Stat Block Parsing**
    -   **Goal**: Extract structured data from creature stat blocks to enable advanced
        queries.
    -   **Description**: This milestone goes beyond simple keyword extraction for stat
        blocks. It introduces a dedicated LLM-based parsing step that converts the raw
        text of a stat block into a structured JSON object containing its discrete
        attributes (CA, DC, Attacks, etc.).
    -   **Key Tasks**: Design a new `STAT_BLOCK_PARSER` prompt. In `ingestion_service.py`,
        for chunks labeled `stat_block`, add a call to this new prompt. Store the
        resulting JSON object in a new `structured_stats` metadata field.
    -   **Outcome**: The vector store now contains structured, queryable data for
        creatures. This enables precise RAG queries that are impossible with text
        alone, such as "Find a creature with CA 15 or higher and more than 6 hit dice."

-   **Milestone 57: Implement Entity Extraction and Relational Metadata**
    -   **Goal**: Create explicit links between related chunks of information in the
        vector store.
    -   **Description**: This final ingestion step builds a relational layer on top of
        our data. It uses the cleaned-up `key_terms` as candidates to identify
        and link related concepts, such as a monster to its lair description.
    -   **Key Tasks**:
        -   Design a new NER prompt that classifies the `key_terms` of a chunk
            into entity types (e.g., `creature`, `location`, `item`).
        -   Add `entities: TEXT` and `linked_chunks: TEXT` fields to the metadata model.
        -   After all chunks in a document are processed, iterate through them, find
            chunks that share common classified entities, and populate the
            `linked_chunks` field with the IDs of related chunks.
    -   **Outcome**: The knowledge base now functions like a graph. Retrieving one piece
        of information (e.g., a room description) allows the system to easily
        find all other chunks explicitly linked to it (e.g., the stat block of a
        monster in that room).

### Phase 17: Intelligent Retrieval & Caching

-   **Milestone 58: Implement Multi-Query Retrieval**
    -   **Goal**: Improve retrieval accuracy by generating and executing multiple search
        queries for each player command.
    -   **Description**: This enhances the start of the RAG process. Instead of relying
        on the player's exact phrasing, we use an LLM to brainstorm better ways to
        search the knowledge base.
    -   **Key Tasks**:
        -   Design a "query expansion" prompt that takes a player command and
            generates 3-5 alternative search queries from different perspectives
            (rules, narrative, entities).
        -   In `rag_service.py`, refactor `generate_response` to call this prompt
            first.
        -   Update the service to execute all generated queries against the vector
            store and merge the unique results before ranking and context assembly.
    -   **Outcome**: Retrieval is more robust and less likely to miss important
        information, even if the player's command is ambiguous.

-   **Milestone 59: Implement Location-Based Context Caching (Cached Augmented Gen)**
    -   **Goal**: Provide the AI DM with a persistent, highly-aligned context for the
        party's current location, improving consistency and performance.
    -   **Description**: This implements the "open page" concept. When the party enters
        a significant, known location, the system performs a single, exhaustive
        query to build a complete "context dossier" for that area, which is then
        cached and used for subsequent turns.
    -   **Key Tasks**:
        -   Add a simple in-memory cache dictionary to the `RAGService`.
        -   Add logic to `generate_response` to attempt to identify a primary
            `location` entity from the narrative context.
        -   Create a new `_build_location_cache` method that, when a new location is
            detected, retrieves the location's main chunk and all chunks linked to it
            via the relational metadata from Milestone 57.
        -   Update `generate_response` to use this cached context block for the LLM
            prompt instead of performing a live vector search on every turn, as long
            as the party remains in the cached location.
    -   **Outcome**: The AI DM's responses become much more consistent and contextually
        aware within a single location. This also reduces latency, as expensive
        vector searches are performed less frequently during exploration scenes.

### Phase 18: Settings Panel Enhancements

-   **Milestone 60: Implement Smart Model Suggestions**
    -   **Goal**: Improve the user experience in the settings panel by providing
        intelligent, filtered suggestions for each model selection field.
    -   **Description**: This enhancement refines the model selection UI. Instead of
        showing a generic list of all available Ollama models for every input, the
        backend will analyze the model names to infer their capabilities (e.g., vision,
        embedding). The frontend will then use these hints to provide clearer and more
        relevant suggestions to the user for each specific role.
    -   **Key Tasks**:
        1.  **Backend**: Modify the `GET /api/ollama/models` endpoint. It will now return a
            list of JSON objects, each containing the model's `name` and a `type_hint`
            (e.g., 'vision', 'embedding', 'text'). The logic will use common
            substrings (like 'llava', 'embed') to generate these hints.
        2.  **Frontend**: Refactor the `_populateModelSuggestions` method in
            `SettingsManager.js` to handle the new API response structure.
        3.  **Frontend**: Update the datalist population logic. For specialized inputs
            like "Vision Model" or "Embedding Model", the suggestions will be filtered
            to show only models with the relevant `type_hint`, making selection easier
            and less error-prone.
    -   **Outcome**: The settings panel becomes significantly more user-friendly. When a
        user interacts with the "Vision Model" input, the dropdown suggestions are
        filtered to relevant models like `llava:latest`, improving clarity and
        configuration speed.

### Phase 19 (Reworked): Granular LLM Configuration

-   **Milestone 61: Backend Configuration Service Rework**
    -   **Goal:** Rework the backend to handle the new granular, role-based LLM
        configuration schema.
    -   **Description**: This milestone refactors the `ConfigService` to handle new
        `[OllamaGame]` and `[OllamaIngestion]` sections in `dmme.cfg`. The service must
        correctly load the settings for each workload, including per-model tuning, and
        provide the correct configuration for any given task.
    -   **Key Tasks**:
        1.  Modify `dmme_lib/services/config_service.py` to create, read, and write the
            new `.ini` structure with `[OllamaGame]` and `[OllamaIngestion]` sections.
        2.  Implement logic to store and parse a JSON object within each new section
            containing the granular settings for each model role.
        3.  Rework the `get_model_config(task_name)` method to retrieve the full
            configuration (model, URL, temperature, context) for a specific task.
        4.  Update services like `RAGService` and `IngestionService` to use this new
            method for all LLM calls.
    -   **Outcome**: The backend can serve and utilize distinct, fully-specified
        configurations for every LLM task based on the new settings structure.

-   **Milestone 62: Frontend Settings UI Rework**
    -   **Goal**: Build the new tabbed user interface for the Granular LLM Configuration
        Panel.
    -   **Description**: This milestone implements the full user interface for the
        settings modal, including the new "Game LLM" and "Ingestion LLM" tabs and all
        their associated controls.
    -   **Key Tasks**:
        1.  Add two new tabs to the settings modal structure: "Game LLM" and "Ingestion
            LLM", resulting in four total tabs (General, Appearance, Game LLM, Ingestion
            LLM).
        2.  Populate the "Game LLM" and "Ingestion LLM" tabs with all specified controls:
            URL inputs, and groups for each model role containing a model selector, a
            temperature slider, and a context window dropdown.
    -   **Outcome**: A visually complete but non-interactive settings panel that
        accurately reflects the new four-tab, role-based design.

-   **Milestone 63: Frontend Logic and API Integration Rework**
    -   **Goal**: Implement the client-side logic to make the new settings panel fully
        interactive and persistent.
    -   **Description**: This involves rewriting `SettingsManager.js` to handle the new UI,
        manage the complex state object, and communicate with the updated backend API.
    -   **Key Tasks**:
        1.  In `SettingsManager.js`, update the tab switching logic to handle all four tabs.
        2.  Rewrite the `saveSettings` and `loadSettings` methods to handle the deeply
            nested JSON object required for the new granular configuration.
    -   **Outcome**: A fully functional and interactive LLM settings panel where users can
        granularly configure all model roles, with choices persisting across sessions.

### Phase 20: Library Hub Overhaul

-   **Milestone 64: Backend - Dashboard & Entity Endpoints**
    -   **Goal**: Create the backend APIs to support the new Library Hub dashboard and
        entity explorer views.
    -   **Description**: These endpoints will provide the aggregated data needed for the
        new high-level overview and entity Browse features, serving as the foundation
        for the frontend overhaul.
    -   **Key Tasks**:
        -   Implement `GET /api/knowledge/dashboard/<kb_name>` to aggregate and return
            stats like chunk counts, entity distribution, and key term frequencies.
        -   Implement `GET /api/knowledge/entities/<kb_name>` to return a complete,
            sorted list of all unique named entities in a KB.
    -   **Outcome**: Two new, functional backend endpoints that provide the necessary
        data to populate the enhanced Library Hub views.

-   **Milestone 65: Backend - Global Search Endpoint**
    -   **Goal**: Implement a powerful search API capable of querying across the entire
        library or a specific collection.
    -   **Description**: This creates the core of the new search utility, allowing the
        frontend to perform flexible and precise vector searches against the knowledge
        bases.
    -   **Key Tasks**:
        -   Create the `GET /api/search` endpoint with `q` (query) and `scope`
            (`all` or `<kb_name>`) parameters.
        -   Implement the service logic to perform a vector search against the
            appropriate ChromaDB collection(s).
        -   Structure the response to include rich metadata for each result.
    -   **Outcome**: A functional, high-performance search endpoint that the frontend
        can use to query all ingested knowledge.

-   **Milestone 66: Frontend - UI Scaffolding & Dashboard**
    -   **Goal**: Build the new multi-tab layout for the Library Hub Inspector and
        implement the Dashboard view.
    -   **Description**: This milestone creates the new frontend structure for the hub
        and wires up the first new feature, providing users with an immediate high-level
        overview of their knowledge bases.
    -   **Key Tasks**:
        -   Refactor `_library-hub.html` to include the new four-tab structure
            (Dashboard, Content, Entities, Assets).
        -   Build the UI components for the Dashboard tab (stats cards, charts).
        -   Wire up the Dashboard to the `/api/knowledge/dashboard/` endpoint.
    -   **Outcome**: The Library Hub features a new, modern tabbed layout, and the
        Dashboard tab is fully functional, displaying aggregated statistics for any
        selected KB.

-   **Milestone 67: Frontend - Enhanced Content & Entity Explorers**
    -   **Goal**: Implement the redesigned Content Explorer and the new Entity Explorer to
        fully expose all ingested metadata.
    -   **Description**: This milestone completes the data visualization aspect of the
        overhaul, allowing users to deeply inspect the semantic structure of their
        knowledge.
    -   **Key Tasks**:
        -   Redesign the "chunk card" in `LibraryHub.js` to clearly display semantic
            labels, key terms, and icons for linked data.
        -   Build the UI for the Entity Explorer tab, including the filterable list of
            all unique entities.
        -   Implement the logic to display all related chunks when an entity is selected.
    -   **Outcome**: Users can browse KB content via enhanced, metadata-rich cards and
        can explore a master list of all extracted entities to see their connections.

-   **Milestone 68: Frontend - Search Utility Integration**
    -   **Goal**: Implement the complete, user-facing global search functionality.
    -   **Description**: This final milestone integrates the search backend with the UI,
        delivering the new headline feature of the Library Hub overhaul.
    -   **Key Tasks**:
        -   Add the search bar and scope selector components to the Library Hub's left
            panel UI.
        -   Write the JavaScript logic in `LibraryHub.js` to call the `/api/search`
            endpoint and handle the response.
        -   Create the UI view for rendering the rich search results in the hub's right
            panel.
    -   **Outcome**: A fully functional search utility is integrated into the Library Hub,
        allowing users to perform fast and accurate searches across their entire
        ingested library.

### Phase 21: Hierarchical Document Navigation

-   **Milestone 69: Implement Context Breadcrumbs**
    -   **Goal**: Enhance all chunk cards with a clickable breadcrumb trail to show
        their structural origin.
    -   **Description**: This provides immediate, in-place context for any piece of
        information, showing the user exactly where it came from in the source
        document's hierarchy.
    -   **Key Tasks**:
        -   **JS (`LibraryHub.js`)**: Modify the `_createChunkCardHTML` function to
            add a new `div` for the breadcrumb in the card's header. It will
            display `KB Name > Section Title`.
        -   **CSS (`library-hub.css`)**: Add styling for the new breadcrumb
            element, making the section title appear as a subtle, clickable link.
        -   **JS (`LibraryHub.js`)**: Add an event listener to the breadcrumb's
            section title link. On click, it will execute a search scoped to the
            current KB for all content matching that `section_title`.
    -   **Outcome**: Every chunk card in the UI will display its hierarchical
        location. Users can click on a section title within a breadcrumb to
        instantly view all related content from that section.

-   **Milestone 70: Implement Section Flow View**
    -   **Goal**: Create a new "Section Flow" display mode for the Content Explorer.
    -   **Description**: This feature allows users to read the knowledge base content in
        its original, linear order, grouped by section headers, providing a more
        book-like reading experience.
    -   **Key Tasks**:
        -   **HTML/CSS**: Add a view-mode toggle icon (e.g., List / Flow) to the
            Content Explorer tab. Add CSS to style the large section headers for
            the new view.
        -   **JS (`LibraryHub.js`)**:
            -   Add state management to track the current view mode (`list` or `flow`).
            -   Refactor the `renderContentView` function to handle both modes.
            -   In "Flow" mode, the function will first get all unique, sorted
                `section_title`s from the cached document data. It will then
                iterate through the sections, creating a prominent header for each,
                and appending the corresponding chunk cards below it.
    -   **Outcome**: A new toggle in the Content Explorer allows users to switch
        between the default flat list of chunks and a new "Section Flow" view that
        groups chunks under their original section headers.

-   **Milestone 71: Implement Semantic Mind Map Tab**
    -   **Goal**: Add a new "Mind Map" tab to the Library Hub that visually represents
        the document's structure and entity relationships.
    -   **Description**: This provides a powerful, at-a-glance graphical overview of
        the document, allowing users to discover and explore connections between
        different topics in a novel way.
    -   **Key Tasks**:
        -   **Dependency**: Select and integrate a lightweight JavaScript library for
            graph visualization (e.g., Mermaid.js).
        -   **HTML**: Add the new "Mind Map" tab and its pane to `_library-hub.html`.
        -   **JS (`LibraryHub.js`)**:
            -   Create a `renderMindMapView` function that is lazy-loaded when the
                tab is clicked.
            -   This function will process all cached chunks for the selected KB to
                build a graph data structure.
            -   It will generate the necessary syntax for the charting library,
                defining section titles as nodes and shared entities as links
                between them, and render the resulting chart.
    -   **Outcome**: A new "Mind Map" tab is available in the Library Hub,
        presenting an interactive, graphical visualization of the selected
        document's sections and their entity-based relationships.

### Phase 22: Advanced Game & Ingestion Configuration

-   **Milestone 72: Implement Per-Session Configuration UI**
    -   **Goal**: Allow users to override the default DM Model and Language for each new game.
    -   **Description**: This enhances the New Game Wizard with new controls, providing more
        flexibility for starting games without changing global settings.
    -   **Key Tasks**:
        -   Add "DM Model" and "Language" dropdowns to the New Game Wizard modal HTML.
        -   Update `NewGameWizard.js` to populate the new dropdowns (models from the
            Ollama API, languages from the i18n config).
        -   Modify the `startGame` method in `NewGameWizard.js` to include the selected
            `llm_model` and `language` in the `gameConfig` object.
    -   **Outcome**: The New Game Wizard displays and captures session-specific overrides
        for the DM model and language.

-   **Milestone 73: Implement Backend Logic for Session Overrides**
    -   **Goal**: Make the backend RAG service respect the new per-session overrides.
    -   **Description**: This connects the new frontend options to the backend logic,
        ensuring the user's choices for a specific session are honored by the LLM.
    -   **Key Tasks**:
        -   In `dmme_lib/services/rag_service.py`, modify the `generate_response` and
            `generate_kickoff_narration` methods.
        -   The methods will now first check the incoming `game_config` object for
            `llm_model` and `language` keys.
        -   If present, these values will be used; otherwise, the service will fall back
            to the global settings from the `ConfigService`.
        -   Update `GameplayHandler.js` to display the session-specific model if set.
    -   **Outcome**: The backend correctly uses the overridden DM model and language for
        gameplay when they are provided in the game configuration.

-   **Milestone 74: Implement Structural Table Secrecy**
    -   **Goal**: Automatically classify all content from structurally-identified PDF
        tables as `dm_knowledge`.
    -   **Description**: This enhances the ingestion pipeline to be more secure by
        default. It leverages the structural analysis from `ppdf_lib` to enforce a
        rule that table content is for the DM's eyes only.
    -   **Key Tasks**:
        -   Modify the `ingest_pdf_text` method in `dmme_lib/services/ingestion_service.py`.
        -   Before sending chunks to the semantic labeler, check if their source
            `Paragraph` object has the `is_table` flag set to `True`.
        -   If it does, directly assign the label `dm_knowledge` to the chunk and skip
            the LLM-based labeling for it.
    -   **Outcome**: All table content from ingested PDFs is reliably and automatically
        classified as `dm_knowledge` without requiring an LLM call.

-   **Milestone 75: Implement Semantic Stat Block Secrecy**
    -   **Goal**: Automatically re-classify any content identified as a stat block to be
        `dm_knowledge`.
    -   **Description**: This adds a second layer of security to the ingestion pipeline.
        It uses the LLM to identify stat blocks semantically, then applies a hard rule
        to ensure they are treated as secret information.
    -   **Key Tasks**:
        -   Modify the ingestion logic in `dmme_lib/services/ingestion_service.py` for
            both PDF and Markdown files.
        -   After a chunk receives its label from the LLM, add a check: if the returned
            label is `stat_block`, overwrite it with `dm_knowledge`.
    -   **Outcome**: All chunks identified as stat blocks by the LLM are correctly
        re-classified as `dm_knowledge` for RAG security purposes.

### Phase 23: Multi-Tag System Implementation

-   **Milestone 76: Update Vector Store Metadata Model**
    -   **Goal**: Modify the backend data model to store a list of tags for each chunk instead
        of a single label.
    -   **Description**: This is the foundational data-layer change for the new system. The
        metadata associated with each document in the vector store will be updated to
        accommodate an array of string tags, allowing for richer, more flexible
        data.
    -   **Key Tasks**: In `ingestion_service.py`, change the structure of the `metadatas`
        list that is passed to `vector_store.add_to_kb`. The single `label` key will be
        replaced with a `tags` key that holds a list of strings.
    -   **Outcome**: The vector store will be populated with a `tags` metadata field for
        all newly ingested documents, capable of storing multiple categorized tags.

-   **Milestone 77: Rework Ingestion Pipeline for Multi-Tag Generation**
    -   **Goal**: Update the ingestion service to generate and apply the new categorized
        multi-tag vocabulary.
    -   **Description**: This milestone adapts the core of the ingestion logic. The
        LLM prompts will be updated to request a JSON array of tags, and the service
        will be modified to parse this output and apply the hard-coded rules we designed
        (e.g., for tables and stat blocks).
    -   **Key Tasks**:
        -   Update the `SEMANTIC_LABELER_ADVENTURE` and `SEMANTIC_LABELER_RULES` prompts in
            `dmme_lib/constants.py` to instruct the LLM to output a JSON array of
            tags based on the new categorized vocabulary.
        -   Modify `ingestion_service.py` to parse the JSON list from the LLM.
        -   Change the logic from "overwriting" labels to "appending" tags (e.g., adding
            `access:dm_only` to stat blocks without removing `type:stat_block`).
    -   **Outcome**: The ingestion pipeline correctly generates and saves a rich list of
        categorized tags for each text chunk, reflecting its content, function, and
        security level.

-   **Milestone 78: Update RAG Service for Tag-Based Filtering**
    -   **Goal**: Adapt the RAG service to use the new tag list for secure and precise
        context retrieval.
    -   **Description**: This task makes the gameplay engine aware of the new data model.
        The core security mechanism will be updated to filter based on the `access:dm_only`
        tag, ensuring player-facing context remains safe.
    -   **Key Tasks**: In `rag_service.py`, modify the `generate_response` method. Change
        the ChromaDB `where` filters from checking a single `label` field to querying
        the new `tags` list (e.g., where `tags` does not contain `access:dm_only`).
    -   **Outcome**: The RAG system correctly and securely retrieves context using the new
        multi-tag system, with no loss of the critical security filtering.

-   **Milestone 79: Implement Tag Chip Display in Library Hub**
    -   **Goal**: Visually represent the new multi-tag metadata on the frontend.
    -   **Description**: This milestone implements the user-facing portion of the new
        system, allowing users to see all the tags associated with a chunk in an intuitive
        way.
    -   **Key Tasks**:
        -   Modify `_library-hub.html` to replace the single label element in the chunk
            card with a `div` container for multiple tags.
        -   Update the `_createChunkCardHTML` function in `LibraryHub.js` to iterate
            over the `tags` list and render each tag as a "chip".
        -   Add CSS to `library-hub.css` to style the new tag chips, including the
            category-based color-coding (e.g., blue for `type`, red for `access`).
    -   **Outcome**: The Library Hub UI displays multiple, color-coded tags on each chunk
        card, providing users with a much richer view of their ingested data.

### Phase 24: Interactive UI Enhancements

-   **Milestone 80: Add Interactive Styling to Tag Chips**
    -   **Goal**: Update the CSS to provide visual feedback that tag chips are clickable
        elements.
    -   **Description**: This milestone focuses purely on the user interface affordance. By
        changing the cursor and adding a hover effect, we signal to the user that the
        tags are interactive elements, paving the way for the filtering logic.
    -   **Key Tasks**: Modify `dmme_lib/frontend/css/components/library-hub.css`. Add
        `cursor: pointer` and a subtle hover effect (e.g., `transform: scale(1.05)`)
        to the `.tag-chip` CSS rule.
    -   **Outcome**: When a user hovers over a tag chip in the Library Hub, the cursor
        changes to a pointer and the chip visually reacts, clearly indicating it is a
        clickable element.

-   **Milestone 81: Implement Client-Side Tag Filtering Logic**
    -   **Goal**: Implement the client-side JavaScript logic to filter the Content Explorer
        when a tag chip is clicked.
    -   **Description**: This milestone implements the core functionality of the interactive
        tags feature. It will use a delegated event listener to capture clicks on tag
        chips and then use the component's cached data to show or hide chunk cards
        in the DOM, providing an instantaneous filtering experience for the user.
    -   **Key Tasks**:
        -   In `dmme_lib/frontend/js/hubs/LibraryHub.js`, add a delegated click event
            listener to the content view container.
        -   Write the filtering function that iterates through the cached chunk data,
            toggling the visibility of `.text-chunk-card` elements.
        -   Implement the logic to display and populate the existing
            `#content-filter-status` banner when a filter is active.
        -   Wire the `#clear-content-filter-btn` to a function that clears the active
            filter and restores the visibility of all chunk cards.
    -   **Outcome**: A user can click any tag chip in the Library Hub, and the view will
        instantly filter to show only content matching that tag. A banner appears
        allowing the user to clear the filter and return to the full view.

---

## 7. Potential Future Extensions

-   **Dynamic Music & Soundscapes**: An "AI DJ" system.
-   **Automated Combat Tracker**: A dedicated UI panel for combat.
-   **Interactive Map Viewer (Graphical)**: A feature to display graphical maps from
    PDFs with tokens.
-   **Adventure Creator Wizard**: A tool to help users write their own adventure modules.
