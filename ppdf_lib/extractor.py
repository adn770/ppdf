#!/usr/bin/env python3
"""
core/extractor.py: The core PDF text and structure extraction engine.
This module contains the PDFTextExtractor class, which performs a multi-stage
analysis to parse PDF files, understand their layout (columns, zones, titles),
and reconstruct the logical reading order.
It also defines all the data model classes used to represent the document's
structure, from low-level physical elements like `Column` and `PageModel` to
high-level logical elements like `Section` and `Paragraph`.
"""
import logging
import os
import re
from collections import Counter, defaultdict

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTImage, LTRect, LTTextLine

# --- LOGGING SETUP ---
log_layout = logging.getLogger("ppdf.layout")
log_structure = logging.getLogger("ppdf.structure")
log_reconstruct = logging.getLogger("ppdf.reconstruct")
log_prescan = logging.getLogger("ppdf.prescan")


# --- DOCUMENT MODEL CLASSES (LOGICAL HIERARCHY) ---
class BoundedElement:
    """Base class for any layout element with a computed bounding box."""


class ContentBlock(BoundedElement):
    """A generic block of content lines from the PDF."""

    def __init__(self, lines):
        self.lines = lines
        self.bbox = PDFTextExtractor.compute_bbox(lines) if lines else (0, 0, 0, 0)


class ProseBlock(ContentBlock):
    """A block of content identified as standard prose text."""


class TableCell:
    """Represents a single cell in a table."""

    def __init__(self, text_lines):
        self.text_lines = text_lines

    @property
    def text(self) -> str:
        """Returns the raw, multi-line text content of the cell."""
        return "\n".join(self.text_lines)

    @property
    def pre_processed_text(self) -> str:
        """Returns pre-processed single-line text for the LLM."""
        if not self.text_lines:
            return ""
        # Merge hyphenated lines
        merged_lines = []
        i = 0
        while i < len(self.text_lines):
            line = self.text_lines[i].strip()
            if line.endswith("-") and (i + 1) < len(self.text_lines):
                next_line = self.text_lines[i + 1].strip()
                merged_line = line[:-1] + next_line
                temp_new_lines = [merged_line] + self.text_lines[i + 2 :]
                return TableCell(temp_new_lines).pre_processed_text
            merged_lines.append(line)
            i += 1
        return ", ".join(line for line in merged_lines if line)


class TableRow:
    """A single row in a table, containing multiple TableCell objects."""

    def __init__(self, cells):
        self.cells: list[TableCell] = cells


class TableBlock(ContentBlock):
    """A structured representation of a table."""

    def __init__(self, all_lines, rows):
        super().__init__(all_lines)
        self.rows: list[TableRow] = rows
        self.num_cols = len(rows[0].cells) if (rows and hasattr(rows[0], "cells")) else 0


class BoxedNoteBlock(ContentBlock):
    """A block of content identified as being enclosed in a graphical box."""

    def __init__(self, title_lines, internal_blocks, all_lines):
        super().__init__(all_lines)
        self.title_lines = title_lines
        self.internal_blocks = internal_blocks
        self._title_text = None  # Cache for formatted title

    @property
    def title(self):
        """Returns the formatted title text of the boxed note."""
        if self._title_text is None:
            # Requires access to the extractor's formatting method
            # This will be set after instantiation by the extractor
            self._title_text = "Note"  # Default
        return self._title_text

    @title.setter
    def title(self, value):
        self._title_text = value


class Title(BoundedElement):
    """Represents a title or heading element."""

    def __init__(self, text, lines):
        self.text, self.lines = text, lines
        self.bbox = PDFTextExtractor.compute_bbox(lines)


class Column:
    """Represents a single column of text on a page."""

    def __init__(self, lines, bbox):
        self.lines, self.bbox, self.blocks = lines, bbox, []


class LayoutZone(BoundedElement):
    """A vertical region of a page with a consistent column layout."""

    def __init__(self, lines, bbox):
        self.lines, self.bbox, self.columns = lines, bbox, []


class PageModel:
    """A structured representation of a single PDF page's physical layout."""

    def __init__(self, layout):
        self.page_layout, self.page_num = layout, layout.pageid
        self.title, self.zones = None, []
        self.body_font_size = 12
        self.page_type = "content"
        self.rects = []


class Paragraph:
    """A logical paragraph of text, reconstructed from various blocks."""

    def __init__(self, lines, page, is_table=False, llm_lines=None):
        self.lines, self.page_num, self.is_table = lines, page, is_table
        self.llm_lines = llm_lines
        self.labels: list[str] | None = None

    def get_text(self):
        """Returns the full text for display, preserving line breaks."""
        return "\n".join(self.lines)

    def get_llm_text(self):
        """Returns the LLM-specific text (e.g., Markdown for tables)."""
        if self.is_table and self.llm_lines:
            return "\n".join(self.llm_lines)
        return self.get_text()


