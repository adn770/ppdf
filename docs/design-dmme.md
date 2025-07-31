# Project: DMme (AI Dungeon Master Engine)

---

## 1. Core Concept

DMme is an AI-powered engine for playing tabletop role-playing games (TTRPGs).
The project is an evolution and extension of **`ppdf`**, a pre-existing, advanced
tool for PDF structure analysis and reformatting. The full system adds a game
driver (`dmme`) to leverage the knowledge bases created by `ppdf`.

The system uses a Retrieval-Augmented Generation (RAG) approach, drawing from
four distinct types of knowledge sources to ground the Large Language Model (LLM).
All components are designed to run locally using Ollama.

#### 1.1. Knowledge Source Types

The RAG system is built upon four types of knowledge bases:

1.  **Rules:** Contains the core mechanics of a specific TTRPG system (e.g., D&D 5e).
2.  **Setting:** Contains the lore, locations, and characters of a game world
    (e.g., Forgotten Realms), independent of a specific adventure.
3.  **Module:** A specific, pre-written adventure, which may optionally be linked
    to a particular `Setting`.
4.  **Adapter:** A reusable knowledge base that translates mechanics from a source
    rule system to a target rule system (e.g., D&D 5e to Pathfinder 2e).

#### 1.2. Game Modes

`dmme` supports two primary modes of play, selectable via a "New Game" wizard:

1.  **Adventure Module Mode:** The standard playstyle where the user selects a
    `Rules` system and a specific `Module` to play through.
2.  **Freestyle Mode:** A sandbox mode where the user selects a `Rules` system and
    a `Setting`. The LLM generates a unique adventure on the fly, using the
    `Setting` for context and potentially drawing inspiration from the entire
    corpus of available modules.

#### 1.3. Campaign and Session Structure

-   **Campaign**: This is the primary, persistent save object. A campaign encompasses
    the party, their inventory, and the entire history of their adventure. Users
    will save and load *Campaigns*.
