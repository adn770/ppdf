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
- Performance Epilogue: In verbose mode, provides detailed statistics on execution
  time, processing speed, and token counts retrieved directly from the Ollama API.
- Topical Debugging: Allows fine-grained debug logging for specific parts of
  the pipeline (e.g., 'layout', 'llm').
- Rich Terminal Output: Can render the final Markdown in real-time directly
  in the terminal using the `rich` library.
- Multiple Output Modes: Can save to a file, print to stdout, or convert to
  speech.

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
[ Logical Sections ] -> [ LLM Formatting ] -> [ Final Markdown ]
                                                      |
                                                      v
          [ Final Markdown ] -> [ Output (File, stdout, Rich Stream, Speech) ]


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


Installation
============
This script requires several external Python libraries. You can install all of
them with a single command:

    pip install pdfminer.six requests gTTS playsound3 rich

"""

import argparse
import json
import logging
import os
import re
import sys
import tempfile
import time
from collections import Counter

# --- Dependency Imports ---
# Third-party libraries that need to be installed via pip
try:
    import requests
    from gtts import gTTS
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar, LTRect, LTTextLine, LTImage
    from playsound3 import playsound
    from rich.console import Console
    from rich.live import Live
    from rich.markdown import Markdown
except ImportError as e:
    print(f"Error: Missing required library. -> {e}")
    print("Please install all dependencies with:")
    print("pip install pdfminer.six requests gTTS playsound3 rich")
    sys.exit(1)

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
            self.COLORS = {level: '' for level in [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL]}
            self.BOLD = ''
            self.RESET = ''

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        level_name = record.levelname[:5] # Truncate level name
        topic = record.name.split('.')[-1][:5] # Truncate topic name
        
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


# --- PROMPT TEXT CONSTANTS ---
# These constants define the building blocks for the LLM prompt.
# Advanced users can edit these, or override the component-based ones via command-line flags.

# --- Internal Components (not overridable by flags) ---
PROMPT_PERSONA = "You are a meticulous document editor. Your responsibility is to take raw, extracted text and produce a clean, consistent, and structurally perfect Markdown document by strictly following a style guide."
PROMPT_ORIGIN = "The following text is from a PDF document."
PROMPT_TASK_FULL = ("Your sole task is to reformat the text for maximum readability by applying the formatting rules, "
                    "producing the entire output as GitHub Flavored Markdown (GFM). "
                    "Ensure the formatting style is consistent across the entire document, as if it were a single file. "
                    "Under no circumstances should you create tables unless following the 'HTML Table Conversion' rule.")
PROMPT_TASK_ALOUD = "Your sole task is to reformat the text for text-to-speech. Omit tables or provide a very brief description of them."

# This is a specialized, minimalist prompt for converting a table and nothing else.
PROMPT_TABLE_CONVERSION_ONLY = ("Convert the following HTML table to GitHub Flavored Markdown. "
                                "For the content inside each cell, first rejoin any hyphenated words, then replace all remaining newlines with a comma and a space. "
                                "Output ONLY the Markdown table. Do not output any other headings, notes, or text.")


# --- Default Component-based Instructions (overridable by flags) ---
PROMPT_GLOBAL_MANDATES = ("**GLOBAL MANDATES: STYLE GUIDE**\n"
                          "* **Headings:** All headings MUST be formatted using ATX-style. For example: '# Top-Level Heading', '## Sub-Heading'. The use of Setext-style headings ('Heading\\n=======') is strictly forbidden.\n"
                          "* **Stat Blocks:** Text containing RPG stat block abbreviations like 'Ini', 'Atq', 'CA', 'DG', or 'SV' MUST be formatted as a single, dense paragraph. You are strictly forbidden from converting such blocks into lists or tables.")
PROMPT_CONTEXT_DEFAULT = ("You must format specific structures exactly as shown in the following examples:\n\n"
                          "**Stat Block Formatting Example:**\n"
                          '*Input Text:* "Hombres Bestia (2): Ini +1; Atq lanza +0...; AL C."\n'
                          '*Required Output:* "**Hombres Bestia (2):** Ini +1; Atq lanza +0 cuerpo a cuerpo (daño 1d6); CA 12; DG 1d8; 3 pg cada uno; MV 30’; Acc 1d20; SV Fort +1, Ref +1, Vol -1; AL C."\n'
                          "This output MUST be a single, dense paragraph. Do not use lists.\n\n"
                          "**Read-Aloud Text Formatting Example:**\n"
                          '*Input Text:* "Si los PJ se aproximan desde el noroeste, lee o parafrasea lo siguiente: Os deslizáis a través de la angosta abertura, dejándoos caer en la pequeña cueva de abajo. El aire está impregnado de polvo blanquecino..."\n'
                          '*Required Output:* "Si los PJ se aproximan desde el noroeste, lee o parafrasea lo siguiente:\n\n*Os deslizáis a través de la angosta abertura, dejándoos caer en la pequeña cueva de abajo. El aire está impregnado de polvo blanquecino...*"\n')
PROMPT_OBJECTIVE_DEFAULT = "Your primary task is to reconstruct the original paragraphs, ensuring a natural and readable flow."
PROMPT_FORMATTING_RULES_DEFAULT = ("You have three main formatting tasks:\n\n"
                                   "1. **Structural Correction:**\n"
                                   "    * You MUST merge lines to form natural, flowing paragraphs.\n"
                                   "    * You MUST correct words that are hyphenated across line breaks.\n"
                                   "    * You MUST correct obvious typographical and OCR errors, such as words incorrectly split by spaces (e.g., 'L A HOJA' becomes 'LA HOJA') or clear misspellings (e.g., 'DE MONÍACA' becomes 'DEMONÍACA').\n\n"
                                   "2. **Stylistic Enhancement:**\n"
                                   "    * As you are editing a Tabletop RPG book, apply the following styles to enhance readability based on that genre's conventions:\n"
                                   "        - Apply **bold** formatting to: creature names, NPC names, specific named items (e.g., **hoja demoníaca**), and cross-references to document sections (e.g., **zona H-3**). If the original text contains an explicit introductory label for a note, it should also be bolded.\n"
                                   "        - Apply *italic* formatting to any paragraph that is clearly intended to be read aloud, such as one that immediately follows a line ending in \"lee o parafrasea lo siguiente:\".\n\n"
                                   "3. **HTML Table Conversion:**\n"
                                   "    * When you are given text structured as an HTML `<table>`, you MUST convert it to a GitHub Flavored Markdown table.\n"
                                   "    * **Important:** Do not add any sub-headings or introductory text for the table; the conversion from `<table>` to a GFM table must be direct.\n"
                                   "    * For the content inside each `<th>` and `<td>` tag, you must process it as follows:\n"
                                   "        1. First, fix any words that are hyphenated across line breaks.\n"
                                   "        2. Then, join any remaining multiple lines of text with a comma followed by a space.\n"
                                   "        3. Finally, apply stylistic formatting (**bold**, *italics*) to the processed content where appropriate.")
PROMPT_CONSTRAINTS_DEFAULT = ("Absolutely do not summarize the original content. **Applying the specified structural and stylistic formatting rules is a mandatory requirement, not rephrasing.** "
                              "When you encounter an HTML `<table>` block, your ONLY task is to convert it to a single GFM table. Do NOT add any surrounding prose, descriptions, or commentary (like 'Nota del Editor') that is not present in the original text. "
                              "Under no other circumstances should you add any of your own commentary, notes, or feedback about the corrections you have made. "
                              "Your output must contain ONLY the reformatted text. "
                              "If a translation is not explicitly requested, you MUST respond in the original language of the text. "
                              "Preserve bulleted lists using standard Markdown syntax (like '*' or '-') for each item); do not convert them into tables.")


# --- DOCUMENT MODEL CLASSES (LOGICAL HIERARCHY) ---

class BoundedElement:
    """Base class for any layout element with a computed bounding box."""
    pass


class ContentBlock(BoundedElement):
    """A generic block of content lines.

    Args:
        lines (list): A list of pdfminer LTTextLine objects.
    """
    def __init__(self, lines):
        self.lines = lines
        self.bbox = PDFTextExtractor._compute_bbox(lines) if lines else (0,0,0,0)


class ProseBlock(ContentBlock):
    """A block of content identified as prose."""
    pass

class TableCell:
    """Represents a single cell in a table, which can contain multiple lines of text.

    Args:
        text_lines (list[str]): A list of text strings within the cell.
    """
    def __init__(self, text_lines):
        self.text_lines = text_lines

    @property
    def text(self):
        """Returns the full, multi-line text content of the cell."""
        return "\n".join(self.text_lines)

class TableRow:
    """Represents a single row in a table, containing multiple TableCell objects.

    Args:
        cells (list[TableCell]): A list of TableCell objects in the row.
    """
    def __init__(self, cells):
        self.cells: list[TableCell] = cells

class TableBlock(ContentBlock):
    """A structured representation of a table, containing rows and cells.

    Args:
        all_lines (list): The original LTTextLine objects forming the table.
        rows (list[TableRow]): A list of structured TableRow objects.
    """
    def __init__(self, all_lines, rows):
        super().__init__(all_lines)
        self.rows: list[TableRow] = rows
        self.num_cols = len(rows[0].cells) if (rows and hasattr(rows[0], 'cells')) else 0


class BoxedNoteBlock(ContentBlock):
    """A block of content identified as a boxed note.

    Args:
        text (str): The detected title of the note.
        all_lines (list): All LTTextLine objects within the note's box.
        title_lines (list): The LTTextLine objects identified as the title.
    """
    def __init__(self, text, all_lines, title_lines):
        super().__init__(all_lines)
        self.text = text
        self.title_lines = title_lines


class Title(BoundedElement):
    """Represents a title element.

    Args:
        text (str): The formatted text of the title.
        lines (list): The LTTextLine objects forming the title.
    """
    def __init__(self, text, lines):
        self.text, self.lines = text, lines
        self.bbox = PDFTextExtractor._compute_bbox(lines)


class Column:
    """Represents a single column of text on a page.

    Args:
        lines (list): LTTextLine objects within this column.
        bbox (tuple): The bounding box of the column.
    """
    def __init__(self, lines, bbox):
        self.lines, self.bbox, self.blocks = lines, bbox, []


class LayoutZone(BoundedElement):
    """Represents a vertical region of a page with a consistent column layout.

    Args:
        lines (list): LTTextLine objects within this zone.
        bbox (tuple): The bounding box of the zone.
    """
    def __init__(self, lines, bbox):
        self.lines = lines
        self.bbox = bbox
        self.columns = []


class PageModel:
    """A structured representation of a single PDF page.

    Args:
        layout (pdfminer.layout.LTPage): The page layout object from pdfminer.
    """
    def __init__(self, layout):
        self.page_layout, self.page_num = layout, layout.pageid
        self.title, self.zones = None, []
        self.body_font_size = 12
        self.page_type = "content"  # 'content', 'cover', 'credits', 'art'
        self.rects = [] # Store all visible rectangles for analysis


class Paragraph:
    """
    Represents a logical paragraph of text with its page number.
    For tables, it can store two different text representations: one for
    display (e.g., in a dry run) and one as a standard HTML table for the LLM.
    """
    def __init__(self, lines, page, is_table=False, html_lines=None):
        self.lines, self.page_num, self.is_table = lines, page, is_table
        self.html_lines = html_lines

    def get_text(self):
        """Returns the full text for display, preserving line breaks."""
        return '\n'.join(self.lines)

    def get_html(self):
        """Returns the LLM-specific HTML formatted text."""
        if self.html_lines is None:
            return self.get_text()
        return '\n'.join(self.html_lines)


class Section:
    """Represents a logical section of a document, containing paragraphs.

    Args:
        title (str, optional): The title of the section. Defaults to None.
        page (int, optional): The starting page number of the section. Defaults to None.
    """
    def __init__(self, title=None, page=None):
        self.title, self.paragraphs = title, []
        self.page_start, self.page_end = page, page
        self._last_add_was_merge = False

    def add_paragraph(self, p: Paragraph):
        """
        Adds a Paragraph object to the section, merging it with the previous
        paragraph if it appears to be an unfinished continuation.
        """
        # Check if the previous paragraph is unfinished and should be merged.
        # The `_last_add_was_merge` flag prevents chain-reaction merges.
        if self.last_paragraph and not self._last_add_was_merge and self._paragraph_is_unfinished(self.last_paragraph):
            log_reconstruct.debug("Merging unfinished paragraph with the next.")
            self.last_paragraph.lines.extend(p.lines)
            # Update page numbers if the merged paragraph spans pages
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
        """
        if not p.lines or p.is_table:
            return False
        
        last_line = p.lines[-1].strip()
        if not last_line:
            return False

        # Check for trailing punctuation that suggests continuation
        if last_line.endswith((':', ';', ',')):
            return True

        # Check for unbalanced brackets
        brackets = {'(': ')', '[': ']', '{': '}'}
        stack = []
        for char in last_line:
            if char in brackets.keys():
                stack.append(char)
            elif char in brackets.values():
                if stack and brackets[stack[-1]] == char:
                    stack.pop()
                else:
                    # Unmatched closing bracket, not our concern
                    pass
        
        # If stack is not empty, there's an unclosed opening bracket
        return bool(stack)

    def get_text(self):
        """Returns the full display text of all paragraphs in the section."""
        return "\n\n".join(p.get_text() for p in self.paragraphs)

    @property
    def last_paragraph(self):
        """Returns the last paragraph in the section, or None."""
        return self.paragraphs[-1] if self.paragraphs else None


