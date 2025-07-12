#!/usr/bin/env python3
"""
ppdf: An advanced PDF text and structure extraction tool.

Overview
========
This script provides a comprehensive solution for extracting, understanding, and
reformatting content from PDF files, especially those with complex layouts like
multi-column RPG books. It goes beyond simple text extraction by performing a
multi-stage analysis to identify the document's logical structure.

The final, reconstructed text is then processed by a local Large Language Model
(LLM) via Ollama to produce a clean, readable, and stylistically enhanced
Markdown file.

Features
========
- Multi-Stage Analysis: Identifies page layouts, columns, titles, paragraphs,
  tables, and boxed notes.
- Logical Reconstruction: Reorders content from columns into a correct,
  single-flow reading order.
- Dynamic Chunk Sizing: Automatically adjusts processing chunk size based on the
  detected context window of the selected Ollama model.
- LLM-Powered Formatting: Uses an LLM to correct OCR/hyphenation errors and
  apply intelligent stylistic formatting (bold, italics).
- Real-time Audio Streaming: When using --speak, the LLM's response is
  converted to speech and played back live as it's being generated.
- Performance Epilogue: In verbose mode, provides detailed statistics on execution
  time, processing speed, and token counts retrieved directly from the Ollama API.
- Topical Debugging: Allows fine-grained debug logging for specific parts of
  the pipeline (e.g., 'layout', 'llm').
- Rich Terminal Output: Can render the final Markdown in real-time directly
  in the terminal using the `rich` library.
- Multiple Output Modes: Can save to a file, print to stdout, or convert to
  speech.

Installation
============
This script requires several external Python libraries. Core dependencies can
be installed with:

    pip install pdfminer.six requests rich

To enable the optional (and recommended) offline speech feature, also install:

    pip install "piper-tts==1.3.0" pyaudio

Processing Pipeline
===================
The script processes the PDF in a series of stages. The high-level flow transforms
the raw file into structured, readable output.

[ PDF File ] -> [ Stage 1: Layout Analysis ] -> [ Page Models ]
                                                      |
                                                      v
[ Page Models ] -> [ Stage 2: Content Structuring ] -> [ Structured Blocks ]
                                                      |
                                                      v
[ Structured Blocks ] -> [ Stage 3: Reconstruction ] -> [ Logical Sections ]
                                                      |
                                                      v
[ Logical Sections ] -> [ LLM Formatting ] -> [ Final Markdown & Audio Stream ]
                                                      |
                                                      v
          [ Final Markdown ] -> [ Output (File, stdout, Rich Stream) ]


Detailed Breakdown: Page to Content Blocks
------------------------------------------
The diagram below offers a more detailed look at the crucial first stages,
showing how a single page's physical layout is analyzed and segmented into
logical chunks. These chunks are then converted into structured objects (like
`Title`, `TableBlock`, or `ProseBlock`). Finally, the reconstruction phase
iterates through these typed blocks to build the final, logical `Section`
objects that make up the document.

[ LTPage Layout Object from PDFMiner ]
             |
             v
+---------------------------------+  <-- [Function: _analyze_single_page_layout]
|         PAGE MODEL N            |
|---------------------------------|
|  Zone 1 (y: Y1 -> Y2)           |  <-- A page is split into vertical zones.
|                                 |
|  +-----------+ +------------+   |
|  | Column 1  | | Column 2   |   |  <-- Each zone is split into columns.
|  | (bbox)    | | (bbox)     |   |      A bounding box is computed for each.
|  +-----------+ +------------+   |
+---------------------------------+
             |
             +---------------------> To a specific Column Processor
             |
+---------------------------------+  <-- [Function: _segment_column_into_blocks]
|       COLUMN'S LINES            |
|---------------------------------|
|  - Title: "SECTION TITLE"       |
|  - Hdr: "TABLE HEADER"          |  <-- Finds "separators" to define boundaries.
|  - ... (table content) ...      |
|  - Title: "NEXT SECTION TITLE"  |
+---------------------------------+
             |
             v
+---------------------------------+  <-- [Function: _segment_prose_and_tables]
| CHUNK 1: "SECTION TITLE" (Title)|
|---------------------------------|
| CHUNK 2: "TABLE HEADER" -> ...  |  <-- Creates bounded chunks of lines.
|---------------------------------|
| CHUNK 3: "NEXT TITLE..." (Title)|
+---------------------------------+
             |
             v
+---------------------------------+  <-- Chunks are instantiated as typed objects.
| Structured Blocks:              |
|  - Title(text="...")            |
|  - TableBlock(...)              |
|  - Title(text="...")            |
+---------------------------------+
             |
             v
+---------------------------------+  <-- [Function: _build_sections_from_models]
|     LOGICAL RECONSTRUCTION      |
|---------------------------------|
| Find Title block ->             |
|   Start new Section(...)        |  <-- Assembles blocks into logical sections
| Find TableBlock ->              |      containing paragraphs.
|   Add Paragraph to Section      |
+---------------------------------+
             |
             v
[ Final list of Section objects ]

"""

import argparse
import json
import logging
import os
import queue
import re
import sys
import threading
import time
from collections import Counter

# --- Dependency Imports ---
# Third-party libraries that need to be installed via pip
try:
    import requests
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTRect, LTTextLine, LTImage
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
except ImportError as e:
    print(f"Error: Missing required library. -> {e}")
    print("Please install all core dependencies with:")
    print("pip install pdfminer.six requests rich")
    sys.exit(1)

# Gracefully handle optional TTS dependencies
try:
    import pyaudio
    from piper import PiperVoice
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False


# --- PROMPT TEXT CONSTANTS ---

PROMPT_SYSTEM = """\
== PRIMARY DIRECTIVES ==

-- Content & Persona Rules --
1. CONTENT & PERSONA:
   You are a data-processing engine. Your ONLY function is to reformat
   the text provided. Your response MUST be 100% derived from the
   source text, preserving all original phrasing and detail. You MUST
   NOT rephrase, rewrite, summarize, add, invent, interpret, or
   explain the content.
2. LANGUAGE:
   You MUST respond in the original language of the text found in the
   DOCUMENT block.

-- Formatting & Structure Rules --
3. FINAL OUTPUT FORMAT:
   Your final generated response MUST end with a single empty line. This
   is a critical technical requirement for downstream processing.
4. OUTPUT CONTENT:
   You MUST NOT include any XML tags like `<thinking>` or `<markdown>`
   in the output. Provide ONLY the final, clean Markdown content.

== SEQUENTIAL WORKFLOW & RULES ==

You are a silent, non-sentient data formatting engine. Your task is to
take the text provided in the "--- BEGIN DOCUMENT ---" block and reformat
it by performing the following two roles in sequence. The roles are
distinct and must not overlap their duties.

1. First, you will act as the "Document Editor".
   Your goal is to produce a structurally perfect version of the text
   with all paragraphs, lists, and tables correctly formatted. The
   output of this stage should be stylistically plain, with the
   exception of the specific rules below.

   Editor's Rulebook:
    - No Self-Reflection: Do not add notes or explanations about the
      edits you have made. Your output must only be the final document.
    - Headings: Preserve the structural integrity and level (e.g., '#', '##')
      of all heading lines. You may correct obvious, single-character
      typographical errors in the heading's text, but you MUST NOT
      rephrase it or apply any stylistic formatting like bold or italics.
    - Paragraphs: Merge broken text lines to form natural, flowing
      paragraphs.
    - Lists: Preserve bulleted lists using standard Markdown ("*" or "-").
    - Corrections: Correct obvious typographical errors, unnatural
      hyphenation, and misplaced commas. Ensure correct final punctuation.
    - Stat Blocks: Format RPG stat blocks as a single, dense paragraph.
    - Introductory Phrases: If a paragraph begins with a descriptive label
      that ends in a colon, format that entire label (including the
      colon) in bold.
    - Tables: Preserve the exact structure of any Markdown tables.

2. Second, you will now act as the "RPG Expert".
   Your goal is to take the clean, structurally-correct text from the
   Editor and apply a final layer of TTRPG-specific stylistic
   formatting according to the "Expert's Style Guide" below.

   Expert's Style Guide:
    - Forbidden Application: Do NOT apply bold formatting to text that is
      a heading (e.g., lines starting with '#').
    - Italics: Format entire paragraphs of descriptive, atmospheric text
      in italics. This applies to scene-setting descriptions and blocks
      of in-world text like poems or inscriptions.
    - Bold: Apply "**bold**" formatting to genre-specific terms, including:
        - Creature, NPC, and character names.
        - Specific named places, areas, and zones.
        - Named items, potions, artifacts, weapons, and armor.
        - Spell names.
        - Dice notation (e.g., "**d20**", "**3d6**").
        - Specific game actions, checks, and saves (e.g., "**attack roll**").

== FINAL CHECK ==

Before providing the final output, ensure it is the complete, reformatted
document and that you have followed all PRIMARY DIRECTIVES.
"""


# --- CUSTOM LOGGING FORMATTER ---
class RichLogFormatter(logging.Formatter):
    """A custom logging formatter for rich, colorful, and aligned console output."""

    def __init__(self, use_color=False):
        super().__init__()
        if use_color:
            # ANSI escape codes for 256-color terminal
            self.COLORS = {
                logging.DEBUG:    '\033[38;5;252m',  # Light Grey
                logging.INFO:     '\033[38;5;111m',  # Pastel Blue
                logging.WARNING:  '\033[38;5;229m',  # Pale Yellow
                logging.ERROR:    '\033[38;5;210m',  # Soft Red
                logging.CRITICAL: '\033[38;5;217m',  # Light Magenta
            }
            self.BOLD = '\033[1m'
            self.RESET = '\033[0m'
        else:
            self.COLORS = {level: '' for level in [
                logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR,
                logging.CRITICAL
            ]}
            self.BOLD = ''
            self.RESET = ''

    def format(self, record):
        """Formats a log record into a colored, aligned string."""
        color = self.COLORS.get(record.levelno, self.RESET)
        level_name = record.levelname[:5]  # Truncate level name
        topic = record.name.split('.')[-1][:5]  # Truncate topic name

        # The prefix for each line of the log message
        prefix = (
            f"{color}{level_name:<5}{self.RESET}"
            f":{self.BOLD}{topic:<5}{self.RESET}: "
        )

        # Format the message and apply the prefix to each line
        message = record.getMessage()
        lines = message.split('\n')
        formatted_lines = [f"{prefix}{line}" for line in lines]

        return "\n".join(formatted_lines)

# --- LOGGING SETUP ---
# Define topic-specific loggers for granular debug control
log_layout = logging.getLogger("ppdf.layout")
log_structure = logging.getLogger("ppdf.structure")
log_reconstruct = logging.getLogger("ppdf.reconstruct")
log_llm = logging.getLogger("ppdf.llm")
log_tts = logging.getLogger("ppdf.tts")


