design-dmme.md
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

-   **Implemented Features (Standalone Tool)**:
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
        local, high-quality text-to-speech engine.
    -   **Debugging Tools**: A `--dry-run` mode with an ASCII layout renderer to
        visualize the detected structure without calling the LLM.

-   **Planned Features (DMme Integration)**:
    -   **Library Refactoring**: The core processing logic will be refactored to be
        easily importable and callable by the `dmme` backend.
    -   **Image Extraction Mode**: A new pipeline dedicated to extracting graphical
        assets from PDFs and using a multimodal LLM to generate descriptions and
        classifications (`art`, `map`, `decoration`).
    -   **Semantic Labeling**: An enhancement to the text processing pipeline that
        uses an LLM to add semantic labels (e.g., `is_stat_block`,
        `is_read_aloud_text`) to text chunks before ingestion.

### 1.5. `dmme` Feature Set

-   **Implemented Features**:
    -   **Campaign & Party Management**: Full CRUD functionality for creating, saving,
        and loading persistent campaigns and parties of characters.
    -   **Interactive Gameplay UI**: A two-column interface featuring a narrative log,
        player input, a dynamically populated party status panel, and a dice roller.
    -   **Advanced RAG System**: A sophisticated Retrieval-Augmented Generation
        system that leverages semantically labeled text chunks for precise,
        context-aware responses.
    -   **Multiple Game Modes**: Support for both pre-defined `Module` play and
        LLM-generated `Freestyle` play.
    -   **Optional Game Aids**: User-selectable aids including an "AI Art Historian" for
        inline visual aids (with thumbnails and lightbox) and an "ASCII Scene Renderer"
        for rogue-like maps.

-   **Planned Features (Hub Paradigm)**:
    -   **Library Hub**: A dedicated hub for all Knowledge Base (KB) management,
        replacing the former "Import" modal. It will feature a KB list, a
        content/asset explorer, and an integrated, multi-step **Ingestion Wizard**.
    -   **Party Hub**: A dedicated hub for creating and managing all parties and their
        characters, replacing the former "Party Manager" modal. It will include an
        **LLM-Powered Character Creator**.
    -   **Advanced Ingestion Workflow**: An enhanced workflow that allows for
        section-level review of a document *before* ingestion, including the
        ability to exclude sections and apply high-level content "cues".
    -   **Custom Asset Upload**: A feature within the Library Hub's asset explorer
        allowing users to add their own images to a KB via drag-and-drop.

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
└── dmme.cfg

---

## 3. Backend Design

### 3.1. `ppdf` - The Document Analysis & Reformatting Utility

`ppdf` is a powerful Python script designed for extracting, understanding, and
reformatting content from PDF files, especially those with complex, multi-column
layouts. It goes beyond simple text extraction by performing a multi-stage
analysis to identify the document's logical structure, then leverages a Large
Language Model (LLM) via Ollama to produce clean, readable, and stylistically
enhanced Markdown.

For the `dmme` project, `ppdf` will be enhanced to serve as a powerful, importable
library for the main application, exposing distinct modes for content and image
processing.

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
-   **Knowledge Ingestion**: Provides an API to support the frontend's **Library
    Hub**. It will invoke `ppdf` for a two-stage process: first to
    `analyze` a document's structure, and second to perform the final `ingestion`
    based on user-provided section configurations.
-   **RAG & LLM Logic**: The core RAG service will query the ChromaDB collections,
    leveraging semantic labels for precision. It will also contain the logic for
    generating Journal Recaps and ASCII Scene Maps.
-   **REST API**:
    -   **Campaigns**: Full CRUD APIs for managing campaigns.
    -   **Parties**: Full CRUD APIs for managing saved parties.
    -   **Knowledge**: APIs to orchestrate the multi-step ingestion process,
        including `POST /api/knowledge/analyze` and
        `POST /api/knowledge/<kb_name>/upload-asset`.
    -   **Gameplay**: `POST /api/game/command` (streams structured JSON with text,
        images, and maps).

### 3.3. `dmme-eval` - The Evaluation Utility

`dmme-eval` is a command-line utility for the systematic testing and evaluation of
both LLM prompts and core backend ingestion pipelines.

#### 3.3.1. CLI Structure
The tool uses a subcommand structure:
-   **`prompt`**: All functionality related to testing and evaluating system prompts.
-   **`ingest`**: All functionality related to testing parts of the ingestion pipeline.

#### 3.3.2. Prompt Evaluation Mode
This mode operates on **Test Suites**. A test suite is a directory containing a
prompt, its configuration, and a set of test scenarios. Key features include an
"LLM-as-a-Judge" evaluation and a `--compare` mode for side-by-side analysis.