class PDFTextExtractor:
    """
    Extracts structured text from a PDF file using a multi-stage process.
    """
    def __init__(self, pdf_path, num_cols="auto", rm_footers=True, style=False):
        self.pdf_path, self.num_columns_str = pdf_path, num_cols
        self.remove_footers, self.keep_style = rm_footers, style
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
        """Computes a bounding box enclosing all given line elements."""
        if not lines: return 0, 0, 0, 0
        lines = [l for l in lines if l]
        if not lines or any(not hasattr(l, 'x0') for l in lines): return 0,0,0,0
        return (min(l.x0 for l in lines), min(l.y0 for l in lines),
                max(l.x1 for l in lines), max(l.y1 for l in lines))

    def extract_sections(self, pages_to_process=None):
        """
        Main orchestration method to perform all analysis and reconstruction.
        """
        try:
            self._analyze_page_layouts(pages_to_process)
            return self._build_sections_from_models()
        except Exception as e:
            logging.error("Error during extraction: %s", e, exc_info=True)
            return []

    def _analyze_page_layouts(self, pages_to_process=None):
        """
        Performs Stage 1 (layout) and Stage 2 (content) analysis on the PDF,
        populating self.page_models with a structured representation of each page.
        """
        self.page_models = []
        logging.getLogger("ppdf").info("Starting PDF processing...")
        for page_layout in extract_pages(self.pdf_path):
            if pages_to_process and page_layout.pageid not in pages_to_process:
                continue
            
            page_model = self._analyze_single_page_layout(page_layout)

            if page_model.page_type != 'content':
                self.page_models.append(page_model)
                continue
            
            logging.getLogger("ppdf").info("--- Stage 2: Structuring Content for Page %d ---", page_model.page_num)
            for z_idx, zone in enumerate(page_model.zones):
                log_structure.debug("--- Analyzing Page %d, Zone %d ---", page_model.page_num, z_idx + 1)
                for c_idx, col in enumerate(zone.columns):
                    log_structure.debug("--- Analyzing Page %d, Zone %d, Col %d ---",
                                page_model.page_num, z_idx + 1, c_idx + 1)
                    col.blocks = self._segment_column_into_blocks(
                        col.lines, page_model.body_font_size, col.bbox, page_model.rects
                    )
            self.page_models.append(page_model)

    def _classify_page_type(self, layout, lines, images):
        """
        Classifies a page as 'cover', 'credits', 'art', or 'content' based on heuristics.
        """
        log_layout.debug("--- Page Classification ---")
        num_lines = len(lines)
        num_images = len(images)
        log_layout.debug("  - Total lines: %d, Total images: %d", num_lines, num_images)
        
        if num_images > 0:
            page_area = layout.width * layout.height
            image_area = sum(img.width * img.height for img in images)
            if page_area > 0 and (image_area / page_area) > 0.7:
                log_layout.debug("  - Decision: Large image coverage (%.2f%%). -> 'art'", (image_area/page_area)*100)
                return 'art'
        if num_lines == 0:
            log_layout.debug("  - Decision: No lines found. -> 'art'")
            return 'art'
        
        if num_lines < 5:
            log_layout.debug("  - Decision: Very few lines (%d). -> 'cover'", num_lines)
            return 'cover'

        full_text = " ".join(l.get_text() for l in lines).lower()
        
        credit_keywords = [
            'créditos', 'copyright', 'editor', 'traducción', 'maquetación',
            'cartógrafos', 'ilustración', 'isbn', 'depósito legal'
        ]
        found_keywords = [kw for kw in credit_keywords if kw in full_text]
        keyword_hits = len(found_keywords)
        log_layout.debug("  - Keyword check: Found %d hits. (%s)", keyword_hits, ", ".join(found_keywords) if found_keywords else "None")
        
        if keyword_hits >= 3:
            log_layout.debug("  - Decision: Sufficient keyword hits (>=3). -> 'credits'")
            return 'credits'

        body_font_size = self._get_page_body_font_size(lines, default_on_fail=False)
        if body_font_size:
            title_like_lines = sum(1 for l in lines if self._get_font_size(l) > body_font_size * 1.2)
            title_ratio = title_like_lines / num_lines if num_lines > 0 else 0
            log_layout.debug("  - Title-like line ratio: %.2f (%d of %d lines)", title_ratio, title_like_lines, num_lines)
            if title_ratio > 0.5:
                log_layout.debug("  - Decision: High ratio of title-like lines. -> 'cover'")
                return 'cover'

        log_layout.debug("  - Decision: No special type detected. -> 'content'")
        log_layout.debug("---------------------------")
        return 'content'

    def _analyze_single_page_layout(self, layout):
        page = PageModel(layout)
        logging.getLogger("ppdf").info("--- Stage 1: Analyzing Page Layout %d ---", page.page_num)
        all_lines = sorted(self._find_elements_by_type(layout, LTTextLine), key=lambda x: (-x.y1, x.x0))
        images = self._find_elements_by_type(layout, LTImage)
        all_rects = self._find_elements_by_type(layout, LTRect)
        page.rects = [r for r in all_rects if r.linewidth > 0 and r.width > 10 and r.height > 10]

        page.page_type = self._classify_page_type(layout, all_lines, images)
        logging.getLogger("ppdf").info("Page %d classified as: %s", page.page_num, page.page_type)
        if page.page_type != 'content' or not all_lines:
            return page

        page.body_font_size = self._get_page_body_font_size(all_lines)
        if self.remove_footers:
            footer_y = self._get_footer_threshold_dynamic(all_lines, layout, page.body_font_size)
            content_lines = [l for l in all_lines if l.y0 > footer_y]
        else:
            content_lines = list(all_lines)

        page.title, title_lines = self._detect_page_title(content_lines, layout, page.body_font_size)
        content_lines = [l for l in content_lines if l not in title_lines]

        # --- Zonal Analysis ---
        breakpoints = {layout.y0, layout.y1}
        dominant_rects = [r for r in page.rects if r.width > layout.width * 0.7]
        for r in dominant_rects:
            breakpoints.add(r.y0)
            breakpoints.add(r.y1)
        
        sorted_breaks = sorted(list(breakpoints), reverse=True)
        log_layout.debug("Page %d: Found %d vertical zone breakpoints at %s", page.page_num, len(sorted_breaks), [f"{y:.2f}" for y in sorted_breaks])

        for i in range(len(sorted_breaks) - 1):
            y_top, y_bottom = sorted_breaks[i], sorted_breaks[i+1]
            if y_top - y_bottom < page.body_font_size: continue # Skip tiny zones

            zone_bbox = (layout.x0, y_bottom, layout.x1, y_top)
            zone_lines = [l for l in content_lines if l.y1 <= y_top and l.y0 >= y_bottom]
            if not zone_lines: continue
            
            zone = LayoutZone(zone_lines, zone_bbox)
            log_layout.debug("  - Zone %d (y: %.2f -> %.2f) has %d lines.", len(page.zones)+1, y_top, y_bottom, len(zone_lines))

            is_dominant_note_zone = any(r.y1 <= y_top and r.y0 >= y_bottom for r in dominant_rects)
            if is_dominant_note_zone:
                num_cols = 1
                log_layout.debug("    This zone contains a dominant rect, forcing 1 column.")
            else:
                 num_cols = int(self.num_columns_str) if self.num_columns_str != 'auto' else self._detect_column_count(zone.lines, layout)
            logging.getLogger("ppdf").info("Page %d, Zone %d: Detected %d column(s).", page.page_num, len(page.zones)+1, num_cols)

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
        """Stage 2: Segments a column's lines into logical blocks, including boxed notes."""
        if not lines: return []
        
        line_to_box_map = {}
        sorted_rects = sorted(page_rects, key=lambda r: (-r.y1, r.x0))
        for r in sorted_rects:
            box_lines = [l for l in lines if l not in line_to_box_map and (r.x0-1<l.x0 and r.y0-1<l.y0 and r.x1+1>l.x1 and r.y1+1>l.y1)]
            if box_lines:
                for l in box_lines: line_to_box_map[l] = r

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
                current_pos = max(lines.index(l) for l in b_lines) + 1 if b_lines else current_pos + 1
            else:
                block_lines = []
                end_pos = current_pos
                while end_pos < len(lines) and lines[end_pos] not in line_to_box_map:
                    block_lines.append(lines[end_pos])
                    end_pos += 1
                
                if block_lines:
                    blocks.extend(self._segment_prose_and_tables(block_lines, font_size, col_bbox))
                
                processed_lines.update(block_lines)
                current_pos = end_pos
        
        return self._merge_multiline_titles(blocks)

    def _segment_prose_and_tables(self, lines, font_size, col_bbox):
        """Helper to segment a run of lines into Prose, Table, and Title blocks."""
        if not lines: return []
        split_indices = [i for i, line in enumerate(lines) if self._is_block_separator(line, font_size, col_bbox)]
        blocks = []
        all_split_points = sorted(list(set([0] + split_indices + [len(lines)])))

        for i in range(len(all_split_points) - 1):
            start_idx, end_idx = all_split_points[i], all_split_points[i+1]
            block_lines = lines[start_idx:end_idx]
            if not block_lines: continue

            first_line = block_lines[0]
            if self._is_line_a_title(first_line, font_size, col_bbox):
                blocks.append(Title(self._format_line_with_style(first_line), [first_line]))
                if len(block_lines) > 1: blocks.append(ProseBlock(block_lines[1:]))
            elif self._is_likely_table_header(first_line, font_size):
                log_structure.debug("Calling _refine_table_lines_by_header with a block of %d lines starting with '%s...'", len(block_lines), block_lines[0].get_text().strip()[:30])
                table_lines = self._refine_table_lines_by_header(block_lines, font_size)
                log_structure.debug("_refine_table_lines_by_header returned %d lines.", len(table_lines))
                
                if table_lines:
                    table_block = self._parse_table_structure(table_lines, font_size)
                    blocks.append(table_block)
                # Handle remaining lines if the function was conservative
                if len(table_lines) < len(block_lines):
                    log_structure.warning("JUNK PARA WARNING: _refine_table_lines_by_header returned fewer lines (%d) than provided (%d). Creating a ProseBlock from the remainder.", len(table_lines), len(block_lines))
                    remaining_lines = block_lines[len(table_lines):]
                    blocks.append(ProseBlock(remaining_lines))
            else:
                blocks.append(ProseBlock(block_lines))
        return blocks

    def _is_block_separator(self, line, font_size, col_bbox):
        """Determines if a line is a title or a likely table header."""
        return self._is_line_a_title(line, font_size, col_bbox) or \
               self._is_likely_table_header(line, font_size)

    def _is_likely_table_header(self, line, font_size):
        """Checks if a line is a plausible table header using strong signals."""
        phrases = self._get_column_phrases_from_line(line, font_size)
        num_cols = len(phrases)
        if num_cols < 2: return False

        text = line.get_text().strip()
        has_dice_pattern = bool(re.search(r'\b\d+d\d+\b', text, re.I))
        capitalized_phrases = sum(1 for p, _ in phrases if p and p[0].isupper())
        cap_ratio = capitalized_phrases / num_cols if num_cols > 0 else 0
        has_cap_pattern = cap_ratio > 0.6 and num_cols < 5
        fonts = self._get_line_fonts(line)
        is_font_consistent = len(fonts) == 1
        is_bold = "bold" in list(fonts)[0].lower() if is_font_consistent else False

        log_structure.debug("  Header check for '%s...': cols=%d, dice=%s, caps_ratio=%.2f (%s), font_consistent=%s, bold=%s", text[:40], num_cols, has_dice_pattern, cap_ratio, has_cap_pattern, is_font_consistent, is_bold)
        return has_dice_pattern or has_cap_pattern or is_bold

    def _refine_table_lines_by_header(self, lines, font_size):
        """
        Refines a pre-bounded list of table lines based on header content.

        This function acts as a safeguard for special "random roll" tables. It inspects
        the header line for a dice pattern (e.g., "1d10"). If found, it truncates
        the line list to the expected number of rows. For all other tables, it trusts
        the input boundaries and returns the provided list of lines unmodified.
        """
        if not lines: return []
        
        log_structure.debug("  Table Extent Analysis Started...")
        header_line = lines[0]
        header_text = header_line.get_text().strip()
        phrases = self._get_column_phrases_from_line(header_line, font_size)
        
        if not phrases or len(phrases) < 2:
            return lines

        # Check for the dice roll pattern heuristic
        expected_rows = 0
        dice_match = re.search(r'(?i)(\d*)d(\d+)', header_text)
        if dice_match:
            try:
                num_dice = int(dice_match.group(1)) if dice_match.group(1) else 1
                die_type = int(dice_match.group(2))
                if die_type in [4, 5, 6, 8, 10, 12, 16, 20, 100] and num_dice > 0:
                    expected_rows = die_type
            except (ValueError, IndexError):
                pass
        
        if not expected_rows:
            log_structure.debug("  Table Extent: No dice pattern found. Returning all %d lines provided.", len(lines))
            return lines

        # If we have a dice pattern, use the row counting safeguard
        log_structure.debug("  Table Extent: Dice pattern found. Expecting %d rows. Counting...", expected_rows)
        col_positions = [p[1] for p in phrases]
        table_lines = [header_line]
        row_count = 0
        i = 1
        while i < len(lines):
            current_line = lines[i]
            words = self._get_words_from_line(current_line)
            if not words:
                i += 1
                continue

            is_new_row_start = abs(words[0][1] - col_positions[0]) < font_size
            if is_new_row_start:
                row_count += 1
                if row_count > expected_rows:
                    log_structure.debug("    Ending table early: found new row after expected row count (%d) was met.", expected_rows)
                    break
            
            table_lines.append(current_line)
            i += 1
        
        log_structure.debug("  Table Extent: Dice pattern logic resulted in %d lines.", len(table_lines))
        return table_lines

    def _parse_table_structure(self, table_lines, font_size):
        """Parses a list of table lines into a structured TableBlock object using a geometric grid approach."""
        if not table_lines: return None
        log_structure.debug("--- Starting Geometric Table Structure Parsing ---")
        
        # 1. Define Column Boundaries from header
        header_line = table_lines[0]
        header_phrases = self._get_column_phrases_from_line(header_line, font_size)
        if not header_phrases or len(header_phrases) < 2:
            logging.warning("Geometric Table Parser: Could not parse table header. Treating as prose.")
            return ProseBlock(table_lines)
            
        table_bbox = self._compute_bbox(table_lines)
        num_cols = len(header_phrases)
        col_x_starts = [p[1] for p in header_phrases]
        tolerance = font_size / 2.0
        
        col_boundaries = []
        for i in range(num_cols):
            x0 = col_x_starts[i] - tolerance
            x1 = col_x_starts[i+1] - tolerance if i + 1 < num_cols else table_bbox[2]
            col_boundaries.append((x0, x1))
        log_structure.debug("  Table Parser: Defined %d column boundaries: %s", num_cols, [f"({b[0]:.1f}-{b[1]:.1f})" for b in col_boundaries])

        # 2. Define Row Boundaries from row anchor lines
        def is_anchor(line):
            words = self._get_words_from_line(line)
            return words and abs(words[0][1] - col_x_starts[0]) < tolerance
            
        anchor_lines = [table_lines[0]] + [l for l in table_lines[1:] if is_anchor(l)]
        log_structure.debug("  Table Parser: Found %d row anchor lines.", len(anchor_lines))
        
        row_y_boundaries = []
        for i in range(len(anchor_lines)):
            y1 = anchor_lines[i].y1 + tolerance
            # The bottom of the row is the top of the next row's anchor, or the table bottom
            y0 = (anchor_lines[i+1].y1 + tolerance) if i + 1 < len(anchor_lines) else table_bbox[1]
            row_y_boundaries.append((y0, y1))
        log_structure.debug("  Table Parser: Defined %d row boundaries (Y): %s", len(row_y_boundaries), [f"({b[0]:.1f}-{b[1]:.1f})" for b in row_y_boundaries])

        # 3. Create a grid of cells and populate them
        num_rows = len(row_y_boundaries)
        cell_grid = [[[] for _ in range(num_cols)] for _ in range(num_rows)]

        for line in table_lines:
            line_y_center = (line.y0 + line.y1) / 2
            target_row = -1
            for r_idx, (y0, y1) in enumerate(row_y_boundaries):
                if y0 <= line_y_center < y1:
                    target_row = r_idx
                    break
            if target_row == -1:
                log_structure.debug("      Line '%s...' at y=%.1f could not be assigned to a row. Skipping.", line.get_text().strip()[:20], line_y_center)
                continue
                
            phrases = self._get_column_phrases_from_line(line, font_size)
            for phrase_text, phrase_x0 in phrases:
                clean_text = re.sub(r'[\s\n\r]+', ' ', phrase_text).strip()
                if not clean_text: continue

                target_col = -1
                phrase_x_center = phrase_x0 + (len(phrase_text) * font_size * 0.4) / 2
                for c_idx, (x0, x1) in enumerate(col_boundaries):
                    if x0 <= phrase_x_center < x1:
                        target_col = c_idx
                        break
                
                if target_col != -1:
                    log_structure.debug("        Assigning phrase '%s' to cell (%d, %d)", clean_text, target_row, target_col)
                    cell_grid[target_row][target_col].append(clean_text)
                else:
                    logging.warning("        Could not assign phrase '%s' (x0=%.2f) to any column.", clean_text, phrase_x0)
                    
        # 4. Build TableRow and TableCell objects from the populated grid
        parsed_table_rows = []
        for r_idx, row_data in enumerate(cell_grid):
            # Sort the text lines within a cell by their original y-coordinate to maintain order
            # This is complex as we've lost the line object. A simpler approach is to join and let it be.
            table_cells = [TableCell(text_lines) for text_lines in row_data]
            parsed_table_rows.append(TableRow(table_cells))
            log_structure.debug("    --> Parsed Row %d Content: %s", r_idx, [[f'"{l}"' for l in cell.text_lines] for cell in table_cells])
        
        log_structure.debug("--- Finished Geometric Table Structure Parsing ---")
        return TableBlock(table_lines, parsed_table_rows)

    def _format_table_for_display(self, table_block: TableBlock):
        """Formats a structured TableBlock into a list of aligned text lines for display."""
        if not table_block or not table_block.rows: return []
        
        # 1. Calculate column widths from the structured data
        col_widths = [0] * table_block.num_cols
        for row in table_block.rows:
            for i, cell in enumerate(row.cells):
                if i < table_block.num_cols:
                    max_line_width = max(len(line) for line in cell.text_lines) if cell.text_lines else 0
                    col_widths[i] = max(col_widths[i], max_line_width)
        log_structure.debug("  Table Formatter: Calculated column widths: %s", col_widths)
                
        # 2. Format the grid into padded strings
        output_lines = []
        for row in table_block.rows:
            if not any(c.text_lines for c in row.cells): continue
            
            max_lines_in_row = max(len(cell.text_lines) for cell in row.cells)
            if max_lines_in_row == 0: continue
            
            for line_idx in range(max_lines_in_row):
                output_row_parts = []
                for i, cell in enumerate(row.cells):
                    if i < table_block.num_cols:
                        text_to_pad = cell.text_lines[line_idx] if line_idx < len(cell.text_lines) else ""
                        output_row_parts.append(text_to_pad.ljust(col_widths[i]))
                output_lines.append("  ".join(output_row_parts))
            
        return output_lines

    def _format_table_as_html(self, table_block: TableBlock):
        """Formats a structured TableBlock into a standard HTML table for the LLM."""
        if not table_block or not table_block.rows: return []
        
        output_lines = ["<table>"]
        
        # Format the header
        header_row = table_block.rows[0]
        output_lines.append("  <thead>")
        output_lines.append("    <tr>")
        for cell in header_row.cells:
            output_lines.append(f"      <th>{cell.text}</th>")
        output_lines.append("    </tr>")
        output_lines.append("  </thead>")
        
        # Format the data rows
        output_lines.append("  <tbody>")
        for row in table_block.rows[1:]:
            output_lines.append("    <tr>")
            for cell in row.cells:
                output_lines.append(f"      <td>{cell.text}</td>")
            output_lines.append("    </tr>")
        output_lines.append("  </tbody>")
        
        output_lines.append("</table>")
        
        return output_lines

    def _merge_multiline_titles(self, blocks):
        if not blocks: return []
        merged_blocks, i = [], 0
        while i < len(blocks):
            current_block = blocks[i]
            if isinstance(current_block, Title):
                title_lines = current_block.lines
                while (i + 1) < len(blocks) and isinstance(blocks[i+1], Title):
                    i += 1
                    title_lines.extend(blocks[i].lines)
                merged_text = " ".join(self._format_line_with_style(l) for l in title_lines)
                merged_blocks.append(Title(merged_text, title_lines))
            else:
                merged_blocks.append(current_block)
            i += 1
        return merged_blocks
    
    def _build_sections_from_models(self):
        """Stage 3: Walks the analyzed PageModels to build final Section objects."""
        logging.getLogger("ppdf").info("--- Stage 3: Reconstructing Document from Page Models ---")
        sections, current_section = [], None
        last_title, cont = None, 2

        def finalize_section(sec):
            if sec and sec.paragraphs:
                log_reconstruct.debug("Finalizing section '%s' (%d paras)", sec.title, len(sec.paragraphs))
                sections.append(sec)

        for page in self.page_models:
            log_reconstruct.debug("Reconstructing from Page %d (%s)", page.page_num, page.page_type)
            
            if page.page_type != 'content':
                finalize_section(current_section); current_section = None
                last_title = f"({page.page_type.capitalize()} Page)"
                continue

            if page.title:
                finalize_section(current_section)
                log_reconstruct.debug("Page Title found: '%s'. Creating new section.", page.title.text)
                current_section, last_title, cont = Section(page.title.text, page.page_num), page.title.text, 2

            for zone in page.zones:
                for col in zone.columns:
                    for block in col.blocks:
                        if not current_section:
                            title = f"{last_title} ({self._to_roman(cont)})" if last_title else "Untitled Section"
                            log_reconstruct.debug("No active section. Creating new untitled section (or continuation: '%s').", title)
                            if last_title: cont += 1
                            current_section = Section(title, page.page_num)
                        
                        if isinstance(block, Title):
                            finalize_section(current_section)
                            log_reconstruct.debug("Column Title found: '%s'. Creating new section.", block.text)
                            current_section = Section(block.text, page.page_num)
                            last_title, cont = block.text, 2
                        elif isinstance(block, BoxedNoteBlock):
                            dangling_paragraph = None
                            if current_section and current_section.last_paragraph:
                                dangling_paragraph = current_section.paragraphs.pop()
                                log_reconstruct.debug("Dangling paragraph found and saved, will be continued after the note.")

                            finalize_section(current_section)

                            body = [l for l in block.lines if l not in block.title_lines]
                            note_sec = Section(block.text, page.page_num)
                            if body:
                                body_text_lines = [self._format_line_with_style(l) for l in body]
                                if any(line.strip() for line in body_text_lines):
                                    note_sec.add_paragraph(Paragraph(body_text_lines, page.page_num))
                            sections.append(note_sec)
                            
                            if dangling_paragraph:
                                title = f"{last_title} ({self._to_roman(cont)})" if last_title else "Untitled Section"
                                log_reconstruct.debug("Creating continuation section '%s' for the dangling paragraph.", title)
                                if last_title:
                                    cont += 1
                                current_section = Section(title, page.page_num)
                                current_section.add_paragraph(dangling_paragraph)
                            else:
                                current_section = None

                        elif isinstance(block, TableBlock):
                            display_lines = self._format_table_for_display(block)
                            html_lines = self._format_table_as_html(block)
                            if display_lines:
                                current_section.add_paragraph(Paragraph(
                                    lines=display_lines,
                                    page=page.page_num,
                                    is_table=True,
                                    html_lines=html_lines
                                ))
                        elif isinstance(block, ProseBlock):
                            self._process_prose_block(block, current_section, page.page_num, page.body_font_size)
        
        finalize_section(current_section)
        return sections

    def _process_prose_block(self, block, section, page, font_size):
        if not block.lines: return
        for p_lines in self._split_prose_block_into_paragraphs(block.lines, font_size):
            section.add_paragraph(Paragraph([self._format_line_with_style(l) for l in p_lines], page))
    
    def _get_column_phrases_from_line(self, line, font_size):
        words = self._get_words_from_line(line)
        if not words: return []
        gap_threshold, phrases, current_phrase, start_x = font_size, [], [], -1
        if words:
            current_phrase, start_x, last_x = [words[0][0]], words[0][1], words[0][2]
            for i in range(1, len(words)):
                text, x0, x1 = words[i]
                if x0 - last_x > gap_threshold:
                    phrases.append((" ".join(current_phrase), start_x)); current_phrase, start_x = [text], x0
                else: current_phrase.append(text)
                last_x = x1
            phrases.append((" ".join(current_phrase), start_x))
        log_structure.debug("    Line tokenized into %d phrases: %s", len(phrases), [p[0] for p in phrases])
        return phrases

    def _get_words_from_line(self, line):
        words, word_chars, start_x, last_x = [], [], -1, -1
        for char in line:
            if isinstance(char, LTChar) and char.get_text().strip():
                if not word_chars or char.x0 - last_x > 1.0:
                    if word_chars: words.append(("".join(word_chars), start_x, last_x))
                    word_chars, start_x = [char.get_text()], char.x0
                else: word_chars.append(char.get_text())
                last_x = char.x1
        if word_chars: words.append(("".join(word_chars), start_x, last_x))
        return words

    def _is_line_a_title(self, line, font_size, col_bbox, is_continuation=False, prev_line=None):
        size = self._get_font_size(line)
        text = line.get_text().strip()
        if not text: return False
        
        rel_x_center = ((line.x0 + line.x1) / 2) - ((col_bbox[0] + col_bbox[2]) / 2)
        col_width = col_bbox[2] - col_bbox[0] if col_bbox[2] > col_bbox[0] else 1
        is_centered = abs(rel_x_center) < (col_width * 0.2)

        if is_continuation:
            prev_size = self._get_font_size(prev_line)
            is_byline = prev_size > size and is_centered
            decision = (abs(size - prev_size) < 1.0 or is_byline) and (prev_line.y0 - line.y1) < (size * 1.5)
            log_structure.debug("  Title continuation check for '%s': decision=%s", text[:30], decision)
            return decision

        is_larger = size > (font_size * 1.2)
        is_caps = text.isupper() and 1 < len(text.split()) < 10
        decision = is_larger or (is_caps and is_centered)

        log_structure.debug("  Title check for '%s...': size=%.2f (body=%.2f, larger=%s), centered=%s, caps=%s -> decision=%s", text[:30], size, font_size, is_larger, is_centered, is_caps, decision)
        return decision

    def _find_elements_by_type(self, obj, t):
        e = [];
        if isinstance(obj, t): e.append(obj)
        if hasattr(obj, '_objs'):
            for child in obj: e.extend(self._find_elements_by_type(child, t))
        return e

    def _find_title_in_box(self, lines_in_box):
        if not lines_in_box or not "".join(l.get_text() for l in lines_in_box).strip(): return "Note", []
        font_sizes = [self._get_font_size(line) for line in lines_in_box if line.get_text().strip()]
        if not font_sizes: return "Note", []

        counts = Counter(font_sizes)
        box_body_font_size = counts.most_common(1)[0][0]
        log_structure.debug("  Box Note Title Check: Body font size is %.2f.", box_body_font_size)
        
        box_bbox = self._compute_bbox(lines_in_box)
        box_width = box_bbox[2] - box_bbox[0]
        box_center_x = (box_bbox[0] + box_bbox[2]) / 2

        title_lines = []
        for i, line in enumerate(lines_in_box[:4]):
            line_text = line.get_text().strip()
            if not line_text: continue

            font_size = self._get_font_size(line)
            fonts = self._get_line_fonts(line)
            is_bold = any("bold" in f.lower() for f in fonts)
            is_all_caps = line_text.isupper() and len(line_text.split()) < 7
            
            line_center_x = (line.x0 + line.x1) / 2
            is_centered = abs(line_center_x - box_center_x) < (box_width * 0.25)
            is_larger_font = font_size > box_body_font_size * 1.1
            is_short_punctuation = len(line_text) <= 2 and not any(c.isalnum() for c in line_text)

            signals = [is_larger_font, is_bold, is_all_caps, is_centered]
            is_title = sum(signals) >= 2
            if not is_title and is_short_punctuation and is_larger_font: is_title = True

            if is_title:
                title_lines.append(line)
            elif title_lines:
                break
                
        if title_lines:
            title_text = " ".join(self._format_line_with_style(l) for l in title_lines)
            if title_text.upper() not in ["NOTE", "WARNING", "IMPORTANT", "CAUTION", "BOX"]:
                log_structure.debug("  --> Found title for box: '%s'", title_text)
                return title_text, title_lines
        return "Note", []

    def _get_font_size(self, line):
        if not hasattr(line,'_objs') or not line._objs: return 0
        sizes=[c.size for c in line if isinstance(c,LTChar) and hasattr(c,'size')]; return Counter(sizes).most_common(1)[0][0] if sizes else 0
    
    def _get_line_fonts(self, line):
        if not hasattr(line, '_objs') or not line._objs: return set()
        return set(c.fontname for c in line if isinstance(c, LTChar))

    def _get_page_body_font_size(self, lines, default_on_fail=True):
        if not lines: return 12 if default_on_fail else None
        sizes=[s for l in lines if(s:=self._get_font_size(l))and 6<=s<=30]
        if not sizes: return 12 if default_on_fail else None
        most_common = Counter(sizes).most_common(1)[0][0]
        log_layout.debug("Determined page body font size: %.2f", most_common)
        return most_common

    def _get_footer_threshold_dynamic(self, lines, layout, font_size):
        limit=layout.y0+(layout.height*0.12)
        p=re.compile(r"^((page|pág\.?)\s+)?\s*-?\s*\d+\s*-?\s*$",re.I)
        cands=[]
        log_layout.debug("Footer check: limit_y=%.2f, body_font_size=%.2f", limit, font_size)
        for l in lines:
            if l.y0 <= limit:
                text = l.get_text().strip()
                l_size = self._get_font_size(l)
                is_match = p.match(text) is not None
                is_small = l_size < (font_size * 0.85)
                if text and (is_match or is_small): cands.append(l)
        if not cands: return 0
        footer_y = max(l.y1 for l in cands)+1
        log_layout.debug("Footer threshold set to y=%.2f", footer_y)
        return footer_y

    def _detect_column_count(self, lines, layout):
        if len(lines) < 5:
            log_layout.debug("Column check: Too few lines (%d), defaulting to 1.", len(lines))
            return 1
        
        mid_x = layout.x0 + layout.width / 2
        leeway = layout.width * 0.05
        left_lines = [l for l in lines if l.x1 < mid_x + leeway]
        right_lines = [l for l in lines if l.x0 > mid_x - leeway]

        if not left_lines or not right_lines:
            log_layout.debug("Column check: No lines on one or both halves. Left: %d, Right: %d. Decision: 1 column.", len(left_lines), len(right_lines))
            return 1

        max_x_left = max((l.x1 for l in left_lines), default=layout.x0)
        min_x_right = min((l.x0 for l in right_lines), default=layout.x1)

        if max_x_left < min_x_right:
            log_layout.debug("Column check: Gutter detected between %.2f and %.2f. Decision: 2 columns.", max_x_left, min_x_right)
            return 2
        
        log_layout.debug("Column check: No clear gutter found (max_x_left=%.2f, min_x_right=%.2f). Using fallback width analysis.", max_x_left, min_x_right)
        
        left_chars = [c for l in left_lines for c in l if isinstance(c, LTChar) and c.get_text().strip()]
        right_chars = [c for l in right_lines for c in l if isinstance(c, LTChar) and c.get_text().strip()]
        
        if not left_chars or not right_chars:
            log_layout.debug("Column check: Fallback found no text on one side. Decision: 1 column.")
            return 1
            
        left_text_width = max(c.x1 for c in left_chars) - min(c.x0 for c in left_chars) if left_chars else 0
        right_text_width = max(c.x1 for c in right_chars) - min(c.x0 for c in right_chars) if right_chars else 0
        
        half_width = layout.width / 2
        is_left_columnar = left_text_width < half_width * 1.1
        is_right_columnar = right_text_width < half_width * 1.1

        log_layout.debug("Column check fallback: Left text width %.2f (%.1f%% of half), Right text width %.2f (%.1f%% of half)", left_text_width, (left_text_width / half_width * 100), right_text_width, (right_text_width / half_width * 100))
            
        if is_left_columnar and is_right_columnar:
            log_layout.debug("Column check: Fallback width method suggests 2 columns. Decision: 2 columns.")
            return 2
                
        log_layout.debug("Column check: All methods failed to confirm multiple columns. Decision: 1 column.")
        return 1

    def _group_lines_into_columns(self, lines, layout, num):
        if num==1: return [lines]
        cols,width=[[] for _ in range(num)],layout.width/num
        for l in lines:
            idx = max(0, min(num - 1, int((l.x0 - layout.x0) / width)))
            cols[idx].append(l)
        return cols

    def _detect_page_title(self, lines, layout, font_size):
        if not lines: return None,[]
        
        sorted_lines = sorted(lines, key=lambda x: -x.y0)
        top_y_threshold = layout.y0 + layout.height * 0.85 
        
        top_candidates = []
        for l in sorted_lines:
            if l.y0 < top_y_threshold: break
            if self._get_font_size(l) > (font_size * 1.4):
                top_candidates.append(l)
        
        if not top_candidates: return None, []
        log_layout.debug("Page Title Check: Found %d candidates at top of page.", len(top_candidates))

        y_groups = {}
        for l in top_candidates:
            found_group = False
            for y_key in y_groups:
                if abs(l.y1 - y_key) < 10:
                    y_groups[y_key].append(l); found_group = True; break
            if not found_group: y_groups[l.y1] = [l]
        
        for y, group in y_groups.items():
            if len(group) > 1:
                log_layout.debug("--> Detected %d title candidates on the same line (y=%.2f), assuming column headers, not page title.", len(group), y)
                return None, []

        cands = [top_candidates[0]]
        first_title_line_idx = sorted_lines.index(cands[0])

        if cands:
            for i in range(first_title_line_idx + 1, len(sorted_lines)):
                l = sorted_lines[i]
                prev_line = cands[-1]
                
                vertical_gap = prev_line.y0 - l.y1; size = self._get_font_size(l); prev_size = self._get_font_size(prev_line)
                is_close_vertically = vertical_gap < (prev_size * 1.5)
                is_font_similar = abs(size - prev_size) < 2.0
                is_byline = size < prev_size and size >= font_size * 1.1
                is_horizontally_close = abs(l.x0 - prev_line.x0) < (layout.width * 0.2)

                if is_close_vertically and (is_font_similar or is_byline) and is_horizontally_close:
                    cands.append(l)
                else: break

        if cands:
            title_text = " ".join(self._format_line_with_style(l) for l in cands)
            log_layout.debug("--> Detected Page Title: '%s'", title_text)
            return Title(title_text, cands), cands
        
        return None,[]

    def _split_prose_block_into_paragraphs(self, lines, font_size):
        if not lines: return []
        paras,para, v_thresh = [], [], font_size * 1.2
        for i, l in enumerate(lines):
            if not para: para.append(l); continue
            prev_line = para[-1] 
            vertical_gap = prev_line.y0 - l.y1
            log_structure.debug("Prose split check: Gap=%.2f (Thresh=%.2f) between '%s' and '%s'", vertical_gap, v_thresh, prev_line.get_text().strip()[:40], l.get_text().strip()[:40])
            if vertical_gap > v_thresh: paras.append(para); para=[l]
            else: para.append(l)
        if para: paras.append(para)
        return paras

    def _format_line_with_style(self, line):
        if not self.keep_style or not hasattr(line,'_objs'):
            return re.sub(r'\s+',' ',line.get_text()).strip()
        parts,style,buf=[],{'bold':False,'italic':False},[]
        for char in line:
            if not isinstance(char,LTChar): continue
            ctext=char.get_text()
            if not ctext.strip() and not ctext.isspace(): continue
            is_b,is_i="bold" in char.fontname.lower(),"italic" in char.fontname.lower()
            if is_b!=style['bold'] or is_i!=style['italic']:
                if buf:
                    text="".join(buf)
                    if style['bold'] and style['italic']: parts.append(f"***{text}***")
                    elif style['bold']: parts.append(f"**{text}**")
                    elif style['italic']: parts.append(f"*{text}*")
                    else: parts.append(text)
                    buf=[]
            style['bold'],style['italic']=is_b,is_i;buf.append(ctext)
        if buf:
            text="".join(buf)
            if style['bold'] and style['italic']: parts.append(f"***{text}***")
            elif style['bold']: parts.append(f"**{text}**")
            elif style['italic']: parts.append(f"*{text}*")
            else: parts.append(text)
        return re.sub(r'\s+',' ',"".join(parts)).strip()


