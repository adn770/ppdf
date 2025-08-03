# --- ppdf_lib/extractor.py ---
"""
core/extractor.py: The core PDF text and structure extraction engine.
This module contains the PDFTextExtractor class, which orchestrates the
multi-stage analysis of a PDF file to produce a logical document structure.
"""
import logging
import os
import re
from collections import Counter

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTTextLine, LTImage

from .scanner import MarginScanner
from .analyzer import PageLayoutAnalyzer
from .segmenter import ContentSegmenter
from .reconstructor import DocumentReconstructor

log_structure = logging.getLogger("ppdf.structure")
log_prescan = logging.getLogger("ppdf.prescan")


class PDFTextExtractor:
    """
    Orchestrates the extraction of structured text from a PDF file.
    This class acts as a facade, coordinating a multi-stage process involving
    specialized components for scanning, layout analysis, content segmentation,
    and final document reconstruction.
    """

    def __init__(self, pdf_path, num_cols="auto", rm_footers=True, style=False):
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        self.pdf_path = pdf_path
        self.num_columns_str = num_cols
        self.remove_footers = rm_footers
        self.keep_style = style
        self.page_models = []
        self.header_cutoff = float("inf")
        self.footer_cutoff = 0
        self.page_manifest = {}

        # Initialize the components for each stage of the pipeline
        self.scanner = MarginScanner(self)
        self.analyzer = PageLayoutAnalyzer(self)
        self.segmenter = ContentSegmenter(self)
        self.reconstructor = DocumentReconstructor(self)

    def extract_sections(self, pages_to_process=None):
        """Main method to perform all analysis and reconstruction."""
        if self.remove_footers:
            self.header_cutoff, self.footer_cutoff = self.scanner.scan(pages_to_process)

        # Stages 1 & 2: Analyze layouts and segment content
        self.page_models = []
        all_pdf_pages = list(extract_pages(self.pdf_path))
        total_pages = all_pdf_pages[-1].pageid if all_pdf_pages else 0

        logging.getLogger("ppdf").info("--- Stages 1 & 2: Analyzing Page Layouts ---")
        for page_layout in all_pdf_pages:
            if pages_to_process and page_layout.pageid not in pages_to_process:
                continue

            # Stage 1: Analyze the physical page layout
            page_model = self.analyzer.analyze_page(page_layout, total_pages)
            if page_model.page_type == "content":
                # Stage 2: Segment the content within the layout
                log_structure.info("Structuring content for Page %d", page_model.page_num)
                for zone in page_model.zones:
                    for col in zone.columns:
                        col.blocks = self.segmenter.segment_column(col, page_model)
            self.page_models.append(page_model)

        # Stage 3: Reconstruct the logical document structure
        return self.reconstructor.build_sections(self.page_models)

    # --- Low-Level Helper & Utility Methods ---
    # These methods are used by the specialized component classes.

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

    def _find_elements_by_type(self, obj, t):
        """Recursively finds all layout elements of a specific type."""
        e = []
        if isinstance(obj, t):
            e.append(obj)
        if hasattr(obj, "_objs"):
            for child in obj:
                e.extend(self._find_elements_by_type(child, t))
        return e

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
            logging.getLogger("ppdf.layout").debug(
                "Could not determine body font size, using default."
            )
            return 12 if default_on_fail else None
        most_common = Counter(sizes).most_common(1)[0][0]
        logging.getLogger("ppdf.layout").debug(
            "Determined page body font size: %.2f", most_common
        )
        return most_common

    def _to_roman(self, n):
        """Converts an integer to a Roman numeral for section continuation."""
        if not 1 <= n <= 3999:
            return str(n)
        val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
        syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
        roman_num, i = "", 0
        while n > 0:
            for _ in range(n // val[i]):
                roman_num += syms[i]
                n -= val[i]
            i += 1
        return roman_num

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
