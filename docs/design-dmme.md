# Project: DMme (AI Dungeon Master Engine)

---

## 1. Core Concept

DMme is an AI-powered engine for playing tabletop role-playing games (TTRPGs). It is
composed of three primary components: the **ppdf** indexer, the **dmme** interactive
game driver, and the **dmme-eval** prompt evaluation tool. The system is designed for
both solo play and shared, multi-device sessions with full multilingual support.

The system uses a Retrieval-Augmented Generation (RAG) approach to ground the Large
Language Model (LLM) in the specific rules and story content of a given game module,
allowing it to act as a knowledgeable and consistent Dungeon Master (DM). All
components are designed to run locally using Ollama.

-   **`ppdf` (The Indexer):** A command-line tool that intelligently parses TTRPG
    adventure modules and rulebooks from PDF files. It uses a multi-step process
    involving text reconstruction and semantic labeling to create persistent,
    language-tagged knowledge bases in a vector database.
-   **`dmme` (The Game Driver):** A web-based application that provides a real-time,
    interactive interface for players. It uses source materials in multiple
    languages to produce a game session in a single, user-selected gameplay
    language. It manages the game session, which is persisted in a **SQLite database**,
    and features automatic session journaling and AI-powered visual aids.
-   **`dmme-eval` (The Evaluation Tool):** A command-line utility designed for prompt
    engineering. It runs a single game input against multiple DM persona prompts in a
    batch, generating comparative outputs to assist in fine-tuning the AI's
    behavior.

---

## 2. File System Structure

The application will create and manage a hidden directory at `~/.dmme/` to store all
generated data. A single SQLite file will serve as the primary database for all
application data besides the vector stores.

`~/.dmme/`
├── assets/
│   └── images/
│       └── <collection_name>/
│           └── ... (*Extracted image files*)
├── chroma/
│   └── ... (*ChromaDB persistent vector storage*)
├── dmme.db         (*SQLite database for sessions and journal entries*)
└── dmme.cfg

---

## 3. Backend Design

### 3.1. `ppdf` - The Indexer Utility (Python CLI)

The `ppdf` script is a dedicated utility with two primary modes of operation.

-   **Modes of Operation**:
    1.  **Reformatter Mode (Default)**: If the `--ingest` flag is not present, `ppdf`
        acts as a document conversion tool, using its LLM presets to reformat a PDF
        into a styled Markdown or plain text file.
    2.  **Indexer Mode**: If the `--ingest` flag is present, `ppdf` acts as a
        knowledge base creator for `dmme`.
-   **Indexer CLI**:
    -   `ppdf.py <pdf> --ingest --type <TYPE> --collection <NAME> --lang <LANG> [--image-processing <MODE>]`
-   **Smart Ingestion Process**:
    1.  **Layout & Asset Analysis**: Builds a structured data model and optionally
        extracts graphical assets from the PDF.
    2.  **Text Reconstruction**: Flattens and cleans the text using a `strict` LLM prompt.
    3.  **Smart Chunking**: Applies a top-down, structure-aware chunking strategy.
    4.  **Metadata Enhancement**: Each text chunk is processed by an LLM to add semantic
        labels.
    5.  **Image-to-Text (Optional)**: If image processing is enabled, a multimodal LLM
        generates rich descriptions for extracted images.
    6.  **Storage**: All text chunks and their metadata are stored in the specified
        ChromaDB collection.

### 3.2. `dmme` - The Game Driver (Python / Flask)

The `dmme` backend is a Flask server that links knowledge bases and synchronizes game
state across multiple clients.

-   **Command-Line Interface**: `dmme.py [--port <PORT>] [--ollama-url <URL>] [-v|-d ...]`
-   **Data Persistence**: All application data is stored in a unified **SQLite
    database** (`dmme.db`).
-   **Real-Time State Synchronization**: Uses **WebSockets** (via `Flask-SocketIO`) to
    broadcast game state updates to all connected clients in real-time.
-   **Multilingual LLM Integration**: Constructs a **language-aware prompt**, labeling
    retrieved context with its source language and instructing the LLM on the target
    output language.
-   **REST API**:
    -   **Setup & Management**: `POST /api/game/new`, `POST /api/game/save`, `GET
        /api/collections`, etc.
    -   **Gameplay**: `GET /api/game/command` (streams LLM response, RAG context, and
        visual aid data).
    -   **Visuals**: `POST /api/image/generate`.
    -   **Asset Management**: Endpoints to get asset disk usage and delete assets by
        collection.

### 3.3. `dmme-eval` - The Prompt Evaluation Utility (Python CLI)

