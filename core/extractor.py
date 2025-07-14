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
from collections import Counter

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTImage, LTRect, LTTextLine

# --- LOGGING SETUP ---
log_layout = logging.getLogger("ppdf.layout")
log_structure = logging.getLogger("ppdf.structure")
log_reconstruct = logging.getLogger("ppdf.reconstruct")


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
            if line.endswith('-') and (i + 1) < len(self.text_lines):
                next_line = self.text_lines[i+1].strip()
                merged_line = line[:-1] + next_line
                temp_new_lines = [merged_line] + self.text_lines[i+2:]
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
        self.num_cols = len(rows[0].cells) if (
            rows and hasattr(rows[0], 'cells')) else 0


class BoxedNoteBlock(ContentBlock):
    """A block of content identified as being enclosed in a graphical box."""
    def __init__(self, text, all_lines, title_lines):
        super().__init__(all_lines)
        self.text = text
        self.title_lines = title_lines


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

    def get_text(self):
        """Returns the full text for display, preserving line breaks."""
        return '\n'.join(self.lines)

    def get_llm_text(self):
        """Returns the LLM-specific text (e.g., Markdown for tables)."""
        if self.is_table and self.llm_lines:
            return '\n'.join(self.llm_lines)
        return self.get_text()


class Section:
    """A logical section of a document, such as a chapter or topic."""
    def __init__(self, title=None, page=None):
        self.title, self.paragraphs = title, []
        self.page_start, self.page_end = page, page
        self._last_add_was_merge = False

    def add_paragraph(self, p: Paragraph):
        """Adds a Paragraph, merging with the last one if it seems unfinished."""
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
        """Checks if a paragraph ends with punctuation suggesting continuation."""
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

    Args:
        pdf_path (str): The file path to the PDF.
        num_cols (str): The number of columns to assume ('auto' or a number).
        rm_footers (bool): Whether to attempt footer removal.
        style (bool): Whether to preserve bold/italic styling.
    """
    def __init__(self, pdf_path, num_cols="auto", rm_footers=True, style=False):
        self.pdf_path = pdf_path
        self.num_columns_str = num_cols
        self.remove_footers = rm_footers
        self.keep_style = style
        self.page_models = []
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF file not found: {self.pdf_path}")

    @staticmethod
    def compute_bbox(lines):
        """Computes a bounding box enclosing all given layout elements."""
        if not lines:
            return 0, 0, 0, 0
        lines = [l for l in lines if l]
        if not lines or any(not hasattr(l, 'x0') for l in lines):
            return 0, 0, 0, 0
        return (min(l.x0 for l in lines), min(l.y0 for l in lines),
                max(l.x1 for l in lines), max(l.y1 for l in lines))

    def format_line_with_style(self, line):
        """Formats a line, optionally preserving bold/italic markdown."""
        if not self.keep_style or not hasattr(line, '_objs'):
            return re.sub(r'\s+', ' ', line.get_text()).strip()
        parts, style, buf = [], {'bold': False, 'italic': False}, []
        for char in line:
            if not isinstance(char, LTChar) or not char.get_text().strip():
                continue
            is_b = "bold" in char.fontname.lower()
            is_i = "italic" in char.fontname.lower()
            if is_b != style['bold'] or is_i != style['italic']:
                if buf:
                    text = "".join(buf)
                    if style['bold']:
                        parts.append(f"**{text}**")
                    elif style['italic']:
                        parts.append(f"*{text}*")
                    else:
                        parts.append(text)
                    buf = []
            style['bold'], style['italic'] = is_b, is_i
            buf.append(char.get_text())
        if buf:
            text = "".join(buf)
            if style['bold']:
                parts.append(f"**{text}**")
            elif style['italic']:
                parts.append(f"*{text}*")
            else:
                parts.append(text)
        return re.sub(r'\s+', ' ', "".join(parts)).strip()

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
        self._analyze_page_layouts(pages_to_process)
        return self._build_sections_from_models()

    def _to_roman(self, n):
        """Converts an integer to a Roman numeral for section continuation."""
        if not 1 <= n <= 3999:
            return str(n)
        val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
        sym = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
        roman_num, i = '', 0
        while n > 0:
            for _ in range(n // val[i]):
                roman_num += sym[i]
                n -= val[i]
            i += 1
        return roman_num

    def _analyze_page_layouts(self, pages_to_process=None):
        """Performs Stage 1 (layout) and Stage 2 (content) analysis."""
        self.page_models = []
        all_pdf_pages = list(extract_pages(self.pdf_path))
        content_pages_to_structure = []

        logging.getLogger("ppdf").info(
            "--- Stage 1: Analyzing Page Layouts ---"
        )
        for page_layout in all_pdf_pages:
            if pages_to_process and page_layout.pageid not in pages_to_process:
                continue
            page_model = self._analyze_single_page_layout(page_layout)
            self.page_models.append(page_model)
            if page_model.page_type == 'content':
                content_pages_to_structure.append(page_model)

        logging.getLogger("ppdf").info(
            "--- Stage 2: Structuring Content from Page Models ---"
        )
        for page_model in content_pages_to_structure:
            log_structure.info("Structuring content for Page %d",
                               page_model.page_num)
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
        """Classifies a page as 'cover', 'credits', 'art', or 'content'."""
        log_layout.debug("--- Page Classification ---")
        num_lines, num_images = len(lines), len(images)
        log_layout.debug("  - Total lines: %d, Total images: %d",
                         num_lines, num_images)
        if num_images > 0:
            page_area = layout.width * layout.height
            image_area = sum(img.width * img.height for img in images)
            if page_area > 0 and (image_area / page_area) > 0.7:
                log_layout.debug(
                    "  - Decision: Large image coverage (%.2f%%). -> 'art'",
                    (image_area / page_area) * 100
                )
                return 'art'
        if num_lines == 0:
            log_layout.debug("  - Decision: No lines found. -> 'art'")
            return 'art'
        if num_lines < 5:
            log_layout.debug("  - Decision: Very few lines (%d). -> 'cover'",
                             num_lines)
            return 'cover'
        full_text = " ".join(l.get_text() for l in lines).lower()
        credit_kw = ['créditos', 'copyright', 'editor', 'traducción',
                     'maquetación', 'cartógrafos', 'ilustración', 'isbn',
                     'depósito legal']
        found_kw = [kw for kw in credit_kw if kw in full_text]
        if len(found_kw) >= 3:
            log_layout.debug("  - Decision: Found %d keywords. -> 'credits'",
                             len(found_kw))
            return 'credits'
        return 'content'

    def _analyze_single_page_layout(self, layout):
        """Analyzes a single page's layout to produce a PageModel."""
        page = PageModel(layout)
        logging.getLogger("ppdf").info("Analyzing Page Layout %d...",
                                       page.page_num)
        all_lines = sorted(
            self._find_elements_by_type(layout, LTTextLine),
            key=lambda x: (-x.y1, x.x0)
        )
        images = self._find_elements_by_type(layout, LTImage)
        all_rects = self._find_elements_by_type(layout, LTRect)
        page.rects = [
            r for r in all_rects
            if r.linewidth > 0 and r.width > 10 and r.height > 10
        ]
        page.page_type = self._classify_page_type(layout, all_lines, images)
        logging.getLogger("ppdf").info("Page %d classified as: %s",
                                       page.page_num, page.page_type)
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

        # Split page into vertical zones based on full-width rectangles
        rect_breaks = {r.y0 for r in page.rects if r.width > layout.width * 0.7}
        rect_breaks.update(
            r.y1 for r in page.rects if r.width > layout.width * 0.7
        )
        breakpoints = {layout.y0, layout.y1, *rect_breaks}
        sorted_breaks = sorted(list(breakpoints), reverse=True)

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
            # Detect columns for the current zone
            if self.num_columns_str != 'auto':
                num_cols = int(self.num_columns_str)
            else:
                num_cols = self._detect_column_count(zone.lines, layout)

            logging.getLogger("ppdf").info(
                "Page %d, Zone %d: Detected %d column(s).",
                page.page_num, len(page.zones)+1, num_cols
            )
            col_groups = self._group_lines_into_columns(
                zone.lines, layout, num_cols
            )
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
        for r in sorted(rects, key=lambda r: (-r.y1, r.x0)):
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
                last_idx = max(lines.index(l) for l in b_lines) if b_lines else -1
                current_pos = last_idx + 1
            else:
                block_lines, end_pos = [], current_pos
                while end_pos<len(lines) and lines[end_pos] not in line_to_box_map:
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
        """Helper to segment lines into Prose, Table, and Title blocks."""
        if not lines:
            return []
        split_indices = [
            i for i, line in enumerate(lines)
            if self._is_block_separator(line, font_size, col_bbox)
        ]
        blocks, points = [], sorted(list(set([0] + split_indices + [len(lines)])))
        for i in range(len(points) - 1):
            start_idx, end_idx = points[i], points[i+1]
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
                table_lines = self._refine_table_lines_by_header(
                    block_lines, font_size
                )
                if table_lines:
                    blocks.append(
                        self._parse_table_structure(table_lines, font_size)
                    )
                if len(table_lines) < len(block_lines):
                    blocks.append(ProseBlock(block_lines[len(table_lines):]))
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
        if len(phrases) < 2:
            return False
        text = line.get_text().strip()
        has_dice = bool(re.search(r'\b\d+d\d+\b', text, re.I))
        fonts = self._get_line_fonts(line)
        is_bold = "bold" in list(fonts)[0].lower() if len(fonts) == 1 else False
        return has_dice or is_bold

    def _refine_table_lines_by_header(self, lines, font_size):
        """Refines table extent based on dice notation in the header."""
        if not lines:
            return []
        header_text = lines[0].get_text().strip()
        dice_match = re.search(r'(?i)(\d*)d(\d+)', header_text)
        if not dice_match:
            return lines
        try:
            expected_rows = int(dice_match.group(2))
        except (ValueError, IndexError):
            return lines
        phrases = self.get_column_phrases_from_line(lines[0], font_size)
        if not phrases:
            return lines
        col_x_start = phrases[0][1]
        table_lines = [lines[0]]
        row_count, i = 0, 1
        while i < len(lines):
            words = self._get_words_from_line(lines[i])
            if words and abs(words[0][1] - col_x_start) < font_size:
                row_count += 1
                if row_count >= expected_rows:
                    table_lines.append(lines[i])
                    break
            table_lines.append(lines[i])
            i += 1
        return table_lines

    def _parse_table_structure(self, table_lines, font_size):
        """Parses lines into a structured TableBlock object."""
        if not table_lines:
            return ProseBlock([])
        header_phrases = self.get_column_phrases_from_line(
            table_lines[0], font_size
        )
        if not header_phrases or len(header_phrases) < 2:
            return ProseBlock(table_lines)

        table_bbox = self.compute_bbox(table_lines)
        num_cols = len(header_phrases)
        log_structure.debug("Table Parser decided on %d columns.", num_cols)

        col_boundaries, left_bound = [], table_bbox[0]
        for i in range(num_cols - 1):
            midpoint = header_phrases[i][2] + \
                (header_phrases[i+1][1] - header_phrases[i][2]) / 2
            col_boundaries.append((left_bound, midpoint))
            left_bound = midpoint
        col_boundaries.append((left_bound, table_bbox[2]))

        anchor_lines = [table_lines[0]]
        first_col_x = header_phrases[0][1]
        for l in table_lines[1:]:
            words = self._get_words_from_line(l)
            if words and abs(words[0][1] - first_col_x) < font_size:
                if not any(abs(l.y1 - prev.y0)<font_size*0.5 for prev in anchor_lines):
                    anchor_lines.append(l)

        row_y_boundaries = [
            (((anchor_lines[i+1].y1 - 1) if i + 1 < len(anchor_lines)
              else table_bbox[1]), anchor_lines[i].y1 + 1)
            for i in range(len(anchor_lines))
        ]

        grid = [[[] for _ in range(num_cols)] for _ in range(len(row_y_boundaries))]
        for r, (y_bot, y_top) in enumerate(row_y_boundaries):
            lines_in_row = sorted([
                l for l in table_lines if y_bot <= (l.y0 + l.y1) / 2 < y_top
            ], key=lambda l: -l.y1)
            for c, (x_left, x_right) in enumerate(col_boundaries):
                cell_lines = []
                for line in lines_in_row:
                    line_text = "".join(
                        char.get_text() for char in line
                        if isinstance(char, LTChar) and x_left <= char.x0 < x_right
                    ).strip()
                    if line_text:
                        cell_lines.append(line_text)
                grid[r][c] = cell_lines
        parsed_rows = [
            TableRow([TableCell(text_lines) for text_lines in row_data])
            for row_data in grid
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
                    max_line = max((len(line) for line in cell.text_lines),
                                   default=0)
                    widths[i] = max(widths[i], max_line)
        output_lines = []
        for row in table_block.rows:
            max_lines = max((len(c.text_lines) for c in row.cells), default=0)
            if not any(c.text_lines for c in row.cells) or max_lines == 0:
                continue
            for line_idx in range(max_lines):
                parts = []
                for i, cell in enumerate(row.cells):
                    if i < table_block.num_cols:
                        text = (cell.text_lines[line_idx]
                                if line_idx < len(cell.text_lines) else "")
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
                cell_texts.append('')
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
                while (i+1) < len(blocks) and isinstance(blocks[i+1], Title):
                    i += 1
                    title_lines.extend(blocks[i].lines)
                merged_blocks.append(Title(
                    " ".join(self.format_line_with_style(l) for l in title_lines),
                    title_lines
                ))
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
                    sec.title, len(sec.paragraphs)
                )
                sections.append(sec)

        for page in self.page_models:
            log_reconstruct.debug("Reconstructing from Page %d (%s)",
                                  page.page_num, page.page_type)
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
                                "No active section. Creating new ('%s').", title
                            )
                            if last_title:
                                cont += 1
                            current_section = Section(title, page.page_num)

                        if isinstance(block, Title):
                            finalize_section(current_section)
                            log_reconstruct.debug(
                                "Column Title: '%s'. Creating new section.",
                                block.text
                            )
                            current_section = Section(block.text, page.page_num)
                            last_title, cont = block.text, 2
                        elif isinstance(block, BoxedNoteBlock):
                            dangling = current_section.paragraphs.pop() if (
                                current_section and current_section.last_paragraph
                            ) else None
                            finalize_section(current_section)
                            body = [l for l in block.lines if l not in block.title_lines]
                            note_sec = Section(block.text, page.page_num)
                            if any(l.get_text().strip() for l in body):
                                note_sec.add_paragraph(Paragraph(
                                    [self.format_line_with_style(l) for l in body],
                                    page.page_num
                                ))
                            sections.append(note_sec)
                            if dangling:
                                title = (f"{last_title} ({self._to_roman(cont)})"
                                         if last_title else "Untitled Section")
                                if last_title:
                                    cont += 1
                                current_section = Section(title, page.page_num)
                                current_section.add_paragraph(dangling)
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
        """Splits a ProseBlock into Paragraphs and adds them to a Section."""
        if not block.lines:
            return
        para_groups = self._split_prose_block_into_paragraphs(
            block.lines, font_size
        )
        for p_lines in para_groups:
            formatted_lines = [self.format_line_with_style(l) for l in p_lines]
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
        if hasattr(obj, '_objs'):
            for child in obj:
                e.extend(self._find_elements_by_type(child, t))
        return e

    def _find_title_in_box(self, lines_in_box):
        """Heuristically finds a title within a boxed note."""
        if not lines_in_box or not "".join(l.get_text() for l in lines_in_box).strip():
            return "Note", []
        sizes = [self._get_font_size(l) for l in lines_in_box if l.get_text().strip()]
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
            is_centered = abs(line_mid_x-box_center_x) < ((box_bbox[2]-box_bbox[0])*0.25)
            if size > box_font_size * 1.1 or is_bold or (is_caps and is_centered):
                title_lines.append(line)
            elif title_lines:
                break
        if title_lines:
            title_text = " ".join(self.format_line_with_style(l) for l in title_lines)
            return title_text, title_lines
        return "Note", []

    def _get_font_size(self, line):
        """Gets the most common font size for a given line."""
        if not hasattr(line, '_objs') or not line._objs:
            return 0
        sizes = [c.size for c in line if isinstance(c, LTChar) and hasattr(c, 'size')]
        return Counter(sizes).most_common(1)[0][0] if sizes else 0

    def _get_line_fonts(self, line):
        """Gets the set of font names used in a given line."""
        if not hasattr(line, '_objs') or not line._objs:
            return set()
        return set(c.fontname for c in line if isinstance(c, LTChar))

    def _get_page_body_font_size(self, lines, default_on_fail=True):
        """Determines the primary body font size for a list of lines."""
        if not lines:
            return 12 if default_on_fail else None
        sizes = [s for l in lines if (s := self._get_font_size(l)) and 6 <= s <= 30]
        if not sizes:
            return 12 if default_on_fail else None
        return Counter(sizes).most_common(1)[0][0]

    def _get_footer_threshold_dynamic(self, lines, layout, font_size):
        """Dynamically calculates the Y-coordinate for the footer."""
        limit = layout.y0 + (layout.height * 0.12)
        p = re.compile(r"^((page|pág\.?)\s+)?\s*-?\s*\d+\s*-?\s*$", re.I)
        cands = [
            l for l in lines if l.y0 <= limit and l.get_text().strip() and
            (p.match(l.get_text().strip()) or self._get_font_size(l)<(font_size*0.85))
        ]
        if not cands:
            return 0
        return max(l.y1 for l in cands) + 1

    def _detect_column_count(self, lines, layout):
        """Detects if a set of lines is in one or two columns."""
        if len(lines) < 5:
            return 1
        mid_x, leeway = layout.x0 + layout.width / 2, layout.width * 0.05
        left = [l for l in lines if l.x1 < mid_x + leeway]
        right = [l for l in lines if l.x0 > mid_x - leeway]
        if not left or not right:
            return 1
        if max((l.x1 for l in left), default=0) < min((l.x0 for l in right), default=9e9):
            return 2
        return 1

    def _group_lines_into_columns(self, lines, layout, num):
        """Groups a list of lines into N columns based on position."""
        if num == 1:
            return [lines]
        cols, width = [[] for _ in range(num)], layout.width / num
        for l in lines:
            idx = max(0, min(num - 1, int((l.x0 - layout.x0) / width)))
            cols[idx].append(l)
        return cols

    def _detect_page_title(self, lines, layout, font_size):
        """Detects a main title at the top of a page."""
        if not lines:
            return None, []
        top_y_thresh = layout.y0 + layout.height * 0.85
        cands = [
            l for l in lines
            if l.y0 >= top_y_thresh and self._get_font_size(l) > (font_size*1.4)
        ]
        if not cands:
            return None, []
        title_lines = [cands[0]]
        for i in range(1, len(cands)):
            l, prev = cands[i], cands[i-1]
            v_dist = (prev.y0 - l.y1)
            h_align = abs(l.x0 - prev.x0)
            if v_dist < (self._get_font_size(prev) * 1.5) and h_align < (layout.width*0.1):
                title_lines.append(l)
            else:
                break
        if title_lines:
            text = " ".join(self.format_line_with_style(l) for l in title_lines)
            return Title(text, title_lines), title_lines
        return None, []

    def _split_prose_block_into_paragraphs(self, lines, font_size):
        """Splits lines into paragraphs based on vertical spacing."""
        if not lines:
            return []
        paras, para, v_thresh = [], [], font_size * 1.2
        for l in lines:
            if para and (para[-1].y0 - l.y1) > v_thresh:
                paras.append(para)
                para = []
            para.append(l)
        if para:
            paras.append(para)
        return paras