class Section:
    """A logical section of a document, such as a chapter or topic."""

    def __init__(self, title=None, page=None):
        self.title, self.paragraphs = title, []
        self.page_start, self.page_end = page, page
        self._last_add_was_merge = False

    def add_paragraph(self, p: Paragraph):
        """Adds a Paragraph, merging with the last one if it seems unfinished."""
        if (
            self.last_paragraph
            and not self._last_add_was_merge
            and self._paragraph_is_unfinished(self.last_paragraph)
        ):
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
        """Checks if a paragraph ends with punctuation suggesting continuation."""
        if not p.lines or p.is_table:
            return False
        last_line = p.lines[-1].strip()
        if not last_line:
            return False
        if last_line.endswith((":", ";", ",")):
            return True
        brackets = {"(": ")", "[": "]", "{": "}"}
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
    Args:
        pdf_path (str): The file path to the PDF.
        num_cols (str): The number of columns to assume ('auto' or a number).
        rm_footers (bool): Whether to attempt footer removal.
        style (bool): Whether to preserve bold/italic formatting.
    """

    def __init__(self, pdf_path, num_cols="auto", rm_footers=True, style=False):
        self.pdf_path = pdf_path
        self.num_columns_str = num_cols
        self.remove_footers = rm_footers
        self.keep_style = style
        self.page_models = []
        self.header_cutoff = float("inf")  # Default: no header cutoff
        self.footer_cutoff = 0  # Default: no footer cutoff
        self.page_manifest = {}  # Stores prescan results for each page
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

    @staticmethod
    def compute_bbox(lines):
        """Computes a bounding box enclosing all given layout elements."""
        if not lines:
            return 0, 0, 0, 0
        lines = [line for line in lines if line]
        if not lines or any(not hasattr(line, "x0") for line in lines):
            return 0, 0, 0, 0
        return (
            min(line.x0 for line in lines),
            min(line.y0 for line in lines),
            max(line.x1 for line in lines),
            max(line.y1 for line in lines),
        )

    def format_line_with_style(self, line):
        """Formats a line, optionally preserving bold/italic markdown."""
        if not self.keep_style or not hasattr(line, "_objs"):
            return re.sub(r"\s+", " ", line.get_text()).strip()
        parts, style, buf = [], {"bold": False, "italic": False}, []
        for char in line:
            if not isinstance(char, LTChar):
                continue
            ctext = char.get_text()
            if not ctext.strip() and not ctext.isspace():
                continue
            is_b = "bold" in char.fontname.lower()
            is_i = "italic" in char.fontname.lower()
            if is_b != style["bold"] or is_i != style["italic"]:
                if buf:
                    text = "".join(buf)
                    if style["bold"] and style["italic"]:
                        parts.append(f"***{text}***")
                    elif style["bold"]:
                        parts.append(f"**{text}**")
                    elif style["italic"]:
                        parts.append(f"*{text}*")
                    else:
                        parts.append(text)
                    buf = []
            style["bold"], style["italic"] = is_b, is_i
            buf.append(ctext)
        if buf:
            text = "".join(buf)
            if style["bold"] and style["italic"]:
                parts.append(f"***{text}***")
            elif style["bold"]:
                parts.append(f"**{text}**")
            elif style["italic"]:
                parts.append(f"*{text}*")
            else:
                parts.append(text)
        return re.sub(r"\s+", " ", "".join(parts)).strip()

    def get_column_phrases_from_line(self, line, font_size):
        """Tokenizes a line into phrases based on horizontal gaps."""
        words = self._get_words_from_line(line)
        if not words:
            return []
        gap_thresh, phrases, current_phrase = font_size, [], []
        start_x, end_x = -1, -1
        for text, x0, x1 in words:
            if not current_phrase or x0 - end_x > gap_thresh:
                if current_phrase:
                    phrases.append((" ".join(current_phrase), start_x, end_x))
                current_phrase, start_x = [text], x0
            else:
                current_phrase.append(text)
            end_x = x1
        if current_phrase:
            phrases.append((" ".join(current_phrase), start_x, end_x))
        return phrases

    def extract_sections(self, pages_to_process=None):
        """Main method to perform all analysis and reconstruction."""
        if self.remove_footers:
            self._prescan(pages_to_process)
        self._analyze_page_layouts(pages_to_process)
        return self._build_sections_from_models()

    def _to_roman(self, n):
        """Converts an integer to a Roman numeral for section continuation."""
        if not 1 <= n <= 3999:
            return str(n)
        val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
        sym = [
            "M",
            "CM",
            "D",
            "CD",
            "C",
            "XC",
            "L",
            "XL",
            "X",
            "IX",
            "V",
            "IV",
            "I",
        ]
        roman_num, i = "", 0
        while n > 0:
            for _ in range(n // val[i]):
                roman_num += sym[i]
                n -= val[i]
            i += 1
        return roman_num

    def _prescan(self, pages_to_process=None):
        """[PRESCAN STAGE] Analyzes all pages to define exclusion zones."""
        log_prescan.info("--- Prescan: Detecting Page Types & Margins ---")
        all_pages = list(extract_pages(self.pdf_path))
        pages_to_scan = [
            p for p in all_pages if not pages_to_process or p.pageid in pages_to_process
        ]
        if len(pages_to_scan) < 3:
            log_prescan.info("  - Not enough pages for reliable analysis. Skipping.")
            return

        total_pages = pages_to_scan[-1].pageid if pages_to_scan else 0

        # Step 1: Create Page Manifest
        margin_lines = defaultdict(list)
        for page_layout in pages_to_scan:
            lines = self._find_elements_by_type(page_layout, LTTextLine)
            images = self._find_elements_by_type(page_layout, LTImage)
            page_type = self._classify_page_type(page_layout, lines, images, total_pages)
            self.page_manifest[page_layout.pageid] = {"type": page_type}
            if page_type != "content":
                continue

            h = page_layout.height
            header_zone_y, footer_zone_y = h * 0.85, h * 0.15
            for line in lines:
                if line.y1 >= header_zone_y or line.y0 <= footer_zone_y:
                    margin_lines[page_layout.pageid].append(line)

        # Step 2: Analyze Margin Lines from Content Pages
        content_page_ids = {
            pid for pid, data in self.page_manifest.items() if data["type"] == "content"
        }
        if len(content_page_ids) < 3:
            log_prescan.info("  - Not enough content pages for reliable analysis. Skipping.")
            return

        line_groups = defaultdict(lambda: {"even": [], "odd": []})
        for page_id in content_page_ids:
            page_type = "even" if page_id % 2 == 0 else "odd"
            for line in margin_lines.get(page_id, []):
                text = re.sub(r"\d+", "#", line.get_text().strip())
                if text:
                    line_groups[text][page_type].append(line)

        # Step 3: Find Consistent Lines and Define Cutoffs
        header_lines, footer_lines = [], []
        consistency_threshold = 0.7 * len(content_page_ids)
        for text, page_groups in line_groups.items():
            for page_type in ["even", "odd"]:
                if len(page_groups[page_type]) >= consistency_threshold / 2:
                    is_header = page_groups[page_type][0].y0 > pages_to_scan[0].height * 0.5
                    target_list = header_lines if is_header else footer_lines
                    target_list.extend(page_groups[page_type])

        if header_lines:
            self.header_cutoff = min(line.y0 for line in header_lines)
            log_prescan.info("  - Header detector: Found at y < %.2f", self.header_cutoff)
        else:
            log_prescan.info("  - Header detector: No consistent headers found.")

        if footer_lines:
            self.footer_cutoff = max(line.y1 for line in footer_lines)
            log_prescan.info("  - Footer detector: Found at y > %.2f", self.footer_cutoff)
        else:
            log_prescan.info("  - Footer detector: No consistent footers found.")

    def _analyze_page_layouts(self, pages_to_process=None):
        """Performs Stage 1 (layout) and Stage 2 (content) analysis."""
        self.page_models = []
        all_pdf_pages = list(extract_pages(self.pdf_path))
        total_pages = all_pdf_pages[-1].pageid if all_pdf_pages else 0
        content_pages_to_structure = []

        logging.getLogger("ppdf").info("--- Stage 1: Analyzing Page Layouts ---")
        for page_layout in all_pdf_pages:
            if pages_to_process and page_layout.pageid not in pages_to_process:
                continue
            page_model = self._analyze_single_page_layout(page_layout, total_pages)
            self.page_models.append(page_model)
            if page_model.page_type == "content":
                content_pages_to_structure.append(page_model)

        logging.getLogger("ppdf").info("--- Stage 2: Structuring Content from Page Models ---")
        for page_model in content_pages_to_structure:
            log_structure.info("Structuring content for Page %d", page_model.page_num)
            for z_idx, zone in enumerate(page_model.zones):
                for c_idx, col in enumerate(zone.columns):
                    log_structure.debug(
                        "Analyzing Page %d, Zone %d, Col %d",
                        page_model.page_num,
                        z_idx + 1,
                        c_idx + 1,
                    )
                    col.blocks = self._segment_column_into_blocks(
                        col.lines,
                        page_model.body_font_size,
                        col.bbox,
                        page_model.rects,
                    )

    def _classify_page_type(self, layout, lines, images, total_pages):
        """Classifies a page as non-content or content."""
        log_prescan.debug("--- Page Classification ---")
        num_lines, num_images = len(lines), len(images)
        log_prescan.debug("  - Total lines: %d, Total images: %d", num_lines, num_images)

        # Positional Heuristic for Covers
        is_first_page = layout.pageid == 1
        is_last_page = layout.pageid == total_pages
        if num_images > 0:
            page_area = layout.width * layout.height
            image_area = sum(img.width * img.height for img in images)
            image_coverage = (image_area / page_area) if page_area > 0 else 0

            if (is_first_page or is_last_page) and image_coverage > 0.7:
                log_prescan.debug(
                    "  - Decision: Positional cover (Page %d, Coverage %.2f%%). -> 'cover'",
                    layout.pageid,
                    image_coverage * 100,
                )
                return "cover"
            if image_coverage > 0.7:
                log_prescan.debug(
                    "  - Decision: Large image coverage (%.2f%%). -> 'art'",
                    image_coverage * 100,
                )
                return "art"

        if num_lines == 0:
            log_prescan.debug("  - Decision: No lines found. -> 'art'")
            return "art"
        if num_lines < 5 and not is_first_page:
            log_prescan.debug("  - Decision: Very few lines (%d). -> 'art'", num_lines)
            return "art"
        if num_lines < 5 and is_first_page:
            log_prescan.debug("  - Decision: Very few lines on first page. -> 'cover'")
            return "cover"

        full_text = " ".join(line.get_text() for line in lines).lower()
        # Check for Open Game License first, as it's very specific
        if "open game license" in full_text:
            log_prescan.debug("  - Decision: Found 'Open Game License'. -> 'legal'")
            return "legal"

        # Check for Table of Contents patterns
        toc_pattern = re.compile(r"(\. ?){5,}\s*\d+\s*$")
        toc_lines = sum(1 for line in lines if toc_pattern.search(line.get_text()))
        if lines and (toc_lines / len(lines)) > 0.3:
            log_prescan.debug("  - Decision: High ratio of ToC patterns. -> 'toc'")
            return "toc"

        # Check for Index patterns
        index_pattern = re.compile(r"^[A-Z][a-zA-Z\s]+,(\s*\d+)+$")
        index_lines = sum(1 for line in lines if index_pattern.search(line.get_text()))
        if lines and (index_lines / len(lines)) > 0.3:
            log_prescan.debug("  - Decision: High ratio of Index patterns. -> 'index'")
            return "index"

        # Check for credits keywords
        credit_kw = [
            "créditos",
            "copyright",
            "editor",
            "traducción",
            "maquetación",
            "cartógrafos",
            "ilustración",
            "isbn",
            "depósito legal",
        ]
        found_kw = [kw for kw in credit_kw if kw in full_text]
        if len(found_kw) >= 3:
            log_prescan.debug("  - Decision: Found %d keywords. -> 'credits'", len(found_kw))
            return "credits"

        body_font_size = self._get_page_body_font_size(lines, default_on_fail=False)
        if body_font_size:
            title_like = sum(
                1 for line in lines if self._get_font_size(line) > body_font_size * 1.2
            )
            title_ratio = title_like / num_lines if num_lines > 0 else 0
            log_prescan.debug("  - Title-like line ratio: %.2f", title_ratio)
            if title_ratio > 0.5:
                log_prescan.debug("  - Decision: High ratio of titles. -> 'cover'")
                return "cover"

        log_prescan.debug("  - Decision: No special type detected. -> 'content'")
        return "content"

    def _analyze_single_page_layout(self, layout, total_pages):
        """Analyzes a single page's layout to produce a PageModel."""
        page = PageModel(layout)
        logging.getLogger("ppdf").info("Analyzing Page Layout %d...", page.page_num)
        all_lines_raw = sorted(
            self._find_elements_by_type(layout, LTTextLine),
            key=lambda x: (-x.y1, x.x0),
        )

        # Use the manifest if available, otherwise classify on the fly
        page.page_type = self.page_manifest.get(page.page_num, {}).get("type")
        if not page.page_type:
            images = self._find_elements_by_type(layout, LTImage)
            page.page_type = self._classify_page_type(
                layout, all_lines_raw, images, total_pages
            )

        logging.getLogger("ppdf").info(
            "Page %d classified as: %s", page.page_num, page.page_type
        )
        if page.page_type != "content":
            return page

        # Apply pre-scan exclusion zones first
        all_lines = [
            line
            for line in all_lines_raw
            if line.y1 < self.header_cutoff and line.y0 > self.footer_cutoff
        ]
        page.rects = [
            r
            for r in self._find_elements_by_type(layout, LTRect)
            if r.linewidth > 0 and r.width > 10 and r.height > 10
        ]
        if not all_lines:
            return page

        page.body_font_size = self._get_page_body_font_size(all_lines)
        # Use dynamic footer detection as a fallback if prescan found nothing
        if self.remove_footers and self.footer_cutoff == 0:
            footer_thresh = self._get_footer_threshold_dynamic(
                all_lines, layout, page.body_font_size
            )
            content_lines = [line for line in all_lines if line.y0 > footer_thresh]
        else:
            content_lines = all_lines

        page_level_cols = self._detect_page_level_column_count(content_lines, layout)

        page.title, title_lines = self._detect_page_title(
            content_lines, layout, page.body_font_size, page_level_cols
        )
        content_lines = [line for line in content_lines if line not in title_lines]

        rect_breaks = {r.y0 for r in page.rects if r.width > layout.width * 0.7}
        rect_breaks.update(r.y1 for r in page.rects if r.width > layout.width * 0.7)
        breakpoints = {layout.y0, layout.y1, *rect_breaks}
        sorted_breaks = sorted(list(breakpoints), reverse=True)

        for i in range(len(sorted_breaks) - 1):
            y_top, y_bottom = sorted_breaks[i], sorted_breaks[i + 1]
            if y_top - y_bottom < page.body_font_size:
                continue
            zone_bbox = (layout.x0, y_bottom, layout.x1, y_top)
            zone_lines = [
                line for line in content_lines if line.y1 <= y_top and line.y0 >= y_bottom
            ]
            if not zone_lines:
                continue
            zone = LayoutZone(zone_lines, zone_bbox)
            log_layout.debug(
                "  - Zone %d (y: %.2f -> %.2f) has %d lines.",
                len(page.zones) + 1,
                y_top,
                y_bottom,
                len(zone_lines),
            )
            # Detect columns for the current zone
            if self.num_columns_str != "auto":
                num_cols = int(self.num_columns_str)
            else:
                num_cols = self._detect_column_count(zone.lines, layout)

            logging.getLogger("ppdf").info(
                "Page %d, Zone %d: Detected %d column(s).",
                page.page_num,
                len(page.zones) + 1,
                num_cols,
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

    def _segment_column_into_blocks(self, lines, font_size, col_bbox, rects):
        """Stage 2: Segments a column's lines into logical blocks."""
        if not lines:
            return []
        line_to_box_map = {}
        sorted_rects = sorted(rects, key=lambda r: (-r.y1, r.x0))
        for rect in sorted_rects:
            box_lines = [
                line
                for line in lines
                if line not in line_to_box_map
                and (
                    rect.x0 - 1 < line.x0
                    and rect.y0 - 1 < line.y0
                    and rect.x1 + 1 > line.x1
                    and rect.y1 + 1 > line.y1
                )
            ]
            if box_lines:
                for line in box_lines:
                    line_to_box_map[line] = rect
        blocks, processed_lines = [], set()
        current_pos = 0
        while current_pos < len(lines):
            line = lines[current_pos]
            if line in processed_lines:
                current_pos += 1
                continue
            if line in line_to_box_map:
                rect = line_to_box_map[line]
                b_lines = [line for line in lines if line_to_box_map.get(line) == rect]
                title_text, title_lines = self._find_title_in_box(b_lines)

                body_lines_in_box = [line for line in b_lines if line not in title_lines]

                internal_blocks = self._segment_prose_and_tables(
                    body_lines_in_box, font_size, col_bbox
                )

                boxed_block = BoxedNoteBlock(title_lines, internal_blocks, b_lines)
                boxed_block.title = title_text
                blocks.append(boxed_block)

                processed_lines.update(b_lines)
                last_idx = max(lines.index(line) for line in b_lines) if b_lines else -1
                current_pos = last_idx + 1
            else:
                block_lines, end_pos = [], current_pos
                while end_pos < len(lines) and lines[end_pos] not in line_to_box_map:
                    block_lines.append(lines[end_pos])
                    end_pos += 1
                if block_lines:
                    blocks.extend(
                        self._segment_prose_and_tables(block_lines, font_size, col_bbox)
                    )
                processed_lines.update(block_lines)
                current_pos = end_pos
        return self._merge_multiline_titles(blocks)

    def _segment_prose_and_tables(self, lines, font_size, col_bbox):
        """Helper to segment lines into Prose, Table, and Title blocks."""
        if not lines:
            return []
        split_indices = [
            i
            for i, line in enumerate(lines)
            if self._is_block_separator(line, font_size, col_bbox)
        ]
        blocks, points = [], sorted(list(set([0] + split_indices + [len(lines)])))
        for i in range(len(points) - 1):
            start_idx, end_idx = points[i], points[i + 1]
            block_lines = lines[start_idx:end_idx]
            if not block_lines:
                continue
            first_line = block_lines[0]
            if self._is_line_a_title(first_line, font_size, col_bbox):
                formatted_line = self.format_line_with_style(first_line)
                blocks.append(Title(formatted_line, [first_line]))
                if len(block_lines) > 1:
                    blocks.append(ProseBlock(block_lines[1:]))
            elif self._is_likely_table_header(first_line, font_size):
                table_lines = self._refine_table_lines_by_header(block_lines, font_size)
                if table_lines:
                    blocks.append(self._parse_table_structure(table_lines, font_size))
                if len(table_lines) < len(block_lines):
                    blocks.append(ProseBlock(block_lines[len(table_lines) :]))
            else:
                blocks.append(ProseBlock(block_lines))
        return blocks

    def _is_block_separator(self, line, font_size, col_bbox):
        """Determines if a line should act as a separator."""
        is_title = self._is_line_a_title(line, font_size, col_bbox)
        is_header = self._is_likely_table_header(line, font_size)
        return is_title or is_header

    def _is_likely_table_header(self, line, font_size):
        """Heuristically determines if a line is a table header."""
        phrases = self.get_column_phrases_from_line(line, font_size)
        num_cols = len(phrases)
        if num_cols < 2:
            return False
        text = line.get_text().strip()
        has_dice = bool(re.search(r"\b\d+d\d+\b", text, re.I))

        # Check for a high ratio of capitalized words
        cap_words = sum(1 for p, _, _ in phrases if p and p[0].isupper())
        cap_ratio = cap_words / num_cols if num_cols > 0 else 0
        has_cap = cap_ratio > 0.6 and num_cols < 5

        # Check for consistent bold styling
        fonts = self._get_line_fonts(line)
        is_font_consistent = len(fonts) == 1
        is_bold = "bold" in list(fonts)[0].lower() if is_font_consistent else False

        return has_dice or has_cap or is_bold

    def _refine_table_lines_by_header(self, lines, font_size):
        """Refines table extent based on header and line density heuristics."""
        if not lines:
            return []
        header_text = lines[0].get_text().strip()
        dice_match = re.search(r"(?i)(\d*)d(\d+)", header_text)
        try:
            expected_rows = int(dice_match.group(2)) if dice_match else -1
        except (ValueError, IndexError):
            expected_rows = -1

        phrases = self.get_column_phrases_from_line(lines[0], font_size)
        if not phrases:
            return lines
        col_x_start = phrases[0][1]
        header_density = self._get_line_density(lines[0])
        log_structure.debug(f"Header line density: {header_density:.2f}")

        table_lines = [lines[0]]
        row_count = 0
        i = 1
        while i < len(lines):
            line = lines[i]
            words = self._get_words_from_line(line)

            if not words:  # Handle empty lines
                if expected_rows != -1 and row_count >= expected_rows:
                    log_structure.debug("Empty line after expected rows. End table.")
                    break
                table_lines.append(line)
                i += 1
                continue

            is_aligned = abs(words[0][1] - col_x_start) < font_size

            # Termination logic for tables with expected row counts
            if expected_rows != -1 and row_count >= expected_rows:
                current_density = self._get_line_density(line)
                line_phrases = self.get_column_phrases_from_line(line, font_size)
                is_single_phrase = len(line_phrases) <= 1
                is_dense_prose = current_density > (header_density * 1.3)

                log_structure.debug(
                    f"Checking line {i + 1} for termination. "
                    f"Density: {current_density:.2f}"
                )
                if is_aligned and (is_single_phrase or is_dense_prose):
                    log_structure.debug(
                        f"Line '{line.get_text().strip()[:50]}...' looks like "
                        f"prose. Terminating table parsing."
                    )
                    break

            if is_aligned:
                row_count += 1
                table_lines.append(line)
            else:
                # If not aligned, could be a multi-line cell. Append it.
                table_lines.append(line)
            i += 1
        return table_lines

    def _parse_table_structure(self, table_lines, font_size):
        """Parses lines into a structured TableBlock object."""
        if not table_lines:
            return ProseBlock([])
        header_phrases = self.get_column_phrases_from_line(table_lines[0], font_size)
        if not header_phrases or len(header_phrases) < 2:
            return ProseBlock(table_lines)

        table_bbox = self.compute_bbox(table_lines)
        num_cols = len(header_phrases)
        log_structure.debug("Table Parser decided on %d columns.", num_cols)

        col_boundaries, left_bound = [], table_bbox[0]
        for i in range(num_cols - 1):
            midpoint = (
                header_phrases[i][2] + (header_phrases[i + 1][1] - header_phrases[i][2]) / 2
            )
            col_boundaries.append((left_bound, midpoint))
            left_bound = midpoint
        col_boundaries.append((left_bound, table_bbox[2]))

        anchor_lines = [table_lines[0]]
        first_col_x = header_phrases[0][1]
        for line in table_lines[1:]:
            words = self._get_words_from_line(line)
            is_new_row = words and abs(words[0][1] - first_col_x) < font_size
            is_close = any(abs(line.y1 - prev.y0) < font_size * 0.5 for prev in anchor_lines)
            if is_new_row and not is_close:
                anchor_lines.append(line)

        row_y_boundaries = [
            (
                ((anchor_lines[i + 1].y1 - 1) if i + 1 < len(anchor_lines) else table_bbox[1]),
                anchor_lines[i].y1 + 1,
            )
            for i in range(len(anchor_lines))
        ]

        grid = [[[] for _ in range(num_cols)] for _ in range(len(row_y_boundaries))]
        for r, (y_bot, y_top) in enumerate(row_y_boundaries):
            lines_in_row = sorted(
                [line for line in table_lines if y_bot <= (line.y0 + line.y1) / 2 < y_top],
                key=lambda line: -line.y1,
            )
            for c, (x_left, x_right) in enumerate(col_boundaries):
                cell_lines = []
                for line in lines_in_row:
                    line_text = "".join(
                        char.get_text()
                        for char in line
                        if isinstance(char, LTChar) and x_left <= char.x0 < x_right
                    ).strip()
                    if line_text:
                        cell_lines.append(line_text)
                grid[r][c] = cell_lines
        parsed_rows = [
            TableRow([TableCell(text_lines) for text_lines in row_data]) for row_data in grid
        ]
        return TableBlock(table_lines, parsed_rows)

    def _format_table_for_display(self, table_block: TableBlock):
        """Formats a TableBlock into a list of strings for readable display."""
        if not table_block or not table_block.rows:
            return []
        widths = [0] * table_block.num_cols
        for row in table_block.rows:
            for i, cell in enumerate(row.cells):
                if i < table_block.num_cols:
                    max_line_len = max((len(line) for line in cell.text_lines), default=0)
                    widths[i] = max(widths[i], max_line_len)
        output_lines = []
        for row in table_block.rows:
            max_lines_in_row = max(len(c.text_lines) for c in row.cells)
            if not any(c.text_lines for c in row.cells) or max_lines_in_row == 0:
                continue
            for line_idx in range(max_lines_in_row):
                parts = []
                for i, cell in enumerate(row.cells):
                    if i < table_block.num_cols:
                        text = (
                            cell.text_lines[line_idx]
                            if line_idx < len(cell.text_lines)
                            else ""
                        )
                        parts.append(text.ljust(widths[i]))
                output_lines.append("  ".join(parts))
        return output_lines

    def _format_table_as_markdown(self, table_block: TableBlock):
        """Converts a TableBlock object into a GitHub Flavored Markdown table."""
        if not table_block or not table_block.rows:
            return []
        h_texts = [cell.pre_processed_text for cell in table_block.rows[0].cells]
        h_line = f"| {' | '.join(h_texts)} |"
        sep_line = f"| {' | '.join(['---'] * table_block.num_cols)} |"
        data_lines = []
        for row in table_block.rows[1:]:
            cell_texts = [cell.pre_processed_text for cell in row.cells]
            while len(cell_texts) < table_block.num_cols:
                cell_texts.append("")
            data_lines.append(f"| {' | '.join(cell_texts[:table_block.num_cols])} |")
        return [h_line, sep_line] + data_lines

    def _merge_multiline_titles(self, blocks):
        """Merges consecutive Title blocks into a single Title block."""
        if not blocks:
            return []
        merged_blocks, i = [], 0
        while i < len(blocks):
            if isinstance(blocks[i], Title):
                title_lines = blocks[i].lines
                # Check for subsequent Title blocks that are close vertically
                while (i + 1) < len(blocks) and isinstance(blocks[i + 1], Title):
                    prev_line = title_lines[-1]
                    next_line = blocks[i + 1].lines[0]
                    v_dist = prev_line.y0 - next_line.y1
                    if v_dist < self._get_font_size(prev_line) * 1.5:
                        i += 1
                        title_lines.extend(blocks[i].lines)
                    else:
                        break
                merged_text = " ".join(
                    self.format_line_with_style(line) for line in title_lines
                )
                merged_blocks.append(Title(merged_text, title_lines))
            else:
                merged_blocks.append(blocks[i])
            i += 1
        return merged_blocks

    def _build_sections_from_models(self):
        """Stage 3: Walks PageModels to build final Section objects."""
        logging.getLogger("ppdf").info(
            "--- Stage 3: Reconstructing Document from Page Models ---"
        )
        sections, current_section, last_title, cont = [], None, None, 2

        def finalize_section(sec):
            if sec and sec.paragraphs:
                log_reconstruct.debug(
                    "Finalizing section '%s' (%d paras)",
                    sec.title,
                    len(sec.paragraphs),
                )
                sections.append(sec)

        for page in self.page_models:
            log_reconstruct.debug(
                "Reconstructing from Page %d (%s)",
                page.page_num,
                page.page_type,
            )
            if page.page_type != "content":
                finalize_section(current_section)
                current_section = None
                last_title = f"({page.page_type.capitalize()} Page)"
                continue
            if page.title:
                finalize_section(current_section)
                log_reconstruct.debug(
                    "Page Title found: '%s'. Creating new section.",
                    page.title.text,
                )
                current_section = Section(page.title.text, page.page_num)
                last_title, cont = page.title.text, 2

            for zone in page.zones:
                for col in zone.columns:
                    for block in col.blocks:
                        if not current_section:
                            title = (
                                f"{last_title} ({self._to_roman(cont)})"
                                if last_title
                                else "Untitled Section"
                            )
                            log_reconstruct.debug(
                                "No active section. Creating new ('%s').",
                                title,
                            )
                            if last_title:
                                cont += 1
                            current_section = Section(title, page.page_num)

                        current_section, last_title, cont = (
                            self._process_block_for_reconstruction(
                                block,
                                page,
                                sections,
                                current_section,
                                last_title,
                                cont,
                            )
                        )

        finalize_section(current_section)
        return sections

    def _process_block_for_reconstruction(
        self, block, page, sections, current_section, last_title, cont
    ):
        """Helper to process a single block during section building."""
        if isinstance(block, Title):
            # Finalize previous section and start a new one with this title
            if current_section and current_section.paragraphs:
                sections.append(current_section)
            log_reconstruct.debug(
                "Column Title found: '%s'. Creating new section.", block.text
            )
            current_section = Section(block.text, page.page_num)
            last_title, cont = block.text, 2
        elif isinstance(block, BoxedNoteBlock):
            current_section, last_title, cont = self._handle_boxed_note_block(
                block, page, sections, current_section, last_title, cont
            )
        elif isinstance(block, TableBlock):
            current_section.add_paragraph(
                Paragraph(
                    lines=self._format_table_for_display(block),
                    page=page.page_num,
                    is_table=True,
                    llm_lines=self._format_table_as_markdown(block),
                )
            )
        elif isinstance(block, ProseBlock):
            self._process_prose_block(
                block, current_section, page.page_num, page.body_font_size
            )
        return current_section, last_title, cont

    def _handle_boxed_note_block(
        self, block, page, sections, current_section, last_title, cont
    ):
        """Creates a dedicated section for a BoxedNoteBlock."""
        dangling_para = None
        if current_section and current_section.last_paragraph:
            dangling_para = current_section.paragraphs.pop()

        if current_section and current_section.paragraphs:
            sections.append(current_section)

        # Create a new section specifically for the boxed note
        note_sec = Section(block.title, page.page_num)

        # Process internal blocks of the BoxedNoteBlock
        for internal_block in block.internal_blocks:
            if isinstance(internal_block, TableBlock):
                note_sec.add_paragraph(
                    Paragraph(
                        lines=self._format_table_for_display(internal_block),
                        page=page.page_num,
                        is_table=True,
                        llm_lines=self._format_table_as_markdown(internal_block),
                    )
                )
            elif isinstance(internal_block, ProseBlock):
                self._process_prose_block(
                    internal_block,
                    note_sec,
                    page.page_num,
                    page.body_font_size,
                )
        sections.append(note_sec)

        # Handle paragraph that was interrupted by the note
        if dangling_para:
            title = (
                f"{last_title} ({self._to_roman(cont)})" if last_title else "Untitled Section"
            )
            if last_title:
                cont += 1
            current_section = Section(title, page.page_num)
            current_section.add_paragraph(dangling_para)
        else:
            current_section = None
        return current_section, last_title, cont

    def _process_prose_block(self, block, section, page, font_size):
        """Splits a ProseBlock into Paragraphs and adds them to a Section."""
        if not block.lines:
            return
        para_groups = self._split_prose_block_into_paragraphs(block.lines, font_size)
        for p_lines in para_groups:
            formatted_lines = [self.format_line_with_style(line) for line in p_lines]
            section.add_paragraph(Paragraph(formatted_lines, page))

    def _get_words_from_line(self, line):
        """Extracts individual words (and coordinates) from a line object."""
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

    def _get_line_density(self, line):
        """
        Calculates a density score for a given text line.
        Density is roughly (sum of char widths) / (width of text bbox).
        """
        text_chars = [c for c in line if isinstance(c, LTChar) and c.get_text().strip()]
        if not text_chars:
            return 0.0

        min_x = min(c.x0 for c in text_chars)
        max_x = max(c.x1 for c in text_chars)
        actual_text_width = max_x - min_x

        if actual_text_width <= 0:
            return 0.0

        total_char_width = sum(c.width for c in text_chars)
        return total_char_width / actual_text_width

    def _is_line_a_title(self, line, font_size, col_bbox):
        """Heuristically determines if a line is a title."""
        size, text = self._get_font_size(line), line.get_text().strip()
        if not text:
            return False
        col_w = col_bbox[2] - col_bbox[0] if col_bbox[2] > col_bbox[0] else 1
        col_mid = (col_bbox[0] + col_bbox[2]) / 2
        line_mid = (line.x0 + line.x1) / 2
        is_centered = abs(line_mid - col_mid) < (col_w * 0.2)
        is_larger = size > (font_size * 1.2)
        is_caps = text.isupper() and 1 < len(text.split()) < 10
        return is_larger or (is_caps and is_centered)

    def _find_elements_by_type(self, obj, t):
        """Recursively finds all layout elements of a specific type."""
        e = []
        if isinstance(obj, t):
            e.append(obj)
        if hasattr(obj, "_objs"):
            for child in obj:
                e.extend(self._find_elements_by_type(child, t))
        return e

    def _find_title_in_box(self, lines_in_box):
        """Heuristically finds a title within a boxed note."""
        if not lines_in_box or not "".join(line.get_text() for line in lines_in_box).strip():
            return "Note", []
        sizes = [
            size
            for line in lines_in_box
            if line.get_text().strip()
            if (size := self._get_font_size(line))
        ]
        if not sizes:
            return "Note", []
        box_font_size = Counter(sizes).most_common(1)[0][0]
        box_bbox = self.compute_bbox(lines_in_box)
        box_center_x = (box_bbox[0] + box_bbox[2]) / 2
        title_lines = []
        for line in lines_in_box[:4]:
            text = line.get_text().strip()
            if not text:
                continue
            fonts, size = self._get_line_fonts(line), self._get_font_size(line)
            is_bold = any("bold" in f.lower() for f in fonts)
            is_caps = text.isupper() and len(text.split()) < 7
            line_mid_x = (line.x0 + line.x1) / 2
            box_width = box_bbox[2] - box_bbox[0]
            is_centered = abs(line_mid_x - box_center_x) < (box_width * 0.25)
            is_larger_font = size > box_font_size * 1.1
            if sum([is_larger_font, is_bold, is_caps, is_centered]) >= 2:
                title_lines.append(line)
            elif title_lines:
                break
        if title_lines:
            title_text = " ".join(self.format_line_with_style(line) for line in title_lines)
            return title_text, title_lines
        return "Note", []

    def _get_font_size(self, line):
        """Gets the most common font size for a given line."""
        if not hasattr(line, "_objs") or not line._objs:
            return 0
        sizes = [c.size for c in line if isinstance(c, LTChar) and hasattr(c, "size")]
        return Counter(sizes).most_common(1)[0][0] if sizes else 0

    def _get_line_fonts(self, line):
        """Gets the set of font names used in a given line."""
        if not hasattr(line, "_objs") or not line._objs:
            return set()
        return {c.fontname for c in line if isinstance(c, LTChar)}

    def _get_page_body_font_size(self, lines, default_on_fail=True):
        """Determines the primary body font size for a list of lines."""
        if not lines:
            return 12 if default_on_fail else None
        sizes = [
            size for line in lines if (size := self._get_font_size(line)) and 6 <= size <= 30
        ]
        if not sizes:
            log_layout.debug("Could not determine body font size, using default.")
            return 12 if default_on_fail else None
        most_common = Counter(sizes).most_common(1)[0][0]
        log_layout.debug("Determined page body font size: %.2f", most_common)
        return most_common

    def _get_footer_threshold_dynamic(self, lines, layout, font_size):
        """Dynamically calculates the Y-coordinate for the footer."""
        limit = layout.y0 + (layout.height * 0.12)
        p = re.compile(r"^((page|pág\.?)\s+)?\s*-?\s*\d+\s*-?\s*$", re.I)
        cands = [
            line
            for line in lines
            if line.y0 <= limit
            and line.get_text().strip()
            and (
                p.match(line.get_text().strip())
                or self._get_font_size(line) < (font_size * 0.85)
            )
        ]
        if not cands:
            return 0
        footer_y = max(line.y1 for line in cands) + 1
        log_layout.debug("Footer threshold set to y=%.2f", footer_y)
        return footer_y

    def _detect_page_level_column_count(self, lines, layout):
        """Detects if a set of lines is in one or two columns, for page-level analysis."""
        if len(lines) < 5:
            return 1
        mid_x, leeway = layout.x0 + layout.width / 2, layout.width * 0.05
        left_lines = [line for line in lines if line.x1 < mid_x + leeway]
        right_lines = [line for line in lines if line.x0 > mid_x - leeway]
        if not left_lines or not right_lines:
            return 1

        # Gutter Check
        max_left = max((line.x1 for line in left_lines), default=layout.x0)
        min_right = min((line.x0 for line in right_lines), default=layout.x1)
        if max_left < min_right:
            return 2
        return 1

    def _detect_column_count(self, lines, layout):
        """Detects if a set of lines is in one or two columns."""
        if len(lines) < 5:
            return 1
        mid_x, leeway = layout.x0 + layout.width / 2, layout.width * 0.05
        left_lines = [line for line in lines if line.x1 < mid_x + leeway]
        right_lines = [line for line in lines if line.x0 > mid_x - leeway]
        if not left_lines or not right_lines:
            return 1

        # 1. Gutter Check
        max_left = max((line.x1 for line in left_lines), default=layout.x0)
        min_right = min((line.x0 for line in right_lines), default=layout.x1)
        if max_left < min_right:
            log_layout.debug("Column check: Gutter detected. Decision: 2 columns.")
            return 2

        # 2. Fallback Width Check
        left_chars = [
            achar
            for line in left_lines
            for achar in line
            if isinstance(achar, LTChar) and achar.get_text().strip()
        ]
        right_chars = [
            achar
            for line in right_lines
            for achar in line
            if isinstance(achar, LTChar) and achar.get_text().strip()
        ]
        if not left_chars or not right_chars:
            return 1
        left_w = max(c.x1 for c in left_chars) - min(c.x0 for c in left_chars)
        right_w = max(c.x1 for c in right_chars) - min(c.x0 for c in right_chars)

        half_layout_w = layout.width / 2 * 1.1
        if left_w < half_layout_w and right_w < half_layout_w:
            log_layout.debug("Column check: Fallback width suggests 2 columns.")
            return 2

        return 1

    def _group_lines_into_columns(self, lines, layout, num):
        """Groups a list of lines into N columns based on position."""
        if num == 1:
            return [lines]
        cols, width = [[] for _ in range(num)], layout.width / num
        for line in lines:
            line_mid_x = (line.x0 + line.x1) / 2
            idx = max(0, min(num - 1, int((line_mid_x - layout.x0) / width)))
            cols[idx].append(line)
        return cols

    def _detect_page_title(self, lines, layout, font_size, page_level_cols):
        """Detects a main title at the top of a page."""
        if not lines:
            return None, []
        sorted_lines = sorted(lines, key=lambda x: (-x.y1, x.x0))
        top_y_thresh = layout.y0 + layout.height * 0.85
        top_candidates = []
        for line in sorted_lines:
            if line.y0 < top_y_thresh:
                continue
            if self._get_font_size(line) <= (font_size * 1.4):
                continue
            # If multi-column, title must span a significant portion of the page width
            if page_level_cols > 1 and line.width < (layout.width * 0.4):
                continue
            top_candidates.append(line)

        if not top_candidates:
            return None, []

        first_title_line = top_candidates[0]
        title_lines = [first_title_line]
        try:
            current_idx = sorted_lines.index(first_title_line)
        except ValueError:
            return None, []

        # Look for subsequent lines that continue the title
        for i in range(current_idx + 1, len(sorted_lines)):
            line, prev = sorted_lines[i], title_lines[-1]
            v_dist = prev.y0 - line.y1
            h_align_ok = abs(line.x0 - prev.x0) < (layout.width * 0.2)

            # Case 1: Continuation of the same title (font size is nearly identical)
            same_level = abs(self._get_font_size(line) - self._get_font_size(prev)) < 0.1

            # Case 2: A subtitle or byline (font is smaller, text is shorter)
            is_subtitle = (
                self._get_font_size(line) < self._get_font_size(prev)
                and len(line.get_text()) < len(prev.get_text()) * 0.9
                and not line.get_text().strip().endswith(".")
            )

            if (
                v_dist < (self._get_font_size(prev) * 1.5)
                and h_align_ok
                and (same_level or is_subtitle)
            ):
                title_lines.append(line)
            else:
                break

        if title_lines:
            text = " ".join(self.format_line_with_style(line) for line in title_lines)
            return Title(text, title_lines), title_lines
        return None, []

    def _split_prose_block_into_paragraphs(self, lines, font_size):
        """Splits lines into paragraphs based on vertical spacing."""
        if not lines:
            return []
        paras, para, v_thresh = [], [], font_size * 1.2
        for line in lines:
            if para and (para[-1].y0 - line.y1) > v_thresh:
                paras.append(para)
                para = []
            para.append(line)
        if para:
            paras.append(para)
        return paras