A command-line tool for systematically testing and comparing different DM persona
prompts.

-   **Goal**: To assist in prompt engineering by generating side-by-side comparisons
    of LLM outputs.
-   **Command-Line Interface**: `dmme_eval.py --content <NAME> --rules <NAME> --input
    "<TEXT>" [--batch-presets]`

---

## 4. Frontend Design (HTML/CSS/JavaScript)

The `dmme` frontend is a single-page application built using a modern, modular **ES6
JavaScript** structure. Game setup is handled entirely through a UI wizard.

-   **New Game Wizard**: A multi-step modal that guides the user through creating a
    new campaign.
-   **DM View**: The primary interface for the person running the game. It includes:
    -   **Header Controls**: `+ New Game`, `Save`, `Load`, `📜 View Journal`, and
        `⚙️ Settings`.
    -   **Status Panel**: An accordion-style list of all party members.
    -   **Inventory Modal**: Accessed via a `🎒` button.
    -   **Narrative Panel**: Displays the game log, recaps, and inline visual aids.
    -   **DM's Insight Panel**: A toggleable panel that shows the raw RAG context
        retrieved for the last turn for debugging.
    -   **Input Panel**: A text area with up/down arrow key command history navigation,
        filtered per-character. Includes a `[🔊 On/Off]` button.
-   **Player View**: A simplified, focused interface for a second player.
-   **Modals & UI Feedback**:
    -   All long-running operations will display a clear visual **spinner** or
        "working..." indicator.
    -   **Settings Panel**: A multi-pane modal for application configuration.
        -   **General Tab**: For configuring LLM models and temperature.
        -   **Appearance Tab**: For themes and the "Immersive Content Display" setting.
        -   **RAG Management Tab**: For viewing, deleting, exporting, and importing
            knowledge bases.
        -   **Asset Management Tab**: For managing disk space used by extracted images.

---

## 5. Source Code Structure

The project is organized into a monorepo containing the three main scripts at the
root, a shared `core` library, and dedicated libraries for each application.