class ASCIIRenderer:
    """Renders an ASCII art diagram of a PageModel."""
    def __init__(self, extractor, width=80, height=50):
        self.extractor = extractor
        self.width = width
        self.height = height

    def render(self, page_model):
        canvas = [['.' for _ in range(self.width)] for _ in range(self.height)]
        layout = page_model.page_layout

        if page_model.page_type != 'content':
             page_type_text = f"--- SKIPPED ({page_model.page_type.upper()}) ---"
             start_col = (self.width - len(page_type_text)) // 2
             for i, char in enumerate(page_type_text):
                 if 0 <= self.height // 2 < self.height and 0 <= start_col + i < self.width:
                     canvas[self.height // 2][start_col + i] = char
             return '\n'.join(''.join(row) for row in canvas) + '\n'

        # Render all blocks within their zones and columns
        for zone in page_model.zones:
            for col in zone.columns:
                for block in col.blocks:
                    if isinstance(block, ProseBlock):
                        self._draw_fill(canvas, layout, block.bbox, 'a', col.bbox)
                    elif isinstance(block, TableBlock) and block.lines:
                        self._draw_fill(canvas, layout, block.bbox, '=', col.bbox)
                        # Draw table header
                        header_line_bbox = self.extractor._compute_bbox([block.lines[0]])
                        header_full_width_bbox = (block.bbox[0], header_line_bbox[1], block.bbox[2], header_line_bbox[3])
                        # The final argument forces the header to a single line in the ASCII render
                        self._draw_fill(canvas, layout, header_full_width_bbox, 'h', col.bbox, force_single_line=True)
                    elif isinstance(block, BoxedNoteBlock):
                        self._draw_fill(canvas, layout, block.bbox, '•', col.bbox)
                        self._draw_text(canvas, layout, block.title_lines, block.bbox, centered=True, v_centered=True)
                    elif isinstance(block, Title):
                        self._draw_text(canvas, layout, block.lines, col.bbox, centered=False)

        if page_model.title:
            self._draw_text(canvas, layout, page_model.title.lines, page_model.page_layout.bbox, centered=True)
        
        # Layer 5: Separators (per-zone)
        for zone in page_model.zones:
            zone_coords = self._to_grid_coords(layout, zone.bbox)
            if not zone_coords: continue
            _, zone_sr, _, zone_er = zone_coords

            # Draw column dividers for this zone
            if len(zone.columns) > 1:
                for i in range(1, len(zone.columns)):
                    sep_x = zone.columns[i - 1].bbox[2]
                    sep_c = int((sep_x - layout.x0) / layout.width * self.width)
                    if 0 < sep_c < self.width:
                        for r in range(zone_sr, zone_er + 1):
                             if 0 <= r < self.height: canvas[r][sep_c] = '|'
            
            # Draw table dividers for tables within this zone
            for col in zone.columns:
                for block in col.blocks:
                    if isinstance(block, TableBlock) and block.lines:
                        phrases = self.extractor._get_column_phrases_from_line(block.lines[0], page_model.body_font_size)
                        coords = self._to_grid_coords(layout, block.bbox, col.bbox)
                        if not coords: continue
                        _, sr, _, er = coords
                        for _, x_pos in phrases[1:]:
                            sep_c = int((x_pos - layout.x0) / layout.width * self.width) - 1
                            for r in range(max(0,sr), min(self.height, er + 1)):
                                if 0 <= sep_c < self.width and canvas[r][sep_c] in ('=','h'):
                                    canvas[r][sep_c] = ':'
        
        return '\n'.join(''.join(row) for row in canvas) + '\n'


    def _to_grid_coords(self, page_layout, bbox, clip_box=None):
        if not bbox or page_layout.width == 0 or page_layout.height == 0: return None
        x0, y0, x1, y1 = bbox
        if clip_box:
            x0, y0 = max(x0, clip_box[0]), max(y0, clip_box[1])
            x1, y1 = min(x1, clip_box[2]), min(y1, clip_box[3])
        if x1 <= x0 or y1 <= y0: return None
        return (int((x0 - page_layout.x0) / page_layout.width * self.width),
                int((page_layout.y1 - y1) / page_layout.height * self.height),
                int((x1 - page_layout.x0) / page_layout.width * self.width),
                int((page_layout.y1 - y0) / page_layout.height * self.height))

    def _draw_fill(self, canvas, page_layout, bbox, char, clip_box=None, force_single_line=False):
        coords = self._to_grid_coords(page_layout, bbox, clip_box)
        if not coords: return
        sc, sr, ec, er = coords
        # If forced, collapse the vertical fill to just the starting row.
        if force_single_line:
            er = sr
        for r in range(max(0, sr), min(self.height, er + 1)):
            for c in range(max(0, sc), min(self.width, ec + 1)):
                if 0 <= r < self.height and 0 <= c < self.width: canvas[r][c] = char

    def _draw_text(self, canvas, page_layout, lines, clip_box=None, centered=False, v_centered=False):
        if not lines: return

        # Vertical Centering Logic
        if v_centered and clip_box:
            clip_coords = self._to_grid_coords(page_layout, clip_box)
            if clip_coords:
                _, clip_sr, _, clip_er = clip_coords
                start_sr = (clip_sr + (clip_er - clip_sr) // 2) - (len(lines) // 2)

                for i, line in enumerate(lines):
                    current_sr = start_sr + i
                    text = self.extractor._format_line_with_style(line)
                    line_coords = self._to_grid_coords(page_layout, line.bbox, clip_box)
                    if not line_coords: continue
                    sc, _, ec, _ = line_coords
                    
                    available_width = ec - sc
                    if available_width <= 0: continue
                    truncated_text = text[:available_width]
                    
                    start_col = sc
                    if centered:
                        container_sc, _, container_ec, _ = self._to_grid_coords(page_layout, clip_box)
                        container_width = container_ec - container_sc
                        center_point = container_sc + container_width // 2
                        start_col = max(container_sc, center_point - len(truncated_text) // 2)
                    
                    for char_idx, char in enumerate(truncated_text):
                        if 0 <= current_sr < self.height and 0 <= start_col + char_idx < self.width:
                            canvas[current_sr][start_col + char_idx] = char
                return

        # Default (non-v_centered) Logic
        for line in lines:
            text = self.extractor._format_line_with_style(line)
            coords = self._to_grid_coords(page_layout, line.bbox, clip_box)
            if not coords: continue
            sc, sr, ec, _ = coords
            
            available_width = ec - sc
            if available_width <= 0: continue
            truncated_text = text[:available_width]
            
            start_col = sc
            if centered:
                container_width, container_sc = self.width, 0
                if clip_box:
                    clip_coords = self._to_grid_coords(page_layout, clip_box)
                    if clip_coords:
                        container_sc, _, container_ec, _ = clip_coords
                        container_width = container_ec - container_sc
                
                center_point = container_sc + container_width // 2
                start_col = max(container_sc, center_point - len(truncated_text) // 2)
            
            for i, char in enumerate(truncated_text):
                if 0 <= sr < self.height and 0 <= start_col + i < self.width:
                    canvas[sr][start_col + i] = char


class Application:
    """Orchestrates the PDF processing workflow based on command-line arguments."""
    DEFAULT_FILENAME_SENTINEL = "__DEFAULT_FILENAME__"
    DEFAULT_CHUNK_SIZE = 4000
    
    def __init__(self, args):
        self.args = args
        self.extractor = PDFTextExtractor(args.pdf_file, args.columns, args.remove_footers, args.keep_style)
        self.stats = {}

    def run(self):
        """Main entry point for the application logic."""
        self.stats['start_time'] = time.monotonic()
        self._configure_logging()
        
        # --- Startup & Configuration ---
        prompt_parts = self._log_run_conditions_and_build_prompt()
        context_size = self._get_model_details()

        if context_size and self.args.chunk_size == self.DEFAULT_CHUNK_SIZE:
            new_chunk_size = int(context_size * 0.8)
            logging.getLogger("ppdf").info(
                "Model context window is %d tokens. Auto-adjusting chunk size to %d.",
                context_size, new_chunk_size
            )
            self.args.chunk_size = new_chunk_size

        if self.args.speak and self.args.mode != 'speech':
            logging.getLogger("ppdf").info("--speak flag used. Overriding mode to 'speech' for optimal TTS output.")
            self.args.mode = 'speech'

        self._resolve_output_filenames()
        
        pages = self._parse_page_selection()
        if pages is None and self.args.pages.lower() != 'all': sys.exit(1)
        
        # --- PDF Processing ---
        pdf_analysis_start = time.monotonic()
        sections = self.extractor.extract_sections(pages)
        self.stats['pdf_analysis_duration'] = time.monotonic() - pdf_analysis_start
        self.stats['pages_processed_count'] = len(self.extractor.page_models)
        self.stats['sections_reconstructed_count'] = len(sections)

        if not self.extractor.page_models: 
            logging.getLogger("ppdf").error("No content could be extracted. Exiting.")
            self._display_performance_epilogue()
            return

        self._save_extracted_text(sections)

        # --- LLM Processing & Output ---
        if self.args.dry_run:
            self._display_dry_run_summary(sections)
        else:
            llm_wall_start = time.monotonic()
            self._generate_output_with_llm(sections, prompt_parts)
            self.stats['llm_wall_duration'] = time.monotonic() - llm_wall_start
        
        self._display_performance_epilogue()

    def _get_model_details(self):
        """Queries Ollama for model details, validates the selected model, and logs info."""
        app_log = logging.getLogger("ppdf")
        app_log.info("Querying details for model: %s...", self.args.model)

        try:
            # Get all available models (tags) for validation
            tags_url = f"{self.args.url}/api/tags"
            tags_response = requests.get(tags_url)
            tags_response.raise_for_status()
            available_models_info = tags_response.json().get('models', [])
            available_model_names = [m['name'] for m in available_models_info]

            # Validate if the selected model exists
            if self.args.model not in available_model_names:
                app_log.error(f"Model '{self.args.model}' not found in Ollama.")
                if available_model_names:
                    available_list_str = "\n".join([f"  - {name}" for name in sorted(available_model_names)])
                    app_log.error(f"Available models are:\n{available_list_str}")
                else:
                    app_log.error("No models appear to be available from the Ollama server.")
                sys.exit(1)

            # Log available models for user info
            if available_models_info:
                output_lines = ["--- Available Models ---"]
                max_len = max(len(name) for name in available_model_names) if available_model_names else 0
                for model_name in sorted(available_model_names):
                    in_use_str = " (in use)" if model_name == self.args.model else ""
                    output_lines.append(f"  - {model_name:<{max_len}} {in_use_str}")
                output_lines.append("----------------------------")
                app_log.info("\n".join(output_lines))

            # Get and log details for the specific model
            show_url = f"{self.args.url}/api/show"
            response = requests.post(show_url, json={"name": self.args.model})
            response.raise_for_status()
            model_info = response.json()

            details = model_info.get('details', {})
            detail_items = {
                "Family": details.get('family', 'N/A'),
                "Parameter Size": details.get('parameter_size', 'N/A'),
                "Quantization": details.get('quantization_level', 'N/A'),
            }

            output_lines = ["--- Ollama Model Details ---"]
            max_key_len = max(len(k) for k in detail_items.keys())
            for key, value in detail_items.items():
                output_lines.append(f"  - {key:<{max_key_len}} : {value}")
            output_lines.append("----------------------------")
            app_log.info("\n".join(output_lines))

            # Extract context size (num_ctx)
            modelfile_content = model_info.get('modelfile', '')
            for line in modelfile_content.split('\n'):
                if 'num_ctx' in line.lower():
                    parts = line.split()
                    if len(parts) == 3 and parts[0].upper() == 'PARAMETER' and parts[1].lower() == 'num_ctx':
                        try:
                            return int(parts[2])
                        except (ValueError, IndexError):
                            continue
            return None

        except requests.exceptions.RequestException as e:
            logging.error("Could not connect to Ollama to get model details: %s", e)
            sys.exit(1)


    def _display_performance_epilogue(self):
        """Displays a summary of performance statistics."""
        app_log = logging.getLogger("ppdf")
        total_duration = time.monotonic() - self.stats.get('start_time', time.monotonic())
        
        # Calculate LLM throughput
        eval_duration_ns = self.stats.get('llm_eval_duration_ns', 0)
        eval_duration_s = eval_duration_ns / 1e9 if eval_duration_ns > 0 else 0
        eval_count = self.stats.get('llm_eval_count', 0)
        tokens_per_sec = (eval_count / eval_duration_s) if eval_duration_s > 0 else 0

        # Build the report string
        report = ["\n--- Performance Epilogue ---"]
        report.append("[ Overall ]")
        report.append(f"  - Total Execution Time: {total_duration:.1f} seconds\n")
        
        report.append("[ PDF Analysis ]")
        report.append(f"  - Pages Processed: {self.stats.get('pages_processed_count', 0)}")
        report.append(f"  - Sections Reconstructed: {self.stats.get('sections_reconstructed_count', 0)}")
        report.append(f"  - Analysis Duration: {self.stats.get('pdf_analysis_duration', 0):.1f} seconds\n")

        if not self.args.dry_run:
            report.append("[ LLM Processing ]")
            report.append(f"  - Total LLM Duration (Wall Clock): {self.stats.get('llm_wall_duration', 0):.1f} seconds")
            report.append(f"  - Text Sent to LLM: {self.stats.get('llm_chars_sent', 0):,} chars")
            report.append(f"  - Text Received from LLM: {self.stats.get('llm_chars_received', 0):,} chars\n")
            
            report.append("  -- LLM Performance (from API) --")
            report.append(f"  - Prompt Tokens Processed: {self.stats.get('llm_prompt_eval_count', 0):,}")
            report.append(f"  - Generated Tokens: {self.stats.get('llm_eval_count', 0):,}")
            report.append(f"  - Generation Speed: {tokens_per_sec:.1f} tokens/sec")
        
        report.append("--------------------------")
        app_log.info("\n".join(report))

    def _log_run_conditions_and_build_prompt(self):
        """Logs arguments and prompt settings, then returns the prompt components."""
        if self.args.debug_topics:
            args_dict = vars(self.args)
            output_lines = ["--- Script Running Conditions ---"]
            max_key_len = max(len(k) for k in args_dict.keys())
            for arg, value in args_dict.items():
                output_lines.append(f"  - {arg:<{max_key_len}} : {value}")
            output_lines.append("---------------------------------")
            log_llm.debug("\n".join(output_lines))
        
        prompt_parts = self._build_llm_prompt()
        lang, persona, mandates, context, objective, formatting_rules, constraints, task, trans = prompt_parts
        
        prompt_log_lines = [
            "--- LLM Prompt Configuration ---",
            f"Persona: {persona}",
            f"Global Mandates: {mandates}",
        ]
        if context: prompt_log_lines.append(f"Context Examples: {context}")
        prompt_log_lines.extend([
            f"Task: {task}",
            f"Objective: {objective}",
            f"Formatting Rules:\n{formatting_rules}",
            f"Constraints: {constraints}",
        ])
        if trans: prompt_log_lines.append(f"Translation: {trans}")
        prompt_log_lines.append("---------------------------------")
        
        logging.getLogger("ppdf").info("\n".join(prompt_log_lines))
        return prompt_parts

    def _configure_logging(self):
        """Configures logging levels and format based on command-line arguments."""
        level = logging.INFO if self.args.verbose else logging.WARNING
        
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        
        if root_logger.hasHandlers():
            root_logger.handlers.clear()
        
        handler = logging.StreamHandler()
        formatter = RichLogFormatter(use_color=self.args.color_logs)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

        app_logger = logging.getLogger("ppdf")
        app_logger.setLevel(level)

        if self.args.debug_topics:
            app_logger.setLevel(logging.INFO)
            user_topics = [t.strip() for t in self.args.debug_topics.split(',')]
            full_topic_names = {'layout', 'structure', 'reconstruct', 'llm'}

            if 'all' in user_topics:
                topics_to_set = full_topic_names
            else:
                topics_to_set = set()
                invalid_topics = []
                for user_topic in user_topics:
                    matches = [full_name for full_name in full_topic_names if full_name.startswith(user_topic)]
                    if len(matches) == 1:
                        topics_to_set.add(matches[0])
                    else:
                        invalid_topics.append(user_topic)
                
                if invalid_topics:
                    logging.warning("Ignoring invalid or ambiguous debug topics: %s", ", ".join(invalid_topics))

            for topic in topics_to_set:
                logging.getLogger(f"ppdf.{topic}").setLevel(logging.DEBUG)
                app_logger.info("Enabled DEBUG logging for topic: '%s'", topic)
        
        if not (self.args.debug_topics and 'all' in self.args.debug_topics):
            logging.getLogger('pdfminer').setLevel(logging.WARNING)
            logging.getLogger('playsound3').setLevel(logging.WARNING)
    
    def _resolve_output_filenames(self):
        if self.args.output_file==self.DEFAULT_FILENAME_SENTINEL or self.args.extracted_file==self.DEFAULT_FILENAME_SENTINEL:
            base=os.path.splitext(os.path.basename(self.args.pdf_file))[0]
            if self.args.output_file==self.DEFAULT_FILENAME_SENTINEL: self.args.output_file=f"{base}.md"
            if self.args.extracted_file==self.DEFAULT_FILENAME_SENTINEL: self.args.extracted_file=f"{base}.extracted"

    def _parse_page_selection(self):
        if self.args.pages.lower()=='all': return None
        pages=set()
        try:
            for p in self.args.pages.split(','):
                part=p.strip()
                if '-' in part: s,e=map(int,part.split('-')); pages.update(range(s,e+1))
                else: pages.add(int(part))
            return pages
        except ValueError: logging.getLogger("ppdf").error("Invalid --pages format: %s.",self.args.pages); return None

    def _display_dry_run_summary(self, sections):
        print("\n--- Document Structure Summary (Dry Run) ---")
        print("\n--- Page Layout Analysis ---")
        renderer = ASCIIRenderer(self.extractor)
        for page in self.extractor.page_models:
            print(f"\n[ Page {page.page_num} Layout ]")
            print(renderer.render(page))
        if sections:
            print("\n--- Reconstructed Sections Summary ---")
            for i, s in enumerate(sections):
                print(f"\nSection {i+1}:\n  Title: {s.title or 'Untitled'}\n  Pages: {s.page_start}-{s.page_end}")
                chars = len(s.get_text())
                num_lines = sum(len(p.lines) for p in s.paragraphs)
                num_paras = len(s.paragraphs)
                num_tables = sum(1 for p in s.paragraphs if p.is_table)
                print(f"  Stats: {num_paras} paras ({num_tables} tables), {num_lines} lines, {chars} chars")
                first_prose_para = next((p for p in s.paragraphs if not p.is_table), None)
                if first_prose_para:
                    preview = first_prose_para.get_text().strip().replace('\n', ' ')
                    print(f"  First Para: \"{preview[:100]}...\"")
                if num_tables > 0:
                    print("  --- Formatted Table(s) ---")
                    for p in s.paragraphs:
                        if p.is_table:
                            indented_table = "\n".join([f"    {line}" for line in p.lines])
                            print(indented_table)
                    print("  ----------------------------")
        print("\n--- End of Dry Run Summary ---")

    def _save_extracted_text(self, sections):
        if self.args.extracted_file and sections:
            content=[f"--- Page {s.page_start}-{s.page_end} (Title: {s.title or 'N/A'}) ---\n{s.get_text()}" for s in sections]
            try:
                with open(self.args.extracted_file,'w',encoding='utf-8') as f: f.write("\n\n\n".join(content))
                logging.getLogger("ppdf").info("Raw extracted text saved to: '%s'", self.args.extracted_file)
            except IOError as e: logging.getLogger("ppdf").error("Error saving raw text: %s", e)

    def _generate_output_with_llm(self, sections, prompt_parts):
        lang = prompt_parts[0]
        total_chars_sent = 0
        total_chars_received = 0

        if self.args.no_chunking:
            logging.getLogger("ppdf").info("Single-prompt mode enabled. Processing entire document at once.")
            full_document_text = "\n\n".join([s.get_text() for s in sections])
            prompt = self._build_single_prompt(full_document_text, prompt_parts)
            log_llm.debug("\nSingle prompt for entire document:\n%s", prompt)
            
            output, llm_stats = self._query_llm_api(self.args.model, self.args.url, prompt, self.args.rich_stream)
            self.stats.update({f'llm_{k}': v for k, v in llm_stats.items()})
            total_chars_sent = len(prompt)
            total_chars_received = len(output) if output else 0
        else:
            output, llm_stats = self._process_in_chunks(sections, prompt_parts)
            self.stats.update({f'llm_{k}': v for k, v in llm_stats.items()})
            total_chars_sent = llm_stats.get('total_chars_sent', 0)
            total_chars_received = llm_stats.get('total_chars_received', 0)

        self.stats['llm_chars_sent'] = total_chars_sent
        self.stats['llm_chars_received'] = total_chars_received

        if not output: 
            logging.getLogger("ppdf").error("Failed to get any response from the LLM.")
            return
            
        if self.args.output_file:
            try:
                with open(self.args.output_file, 'w', encoding='utf-8') as f: f.write(output)
                logging.getLogger("ppdf").info("\nLLM output saved to: '%s'", self.args.output_file)
            except IOError as e: logging.getLogger("ppdf").error("Error saving LLM output: %s", e)
        if self.args.speak: self._speak_text(output, lang)

    def _build_full_system_prompt(self, prompt_parts):
        """Helper to assemble the main system prompt from its components."""
        lang, persona, mandates, context, objective, formatting_rules, constraints, task, trans = prompt_parts
        prompt_components = [persona, mandates, context, task, objective, formatting_rules, constraints, PROMPT_ORIGIN, trans]
        return "\n".join(filter(None, prompt_components))

    def _build_single_prompt(self, text, prompt_parts):
        """Builds a single prompt for the entire document text."""
        system_prompt = self._build_full_system_prompt(prompt_parts)
        return f"{system_prompt}\n\nContent to process:\n---\n{text}\n---"
        
    def _process_in_chunks(self, sections, prompt_parts):
        """Processes the document section by section, chunk by chunk. Returns final text and aggregated stats."""
        full_system_prompt = self._build_full_system_prompt(prompt_parts)
        all_output = []
        
        # Aggregated stats collectors
        total_prompt_eval_count, total_eval_count, total_eval_duration_ns = 0, 0, 0
        total_chars_sent, total_chars_received = 0, 0

        for i,s in enumerate(sections):
            logging.getLogger("ppdf").info("\nProcessing section %d/%d: '%s'", i+1, len(sections), s.title or 'Untitled')
            if not s.paragraphs: continue
            chunks = Application._chunk_paragraphs(s.paragraphs, self.args.chunk_size, self.args.overlap_paragraphs)
            for j,(c_paras,c_text) in enumerate(chunks):
                start,end = c_paras[0].page_num,c_paras[-1].page_num
                
                is_table_only_chunk = c_text.strip().startswith("<table>") and c_text.strip().endswith("</table>")

                if is_table_only_chunk:
                    log_llm.debug("Table-only chunk detected. Using minimalist prompt.")
                    prompt = f"{PROMPT_TABLE_CONVERSION_ONLY}\n\n{c_text}"
                else:
                    h_instr = "Use the section title as a main heading in your output." if j==0 else "Do not repeat content from previous chunks and do not add a title heading."
                    intro = f"This text is {'the beginning of' if j==0 else 'a continuation of'} a section titled '{s.title or 'N/A'}' from pages {start}-{end}."
                    prompt = f"{full_system_prompt}\n\n{h_instr}\n\n{intro}\n\nContent to process:\n---\n{c_text}\n---"

                log_llm.debug("\nPrompt for section %d, chunk %d:\n%s", i+1, j+1, prompt)
                
                resp, chunk_stats = self._query_llm_api(self.args.model, self.args.url, prompt, self.args.rich_stream)
                all_output.append(resp or f"\n[ERROR: Could not process chunk]")
                
                # Aggregate stats
                total_prompt_eval_count += chunk_stats.get('prompt_eval_count', 0)
                total_eval_count += chunk_stats.get('eval_count', 0)
                total_eval_duration_ns += chunk_stats.get('eval_duration', 0)
                total_chars_sent += len(prompt)
                total_chars_received += len(resp) if resp else 0
                
        aggregated_stats = {
            'prompt_eval_count': total_prompt_eval_count,
            'eval_count': total_eval_count,
            'eval_duration_ns': total_eval_duration_ns,
            'total_chars_sent': total_chars_sent,
            'total_chars_received': total_chars_received
        }
        return "\n\n".join(all_output), aggregated_stats

    def _build_llm_prompt(self):
        """Prepares all the components of the LLM prompt based on arguments."""
        task = PROMPT_TASK_FULL if self.args.mode == 'markdown' else PROMPT_TASK_ALOUD
        trans, lang = ("", 'en')
        if self.args.translate:
            language_name = self.args.translate
            trans = f"Translate the entire processed text into {language_name.capitalize()}."
            lang = self.args.translate[:2]
        persona = PROMPT_PERSONA
        mandates = PROMPT_GLOBAL_MANDATES
        context = self.args.llm_prompt_context if self.args.llm_prompt_context is not None else PROMPT_CONTEXT_DEFAULT
        objective = self.args.llm_prompt_objective if self.args.llm_prompt_objective is not None else PROMPT_OBJECTIVE_DEFAULT
        formatting_rules = self.args.llm_formatting_rules if self.args.llm_formatting_rules is not None else PROMPT_FORMATTING_RULES_DEFAULT
        constraints = self.args.llm_prompt_constraints if self.args.llm_prompt_constraints is not None else PROMPT_CONSTRAINTS_DEFAULT
        return lang, persona, mandates, context, objective, formatting_rules, constraints, task, trans

    @staticmethod
    def _chunk_paragraphs(paras, size=4000, overlap=1):
        """
        Chunks a list of Paragraph objects for LLM processing. It intelligently
        selects the correct text representation (standard vs. HTML) for each paragraph.
        """
        if not paras: return []
        def get_para_text(p): return p.get_html() if p.is_table else p.get_text()
        chunks, c_paras, c_len = [], [], 0
        for i, p in enumerate(paras):
            p_text, p_len = get_para_text(p), len(get_para_text(p))
            if c_len > 0 and (c_len + 4 + p_len) > size:
                chunks.append((c_paras, "\n\n".join(get_para_text(cp) for cp in c_paras)))
                c_paras, c_len = [], 0
                for op_i in range(max(0, i - overlap), i):
                    op = paras[op_i]
                    c_paras.append(op)
                    c_len += len(get_para_text(op)) + 4
            c_paras.append(p)
            c_len += p_len + 4
        if c_paras: chunks.append((c_paras, "\n\n".join(get_para_text(cp) for cp in c_paras)))
        return chunks

    @staticmethod
    def _query_llm_api(model, url, prompt, rich_stream=False):
        """Queries the Ollama API, returning the full response text and a dictionary of performance stats."""
        api, headers = f"{url}/api/generate", {'Content-Type': 'application/json'}
        data = {"model": model, "prompt": prompt, "stream": True}
        full_content, stats = "", {}
        
        try:
            r = requests.post(api, headers=headers, json=data, stream=True)
            r.raise_for_status()
            
            if rich_stream:
                console = Console()
                with Live(console=console, auto_refresh=False, vertical_overflow="visible") as live:
                    for line in r.iter_lines():
                        if not line: continue
                        try:
                            j = json.loads(line.decode('utf-8'))
                            chunk = j.get('response','')
                            full_content += chunk
                            live.update(Markdown(full_content), refresh=True)
                            if j.get('done'): stats = j
                        except json.JSONDecodeError: continue
            else:
                print() # Add a newline before the stream
                for line in r.iter_lines():
                    if not line: continue
                    try:
                        j = json.loads(line.decode('utf-8'))
                        chunk = j.get('response','')
                        full_content += chunk
                        print(chunk, end='', flush=True)
                        if j.get('done'): stats = j
                    except json.JSONDecodeError: continue
                print() # Add a newline after the stream
            return full_content, stats

        except requests.exceptions.RequestException as e: 
            logging.getLogger("ppdf.llm").error("Ollama API request failed: %s", e)
            return None, {}
    
    @staticmethod
    def _speak_text(text, lang='en'):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp: temp_path = fp.name
            gTTS(text=text, lang=lang).save(temp_path)
            playsound(temp_path)
            os.remove(temp_path)
        except Exception as e: logging.getLogger("ppdf").error("Error during text-to-speech: %s", e)

    @staticmethod
    def parse_arguments():
        def column_type(value):
            if value == 'auto': return value
            try:
                ivalue = int(value)
                if 1 <= ivalue <= 6: return str(ivalue)
                else: raise argparse.ArgumentTypeError(f"invalid column count: '{value}' is not in the range 1-6.")
            except ValueError: raise argparse.ArgumentTypeError(f"invalid column count: '{value}' is not a valid integer or 'auto'.")

        epilog = """Examples:
  Basic usage (with auto-adjusted chunk size):
    python ppdf.py document.pdf -o "output.md"

  Render output live and see performance stats:
    python ppdf.py document.pdf --rich-stream -v
  
  Enable colored logging for better readability:
    python ppdf.py document.pdf --color-logs -v

  Process a small PDF in a single pass:
    python ppdf.py small.pdf --no-chunking

  Debug only the LLM and structure-detection parts:
    python ppdf.py document.pdf -d llm,structure --color-logs
"""
        p = argparse.ArgumentParser(description="Extract and process text from a PDF.", formatter_class=argparse.RawTextHelpFormatter, add_help=False, epilog=epilog)
        S = Application.DEFAULT_FILENAME_SENTINEL
        
        p.set_defaults(remove_footers=True)
        
        g_opts = p.add_argument_group('options')
        g_opts.add_argument("pdf_file", help="Path to the input PDF file.")
        g_opts.add_argument("-h", "--help", action="help", help="Show this help message and exit.")

        g_proc = p.add_argument_group('Processing Control')
        g_proc.add_argument("-p", "--pages", default="all", metavar="PAGES", help="Specify pages to process, e.g., '1,3,5-7'. (default: all).")
        g_proc.add_argument("-C", "--columns", type=column_type, default="auto", metavar="COUNT", help="Force column count (1-6, or 'auto') for all pages. (default: auto).")
        g_proc.add_argument("--no-remove-footers", dest="remove_footers", action="store_false", help="Disable the default behavior of removing page footers.")
        g_proc.add_argument("-K", "--keep-style", action="store_true", help="Preserve bold/italic formatting as Markdown. (default: disabled).")
        g_proc.add_argument("--no-chunking", action="store_true", help="Process the entire document in a single LLM call. Best for consistency on small documents. May fail on large documents if the context window is exceeded. (default: disabled).")

        g_llm = p.add_argument_group('LLM & Output Configuration')
        g_llm.add_argument("-m", "--mode", choices=['markdown', 'speech'], default="markdown", metavar="MODE", help="Set LLM processing mode ('markdown' or 'speech'). (default: markdown).")
        g_llm.add_argument("-t", "--translate", default=None, metavar="LANG", help="Translate the final output to a specified language (e.g., 'es', 'fr').")
        g_llm.add_argument("-M", "--model", default="llama3.1", metavar="MODEL", help="Ollama model to use. (default: llama3.1).")
        g_llm.add_argument("-U", "--url", default="http://localhost:11434", metavar="URL", help="Ollama API URL. (default: http://localhost:11434).")
        g_llm.add_argument("-z", "--chunk-size", type=int, default=Application.DEFAULT_CHUNK_SIZE, metavar="SIZE", help=f"Max characters per chunk sent to LLM. Is auto-adjusted based on model unless specified. (default: {Application.DEFAULT_CHUNK_SIZE}).")
        g_llm.add_argument("-O", "--overlap-paragraphs", type=int, default=0, metavar="N", help="Number of paragraphs to overlap between chunks (ignored if --no-chunking is used). (default: 0).")
        
        g_prompt = p.add_argument_group('LLM Prompt Customization')
        g_prompt.add_argument("--llm-prompt-context", default=None, metavar="TEXT", help="[DEPRECATED] This flag is no longer used. Context is now built-in.")
        g_prompt.add_argument("--llm-prompt-objective", default=None, metavar="TEXT", help="Override the default prompt text for the main objective.")
        g_prompt.add_argument("--llm-formatting-rules", default=None, metavar="TEXT", help="Override the default prompt text for formatting rules.")
        g_prompt.add_argument("--llm-prompt-constraints", default=None, metavar="TEXT", help="Override the default prompt text for LLM constraints.")

        g_out = p.add_argument_group('Script Output & Actions')
        g_out.add_argument("-o", "--output-file", nargs='?', const=S, default=None, metavar="FILENAME", help="Save final processed output. If no path is given, defaults to the PDF name with a .md extension.")
        g_out.add_argument("-e", "--extracted-file", nargs='?', const=S, default=None, metavar="FILENAME", help="Save raw extracted text before LLM processing. If no path is given, defaults to the PDF name with a .extracted extension.")
        g_out.add_argument("--rich-stream", action="store_true", help="Render LLM output as Markdown in the terminal in real-time. (default: disabled).")
        g_out.add_argument("--color-logs", action="store_true", help="Enable colored and styled logging output in the terminal. (default: disabled).")
        g_out.add_argument("-S", "--speak", action="store_true", help="Convert the final output to speech using gTTS. (default: disabled).")
        g_out.add_argument("-D", "--dry-run", action="store_true", help="Analyze document structure and print a summary without processing or saving files. (default: disabled).")
        g_out.add_argument("-v", "--verbose", action="store_true", help="Enable INFO logging for detailed progress and model information. (default: disabled).")
        g_out.add_argument("-d", "--debug", nargs='?', const="all", default=None, dest="debug_topics", metavar="TOPICS",
                           help="Enable DEBUG logging. Optionally provide a comma-separated list of topics (e.g., 'llm,structure'). "
                                "Available: all, layout, structure, reconstruct, llm. "
                                "Defaults to 'all' if flag is present without a value.")

        args=p.parse_args()
        return args

def main():
    """Main entry point for the script."""
    # We configure logging first so that any errors during argument parsing can be
    # logged if needed, though argparse handles its own error printing.
    args = Application.parse_arguments()
    app = Application(args)

    # The main try-except block wraps the application run
    try:
        app.run()
    except KeyboardInterrupt:
        # Use the configured logger to print the interruption message
        logging.getLogger("ppdf").info("\nProcess interrupted by user. Exiting.")
        sys.exit(0)
    except Exception as e:
        # Use the configured logger for consistency in error reporting
        logging.getLogger("ppdf").critical("\nAn unexpected error occurred: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