#### 3.3.3. Ingestion Test Mode
This mode allows for isolated testing of backend services. The primary task is
`extract-images`, which runs the full image processing pipeline on a PDF and
generates a visual Markdown report for easy analysis.

---

## 4. Frontend Design (HTML/CSS/JavaScript)

The `dmme` frontend will be a single-page application built using a modern, modular
**ES6 JavaScript** structure. It will feature a modern, component-based design with
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

-   **Theming System**: The application will be themeable. The settings panel will
    allow users to choose from several pre-defined themes, including:
    -   Default
    -   Vibrant Focus
    -   High Contrast

### 4.2. UI/UX Paradigm

The application is organized around three distinct views, a contextual header, and
status bar navigation.

-   **Main Views:**
    1.  **Game View:** The immersive environment for active gameplay.
    2.  **Library View:** A dedicated hub for all Knowledge Base (KB) management.
    3.  **Party View:** A dedicated hub for creating and managing all parties and
        characters.

-   **Status Bar Navigation:** The primary method for switching between views will be
    a set of icons on the left side of the bottom status bar.

-   **Contextual Header:** The main header buttons will change based on the active view.
    -   **Game View Header:** `New Game` | `Load Game` | `Settings`
    -   **Library View Header:** `+ New Knowledge Base` | `Settings`
    -   **Party View Header:** `+ New Party` | `Settings`

### 4.3. Core Layouts

#### 4.3.1. Game View

The main gameplay interface will be a **two-column layout**:

-   **Left Panel (approx. 1/4 width):** A fixed-width side panel containing:
    -   An upper, scrollable **Party Status Panel** with an accordion view for character
        details.
    -   A lower, fixed **Dice Roller** component anchored to the bottom.
-   **Right Panel (approx. 3/4 width):** The main interaction area containing:
    -   **Knowledge Source Panel:** Displays active KBs for the session.
    -   **Narrative View:** The main log displaying the game's story.
    -   **Input Panel:** The text area for user commands.

#### 4.3.2. Library Hub

A two-panel layout for all KB-related tasks.

-   **Left Panel:** A searchable list of all created KBs.
-   **Right Panel (KB Inspector):** A tabbed interface for the selected KB, also
    containing the integrated **Ingestion Wizard**.

#### 4.3.3. Party Hub

A two-panel layout for all party and character management.

-   **Left Panel:** A searchable list of all created Parties.
-   **Right Panel (Party Inspector):** Displays the selected party's character
    roster and contains all UI for adding and editing characters.

### 4.4. Modals and Wizards

-   **New Game Wizard:** A modal launched from the Game View to guide the user
    through selecting a Game Mode and the required knowledge bases.
-   **DM's Insight Modal**: Triggered by an inline '🔍' button on an AI response, this
    modal displays the raw RAG context used for that specific generation.
-   **Image Lightbox Modal**: A simple, reusable modal overlay that displays a
    full-resolution image when a thumbnail in the narrative view is clicked.
-   **Settings Panel:** A multi-pane modal for application configuration. The RAG
    management pane will be removed in favor of the Library Hub.

---

## 5. Source Code Structure

The project is organized into a monorepo containing the main scripts at the
root, a shared `core` library, and dedicated libraries for each application.

`dmme_project/`
├── **ppdf.py**: Main entry point for the PDF utility (Reformatter & Indexer).
├── **dmme.py**: Main entry point to launch the Game Driver Flask server.
├── **dmme-eval.py**: A command-line utility for prompt engineering.
|
├── **core/**: A library for utilities shared across all scripts.
│   ├── `log_utils.py`: `RichLogFormatter` for consistent, colored console logging.
│   └── `tts.py`: The Text-to-Speech engine manager.
│
├── **ppdf_lib/**: All internal logic exclusive to the `ppdf` utility.
│   ├── `constants.py`: Stores presets for Reformatter mode.
│   ├── `extractor.py`: The core PDF layout and asset analysis engine.
│   └── `renderer.py`: `ASCIIRenderer` for visualizing page layout.
│
└── **dmme_lib/**: A self-contained package for the `dmme` web server.
    ├── `app.py`: The Flask app factory (`create_app`) and WebSocket setup.
    ├── `constants.py`: Stores DM persona presets for the game.
    ├── `api/`: Contains all Flask Blueprints for the REST API.
    ├── `services/`: Contains all backend business logic (SQLite, RAG, LLM, etc.).
    └── `frontend/`: All frontend code for the web UI, built with ES6 modules.

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

---

## 7. Potential Future Extensions

-   **Dynamic Music & Soundscapes**: An "AI DJ" system.
-   **Automated Combat Tracker**: A dedicated UI panel for combat.
-   **Interactive Map Viewer (Graphical)**: A feature to display graphical maps from
    PDFs with tokens.
-   **Adventure Creator Wizard**: A tool to help users write their own adventure modules.