`dmme_project/`
├── **ppdf.py**: Main entry point for the PDF utility (Reformatter & Indexer).
├── **dmme.py**: Main entry point to launch the Game Driver Flask server.
├── **dmme_eval.py**: Main entry point for the Prompt Evaluation CLI.
|
├── **core/**: A library for utilities shared across all scripts.
│   ├── `log_utils.py`: `RichLogFormatter` for consistent, colored console logging.
│   └── `tts.py`: The Text-to-Speech engine manager.
│
├── **ppdf_lib/**: All internal logic exclusive to the `ppdf` utility.
│   ├── `constants.py`: Stores presets (`strict`, `creative`, etc.) for Reformatter
│   │   mode.
│   └── `extractor.py`: The core PDF layout and asset analysis engine.
│
└── **dmme_lib/**: A self-contained package for the `dmme` web server and eval tool.
    ├── `app.py`: The Flask app factory (`create_app`) and WebSocket setup.
    ├── `constants.py`: Stores DM persona presets for the game and eval tool.
    ├── `api/`: Contains all Flask Blueprints for the REST API.
    ├── `services/`: Contains all backend business logic (SQLite, RAG, LLM, etc.).
    └── `frontend/`: All frontend code for the web UI, built with ES6 modules.

---

## 6. Implementation Plan

This implementation plan is broken down into fine-grained, incremental milestones.

### Phase 1: Project Foundation

-   **Milestone 1: Repository Refactoring**
    -   **Goal**: Restructure the existing `ppdf` repository into the new `dmme_project`
        monorepo layout.
    -   **Description**: Prepares the codebase for new features while preserving git
        history.
    -   **Key Tasks**: Create new directories, `git mv` existing files, create
        placeholder scripts, and update all `import` statements.
    -   **Outcome**: A clean repository structure that matches the design document.

-   **Milestone 2: Shared Logging Infrastructure**
    -   **Goal**: Create a robust, shared logging utility for all components.
    -   **Description**: Establishes a consistent logging framework.
    -   **Key Tasks**: Create and integrate `core/log_utils.py` into all three main
        scripts with CLI arguments.
    -   **Outcome**: All scripts have a consistent, configurable logging system.

### Phase 2: The `ppdf` Indexer

-   **Milestone 3: `ppdf` CLI & ChromaDB Integration**
    -   **Goal**: Implement the `ppdf` Indexer Mode interface and connect it to ChromaDB.
    -   **Description**: Wires up the main arguments for `ppdf`'s Indexer Mode.
    -   **Key Tasks**: Implement `--ingest`, `--type`, `--collection`, `--lang`,
        `--system` argument parsing.
    -   **Outcome**: `ppdf` can create an empty, correctly configured ChromaDB
        collection.

-   **Milestone 4: `ppdf` Smart Chunking & LLM Enhancement**
    -   **Goal**: Implement the full smart ingestion pipeline and save to ChromaDB.
    -   **Description**: Finalizes the `ppdf` Indexer Mode by implementing the core
        content processing logic.
    -   **Key Tasks**: Implement structure-aware chunking and the two-step LLM
        enhancement chain.
    -   **Outcome**: `ppdf` is fully functional and can create a high-quality,
        RAG-optimized knowledge base.

### Phase 3: The `dmme` Backend

-   **Milestone 5: `dmme` Backend Skeleton & Database**
    -   **Goal**: Establish a runnable Flask server with its SQLite database foundation.
    -   **Description**: Creates the core structure of the game server and its database
        service layer.
    -   **Key Tasks**: Create the `dmme_lib` structure, SQLite schema, and
        `storage_service.py`.
    -   **Outcome**: A Flask server that can connect to and interact with the
        `dmme.db` file.

-   **Milestone 6: API for Wizard Support**
    -   **Goal**: Implement the backend APIs required to power the New Game Wizard.
    -   **Description**: Builds the endpoints that allow the frontend to discover
        available collections.
    -   **Key Tasks**: Implement the `GET /api/collections` endpoint in the backend.
    -   **Outcome**: The backend can provide the necessary data for the frontend wizard.

-   **Milestone 7: Core Gameplay RAG Logic**
    -   **Goal**: Implement the core RAG function that generates prompts.
    -   **Description**: Builds the brain of the DM, enabling it to process commands.
    -   **Key Tasks**: Implement the core RAG function that queries the collections and
        constructs a complete, language-aware prompt.
    -   **Outcome**: The backend can take a player input and generate a final prompt for
        the LLM.

### Phase 4: The `dmme` Frontend & Core Loop

-   **Milestone 8: Frontend Modular Setup & Shell**
    -   **Goal**: Create the visual shell and modular file structure for the frontend.
    -   **Description**: Builds the static user interface and establishes the modern
        JavaScript architecture.
    -   **Key Tasks**: Create the `frontend/src` directory. Write the `index.html`
        structure. Develop the `style.css`.
    -   **Outcome**: A visually complete, static web page is served.

-   **Milestone 9: New Game Wizard Implementation**
    -   **Goal**: Make the New Game Wizard fully interactive and functional.
    -   **Description**: Implements the full, multi-step logic for setting up and
        launching a new game session from the UI.
    -   **Key Tasks**: Implement the frontend logic for each step of the wizard,
        connecting it to the backend APIs.
    -   **Outcome**: A user can use the wizard to configure and successfully start a
        new game session.

-   **Milestone 10: Gameplay Integration & Streaming**
    -   **Goal**: Wire the UI to the backend to create a playable solo loop.
    -   **Description**: Implements the main gameplay interaction, streaming the AI's
        response to the narrative panel.
    -   **Key Tasks**: Implement the backend streaming endpoint. Connect the frontend
        input to this endpoint and render the SSE stream.
    -   **Outcome**: The full frontend-backend loop functions for a single player.

-   **Milestone 11: UI Quality of Life**
    -   **Goal**: Implement smaller UI/UX enhancements for a better user experience.
    -   **Description**: Adds features like command history navigation and spinners for
        long operations.
    -   **Key Tasks**: Implement the per-character up/down arrow command history. Add
        spinners to all long-running UI operations.
    -   **Outcome**: The command input is more efficient and the UI provides better
        feedback.

### Phase 5: Core Features

-   **Milestone 12: State Management & Autosave**
    -   **Goal**: Implement the full game state lifecycle with the database.
    -   **Description**: Makes the game persistent with automatic progress protection.
    -   **Key Tasks**: Implement save/load APIs to SQLite. Implement frontend logic for
        periodic autosaving.
    -   **Outcome**: A user can manage a party, save/resume their game, and is
        protected by autosaves.

-   **Milestone 13: Journaling & Session Recap**
    -   **Goal**: Implement the automatic diary and session recap features.
    -   **Description**: Adds the "AI Chronicler" functionality.
    -   **Key Tasks**: Implement the journal generation API, save entries to the DB,
        and display the last entry on game load.
    -   **Outcome**: The application automatically creates a narrative summary of
        gameplay.

-   **Milestone 14: LLM-Powered Character Creation**
    -   **Goal**: Implement the "Add Character" modal with LLM automation.
    -   **Description**: Builds the feature for creating characters from natural
        language prompts.
    -   **Key Tasks**: Implement the backend character generation API and the two-stage
        "prompt-then-edit" modal.
    -   **Outcome**: A user can generate a new party member using the LLM.

-   **Milestone 15: DM's Insight Panel**
    -   **Goal**: Implement the UI panel for viewing the RAG context.
    -   **Description**: Provides a "behind-the-scenes" look at the AI's reasoning for
        debugging and transparency.
    -   **Key Tasks**: Modify the backend streaming endpoint to also emit the RAG
        context. Build the frontend panel to display this context.
    -   **Outcome**: The DM can see the exact context the AI used for its last response.

### Phase 6: Advanced Features

-   **Milestone 16: "AI Art Historian" Feature**
    -   **Goal**: Implement the optional ingestion and display of graphical assets.
    -   **Description**: Enhances `ppdf` to extract images, use a multimodal LLM to
        generate descriptions, and adds the UI in `dmme` to display them.
    -   **Key Tasks**: Add `--image-processing` flag to `ppdf`. Implement image
        extraction and description generation. Add the frontend display logic.
    -   **Outcome**: The game can be enhanced with rich, contextual artwork.

-   **Milestone 17: Settings Panel & Management UIs**
    -   **Goal**: Implement the multi-pane settings modal.
    -   **Description**: Builds the user interface for configuring the application and
        managing its data.
    -   **Key Tasks**: Build the tabbed modal UI for General (Models), Appearance, RAG
        Management, and Asset Management.
    -   **Outcome**: The user can fully configure the application through a graphical
        interface.

-   **Milestone 18: Collection Import/Export**
    -   **Goal**: Implement a system for sharing knowledge bases.
    -   **Description**: Creates a workflow for exporting and importing collections and
        their associated assets as a single package.
    -   **Key Tasks**: Implement backend logic for packaging/unpackaging collections and
        assets into tarballs. Build the corresponding UI in the RAG Management panel.
    -   **Outcome**: Users can easily share their created knowledge bases with others.

-   **Milestone 19: Multilingual Support**
    -   **Goal**: Implement the full multilingual ingestion and gameplay pipeline.
    -   **Description**: Enables using source materials in different languages to
        produce a session in a single, chosen language.
    -   **Key Tasks**: Implement language-aware prompt construction and add language
        selectors to the UI.
    -   **Outcome**: The application can run a game using mixed-language sources into a
        single target language.

-   **Milestone 20: Multi-Player Support**
    -   **Goal**: Evolve the application to support multiple, synchronized clients.
    -   **Description**: Refactors the backend for real-time communication and creates
        the distinct UI views for DMs and Players.
    -   **Key Tasks**: Integrate `Flask-SocketIO`, broadcast state updates via
        WebSockets, and implement logic to serve DM vs. Player Views.
    -   **Outcome**: A second player can join a running game from another device.

### Phase 7: Finalization

-   **Milestone 21: Prompt Evaluation Tool (`dmme-eval`)**
    -   **Goal**: Build the `dmme-eval` command-line utility for prompt engineering.
    -   **Description**: Creates the auxiliary tool for batch-testing DM prompts.
    -   **Key Tasks**: Create `run_dmme_eval.py` and implement the batch-processing
        loop.
    -   **Outcome**: A user can run a single command to get side-by-side comparisons of
        different system prompts.

-   **Milestone 22: Finalization & Documentation**
    -   **Goal**: Prepare the project for distribution and use.
    -   **Description**: This final milestone involves polishing the application and
        writing comprehensive documentation.
    -   **Key Tasks**: Write a `README.md`, finalize CLI args, add a `LICENSE` file, and
        lock `requirements.txt`.
    -   **Outcome**: The project is well-documented, stable, and ready for use.

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

-   **Dynamic Music & Soundscapes**: An "AI DJ" system where a classifier LLM analyzes
    the narrative and triggers appropriate background music or sound effects from a
    curated local library.
-   **Automated Combat Tracker**: A dedicated UI panel for combat that tracks
    initiative, HP, and status effects, automatically updated by structured JSON
    output from the LLM.
-   **Interactive Map Viewer (Graphical)**: A feature to extract graphical maps from
    module PDFs and display them in the UI, with a token representing the party's
    location that the AI can update.
-   **Adventure Creator Wizard**: A new tool that acts as a "reverse `ppdf`," using an
    LLM to help a user write their own adventure module from an outline.