# --- TTS STREAMING MANAGER ---
class TTSManager:
    """
    Manages real-time text-to-speech synthesis and playback using Piper and PyAudio.
    This class handles voice model loading, audio stream setup, and processing
    text chunks into audible speech in a separate thread.
    """
    _SENTENCE_END = re.compile(r'(?<=[.!?])\s')

    def __init__(self, lang: str):
        """
        Initializes the TTS manager, loads the voice model, and sets up the audio stream.

        Args:
            lang (str): The language code for the voice model to use (e.g., 'en', 'es').
        """
        self.app_log = logging.getLogger("ppdf")
        self.voice = self._get_piper_engine(lang)
        if not self.voice:
            raise RuntimeError("Failed to initialize Piper TTS engine.")

        self.pyaudio_instance = pyaudio.PyAudio()

        # Safely get audio parameters with sensible fallbacks.
        sample_rate = getattr(self.voice.config, 'sample_rate', 22050)
        num_channels = getattr(self.voice.config, 'num_channels', 1)
        # The original error is on sample_width. We default to 2 for 16-bit audio.
        sample_width = getattr(self.voice.config, 'sample_width', 2)

        log_tts.debug(
            "Initializing PyAudio stream with: Rate=%d, Channels=%d, Width=%d",
            sample_rate, num_channels, sample_width
        )

        self.stream = self.pyaudio_instance.open(
            format=self.pyaudio_instance.get_format_from_width(sample_width),
            channels=num_channels,
            rate=sample_rate,
            output=True
        )

        self.text_queue = queue.Queue()
        self.processing_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.processing_thread.start()
        self.text_buffer = ""

    def _get_piper_engine(self, lang: str):
        """
        Checks for a cached Piper TTS model and downloads it if not found.
        Models are cached in ~/.cache/ppdf/models/.
        """
        MODELS_CONFIG = {
            "en": {"model": "en_US-lessac-medium.onnx", "url_base": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/"},
            "es": {"model": "es_ES-sharvard-medium.onnx", "url_base": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/sharvard/medium/"},
            "ca": {"model": "ca_ES-upc_ona-medium.onnx", "url_base": "https://huggingface.co/rhasspy/piper-voices/resolve/main/ca/ca_ES/upc_ona/medium/"}
        }
        config = MODELS_CONFIG.get(lang)
        if not config:
            self.app_log.error(f"Language '{lang}' is not supported for speech synthesis.")
            return None

        cache_dir = os.path.expanduser("~/.cache/ppdf/models")
        os.makedirs(cache_dir, exist_ok=True)
        model_path = os.path.join(cache_dir, config["model"])

        for path_suffix in [config["model"], f"{config['model']}.json"]:
            path = os.path.join(cache_dir, path_suffix)
            if not os.path.exists(path):
                filename = os.path.basename(path)
                self.app_log.info(f"Performing one-time download for '{filename}'...")
                try:
                    url = config["url_base"] + path_suffix
                    with requests.get(url, stream=True) as r:
                        r.raise_for_status()
                        with open(path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    self.app_log.info(f"Successfully downloaded {filename}")
                except requests.exceptions.RequestException as e:
                    self.app_log.error(f"Failed to download voice model component: {e}")
                    if os.path.exists(path): os.remove(path)
                    return None
        return PiperVoice.load(model_path)

    def add_text(self, text: str):
        """
        Adds a chunk of text to the buffer, processing and queueing complete sentences.
        """
        # Clean markdown and other artifacts before synthesizing
        clean_text = re.sub(r'#+\s*|[\*_`]|<[^>]+>', '', text, flags=re.DOTALL)
        self.text_buffer += clean_text

        while True:
            match = self._SENTENCE_END.search(self.text_buffer)
            if match:
                sentence = self.text_buffer[:match.end()]
                self.text_buffer = self.text_buffer[match.end():]
                if sentence.strip():
                    log_tts.debug("Queueing sentence: '%s'", sentence.strip())
                    self.text_queue.put(sentence)
            else:
                break

    def _process_queue(self):
        """Worker thread function to process sentences from the queue and play audio."""
        while True:  # Loop forever until the sentinel is received
            try:
                sentence = self.text_queue.get()  # Block until an item is available
                if sentence is None:  # This is the "poison pill"
                    log_tts.debug("Sentinel received, shutting down TTS worker thread.")
                    self.text_queue.task_done()
                    break  # Exit the loop

                # voice.synthesize() returns a generator of AudioChunk objects.
                audio_generator = self.voice.synthesize(sentence)
                for audio_chunk in audio_generator:
                    # Access the correct attribute to get the raw bytes.
                    self.stream.write(audio_chunk.audio_int16_bytes)

                self.text_queue.task_done()
            except Exception as e:
                log_tts.error("Fatal error in TTS processing thread, stopping TTS: %s", e)
                break  # Exit the loop on any other fatal error

    def finalize(self):
        """
        Signals that no more text will be added. Processes any remaining buffered text.
        """
        if self.text_buffer.strip():
            log_tts.debug("Queueing final buffer: '%s'", self.text_buffer.strip())
            self.text_queue.put(self.text_buffer)
            self.text_buffer = ""

    def cleanup(self):
        """
        Waits for the queue to finish, sends a sentinel to stop the thread,
        then closes the audio stream and PyAudio instance.
        """
        log_tts.info("Finalizing TTS, waiting for audio queue to finish...")
        self.finalize()
        self.text_queue.join()  # Wait for all real sentences to be processed

        # Put the "poison pill" on the queue to stop the worker thread
        self.text_queue.put(None)

        self.processing_thread.join(timeout=2)  # Wait for the thread to exit

        if self.stream.is_active():
            self.stream.stop_stream()
        self.stream.close()
        self.pyaudio_instance.terminate()
        log_tts.info("TTS Manager cleaned up successfully.")


# --- DOCUMENT MODEL CLASSES (LOGICAL HIERARCHY) ---
"""
Data Model Relationship Diagram
===============================
This diagram illustrates how the different data classes relate to each other,
from the highest-level logical objects to the lowest-level physical ones.

[ Section ]
    |
    +-- contains [ Paragraph ]  (Logical stream for the LLM)

==================== PHYSICAL LAYOUT HIERARCHY ====================

[ PageModel ]
    |
    +-- contains [ LayoutZone ] (inherits: BoundedElement)
          |
          +-- contains [ Column ]
                |
                +-- contains [ Title ]          (inherits: BoundedElement)
                |
                +-- contains [ ContentBlock ]   (inherits: BoundedElement)
                        |
                        +-- (is a) [ ProseBlock ]
                        |
                        +-- (is a) [ BoxedNoteBlock ]
                        |
                        +-- (is a) [ TableBlock ]
                              |
                              +-- contains [ TableRow ]
                                    |
                                    +-- contains [ TableCell ]
"""

class BoundedElement:
    """Base class for any layout element with a computed bounding box."""
    pass


class ContentBlock(BoundedElement):
    """
    A generic block of content lines from the PDF.

    Args:
        lines (list): A list of pdfminer LTTextLine objects.

    Attributes:
        lines (list): The LTTextLine objects comprising this block.
        bbox (tuple): The computed bounding box (x0, y0, x1, y1) for the block.
    """
    def __init__(self, lines):
        self.lines = lines
        self.bbox = PDFTextExtractor._compute_bbox(lines) if lines else (0, 0, 0, 0)


class ProseBlock(ContentBlock):
    """A block of content identified as standard prose text."""
    pass


class TableCell:
    """
    Represents a single cell in a table, containing multiple lines of text.

    Args:
        text_lines (list[str]): The lines of text found within this cell.

    Attributes:
        text_lines (list[str]): The stored lines of text.
    """
    def __init__(self, text_lines):
        self.text_lines = text_lines

    @property
    def text(self) -> str:
        """Returns the raw, multi-line text content of the cell for display."""
        return "\n".join(self.text_lines)

    @property
    def pre_processed_text(self) -> str:
        """
        Returns pre-processed single-line text for the LLM.

        This method fixes hyphenation across lines and joins them into a single,
        comma-separated string, making it easier for the LLM to parse table rows.
        """
        if not self.text_lines:
            return ""

        # First pass: merge hyphenated lines
        merged_lines = []
        i = 0
        while i < len(self.text_lines):
            line = self.text_lines[i].strip()
            # Check if line ends with a hyphen and there is a next line to merge
            if line.endswith('-') and (i + 1) < len(self.text_lines):
                next_line = self.text_lines[i+1].strip()
                # Merge the current line (without hyphen) with the next line
                merged_line = line[:-1] + next_line
                # Use a temporary list to handle potential chain-hyphenation
                temp_new_lines = [merged_line] + self.text_lines[i+2:]
                # Recurse on the newly formed line list
                return TableCell(temp_new_lines).pre_processed_text
            else:
                merged_lines.append(line)
            i += 1

        # Second pass: join the (now de-hyphenated) lines with a comma and space
        return ", ".join(line for line in merged_lines if line)


class TableRow:
    """
    A single row in a table, containing multiple TableCell objects.

    Args:
        cells (list[TableCell]): A list of TableCell objects for this row.
    """
    def __init__(self, cells):
        self.cells: list[TableCell] = cells


class TableBlock(ContentBlock):
    """
    A structured representation of a table, containing rows and cells.

    Args:
        all_lines (list): All LTTextLine objects associated with the table.
        rows (list[TableRow]): A list of the parsed TableRow objects.
    """
    def __init__(self, all_lines, rows):
        super().__init__(all_lines)
        self.rows: list[TableRow] = rows
        self.num_cols = len(rows[0].cells) if (
            rows and hasattr(rows[0], 'cells')) else 0


class BoxedNoteBlock(ContentBlock):
    """
    A block of content identified as being enclosed in a graphical box.

    Args:
        text (str): The identified title of the boxed note.
        all_lines (list): All LTTextLine objects within the box.
        title_lines (list): The specific lines identified as the title.
    """
    def __init__(self, text, all_lines, title_lines):
        super().__init__(all_lines)
        self.text = text
        self.title_lines = title_lines


class Title(BoundedElement):
    """
    Represents a title or heading element.

    Args:
        text (str): The formatted text of the title.
        lines (list): The raw LTTextLine objects making up the title.
    """
    def __init__(self, text, lines):
        self.text, self.lines = text, lines
        self.bbox = PDFTextExtractor._compute_bbox(lines)


class Column:
    """
    Represents a single column of text on a page.

    Args:
        lines (list): The LTTextLine objects belonging to this column.
        bbox (tuple): The bounding box of the column.

    Attributes:
        blocks (list): A list of ContentBlock objects parsed from the column.
    """
    def __init__(self, lines, bbox):
        self.lines, self.bbox, self.blocks = lines, bbox, []


class LayoutZone(BoundedElement):
    """
    Represents a vertical region of a page with a consistent column layout.

    Args:
        lines (list): The LTTextLine objects within this zone.
        bbox (tuple): The bounding box of the zone.
    """
    def __init__(self, lines, bbox):
        self.lines = lines
        self.bbox = bbox
        self.columns = []


class PageModel:
    """
    A structured representation of a single PDF page's physical layout.

    Args:
        layout (LTPage): The pdfminer LTPage layout object for this page.

    Attributes:
        page_num (int): The one-based page number.
        title (Title | None): The main title found at the top of the page.
        zones (list[LayoutZone]): A list of vertical layout zones on the page.
        body_font_size (float): The most common font size on the page.
        page_type (str): Classification of the page ('content', 'art', etc.).
        rects (list[LTRect]): A list of detected graphical rectangles on the page.
    """
    def __init__(self, layout):
        self.page_layout, self.page_num = layout, layout.pageid
        self.title, self.zones = None, []
        self.body_font_size = 12
        self.page_type = "content"  # 'content', 'cover', 'credits', 'art'
        self.rects = []  # Store all visible rectangles for analysis


class Paragraph:
    """
    Represents a logical paragraph of text, reconstructed from various blocks.

    Args:
        lines (list[str]): The text lines that form the paragraph.
        page (int): The page number where this paragraph starts.
        is_table (bool): Flag indicating if this paragraph is a table.
        llm_lines (list[str] | None): Special formatting for the LLM (e.g., Markdown table).
    """
    def __init__(self, lines, page, is_table=False, llm_lines=None):
        self.lines, self.page_num, self.is_table = lines, page, is_table
        self.llm_lines = llm_lines

    def get_text(self):
        """Returns the full text for display, preserving line breaks."""
        return '\n'.join(self.lines)

    def get_llm_text(self):
        """Returns the LLM-specific text (Markdown for tables, standard)."""
        if self.is_table and self.llm_lines:
            return '\n'.join(self.llm_lines)
        return self.get_text()


class Section:
    """
    Represents a logical section of a document, such as a chapter or topic.
    A section has a title and contains one or more paragraphs.

    Args:
        title (str | None): The title of the section.
        page (int | None): The page number where the section begins.
    """
    def __init__(self, title=None, page=None):
        self.title, self.paragraphs = title, []
        self.page_start, self.page_end = page, page
        self._last_add_was_merge = False

    def add_paragraph(self, p: Paragraph):
        """
        Adds a Paragraph object to the section.

        This method contains logic to merge a new paragraph with the previous one
        if the previous paragraph seems to be unfinished (e.g., ends in a comma).
        """
        if (self.last_paragraph and not self._last_add_was_merge and
                self._paragraph_is_unfinished(self.last_paragraph)):
            log_reconstruct.debug("Merging unfinished paragraph with the next.")
            self.last_paragraph.lines.extend(p.lines)
            if p.page_num:
                self.page_end = max(self.page_end or p.page_num, p.page_num)
            self._last_add_was_merge = True
        else:
            self.paragraphs.append(p)
            if p.page_num:
                self.page_end = max(self.page_end or p.page_num, p.page_num)
            self._last_add_was_merge = False

    def _paragraph_is_unfinished(self, p: Paragraph) -> bool:
        """
        Checks if a paragraph seems to be unfinished based on its last line.

        A paragraph is considered unfinished if it ends with certain punctuation
        (like ',', ':', ';') or has unbalanced brackets.

        Returns:
            bool: True if the paragraph appears unfinished.
        """
        if not p.lines or p.is_table:
            return False
        last_line = p.lines[-1].strip()
        if not last_line:
            return False
        if last_line.endswith((':', ';', ',')):
            return True
        brackets = {'(': ')', '[': ']', '{': '}'}
        stack = []
        for char in last_line:
            if char in brackets.keys():
                stack.append(char)
            elif char in brackets.values():
                if stack and brackets[stack[-1]] == char:
                    stack.pop()
        return bool(stack)

    def get_text(self):
        """Returns the full display text of all paragraphs in the section."""
        return "\n\n".join(p.get_text() for p in self.paragraphs)

    def get_llm_text(self):
        """Returns the full LLM-ready text of all paragraphs in the section."""
        return "\n\n".join(p.get_llm_text() for p in self.paragraphs)

    @property
    def last_paragraph(self):
        """Returns the last paragraph in the section, or None."""
        return self.paragraphs[-1] if self.paragraphs else None


class PDFTextExtractor:
    """
    Extracts structured text from a PDF file using a multi-stage process.

    This class orchestrates the entire pipeline from PDF parsing to the creation
    of logical Section objects.
    """
    def __init__(self, pdf_path, num_cols="auto", rm_footers=True, style=False):
        """
        Initializes the PDFTextExtractor.

        Args:
            pdf_path (str): The file path to the PDF.
            num_cols (str): The number of columns to assume ('auto' or a number).
            rm_footers (bool): Whether to attempt footer removal.
            style (bool): Whether to preserve bold/italic styling.
        """
        self.pdf_path = pdf_path
        self.num_columns_str = num_cols
        self.remove_footers = rm_footers
        self.keep_style = style
        self.page_models = []
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

    @staticmethod
    def _to_roman(n):
        """Converts an integer to a Roman numeral for section continuation."""
        if not 1 <= n <= 3999:
            return str(n)
        val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
        syb = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
        roman_num, i = '', 0
        while n > 0:
            for _ in range(n // val[i]):
                roman_num += syb[i]
                n -= val[i]
            i += 1
        return roman_num

    @staticmethod
    def _compute_bbox(lines):
        """
        Computes a bounding box enclosing all given pdfminer layout elements.

        Args:
            lines (list): A list of pdfminer objects with bbox attributes.

        Returns:
            tuple: A bounding box (x0, y0, x1, y1), or (0,0,0,0) if no lines.
        """
        if not lines:
            return 0, 0, 0, 0
        lines = [l for l in lines if l]
        if not lines or any(not hasattr(l, 'x0') for l in lines):
            return 0, 0, 0, 0
        return (min(l.x0 for l in lines), min(l.y0 for l in lines),
                max(l.x1 for l in lines), max(l.y1 for l in lines))

    def extract_sections(self, pages_to_process=None):
        """
        Main orchestration method to perform all analysis and reconstruction.

        Args:
            pages_to_process (set | None): A set of page numbers to process. If None,
                all pages are processed.

        Returns:
            list[Section]: A list of the final, reconstructed Section objects.
        """
        self._analyze_page_layouts(pages_to_process)
        return self._build_sections_from_models()

    def _analyze_page_layouts(self, pages_to_process=None):
        """
        Performs Stage 1 (layout) and Stage 2 (content) analysis on the PDF.

        This method first analyzes the layout of all pages (Stage 1), then
        iterates through the resulting models to structure the content (Stage 2),
        ensuring a clean, sequential log output.

        Args:
            pages_to_process (set | None): A set of page numbers to process.
        """
        self.page_models = []
        all_pdf_pages = list(extract_pages(self.pdf_path))
        content_pages_to_structure = []

        # --- STAGE 1: LAYOUT ANALYSIS ---
        logging.getLogger("ppdf").info("--- Stage 1: Analyzing Page Layouts ---")
        for page_layout in all_pdf_pages:
            if pages_to_process and page_layout.pageid not in pages_to_process:
                continue

            # This call performs the core Stage 1 analysis for a single page.
            page_model = self._analyze_single_page_layout(page_layout)
            self.page_models.append(page_model)
            if page_model.page_type == 'content':
                content_pages_to_structure.append(page_model)

        # --- STAGE 2: CONTENT STRUCTURING ---
        logging.getLogger("ppdf").info(
            "--- Stage 2: Structuring Content from Page Models ---"
        )
        for page_model in content_pages_to_structure:
            log_structure.info("Structuring content for Page %d", page_model.page_num)
            for z_idx, zone in enumerate(page_model.zones):
                for c_idx, col in enumerate(zone.columns):
                    log_structure.debug(
                        "Analyzing Page %d, Zone %d, Col %d",
                        page_model.page_num, z_idx + 1, c_idx + 1
                    )
                    col.blocks = self._segment_column_into_blocks(
                        col.lines, page_model.body_font_size, col.bbox,
                        page_model.rects
                    )

    def _classify_page_type(self, layout, lines, images):
        """
        Classifies a page as 'cover', 'credits', 'art', or 'content'.

        This uses heuristics like image coverage, line count, and keywords.

        Args:
            layout (LTPage): The page layout object.
            lines (list): All text lines on the page.
            images (list): All image objects on the page.

        Returns:
            str: The classified page type.
        """
        log_layout.debug("--- Page Classification ---")
        num_lines, num_images = len(lines), len(images)
        log_layout.debug(
            "  - Total lines: %d, Total images: %d", num_lines, num_images
        )
        if num_images > 0:
            page_area = layout.width * layout.height
            image_area = sum(img.width * img.height for img in images)
            if page_area > 0 and (image_area / page_area) > 0.7:
                log_layout.debug(
                    "  - Decision: Large image coverage (%.2f%%). -> 'art'",
                    (image_area/page_area)*100
                )
                return 'art'
        if num_lines == 0:
            log_layout.debug("  - Decision: No lines found. -> 'art'")
            return 'art'
        if num_lines < 5:
            log_layout.debug(
                "  - Decision: Very few lines (%d). -> 'cover'", num_lines
            )
            return 'cover'
        full_text = " ".join(l.get_text() for l in lines).lower()
        credit_keywords = ['créditos', 'copyright', 'editor', 'traducción',
                           'maquetación', 'cartógrafos', 'ilustración', 'isbn',
                           'depósito legal']
        found_keywords = [kw for kw in credit_keywords if kw in full_text]
        keyword_hits = len(found_keywords)
        log_layout.debug(
            "  - Keyword check: Found %d hits. (%s)", keyword_hits,
            ", ".join(found_keywords) if found_keywords else "None"
        )
        if keyword_hits >= 3:
            log_layout.debug(
                "  - Decision: Sufficient keyword hits (>=3). -> 'credits'"
            )
            return 'credits'
        body_font_size = self._get_page_body_font_size(
            lines, default_on_fail=False
        )
        if body_font_size:
            title_like_lines = sum(
                1 for l in lines if self._get_font_size(l) > body_font_size * 1.2
            )
            title_ratio = title_like_lines / num_lines if num_lines > 0 else 0
            log_layout.debug(
                "  - Title-like line ratio: %.2f (%d of %d lines)",
                title_ratio, title_like_lines, num_lines
            )
            if title_ratio > 0.5:
                log_layout.debug(
                    "  - Decision: High ratio of title-like lines. -> 'cover'"
                )
                return 'cover'
        log_layout.debug("  - Decision: No special type detected. -> 'content'")
        log_layout.debug("---------------------------")
        return 'content'

    def _analyze_single_page_layout(self, layout):
        """
        Analyzes a single page's layout to produce a PageModel.

        This involves finding all text/image/rect elements, classifying the page,
        detecting titles and footers, and splitting the page into vertical zones
        and columns. This corresponds to "Stage 1" of the processing pipeline.

        Args:
            layout (LTPage): The pdfminer LTPage object to analyze.

        Returns:
            PageModel: A structured model of the page layout.
        """
        page = PageModel(layout)
        logging.getLogger("ppdf").info(
            "Analyzing Page Layout %d...", page.page_num
        )
        all_lines = sorted(
            self._find_elements_by_type(layout, LTTextLine),
            key=lambda x: (-x.y1, x.x0)
        )
        images = self._find_elements_by_type(layout, LTImage)
        all_rects = self._find_elements_by_type(layout, LTRect)
        page.rects = [
            r for r in all_rects if r.linewidth > 0 and r.width > 10 and r.height > 10
        ]
        page.page_type = self._classify_page_type(layout, all_lines, images)
        logging.getLogger("ppdf").info(
            "Page %d classified as: %s", page.page_num, page.page_type
        )
        if page.page_type != 'content' or not all_lines:
            return page
        page.body_font_size = self._get_page_body_font_size(all_lines)
        footer_thresh = self._get_footer_threshold_dynamic(
            all_lines, layout, page.body_font_size
        )
        content_lines = [l for l in all_lines if l.y0 > footer_thresh]
        if not self.remove_footers:
            content_lines = list(all_lines)

        page.title, title_lines = self._detect_page_title(
            content_lines, layout, page.body_font_size
        )
        content_lines = [l for l in content_lines if l not in title_lines]
        rect_breaks = {
            r.y0 for r in page.rects if r.width > layout.width * 0.7
        }
        rect_breaks.update(
            r.y1 for r in page.rects if r.width > layout.width * 0.7
        )
        breakpoints = {layout.y0, layout.y1, *rect_breaks}
        sorted_breaks = sorted(list(breakpoints), reverse=True)
        log_layout.debug(
            "Page %d: Found %d vertical zone breakpoints at %s", page.page_num,
            len(sorted_breaks), [f"{y:.2f}" for y in sorted_breaks]
        )
        for i in range(len(sorted_breaks) - 1):
            y_top, y_bottom = sorted_breaks[i], sorted_breaks[i+1]
            if y_top - y_bottom < page.body_font_size:
                continue
            zone_bbox = (layout.x0, y_bottom, layout.x1, y_top)
            zone_lines = [
                l for l in content_lines if l.y1 <= y_top and l.y0 >= y_bottom
            ]
            if not zone_lines:
                continue
            zone = LayoutZone(zone_lines, zone_bbox)
            log_layout.debug(
                "  - Zone %d (y: %.2f -> %.2f) has %d lines.",
                len(page.zones)+1, y_top, y_bottom, len(zone_lines)
            )
            is_full_width = any(
                r.y1 <= y_top and r.y0 >= y_bottom for r in page.rects
                if r.width > layout.width * 0.7
            )
            if is_full_width:
                num_cols = 1
            elif self.num_columns_str != 'auto':
                num_cols = int(self.num_columns_str)
            else:
                num_cols = self._detect_column_count(zone.lines, layout)

            logging.getLogger("ppdf").info(
                "Page %d, Zone %d: Detected %d column(s).",
                page.page_num, len(page.zones)+1, num_cols
            )
            col_groups = self._group_lines_into_columns(zone.lines, layout, num_cols)
            col_w = zone.bbox[2] / num_cols if num_cols > 0 else zone.bbox[2]
            for i in range(num_cols):
                c_lines = col_groups[i] if i < len(col_groups) else []
                cx0 = zone.bbox[0] + (i * col_w)
                col_bbox = (cx0, zone.bbox[1], cx0 + col_w, zone.bbox[3])
                zone.columns.append(Column(c_lines, col_bbox))
            page.zones.append(zone)
        return page

    def _segment_column_into_blocks(self, lines, font_size, col_bbox, page_rects):
        """
        Stage 2: Segments a column's lines into logical blocks.

        This method identifies boxed notes and separates them from the main flow
        of prose and tables.

        Args:
            lines (list): The LTTextLine objects in the column.
            font_size (float): The page's main body font size.
            col_bbox (tuple): The bounding box of the column.
            page_rects (list): A list of all LTRect objects on the page.

        Returns:
            list: A list of ContentBlock objects (or subclasses).
        """
        if not lines:
            return []
        line_to_box_map = {}
        sorted_rects = sorted(page_rects, key=lambda r: (-r.y1, r.x0))
        for r in sorted_rects:
            box_lines = [
                l for l in lines if l not in line_to_box_map and
                (r.x0-1<l.x0 and r.y0-1<l.y0 and r.x1+1>l.x1 and r.y1+1>l.y1)
            ]
            if box_lines:
                for l in box_lines:
                    line_to_box_map[l] = r
        blocks, processed_lines = [], set()
        current_pos = 0
        while current_pos < len(lines):
            line = lines[current_pos]
            if line in processed_lines:
                current_pos += 1
                continue
            if line in line_to_box_map:
                rect = line_to_box_map[line]
                b_lines = [l for l in lines if line_to_box_map.get(l) == rect]
                title_text, title_lines = self._find_title_in_box(b_lines)
                blocks.append(BoxedNoteBlock(title_text, b_lines, title_lines))
                processed_lines.update(b_lines)
                # Jump past the lines we just processed
                last_index = max(lines.index(l) for l in b_lines) if b_lines else -1
                current_pos = last_index + 1
            else:
                block_lines, end_pos = [], current_pos
                while end_pos < len(lines) and lines[end_pos] not in line_to_box_map:
                    block_lines.append(lines[end_pos])
                    end_pos += 1
                if block_lines:
                    blocks.extend(self._segment_prose_and_tables(
                        block_lines, font_size, col_bbox
                    ))
                processed_lines.update(block_lines)
                current_pos = end_pos
        return self._merge_multiline_titles(blocks)

    def _segment_prose_and_tables(self, lines, font_size, col_bbox):
        """
        Helper to segment a run of lines into Prose, Table, and Title blocks.

        It works by finding "separator" lines (titles or table headers) and
        chunking the content between them.

        Args:
            lines (list): A list of LTTextLine objects to segment.
            font_size (float): The page's main body font size.
            col_bbox (tuple): The bounding box of the current column.

        Returns:
            list: A list of ContentBlock objects.
        """
        if not lines:
            return []
        split_indices = [
            i for i, line in enumerate(lines)
            if self._is_block_separator(line, font_size, col_bbox)
        ]
        blocks = []
        all_split_points = sorted(list(set([0] + split_indices + [len(lines)])))
        for i in range(len(all_split_points) - 1):
            start_idx, end_idx = all_split_points[i], all_split_points[i+1]
            block_lines = lines[start_idx:end_idx]
            if not block_lines:
                continue
            first_line = block_lines[0]
            if self._is_line_a_title(first_line, font_size, col_bbox):
                formatted_line = self._format_line_with_style(first_line)
                blocks.append(Title(formatted_line, [first_line]))
                if len(block_lines) > 1:
                    blocks.append(ProseBlock(block_lines[1:]))
            elif self._is_likely_table_header(first_line, font_size):
                table_lines = self._refine_table_lines_by_header(
                    block_lines, font_size
                )
                if table_lines:
                    blocks.append(self._parse_table_structure(table_lines, font_size))
                if len(table_lines) < len(block_lines):
                    log_structure.warning(
                        "Creating ProseBlock from %d remaining lines after table.",
                        len(block_lines) - len(table_lines)
                    )
                    blocks.append(ProseBlock(block_lines[len(table_lines):]))
            else:
                blocks.append(ProseBlock(block_lines))
        return blocks

    def _is_block_separator(self, line, font_size, col_bbox):
        """
        Determines if a line should act as a separator between content blocks.

        Args:
            line (LTTextLine): The line to check.
            font_size (float): The page's body font size.
            col_bbox (tuple): The column's bounding box.

        Returns:
            bool: True if the line is a title or a likely table header.
        """
        is_title = self._is_line_a_title(line, font_size, col_bbox)
        is_header = self._is_likely_table_header(line, font_size)
        return is_title or is_header

    def _is_likely_table_header(self, line, font_size):
        """
        Heuristically determines if a line is a table header.

        The heuristic checks for multiple "phrases" on one line, the presence of
        dice notation (e.g., 'd20'), a high ratio of capitalized words, or bold
        font styling.

        Args:
            line (LTTextLine): The line to check.
            font_size (float): The page's body font size.

        Returns:
            bool: True if the line is likely a table header.
        """
        phrases = self._get_column_phrases_from_line(line, font_size)
        num_cols = len(phrases)
        if num_cols < 2:
            return False
        text = line.get_text().strip()
        has_dice = bool(re.search(r'\b\d+d\d+\b', text, re.I))
        if num_cols > 0:
            cap_ratio = sum(1 for p, _, _ in phrases if p and p[0].isupper()) / num_cols
        else:
            cap_ratio = 0
        has_cap = cap_ratio > 0.6 and num_cols < 5
        fonts = self._get_line_fonts(line)
        is_font_consistent = len(fonts) == 1
        is_bold = "bold" in list(fonts)[0].lower() if is_font_consistent else False
        log_structure.debug(
            "  Header check for '%.40s...': "
            "cols=%d, dice=%s, caps_ratio=%.2f (%s), "
            "font_consistent=%s, bold=%s",
            text, num_cols, has_dice, cap_ratio, has_cap, is_font_consistent, is_bold
        )
        return has_dice or has_cap or is_bold

    def _refine_table_lines_by_header(self, lines, font_size):
        """
        Refines the extent of a table based on dice notation in the header.

        If a header contains e.g., 'd20', it assumes the table has 20 rows and
        tries to capture them.

        Args:
            lines (list): A list of lines starting with a potential table header.
            font_size (float): The page's body font size.

        Returns:
            list: The refined list of lines belonging to the table.
        """
        if not lines:
            return []
        header_line = lines[0]
        header_text = header_line.get_text().strip()
        phrases = self._get_column_phrases_from_line(header_line, font_size)
        if not phrases or len(phrases) < 2:
            return lines
        expected_rows = 0
        dice_match = re.search(r'(?i)(\d*)d(\d+)', header_text)
        if dice_match:
            try:
                die_type = int(dice_match.group(2))
                if die_type in [4, 6, 8, 10, 12, 20, 100]:
                    expected_rows = die_type
            except (ValueError, IndexError):
                pass
        if not expected_rows:
            return lines
        col_positions = [p[1] for p in phrases]
        table_lines = [header_line]
        row_count = 0
        i = 1
        while i < len(lines):
            words = self._get_words_from_line(lines[i])
            if words and abs(words[0][1] - col_positions[0]) < font_size:
                row_count += 1
                if row_count > expected_rows:
                    break
            table_lines.append(lines[i])
            i += 1
        return table_lines

    def _parse_table_structure(self, table_lines, font_size):
        """
        Parses a list of lines into a structured TableBlock object.

        This method defines column boundaries based on the header and then assigns
        all subsequent text to the appropriate cell in a grid. It uses a grid-based
        approach, assigning characters to cells based on their coordinates.

        Args:
            table_lines (list): The LTTextLine objects making up the table.
            font_size (float): The page's body font size.

        Returns:
            TableBlock | ProseBlock: A structured TableBlock, or a ProseBlock
            if parsing fails.
        """
        if not table_lines:
            return ProseBlock(table_lines)

        header_phrases = self._get_column_phrases_from_line(table_lines[0], font_size)
        if not header_phrases or len(header_phrases) < 2:
            log_structure.warning(
                "Table Parser: Header has < 2 phrases. Treating as prose.")
            return ProseBlock(table_lines)

        table_bbox = self._compute_bbox(table_lines)
        num_cols = len(header_phrases)
        log_structure.debug("Table Parser decided on %d columns.", num_cols)

        # Calculate column boundaries based on the midpoint of the gutter
        col_boundaries = []
        left_bound = table_bbox[0]
        for i in range(num_cols - 1):
            end_of_current = header_phrases[i][2]
            start_of_next = header_phrases[i+1][1]
            midpoint = end_of_current + (start_of_next - end_of_current) / 2
            col_boundaries.append((left_bound, midpoint))
            left_bound = midpoint
        col_boundaries.append((left_bound, table_bbox[2]))

        # Find "anchor" lines (start of each row) to determine vertical row boundaries.
        anchor_lines = [table_lines[0]]
        first_col_x_start = header_phrases[0][1]
        tolerance = font_size
        for l in table_lines[1:]:
            words = self._get_words_from_line(l)
            # A line is an anchor if its first word aligns with the first column header
            if words and abs(words[0][1] - first_col_x_start) < tolerance:
                # And is not part of the previous anchor line (multi-line cell)
                if not any(abs(l.y1 - prev_l.y0) < font_size * 0.5 for prev_l in anchor_lines):
                     anchor_lines.append(l)

        row_y_boundaries = [
            (((anchor_lines[i+1].y1 - 1) if i + 1 < len(anchor_lines)
              else table_bbox[1]), anchor_lines[i].y1 + 1)
            for i in range(len(anchor_lines))
        ]

        # --- REWRITTEN CELL POPULATION LOGIC ---
        cell_grid = [[[] for _ in range(num_cols)] for _ in range(len(row_y_boundaries))]

        # For each conceptual row in the grid...
        for r_idx, (y_bottom, y_top) in enumerate(row_y_boundaries):
            # Find all text lines that are vertically part of this row
            lines_in_row = sorted(
                [l for l in table_lines if y_bottom <= (l.y0 + l.y1) / 2 < y_top],
                key=lambda l: -l.y1
            )
            # For each conceptual column in the grid...
            for c_idx, (x_left, x_right) in enumerate(col_boundaries):
                cell_lines = []
                # Reconstruct the lines within this specific (row, col) cell
                for line in lines_in_row:
                    line_text = "".join(
                        c.get_text() for c in line
                        if isinstance(c, LTChar) and x_left <= c.x0 < x_right
                    ).strip()
                    if line_text:
                        cell_lines.append(line_text)
                cell_grid[r_idx][c_idx] = cell_lines
        # --- END REWRITTEN LOGIC ---

        parsed_rows = [
            TableRow([TableCell(text_lines) for text_lines in row_data])
            for row_data in cell_grid
        ]
        return TableBlock(table_lines, parsed_rows)

    def _format_table_for_display(self, table_block: TableBlock):
        """
        Formats a TableBlock into a list of strings for readable display.

        Args:
            table_block (TableBlock): The table to format.

        Returns:
            list[str]: A list of formatted lines representing the table.
        """
        if not table_block or not table_block.rows:
            return []
        col_widths = [0] * table_block.num_cols
        for row in table_block.rows:
            for i, cell in enumerate(row.cells):
                if i < table_block.num_cols:
                    max_line = max((len(line) for line in cell.text_lines), default=0)
                    col_widths[i] = max(col_widths[i], max_line)
        output_lines = []
        for row in table_block.rows:
            if not any(c.text_lines for c in row.cells):
                continue
            max_lines_in_row = max(
                (len(cell.text_lines) for cell in row.cells), default=0
            )
            if max_lines_in_row == 0:
                continue
            for line_idx in range(max_lines_in_row):
                parts = []
                for i, cell in enumerate(row.cells):
                    if i < table_block.num_cols:
                        text = (cell.text_lines[line_idx]
                                if line_idx < len(cell.text_lines) else "")
                        parts.append(text.ljust(col_widths[i]))
                output_lines.append("  ".join(parts))
        return output_lines

    def _format_table_as_markdown(self, table_block: TableBlock):
        """
        Converts a TableBlock object into a GitHub Flavored Markdown table.

        Args:
            table_block (TableBlock): The table to format.

        Returns:
            list[str]: A list of lines forming the Markdown table.
        """
        if not table_block or not table_block.rows:
            return []
        header_texts = [cell.pre_processed_text for cell in table_block.rows[0].cells]
        header_line = f"| {' | '.join(header_texts)} |"
        separator_line = f"| {' | '.join(['---'] * table_block.num_cols)} |"
        data_lines = []
        for row in table_block.rows[1:]:
            cell_texts = [cell.pre_processed_text for cell in row.cells]
            # Ensure the row has the correct number of cells for markdown
            if len(cell_texts) > table_block.num_cols:
                cell_texts = cell_texts[:table_block.num_cols]
            while len(cell_texts) < table_block.num_cols:
                cell_texts.append('')
            data_lines.append(f"| {' | '.join(cell_texts)} |")
        return [header_line, separator_line] + data_lines

    def _merge_multiline_titles(self, blocks):
        """
        Merges consecutive Title blocks into a single Title block.

        Args:
            blocks (list): A list of ContentBlock objects.

        Returns:
            list: A new list of blocks with titles merged.
        """
        if not blocks:
            return []
        merged_blocks, i = [], 0
        while i < len(blocks):
            if isinstance(blocks[i], Title):
                title_lines = blocks[i].lines
                while (i+1) < len(blocks) and isinstance(blocks[i+1], Title):
                    i += 1
                    title_lines.extend(blocks[i].lines)
                merged_blocks.append(Title(
                    " ".join(self._format_line_with_style(l) for l in title_lines),
                    title_lines
                ))
            else:
                merged_blocks.append(blocks[i])
            i += 1
        return merged_blocks

    def _build_sections_from_models(self):
        """
        Stage 3: Walks the analyzed PageModels to build final Section objects.

        This method iterates through the pages, zones, columns, and blocks in order
        to reconstruct the logical reading flow of the document.

        Returns:
            list[Section]: The final list of logical Section objects.
        """
        logging.getLogger("ppdf").info(
            "--- Stage 3: Reconstructing Document from Page Models ---"
        )
        sections, current_section, last_title, cont = [], None, None, 2
        def finalize_section(sec):
            if sec and sec.paragraphs:
                log_reconstruct.debug(
                    "Finalizing section '%s' (%d paras)",
                    sec.title, len(sec.paragraphs)
                )
                sections.append(sec)

        for page in self.page_models:
            log_reconstruct.debug(
                "Reconstructing from Page %d (%s)", page.page_num, page.page_type
            )
            if page.page_type != 'content':
                finalize_section(current_section)
                current_section = None
                last_title = f"({page.page_type.capitalize()} Page)"
                continue
            if page.title:
                finalize_section(current_section)
                log_reconstruct.debug(
                    "Page Title found: '%s'. Creating new section.", page.title.text
                )
                current_section = Section(page.title.text, page.page_num)
                last_title, cont = page.title.text, 2
            for zone in page.zones:
                for col in zone.columns:
                    for block in col.blocks:
                        if not current_section:
                            title = (f"{last_title} ({self._to_roman(cont)})"
                                     if last_title else "Untitled Section")
                            log_reconstruct.debug(
                                "No active section. Creating new section ('%s').", title
                            )
                            if last_title:
                                cont += 1
                            current_section = Section(title, page.page_num)
                        if isinstance(block, Title):
                            finalize_section(current_section)
                            log_reconstruct.debug(
                                "Column Title found: '%s'. Creating new section.",
                                block.text
                            )
                            current_section = Section(block.text, page.page_num)
                            last_title, cont = block.text, 2
                        elif isinstance(block, BoxedNoteBlock):
                            dangling_p = None
                            if current_section and current_section.last_paragraph:
                                dangling_p = current_section.paragraphs.pop()
                                log_reconstruct.debug(
                                    "Dangling paragraph found and saved."
                                )
                            finalize_section(current_section)
                            body_lines = [
                                l for l in block.lines if l not in block.title_lines
                            ]
                            note_sec = Section(block.text, page.page_num)
                            formatted_lines = [
                                self._format_line_with_style(l) for l in body_lines
                            ]
                            if any(line.strip() for line in formatted_lines):
                                note_sec.add_paragraph(
                                    Paragraph(formatted_lines, page.page_num)
                                )
                            sections.append(note_sec)
                            if dangling_p:
                                title = (f"{last_title} ({self._to_roman(cont)})"
                                         if last_title else "Untitled Section")
                                if last_title:
                                    cont += 1
                                current_section = Section(title, page.page_num)
                                current_section.add_paragraph(dangling_p)
                            else:
                                current_section = None
                        elif isinstance(block, TableBlock):
                            current_section.add_paragraph(Paragraph(
                                lines=self._format_table_for_display(block),
                                page=page.page_num, is_table=True,
                                llm_lines=self._format_table_as_markdown(block)
                            ))
                        elif isinstance(block, ProseBlock):
                            self._process_prose_block(
                                block, current_section, page.page_num,
                                page.body_font_size
                            )
        finalize_section(current_section)
        return sections

    def _process_prose_block(self, block, section, page, font_size):
        """
        Splits a ProseBlock into logical Paragraphs and adds them to a Section.

        Args:
            block (ProseBlock): The block to process.
            section (Section): The section to add paragraphs to.
            page (int): The current page number.
            font_size (float): The page's body font size.
        """
        if not block.lines:
            return
        for p_lines in self._split_prose_block_into_paragraphs(
                block.lines, font_size):
            formatted_lines = [self._format_line_with_style(l) for l in p_lines]
            section.add_paragraph(Paragraph(formatted_lines, page))

    def _get_column_phrases_from_line(self, line, font_size):
        """
        Tokenizes a line into phrases based on horizontal gaps between words.

        This is a key part of table and column detection. A "phrase" is a
        sequence of words separated by small gaps.

        Args:
            line (LTTextLine): The line to process.
            font_size (float): The page's body font size, used for gap threshold.

        Returns:
            list[tuple[str, float, float]]: A list of (text, x0, x1) tuples.
        """
        words = self._get_words_from_line(line)
        if not words:
            return []
        gap_threshold, phrases, current_phrase = font_size, [], []
        start_x, end_x = -1, -1

        for text, x0, x1 in words:
            # If this is the first word of a new phrase...
            if not current_phrase or x0 - end_x > gap_threshold:
                # Finalize the previous phrase if it exists
                if current_phrase:
                    phrases.append((" ".join(current_phrase), start_x, end_x))
                # Start a new phrase
                current_phrase, start_x = [text], x0
            else:
                # Continue the current phrase
                current_phrase.append(text)
            # Update the end coordinate of the current phrase
            end_x = x1

        # Add the last phrase after the loop finishes
        if current_phrase:
            phrases.append((" ".join(current_phrase), start_x, end_x))

        log_structure.debug(
            "    Line tokenized into %d phrases: %s",
            len(phrases), [p[0] for p in phrases]
        )
        return phrases

    def _get_words_from_line(self, line):
        """
        Extracts individual words (and their coordinates) from a line object.

        A "word" is a sequence of characters with no significant horizontal gap.

        Args:
            line (LTTextLine): The line to process.

        Returns:
            list[tuple[str, float, float]]: List of (text, x0, x1) tuples.
        """
        words, word_chars, start_x, last_x = [], [], -1, -1
        for char in line:
            if isinstance(char, LTChar) and char.get_text().strip():
                if not word_chars or char.x0 - last_x > 1.0:
                    if word_chars:
                        words.append(("".join(word_chars), start_x, last_x))
                    word_chars, start_x = [char.get_text()], char.x0
                else:
                    word_chars.append(char.get_text())
                last_x = char.x1
        if word_chars:
            words.append(("".join(word_chars), start_x, last_x))
        return words

    def _is_line_a_title(self, line, font_size, col_bbox, is_continuation=False,
                         prev_line=None):
        """
        Heuristically determines if a line is a title.

        A line is a title if it's significantly larger than the body text,
        or if it's all-caps and centered.

        Args:
            line (LTTextLine): The line to check.
            font_size (float): The page's body font size.
            col_bbox (tuple): The bounding box of the containing column.
            is_continuation (bool): If checking if this is a second line of a title.
            prev_line (LTTextLine): The previous line (if is_continuation).

        Returns:
            bool: True if the line is likely a title.
        """
        size, text = self._get_font_size(line), line.get_text().strip()
        if not text:
            return False
        col_width = col_bbox[2] - col_bbox[0] if col_bbox[2] > col_bbox[0] else 1
        col_mid_x = (col_bbox[0] + col_bbox[2]) / 2
        line_mid_x = (line.x0 + line.x1) / 2
        is_centered = abs(line_mid_x - col_mid_x) < (col_width * 0.2)
        if is_continuation:
            prev_size = self._get_font_size(prev_line)
            v_dist_ok = (prev_line.y0 - line.y1) < (size * 1.5)
            decision = (abs(size - prev_size) < 1.0 or
                        (prev_size > size and is_centered)) and v_dist_ok
            return decision
        is_larger = size > (font_size * 1.2)
        is_caps = text.isupper() and 1 < len(text.split()) < 10
        decision = is_larger or (is_caps and is_centered)
        log_structure.debug(
            "  Title check for '%s...': size=%.2f (body=%.2f, larger=%s), "
            "centered=%s, caps=%s -> decision=%s",
            text[:30], size, font_size, is_larger, is_centered, is_caps, decision
        )
        return decision

    def _find_elements_by_type(self, obj, t):
        """
        Recursively finds all layout elements of a specific type in a container.

        Args:
            obj: The pdfminer layout object to search within (e.g., LTPage).
            t: The type of object to find (e.g., LTTextLine).

        Returns:
            list: A list of found elements.
        """
        e = []
        if isinstance(obj, t):
            e.append(obj)
        if hasattr(obj, '_objs'):
            for child in obj:
                e.extend(self._find_elements_by_type(child, t))
        return e

    def _find_title_in_box(self, lines_in_box):
        """
        Heuristically finds a title within a boxed note.

        Looks for lines that are bolder, larger, all-caps, or centered relative
        to the other lines within the box.

        Args:
            lines_in_box (list): A list of LTTextLine objects inside a box.

        Returns:
            tuple[str, list]: The found title text and the lines comprising it.
            Defaults to "Note" and an empty list.
        """
        if (not lines_in_box or
                not "".join(l.get_text() for l in lines_in_box).strip()):
            return "Note", []
        font_sizes = [
            self._get_font_size(line) for line in lines_in_box
            if line.get_text().strip()
        ]
        if not font_sizes:
            return "Note", []
        box_body_font_size = Counter(font_sizes).most_common(1)[0][0]
        box_bbox = self._compute_bbox(lines_in_box)
        box_center_x = (box_bbox[0] + box_bbox[2]) / 2
        title_lines = []
        for i, line in enumerate(lines_in_box[:4]):
            line_text = line.get_text().strip()
            if not line_text:
                continue
            fonts, size = self._get_line_fonts(line), self._get_font_size(line)
            is_bold = any("bold" in f.lower() for f in fonts)
            is_all_caps = line_text.isupper() and len(line_text.split()) < 7
            box_width = box_bbox[2] - box_bbox[0]
            line_mid_x = (line.x0 + line.x1) / 2
            is_centered = abs(line_mid_x - box_center_x) < (box_width * 0.25)
            is_larger_font = size > box_body_font_size * 1.1
            if sum([is_larger_font, is_bold, is_all_caps, is_centered]) >= 2:
                title_lines.append(line)
            elif title_lines:
                break
        if title_lines:
            title_text = " ".join(self._format_line_with_style(l)
                                  for l in title_lines)
            if title_text.upper() not in ["NOTE", "WARNING", "IMPORTANT"]:
                return title_text, title_lines
        return "Note", []

    def _get_font_size(self, line):
        """
        Gets the most common font size for a given line.

        Args:
            line (LTTextLine): The line to analyze.

        Returns:
            float: The most common font size, or 0 if none found.
        """
        if not hasattr(line, '_objs') or not line._objs:
            return 0
        sizes = [
            c.size for c in line if isinstance(c, LTChar) and hasattr(c, 'size')
        ]
        return Counter(sizes).most_common(1)[0][0] if sizes else 0

    def _get_line_fonts(self, line):
        """
        Gets the set of font names used in a given line.

        Args:
            line (LTTextLine): The line to analyze.

        Returns:
            set: A set of font names (str).
        """
        if not hasattr(line, '_objs') or not line._objs:
            return set()
        return set(c.fontname for c in line if isinstance(c, LTChar))

    def _get_page_body_font_size(self, lines, default_on_fail=True):
        """
        Determines the primary body font size for a list of lines.

        Args:
            lines (list): A list of LTTextLine objects.
            default_on_fail (bool): If True, return 12.0 on failure.

        Returns:
            float | None: The most common font size.
        """
        if not lines:
            return 12 if default_on_fail else None
        sizes = [s for l in lines if (s := self._get_font_size(l)) and 6 <= s <= 30]
        if not sizes:
            return 12 if default_on_fail else None
        most_common = Counter(sizes).most_common(1)[0][0]
        log_layout.debug("Determined page body font size: %.2f", most_common)
        return most_common

    def _get_footer_threshold_dynamic(self, lines, layout, font_size):
        """
        Dynamically calculates the Y-coordinate below which content is a footer.

        It looks for page numbers or text with smaller-than-body font size in the
        bottom 12% of the page.

        Args:
            lines (list): All LTTextLine objects on the page.
            layout (LTPage): The page layout object.
            font_size (float): The page's body font size.

        Returns:
            float: The Y-coordinate of the footer threshold. Content below this
            is considered a footer. Returns 0 if no footer is detected.
        """
        limit = layout.y0 + (layout.height * 0.12)
        p = re.compile(r"^((page|pág\.?)\s+)?\s*-?\s*\d+\s*-?\s*$", re.I)
        cands = [
            l for l in lines if l.y0 <= limit and l.get_text().strip() and
            (p.match(l.get_text().strip()) is not None or
             self._get_font_size(l) < (font_size*0.85))
        ]
        if not cands:
            return 0
        footer_y = max(l.y1 for l in cands) + 1
        log_layout.debug("Footer threshold set to y=%.2f", footer_y)
        return footer_y

    def _detect_column_count(self, lines, layout):
        """
        Detects if a set of lines is arranged in one or two columns.

        It first checks for a clear vertical gutter between text on the left and
        right halves of the layout area. If that fails, it checks if the total
        width of text on each side is less than half the layout width.

        Args:
            lines (list): A list of LTTextLine objects to analyze.
            layout (LTPage | LayoutZone): The container for the lines.

        Returns:
            int: The detected number of columns (1 or 2).
        """
        if len(lines) < 5:
            return 1
        mid_x, leeway = layout.x0 + layout.width / 2, layout.width * 0.05
        left_lines = [l for l in lines if l.x1 < mid_x + leeway]
        right_lines = [l for l in lines if l.x0 > mid_x - leeway]
        if not left_lines or not right_lines:
            return 1
        max_left = max((l.x1 for l in left_lines), default=layout.x0)
        min_right = min((l.x0 for l in right_lines), default=layout.x1)
        if max_left < min_right:
            log_layout.debug("Column check: Gutter detected. Decision: 2 columns.")
            return 2
        left_chars = [
            c for l in left_lines for c in l
            if isinstance(c, LTChar) and c.get_text().strip()
        ]
        right_chars = [
            c for l in right_lines for c in l
            if isinstance(c, LTChar) and c.get_text().strip()
        ]
        if not left_chars or not right_chars:
            return 1
        left_w = max(c.x1 for c in left_chars) - min(c.x0 for c in left_chars)
        right_w = max(c.x1 for c in right_chars) - min(c.x0 for c in right_chars)
        half_layout_w = layout.width / 2 * 1.1
        if left_w < half_layout_w and right_w < half_layout_w:
            log_layout.debug(
                "Column check: Fallback width method suggests 2 columns."
            )
            return 2
        return 1

    def _group_lines_into_columns(self, lines, layout, num):
        """
        Groups a list of lines into N columns based on horizontal position.

        Args:
            lines (list): LTTextLine objects to group.
            layout (LTPage | LayoutZone): The container for the lines.
            num (int): The number of columns to create.

        Returns:
            list[list]: A list of lists, where each inner list contains the
            lines for one column.
        """
        if num == 1:
            return [lines]
        cols = [[] for _ in range(num)]
        width = layout.width/num
        for l in lines:
            idx = max(0, min(num - 1, int((l.x0 - layout.x0) / width)))
            cols[idx].append(l)
        return cols

    def _detect_page_title(self, lines, layout, font_size):
        """
        Detects a main title at the top of a page.

        It looks for large, prominent text in the top 15% of the page.

        Args:
            lines (list): All content lines on the page.
            layout (LTPage): The page layout object.
            font_size (float): The page's body font size.

        Returns:
            tuple[Title | None, list]: The found Title object (or None) and the
            list of lines belonging to it.
        """
        if not lines:
            return None, []
        sorted_lines = sorted(lines, key=lambda x: -x.y0)
        top_y_threshold = layout.y0 + layout.height * 0.85
        top_candidates = [
            l for l in sorted_lines
            if l.y0 >= top_y_threshold and self._get_font_size(l) > (font_size * 1.4)
        ]
        if not top_candidates:
            return None, []
        # Ensure candidate lines aren't on the same Y-level (likely side-by-side text)
        y_groups = {}
        for l in top_candidates:
            key = next((y for y in y_groups if abs(l.y1-y) < 10), None)
            if key:
                y_groups[key].append(l)
            else:
                y_groups[l.y1] = [l]
        if any(len(g) > 1 for g in y_groups.values()):
            return None, []
        # Find multi-line titles
        cands = [top_candidates[0]]
        first_idx = sorted_lines.index(top_candidates[0])
        for i in range(first_idx + 1, len(sorted_lines)):
            l, prev_line = sorted_lines[i], cands[-1]
            prev_font_size = self._get_font_size(prev_line)
            curr_font_size = self._get_font_size(l)
            v_dist_ok = (prev_line.y0 - l.y1) < (prev_font_size * 1.5)
            h_align_ok = abs(l.x0 - prev_line.x0) < (layout.width * 0.2)
            font_size_ok = (abs(curr_font_size - prev_font_size) < 2.0 or
                            curr_font_size < prev_font_size)
            if v_dist_ok and h_align_ok and font_size_ok:
                cands.append(l)
            else:
                break
        if cands:
            title_text = " ".join(self._format_line_with_style(l) for l in cands)
            return Title(title_text, cands), cands
        return None, []

    def _split_prose_block_into_paragraphs(self, lines, font_size):
        """
        Splits a list of lines into paragraphs based on vertical spacing.

        Args:
            lines (list): A list of LTTextLine objects from a ProseBlock.
            font_size (float): The page's body font size.

        Returns:
            list[list[LTTextLine]]: A list of paragraphs, where each paragraph
            is a list of its constituent lines.
        """
        if not lines:
            return []
        paras, para, v_thresh = [], [], font_size * 1.2
        for i, l in enumerate(lines):
            if para and (para[-1].y0 - l.y1) > v_thresh:
                paras.append(para)
                para = []
            para.append(l)
        if para:
            paras.append(para)
        return paras

    def _format_line_with_style(self, line):
        """
        Formats a line, optionally preserving bold/italic markdown.

        If `self.keep_style` is True, it inspects the font name of each
        character to wrap bold and italic text in markdown syntax.

        Args:
            line (LTTextLine): The line to format.

        Returns:
            str: The formatted text of the line.
        """
        if not self.keep_style or not hasattr(line, '_objs'):
            return re.sub(r'\s+', ' ', line.get_text()).strip()
        parts, style, buf = [], {'bold': False, 'italic': False}, []
        for char in line:
            if not isinstance(char, LTChar):
                continue
            ctext = char.get_text()
            if not ctext.strip() and not ctext.isspace():
                continue
            is_b = "bold" in char.fontname.lower()
            is_i = "italic" in char.fontname.lower()
            if is_b != style['bold'] or is_i != style['italic']:
                if buf:
                    text = "".join(buf)
                    if style['bold'] and style['italic']:
                        parts.append(f"***{text}***")
                    elif style['bold']:
                        parts.append(f"**{text}**")
                    elif style['italic']:
                        parts.append(f"*{text}*")
                    else:
                        parts.append(text)
                    buf = []
            style['bold'], style['italic'] = is_b, is_i
            buf.append(ctext)
        if buf:
            text = "".join(buf)
            if style['bold'] and style['italic']:
                parts.append(f"***{text}***")
            elif style['bold']:
                parts.append(f"**{text}**")
            elif style['italic']:
                parts.append(f"*{text}*")
            else:
                parts.append(text)
        return re.sub(r'\s+', ' ', "".join(parts)).strip()


class ASCIIRenderer:
    """Renders an ASCII art diagram of a PageModel for debugging."""
    def __init__(self, extractor, width=80, height=50):
        self.extractor = extractor
        self.width = width
        self.height = height

    def render(self, page_model):
        """
        Renders a single PageModel to an ASCII string.

        Args:
            page_model (PageModel): The page model to render.

        Returns:
            str: The ASCII art representation of the page layout.
        """
        canvas = [['.' for _ in range(self.width)] for _ in range(self.height)]
        layout = page_model.page_layout

        if page_model.page_type != 'content':
            page_type_text = f"--- SKIPPED ({page_model.page_type.upper()}) ---"
            start_col = (self.width - len(page_type_text)) // 2
            for i, char in enumerate(page_type_text):
                if (0 <= self.height // 2 < self.height and
                        0 <= start_col + i < self.width):
                    canvas[self.height // 2][start_col + i] = char
            return '\n'.join(''.join(row) for row in canvas) + '\n'

        for zone in page_model.zones:
            for col in zone.columns:
                for block in col.blocks:
                    if isinstance(block, ProseBlock):
                        self._draw_fill(
                            canvas, layout, block.bbox, 'a', col.bbox
                        )
                    elif isinstance(block, TableBlock) and block.lines:
                        self._draw_fill(
                            canvas, layout, block.bbox, '=', col.bbox
                        )
                        header_bbox = self.extractor._compute_bbox([block.lines[0]])
                        self._draw_fill(
                            canvas, layout,
                            (block.bbox[0], header_bbox[1],
                             block.bbox[2], header_bbox[3]),
                            'h', col.bbox, force_single_line=True
                        )
                    elif isinstance(block, BoxedNoteBlock):
                        self._draw_fill(
                            canvas, layout, block.bbox, '•', col.bbox
                        )
                        self._draw_text(
                            canvas, layout, block.title_lines, block.bbox,
                            centered=True, v_centered=True
                        )
                    elif isinstance(block, Title):
                        self._draw_text(canvas, layout, block.lines, col.bbox)
        if page_model.title:
            self._draw_text(
                canvas, layout, page_model.title.lines,
                page_model.page_layout.bbox, centered=True
            )
        for zone in page_model.zones:
            zone_coords = self._to_grid_coords(layout, zone.bbox)
            if not zone_coords:
                continue
            _, zone_sr, _, zone_er = zone_coords
            if len(zone.columns) > 1:
                for i in range(1, len(zone.columns)):
                    col_bbox = zone.columns[i - 1].bbox
                    sep_c = int((col_bbox[2] - layout.x0) / layout.width * self.width)
                    if 0 < sep_c < self.width:
                        for r in range(zone_sr, zone_er + 1):
                            if 0 <= r < self.height:
                                canvas[r][sep_c] = '|'
            for col in zone.columns:
                for block in col.blocks:
                    if isinstance(block, TableBlock) and block.lines:
                        phrases = self.extractor._get_column_phrases_from_line(
                            block.lines[0], page_model.body_font_size
                        )
                        coords = self._to_grid_coords(layout, block.bbox, col.bbox)
                        if not coords:
                            continue
                        _, sr, _, er = coords
                        for _, x_pos, _ in phrases[1:]:
                            sep_c = int(
                                (x_pos - layout.x0) / layout.width * self.width
                            ) - 1
                            for r in range(max(0, sr), min(self.height, er + 1)):
                                if (0 <= sep_c < self.width and
                                        canvas[r][sep_c] in ('=', 'h')):
                                    canvas[r][sep_c] = ':'
        return '\n'.join(''.join(row) for row in canvas) + '\n'

    def _to_grid_coords(self, page_layout, bbox, clip_box=None):
        """
        Converts a PDF bounding box to canvas grid coordinates.

        Args:
            page_layout (LTPage): The main page layout object for reference.
            bbox (tuple): The (x0, y0, x1, y1) box to convert.
            clip_box (tuple | None): A bounding box to clip the result to.

        Returns:
            tuple | None: A (start_col, start_row, end_col, end_row) tuple, or
            None if the box is invalid.
        """
        if not bbox or page_layout.width == 0 or page_layout.height == 0:
            return None
        x0, y0, x1, y1 = bbox
        if clip_box:
            x0, y0 = max(x0, clip_box[0]), max(y0, clip_box[1])
            x1, y1 = min(x1, clip_box[2]), min(y1, clip_box[3])
        if x1 <= x0 or y1 <= y0:
            return None
        return (int((x0 - page_layout.x0) / page_layout.width * self.width),
                int((page_layout.y1 - y1) / page_layout.height * self.height),
                int((x1 - page_layout.x0) / page_layout.width * self.width),
                int((page_layout.y1 - y0) / page_layout.height * self.height))

    def _draw_fill(self, canvas, page_layout, bbox, char,
                   clip_box=None, force_single_line=False):
        """
        Fills a region of the canvas with a character.

        Args:
            canvas (list[list[str]]): The character grid to draw on.
            page_layout (LTPage): The page layout for coordinate conversion.
            bbox (tuple): The bounding box of the region to fill.
            char (str): The character to fill with.
            clip_box (tuple | None): An optional box to clip the drawing to.
            force_single_line (bool): If True, only draw on the first row.
        """
        coords = self._to_grid_coords(page_layout, bbox, clip_box)
        if not coords:
            return
        sc, sr, ec, er = coords
        if force_single_line:
            er = sr
        for r in range(max(0, sr), min(self.height, er + 1)):
            for c in range(max(0, sc), min(self.width, ec + 1)):
                if 0 <= r < self.height and 0 <= c < self.width:
                    canvas[r][c] = char

    def _draw_text(self, canvas, page_layout, lines,
                   clip_box=None, centered=False, v_centered=False):
        """
        Draws text onto the canvas.

        Args:
            canvas (list[list[str]]): The character grid to draw on.
            page_layout (LTPage): The page layout for coordinate conversion.
            lines (list): The LTTextLine objects to draw.
            clip_box (tuple | None): An optional box to clip the drawing to.
            centered (bool): If True, horizontally center the text.
            v_centered (bool): If True, vertically center the text.
        """
        if not lines:
            return
        if v_centered and clip_box:
            clip_coords = self._to_grid_coords(page_layout, clip_box)
            if clip_coords:
                _, clip_sr, _, clip_er = clip_coords
                start_sr = (clip_sr + (clip_er - clip_sr) // 2) - (len(lines) // 2)
                for i, line in enumerate(lines):
                    current_sr = start_sr + i
                    text = self.extractor._format_line_with_style(line)
                    line_coords = self._to_grid_coords(page_layout, line.bbox, clip_box)
                    if not line_coords:
                        continue
                    sc, _, ec, _ = line_coords
                    available_width = ec - sc
                    if available_width <= 0:
                        continue
                    truncated_text = text[:available_width]
                    c_sc, _, c_ec, _ = self._to_grid_coords(page_layout, clip_box)
                    start_col = sc
                    if centered:
                        start_col = max(
                            c_sc, c_sc + (c_ec - c_sc)//2 - len(truncated_text)//2
                        )
                    for char_idx, char in enumerate(truncated_text):
                        if (0 <= current_sr < self.height and
                                0 <= start_col + char_idx < self.width):
                            canvas[current_sr][start_col + char_idx] = char
                return
        for line in lines:
            text = self.extractor._format_line_with_style(line)
            coords = self._to_grid_coords(page_layout, line.bbox, clip_box)
            if not coords:
                continue
            sc, sr, ec, _ = coords
            available_width = ec - sc
            if available_width <= 0:
                continue
            truncated_text = text[:available_width]
            start_col = sc
            if centered:
                container_width, container_sc = self.width, 0
                if clip_box:
                    clip_coords = self._to_grid_coords(page_layout, clip_box)
                    if clip_coords:
                        container_sc, _, c_ec, _ = clip_coords
                        container_width = c_ec - container_sc
                start_col = max(
                    container_sc,
                    container_sc + container_width//2 - len(truncated_text)//2
                )
            for i, char in enumerate(truncated_text):
                if 0 <= sr < self.height and 0 <= start_col + i < self.width:
                    canvas[sr][start_col + i] = char


class Application:
    """Orchestrates the PDF processing workflow based on command-line arguments."""
    DEFAULT_FILENAME_SENTINEL = "__DEFAULT_FILENAME__"
    DEFAULT_CHUNK_SIZE = 4000

    def __init__(self, args):
        """
        Initializes the Application.

        Args:
            args (argparse.Namespace): The parsed command-line arguments.
        """
        self.args = args
        self.stats = {}
        self.extractor = PDFTextExtractor(
            args.pdf_file, args.columns, args.remove_footers, args.keep_style
        )
        self.tts_manager = None

    def run(self):
        """Main entry point for the application logic."""
        self.stats['start_time'] = time.monotonic()
        self._configure_logging()

        try:
            system_prompt = self._build_system_prompt()
            self._log_run_conditions(system_prompt)

            context_size = self._get_model_details()
            if context_size and self.args.chunk_size == self.DEFAULT_CHUNK_SIZE:
                self.args.chunk_size = int(context_size * 0.8)
                logging.getLogger("ppdf").info(
                    "Auto-adjusting chunk size to %d.", self.args.chunk_size
                )

            self._resolve_output_filenames()
            pages = self._parse_page_selection()
            if pages is None and self.args.pages.lower() != 'all':
                sys.exit(1)

            pdf_analysis_start = time.monotonic()
            sections = self.extractor.extract_sections(pages)
            self.stats['pdf_analysis_duration'] = time.monotonic() - pdf_analysis_start
            self.stats['pages_processed_count'] = len(self.extractor.page_models)
            self.stats['sections_reconstructed_count'] = len(sections)

            if not self.extractor.page_models:
                logging.getLogger("ppdf").error("No content could be extracted. Exiting.")
                return

            self._save_extracted_text(sections)

            if self.args.dry_run:
                self._display_dry_run_summary(sections)
            else:
                # Initialize TTS manager just before it's needed.
                if self.args.speak:
                    self._initialize_tts()

                llm_wall_start = time.monotonic()
                final_markdown = self._generate_output_with_llm(sections, system_prompt)
                self.stats['llm_wall_duration'] = time.monotonic() - llm_wall_start

                self._save_llm_output(final_markdown)

        finally:
            if self.tts_manager:
                self.tts_manager.cleanup()
            self._display_performance_epilogue()

    def _initialize_tts(self):
        """Initializes the TTSManager if the --speak flag is used."""
        if not PIPER_AVAILABLE:
            logging.warning(
                "TTS dependencies not installed. --speak flag will be ignored."
            )
            logging.warning(
                'To enable speech, install: pip install "piper-tts==1.3.0" pyaudio'
            )
            self.args.speak = None # Disable speaking
            return

        try:
            self.tts_manager = TTSManager(lang=self.args.speak)
            logging.getLogger("ppdf.tts").info(
                "TTS Manager initialized for language: '%s'", self.args.speak
            )
        except Exception as e:
            logging.getLogger("ppdf.tts").error(
                "Failed to initialize TTS Manager: %s", e, exc_info=True
            )
            self.tts_manager = None
            self.args.speak = None # Disable speaking


    def _get_model_details(self):
        """
        Queries the Ollama /api/show endpoint for model details.

        It validates that the selected model exists and attempts to find its
        context window size (`num_ctx`).

        Returns:
            int | None: The context window size, or None if not found.
        """
        app_log = logging.getLogger("ppdf")
        app_log.info("Querying details for model: %s...", self.args.model)
        try:
            tags_url = f"{self.args.url}/api/tags"
            show_url = f"{self.args.url}/api/show"
            tags_response = requests.get(tags_url)
            tags_response.raise_for_status()
            models_info = tags_response.json().get('models', [])
            if not any(m['name'] == self.args.model for m in models_info):
                names = "\n".join(
                    f"  - {m['name']}" for m in sorted(models_info, key=lambda x: x['name'])
                )
                error_msg = (
                    f"Model '{self.args.model}' not found. Available models:\n"
                    f"{names if names else '  (None)'}"
                )
                app_log.error(error_msg)
                sys.exit(1)

            response = requests.post(show_url, json={"name": self.args.model})
            response.raise_for_status()
            model_info = response.json()
            details = model_info.get('details', {})
            app_log.info(
                "---\nOllama Model Details:\n"
                "  - Family: %s\n  - Parameter Size: %s\n  - Quantization: %s\n---",
                details.get('family', 'N/A'), details.get('parameter_size', 'N/A'),
                details.get('quantization_level', 'N/A')
            )

            for line in model_info.get('modelfile', '').split('\n'):
                if 'num_ctx' in line.lower():
                    try:
                        return int(line.split()[1])
                    except (ValueError, IndexError):
                        continue
            return None
        except requests.exceptions.RequestException as e:
            logging.error("Could not connect to Ollama: %s", e)
            sys.exit(1)

    def _display_performance_epilogue(self):
        """Displays a summary of performance statistics at the end of a run."""
        app_log = logging.getLogger("ppdf")
        total_duration = time.monotonic() - self.stats.get('start_time',
                                                           time.monotonic())
        eval_duration_s = self.stats.get('llm_eval_duration', 0) / 1e9
        eval_count = self.stats.get('llm_eval_count', 0)
        tokens_per_sec = (eval_count / eval_duration_s) if eval_duration_s > 0 else 0
        report = [
            "\n--- Performance Epilogue ---",
            "[ Overall ]",
            f"  - Total Execution Time: {total_duration:.1f} seconds\n",
            "[ PDF Analysis ]",
            f"  - Pages Processed: {self.stats.get('pages_processed_count', 0)}",
            f"  - Sections Reconstructed: "
            f"{self.stats.get('sections_reconstructed_count', 0)}",
            f"  - Analysis Duration: "
            f"{self.stats.get('pdf_analysis_duration', 0):.1f} seconds\n"
        ]
        if not self.args.dry_run:
            report.extend([
                "[ LLM Processing ]",
                f"  - Total LLM Duration (Wall Clock): "
                f"{self.stats.get('llm_wall_duration', 0):.1f} seconds",
                f"  - Text Sent to LLM: "
                f"{self.stats.get('llm_chars_sent', 0):,} chars",
                f"  - Text Received from LLM: "
                f"{self.stats.get('llm_chars_received', 0):,} chars\n",
                "  -- LLM Performance (from API) --",
                f"  - Prompt Tokens Processed: "
                f"{self.stats.get('llm_prompt_eval_count', 0):,}",
                f"  - Generated Tokens: {self.stats.get('llm_eval_count', 0):,}",
                f"  - Generation Speed: {tokens_per_sec:.1f} tokens/sec"
            ])
        report.append("--------------------------")
        app_log.info("\n".join(report))

    def _log_run_conditions(self, system_prompt):
        """If debugging is enabled, logs script arguments and the system prompt."""
        if self.args.debug_topics:
            args_dict = vars(self.args)
            output_lines = [
                "--- Script Running Conditions ---",
                *[f"  - {arg:<14} : {value}" for arg, value in args_dict.items()],
                "---------------------------------"
            ]
            log_llm.debug("\n".join(output_lines))
        logging.getLogger("ppdf").info(
            "---\nLLM System Prompt Configuration:\n%s\n---", system_prompt
        )

    def _configure_logging(self):
        """Configures logging levels and format based on command-line arguments."""
        level = logging.INFO if self.args.verbose else logging.WARNING
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        if root_logger.hasHandlers():
            root_logger.handlers.clear()
        handler = logging.StreamHandler()
        handler.setFormatter(RichLogFormatter(use_color=self.args.color_logs))
        root_logger.addHandler(handler)
        logging.getLogger("ppdf").setLevel(level)
        if self.args.debug_topics:
            logging.getLogger("ppdf").setLevel(logging.INFO)
            full_topics = {'layout', 'structure', 'reconstruct', 'llm', 'tts'}
            user_topics = [t.strip() for t in self.args.debug_topics.split(',')]
            if 'all' in user_topics:
                topics_to_set = full_topics
            else:
                topics_to_set = {
                    full for user in user_topics for full in full_topics
                    if full.startswith(user)
                }
            invalid = [
                user for user in user_topics if user != 'all' and not any(
                    full.startswith(user) for full in full_topics
                )
            ]
            if invalid:
                logging.warning("Ignoring invalid debug topics: %s", ", ".join(invalid))
            for topic in topics_to_set:
                logging.getLogger(f"ppdf.{topic}").setLevel(logging.DEBUG)
        if not (self.args.debug_topics and 'all' in self.args.debug_topics):
            logging.getLogger('pdfminer').setLevel(logging.WARNING)

    def _resolve_output_filenames(self):
        """Sets default output filenames based on the input PDF name if needed."""
        S = self.DEFAULT_FILENAME_SENTINEL
        if self.args.output_file == S or self.args.extracted_file == S:
            base = os.path.splitext(os.path.basename(self.args.pdf_file))[0]
            if self.args.output_file == S:
                self.args.output_file = f"{base}.md"
            if self.args.extracted_file == S:
                self.args.extracted_file = f"{base}.extracted"

    def _parse_page_selection(self):
        """
        Parses the --pages argument string (e.g., '1,3,5-7') into a set.

        Returns:
            set | None: A set of integer page numbers, or None if 'all'. Returns
            None and logs an error on invalid format.
        """
        if self.args.pages.lower() == 'all':
            return None
        pages = set()
        try:
            for p in self.args.pages.split(','):
                part = p.strip()
                if '-' in part:
                    s, e = map(int, part.split('-'))
                    pages.update(range(s, e + 1))
                else:
                    pages.add(int(part))
            return pages
        except ValueError:
            logging.getLogger("ppdf").error(
                "Invalid --pages format: %s.", self.args.pages
            )
            return None

    def _display_dry_run_summary(self, sections):
        """Prints a detailed summary of the extracted document structure."""
        print("\n--- Document Structure Summary (Dry Run) ---")
        print("\n--- Page Layout Analysis ---")
        renderer = ASCIIRenderer(self.extractor)
        for page in self.extractor.page_models:
            print(f"\n[ Page {page.page_num} Layout ]")
            print(renderer.render(page))
        if sections:
            print("\n--- Reconstructed Sections Summary ---")
            for i, s in enumerate(sections):
                title = s.title or 'Untitled'
                print(f"\nSection {i+1}:\n  Title: {title}\n"
                      f"  Pages: {s.page_start}-{s.page_end}")
                num_tables = sum(1 for p in s.paragraphs if p.is_table)
                num_paras = len(s.paragraphs)
                num_lines = sum(len(p.lines) for p in s.paragraphs)
                num_chars = len(s.get_text())
                print(
                    f"  Stats: {num_paras} paras ({num_tables} tables), "
                    f"{num_lines} lines, {num_chars} chars"
                )
                if num_tables > 0:
                    print("  --- Formatted Table(s) ---")
                    for p in s.paragraphs:
                        if p.is_table:
                            print("\n".join([f"    {line}" for line in p.lines]))
        print("\n--- End of Dry Run Summary ---")

    def _save_extracted_text(self, sections):
        """Saves the raw, reconstructed text to a file if requested."""
        if self.args.extracted_file and sections:
            content = [
                f"--- Page {s.page_start}-{s.page_end} "
                f"(Title: {s.title or 'N/A'}) ---\n{s.get_text()}"
                for s in sections
            ]
            try:
                with open(self.args.extracted_file, 'w', encoding='utf-8') as f:
                    f.write("\n\n\n".join(content))
                logging.getLogger("ppdf").info(
                    "Raw extracted text saved to: '%s'", self.args.extracted_file
                )
            except IOError as e:
                logging.getLogger("ppdf").error("Error saving raw text: %s", e)

    def _save_llm_output(self, markdown_text):
        """Saves the final LLM-generated markdown to a file."""
        if not self.args.output_file:
            return
        try:
            with open(self.args.output_file, 'w', encoding='utf-8') as f:
                f.write(markdown_text)
            logging.getLogger("ppdf").info(
                "\nLLM output saved to: '%s'", self.args.output_file
            )
        except IOError as e:
            logging.getLogger("ppdf").error("Error saving LLM output: %s", e)

    def _generate_output_with_llm(self, sections, system_prompt):
        """
        Orchestrates the chunking and processing of sections with the LLM.

        Args:
            sections (list[Section]): The reconstructed sections of the document.
            system_prompt (str): The system prompt for the LLM.

        Returns:
            str: The final, combined response from all chunks.
        """
        all_markdown = []
        agg_stats = {'prompt_eval_count': 0, 'eval_count': 0, 'eval_duration': 0}
        chunks = Application._chunk_sections(sections, self.args.chunk_size)
        for i, chunk_sections in enumerate(chunks):
            s_page = chunk_sections[0].page_start
            e_page = chunk_sections[-1].page_end
            logging.getLogger("ppdf").info(
                "\nProcessing chunk %d/%d (Sections: %d, Pages: %s-%s)",
                i + 1, len(chunks), len(chunk_sections), s_page, e_page
            )
            user_content = "\n\n".join([
                f"# {s.title or 'Untitled'}\n\n{s.get_llm_text()}"
                for s in chunk_sections
            ])
            guarded_content = (
                f"\n\n--- BEGIN DOCUMENT ---\n\n{user_content}\n\n--- END DOCUMENT ---"
            )
            log_llm.debug(
                "\nGuarded user content for chunk %d:\n%s", i + 1, guarded_content
            )
            full_response, chunk_stats = self._query_llm_api(
                system_prompt, guarded_content, self.tts_manager
            )
            if full_response:
                all_markdown.append(full_response)
                for key in agg_stats:
                    agg_stats[key] += chunk_stats.get(key, 0)
                sent = len(system_prompt) + len(guarded_content)
                self.stats['llm_chars_sent'] = self.stats.get('llm_chars_sent', 0) + sent
                self.stats['llm_chars_received'] = self.stats.get('llm_chars_received', 0) + len(full_response)
            else:
                all_markdown.append(f"\n[ERROR: Could not process chunk {i+1}]")


        self.stats.update({f'llm_{k}': v for k, v in agg_stats.items()})
        final_markdown_text = "\n\n".join(all_markdown)

        if not final_markdown_text.strip():
            logging.getLogger("ppdf").error(
                "Failed to get any usable content from the LLM."
            )
            return ""

        return final_markdown_text

    def _build_system_prompt(self):
        """
        Prepares the system prompt. Now static except for translation.

        Returns:
            str: The fully constructed system prompt.
        """
        system_prompt = PROMPT_SYSTEM

        # Append the translation mandate if requested.
        if self.args.translate:
            lang = self.args.translate.capitalize()
            system_prompt += (
                f"\n\n**Translation Mandate:** After all formatting, you MUST "
                f"translate the entire Markdown output into {lang}."
            )

        return system_prompt

    def _parse_llm_response(self, response_text):
        """
        Parses the LLM's full response. In a simplified script, this just strips
        whitespace, but is kept for TTS compatibility to ensure only markdown
        is spoken.
        """
        # No longer expecting <thinking> or <markdown> tags in final output.
        # This function now primarily serves to ensure only clean text is passed to TTS.
        return "", response_text.strip()

    @staticmethod
    def _chunk_sections(sections, size=4000):
        """
        Greedily chunks sections to maximize context window usage.

        Args:
            sections (list[Section]): The list of sections to chunk.
            size (int): The maximum character size for a chunk's content.

        Returns:
            list[list[Section]]: A list of chunks, where each chunk is a list
            of sections.
        """
        if not sections:
            return []
        all_chunks, current_chunk, current_len, i = [], [], 0, 0
        while i < len(sections):
            section = sections[i]
            section_len = len(
                f"## Section: {section.title or 'Untitled'}\n\n"
            ) + len(section.get_llm_text())
            if section_len > size and not current_chunk:
                log_llm.warning(
                    "Section '%s' is larger than chunk size and will be "
                    "processed alone.", section.title
                )
                all_chunks.append([section])
                i += 1
                continue
            if current_chunk and (current_len + section_len) > size:
                all_chunks.append(current_chunk)
                current_chunk, current_len = [], 0
            current_chunk.append(section)
            current_len += section_len
            i += 1
        if current_chunk:
            all_chunks.append(current_chunk)
        return all_chunks

    def _query_llm_api(self, system, user, tts_manager=None):
        """
        Queries the Ollama /api/generate endpoint and streams the response.

        Args:
            system (str): The system prompt.
            user (str): The user prompt (containing the document text).
            tts_manager (TTSManager | None): The TTS manager for audio streaming.

        Returns:
            tuple[str | None, dict]: A tuple containing the full response content
            and the final JSON object with performance stats from the API.
        """
        data = {
            "model": self.args.model,
            "system": system,
            "prompt": user,
            "stream": True
        }
        full_content, stats = "", {}
        try:
            r = requests.post(
                f"{self.args.url}/api/generate", json=data, stream=True
            )
            r.raise_for_status()

            # --- Visual Output Logic ---
            if self.args.rich_stream:
                console = Console()
                live = Live(
                    console=console, auto_refresh=False,
                    vertical_overflow="visible"
                )
                with live:
                    for line in r.iter_lines():
                        if not line: continue
                        j, chunk = self._process_stream_line(line, tts_manager)
                        if chunk is not None:
                            full_content += chunk
                            live.update(Markdown(full_content), refresh=True)
                        if j and j.get('done'): stats = j
            else:
                # Standard stdout streaming
                print()  # Add a newline before the stream
                for line in r.iter_lines():
                    if not line: continue
                    j, chunk = self._process_stream_line(line, tts_manager)
                    if chunk is not None:
                        full_content += chunk
                        print(chunk, end='', flush=True)
                    if j and j.get('done'): stats = j
                print() # Add a newline after the stream

            return full_content, stats
        except requests.exceptions.RequestException as e:
            logging.getLogger("ppdf.llm").error("Ollama API request failed: %s", e)
            return None, {}

    def _process_stream_line(self, line, tts_manager):
        """Helper to process a single line from the Ollama stream."""
        try:
            j = json.loads(line.decode('utf-8'))
            chunk = j.get('response', '')
            if chunk and tts_manager:
                tts_manager.add_text(chunk)
            return j, chunk
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, None


    @staticmethod
    def parse_arguments():
        """
        Parses command-line arguments for the script.

        Returns:
            argparse.Namespace: The populated namespace with argument values.
        """
        p = argparse.ArgumentParser(
            description="An advanced PDF text and structure extraction tool.",
            formatter_class=argparse.RawTextHelpFormatter,
            add_help=False,
            epilog="""Examples:
  Basic usage:
    python ppdf.py document.pdf -o "output.md"

  Render output live and see performance stats:
    python ppdf.py document.pdf --rich-stream -v

  Stream the output as speech in real-time (English):
    python ppdf.py document.pdf -S en

  Debug only the LLM and structure-detection parts:
    python ppdf.py document.pdf -d llm,struct --color-logs
"""
        )
        S = Application.DEFAULT_FILENAME_SENTINEL

        g_opts = p.add_argument_group('Main Options')
        g_opts.add_argument("pdf_file", help="Path to the input PDF file.")
        g_opts.add_argument(
            "-h", "--help", action="help", help="Show this help message and exit."
        )

        g_proc = p.add_argument_group('Processing Control')
        g_proc.add_argument(
            "-p", "--pages", default="all", metavar="PAGES",
            help="Pages to process, e.g., '1,3,5-7'."
        )
        g_proc.add_argument(
            "-C", "--columns", default="auto", metavar="COUNT",
            help="Force column count (1-6, or 'auto')."
        )
        g_proc.add_argument(
            "--no-remove-footers", action="store_false", dest="remove_footers",
            help="Disable footer removal."
        )
        g_proc.add_argument(
            "-K", "--keep-style", action="store_true",
            help="Preserve bold/italic formatting from source."
        )

        g_llm = p.add_argument_group('LLM Configuration')
        g_llm.add_argument(
            "-M", "--model", default="llama3.1:latest", metavar="MODEL",
            help="Ollama model to use."
        )
        g_llm.add_argument(
            "-U", "--url", default="http://localhost:11434", metavar="URL",
            help="Ollama API URL."
        )
        g_llm.add_argument(
            "-z", "--chunk-size", type=int, default=Application.DEFAULT_CHUNK_SIZE,
            metavar="SIZE", help="Max characters per chunk sent to LLM."
        )
        g_llm.add_argument(
            "-t", "--translate", default=None, metavar="LANG",
            help="Translate final output to language code."
        )

        g_out = p.add_argument_group('Script Output & Actions')
        g_out.add_argument(
            "-o", "--output-file", nargs='?', const=S, default=None, metavar="FILE",
            help="Save final output. Defaults to PDF name."
        )
        g_out.add_argument(
            "-e", "--extracted-file", nargs='?', const=S, default=None, metavar="FILE",
            help="Save raw text. Defaults to PDF name."
        )
        g_out.add_argument(
            "--rich-stream", action="store_true",
            help="Render LLM output as Markdown in the terminal."
        )
        g_out.add_argument(
            "--color-logs", action="store_true", help="Enable colored logging output."
        )
        g_out.add_argument(
            "-S", "--speak", nargs='?', const='en', default=None,
            choices=['en', 'es', 'ca'],
            help="Stream final output to speech. Specify language."
        )
        g_out.add_argument(
            "-D", "--dry-run", action="store_true",
            help="Analyze structure without LLM processing."
        )
        g_out.add_argument(
            "-v", "--verbose", action="store_true",
            help="Enable INFO logging for detailed progress."
        )
        g_out.add_argument(
            "-d", "--debug", nargs='?', const="all", default=None,
            dest="debug_topics", metavar="TOPICS",
            help="Enable DEBUG logging for topics (all,layout,structure,reconstruct,llm,tts)."
        )

        return p.parse_args()


def main():
    """
    Main entry point for the script.

    Parses arguments, initializes the Application, and runs the main process,
    handling top-level exceptions like file-not-found and keyboard interrupts.
    """
    # Basic configuration for logging in case of early errors
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    try:
        args = Application.parse_arguments()
        app = Application(args)
        app.run()
    except FileNotFoundError as e:
        # Gracefully handle the case where the PDF file does not exist
        logging.getLogger("ppdf").critical(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logging.getLogger("ppdf").info("\nProcess interrupted by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        # Catch all other unexpected errors
        logging.getLogger("ppdf").critical(
            "\nAn unexpected error occurred: %s", e, exc_info=True
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