-   **Session**: A single instance of gameplay within a campaign (e.g., a single
    evening's play).
-   **Journal Recap**: An LLM-generated, shareable summary of a single **Session**.
    When a campaign is loaded, the recap of the *previous* session will be
    displayed to remind players of what happened.

#### 1.4. `ppdf` Feature Set

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

#### 1.5. `dmme` Feature Set

-   **Planned Features**:
    -   **Knowledge Ingestion Wizard**: A web UI for creating knowledge bases from
        Markdown or PDF files, including a "human-in-the-loop" review and approval
        step for extracted images.
    -   **Campaign & Party Management**: Full CRUD functionality for creating, saving,
        and loading persistent campaigns and parties of characters.
    -   **LLM-Powered Character Creator**: A wizard to generate TTRPG characters from
        natural language descriptions.
    -   **Interactive Gameplay UI**: A two-column interface featuring a narrative log,
        player input, a party status panel, and a dice roller.
    -   **Advanced RAG System**: A sophisticated Retrieval-Augmented Generation
        system that leverages semantically labeled text chunks for precise,
        context-aware responses.
    -   **Multiple Game Modes**: Support for both pre-defined `Module` play and
        LLM-generated `Freestyle` play.
    -   **Optional Game Aids**: User-selectable aids including an "AI Art Historian" for
        inline visual aids and an "ASCII Scene Renderer" for rogue-like maps.

---

## 2. File System Structure

The application will create and manage a hidden directory at `~/.dmme/` to store all
generated data. A single SQLite file will serve as the primary database for all
application data besides the vector stores.

`~/.dmme/`
├── assets/
│   └── images/
│       └── <collection_name>/
│           └── ... (*Extracted image files & JSON metadata*)
├── chroma/
│   └── ... (*ChromaDB persistent vector storage*)
├── dmme.db         (*SQLite database for campaigns, sessions, parties, etc.*)
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
    `ContentBlock` that represent standard text, structured tables, or sidebars
   .
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
-   **Knowledge Ingestion**: Provides an API to support the frontend's **Import
    Knowledge Wizard**. It will programmatically invoke the enhanced `ppdf` library
    to handle PDF processing for both content and images.
-   **RAG & LLM Logic**: The core RAG service will query the ChromaDB collections,
    leveraging semantic labels for precision. It will also contain the logic for
    generating Journal Recaps and ASCII Scene Maps.
-   **REST API**:
    -   **Campaigns**: Full CRUD APIs for managing campaigns (e.g., `GET /api/campaigns`).
    -   **Parties**: Full CRUD APIs for managing saved parties.
    -   **Knowledge**: APIs to orchestrate the multi-step ingestion process for text
        and images.
    -   **Gameplay**: `POST /api/game/command` (streams structured JSON with text,
        images, and maps).

---

## 4. Frontend Design (HTML/CSS/JavaScript)

The `dmme` frontend will be a single-page application built using a modern, modular
**ES6 JavaScript** structure. It will feature a modern, component-based design with
a dark, themeable interface.

#### 4.1. Detailed Style Guide

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

#### 4.2. Core Layout

The main interface will be a **two-column layout**:

-   **Left Panel (approx. 1/4 width):** A fixed-width side panel containing:
    -   **Party Status Panel:** An accordion view displaying the current party's
        characters and stats. It will integrate a **"+" button** to launch a new
        "Party Creation Wizard."
    -   **Dice Roller:** A UI component for making common dice rolls (d4, d6, d20, etc.).

-   **Right Panel (approx. 3/4 width):** The main interaction area containing:
    -   **Knowledge Source Panel:** A horizontal panel displaying the active
        knowledge bases for the current session.
    -   **Narrative View:** The main log displaying the game's story, which can
        render text, inline images, and pre-formatted ASCII maps.
    -   **Input Panel:** The text area for user commands.

#### 4.3. Modals and Wizards

-   **Import Knowledge Wizard**: A multi-step modal for creating knowledge bases. It
    will handle PDF/Markdown uploads, knowledge type classification, metadata entry,
    and the new "human-in-the-loop" **Image Review** step (with a slideshow and
    editing tools).
-   **New Game Wizard:** A modal that guides the user through selecting a Game Mode
    and the required knowledge bases. It will include a step to select a saved
    party or launch the Party Creation Wizard.
-   **Party Creation Wizard**: A dedicated wizard for creating a new party and its
    characters, including an interface for the LLM-powered character generator.
-   **DM's Insight Modal**: Triggered by an inline '🔍' button on an AI response, this
    modal displays the raw RAG context used for that specific generation.
-   **Settings Panel:** A multi-pane modal for application configuration, including a
    toggle for optional game aids like the **ASCII Scene Renderer** and **Visual Aids**.

---

## 5. Source Code Structure

The project is organized into a monorepo containing the two main scripts at the
root, a shared `core` library, and dedicated libraries for each application.

`dmme_project/`
├── **ppdf.py**: Main entry point for the PDF utility (Reformatter & Indexer).
├── **dmme.py**: Main entry point to launch the Game Driver Flask server.
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

This implementation plan starts from the existing state of the `ppdf` codebase and
details the incremental steps to build the `dmme` application.

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
    -   **Goal**: Create the static HTML and CSS for the main two-column gameplay interface.
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

-   **Milestone 13: Connect UI to Gameplay Stub**
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

---

## 7. AI Assistant Procedures

This section outlines the collaborative workflows between the developer and the AI
assistant.

### 7.0. Main Rules
-   **Developer-Led Workflow**: The developer always initiates the activity.
-   **Providing Context**: The developer will provide the relevant project context.
-   **Confirmation and Readiness**: The assistant will confirm its understanding and
    signal its readiness.

### 7.1. Design & Refinement Process
-   The developer initiates a design discussion. The AI assistant provides an expert
    evaluation and proposes alternatives. The developer makes a decision, and the AI
    assistant creates an actionable plan.

### 7.2. Brainstorming Workflow
-   The developer kicks off a brainstorming session. The AI assistant generates a
    diverse range of ideas. The developer selects avenues for deeper exploration, and
    the assistant provides a more detailed breakdown.

### 7.3. Milestone Implementation Workflow
-   The AI assistant presents the next milestone. Upon developer approval, the
    assistant generates the **complete source code**.

### 7.4. Bug Fixing Workflow
-   The developer reports a bug. The assistant analyzes the issue and proposes a minimal
    bug-fix plan. Upon approval, the assistant generates the necessary code.

### 7.5. Code & Document Generation
-   **Complete Code**: All source code must be complete and self-contained.
-   **File Content Presentation**: The file's path must be clearly indicated.
-   **Line Length & Formatting**: Code and text should be formatted to a maximum of 95
    characters per line, with no trailing whitespace.
-   **Document Integrity**: Design documents must be presented in their complete form.
-   **Milestone Detail**: Milestones must include a `Goal`, `Description`, `Key
    Tasks`, and `Outcome`.
-   **Copy-Friendly Markdown**: Documents in Markdown must be delivered as a raw
    markdown code block.

---

## 8. Potential Future Extensions

This section serves as a wishlist for powerful features that are outside the scope of
the initial implementation plan but could be added in the future.

-   **Prompt Evaluation Tool (`dmme-eval`)**: A command-line utility for prompt
    engineering.
-   **Dynamic Music & Soundscapes**: An "AI DJ" system.
-   **Automated Combat Tracker**: A dedicated UI panel for combat.
-   **Interactive Map Viewer (Graphical)**: A feature to display graphical maps from
    PDFs with tokens.
-   **Adventure Creator Wizard**: A tool to help users write their own adventure modules.
