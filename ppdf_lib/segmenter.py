# --- ppdf_lib/segmenter.py ---
"""
ppdf_lib/segmenter.py: Contains the ContentSegmenter for Stage 2 processing.
"""
import logging
import re
from collections import Counter
from pdfminer.layout import LTChar
from .models import (
    BoxedNoteBlock,
    ProseBlock,
    TableBlock,
    Title,
    TableRow,
    TableCell,
    compute_bbox,
)

log_structure = logging.getLogger("ppdf.structure")


class ContentSegmenter:
    """
    Segments a column of text lines into logical blocks like Prose, Tables, etc.
    """

    def __init__(self, extractor):
        self.extractor = extractor

    def segment_column(self, column, page_model):
        """
        Takes a Column object and populates its .blocks attribute.
        """
        lines = column.lines
        font_size = page_model.body_font_size
        col_bbox = column.bbox
        rects = page_model.rects

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
                    body_lines_in_box, font_size, col_bbox, page_model
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
                        self._segment_prose_and_tables(
                            block_lines, font_size, col_bbox, page_model
                        )
                    )
                processed_lines.update(block_lines)
                current_pos = end_pos
        return self._merge_multiline_titles(blocks)

    def _segment_prose_and_tables(self, lines, font_size, col_bbox, page_model):
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
            if self.extractor._is_line_a_title(first_line, font_size, col_bbox):
                formatted_line = self.extractor.format_line_with_style(first_line)
                blocks.append(Title(formatted_line, [first_line]))
                if len(block_lines) > 1:
                    blocks.append(ProseBlock(block_lines[1:]))
            elif self._is_likely_table_header(first_line, font_size):
                table_lines = self._refine_table_lines_by_header(block_lines, font_size)
                if table_lines:
                    blocks.append(
                        self._parse_table_structure(table_lines, font_size, page_model)
                    )
                if len(table_lines) < len(block_lines):
                    blocks.append(ProseBlock(block_lines[len(table_lines) :]))
            else:
                blocks.append(ProseBlock(block_lines))
        return blocks

    def _is_block_separator(self, line, font_size, col_bbox):
        """Determines if a line should act as a separator."""
        is_title = self.extractor._is_line_a_title(line, font_size, col_bbox)
        is_header = self._is_likely_table_header(line, font_size)
        return is_title or is_header

    def _is_likely_table_header(self, line, font_size):
        """Heuristically determines if a line is a table header."""
        phrases = self.extractor.get_column_phrases_from_line(line, font_size)
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
        fonts = self.extractor._get_line_fonts(line)
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

        phrases = self.extractor.get_column_phrases_from_line(lines[0], font_size)
        if not phrases:
            return lines
        col_x_start = phrases[0][1]
        header_density = self.extractor._get_line_density(lines[0])
        log_structure.debug(f"Header line density: {header_density:.2f}")

        table_lines = [lines[0]]
        row_count = 0
        i = 1
        while i < len(lines):
            line = lines[i]
            words = self.extractor._get_words_from_line(line)

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
                current_density = self.extractor._get_line_density(line)
                line_phrases = self.extractor.get_column_phrases_from_line(line, font_size)
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

    def _parse_table_structure(self, table_lines, font_size, page_model):
        """Parses lines into a structured TableBlock object."""
        if not table_lines:
            return ProseBlock([])
        header_phrases = self.extractor.get_column_phrases_from_line(table_lines[0], font_size)
        if not header_phrases or len(header_phrases) < 2:
            return ProseBlock(table_lines)

        table_bbox = compute_bbox(table_lines)
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
            words = self.extractor._get_words_from_line(line)
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

    def _find_title_in_box(self, lines_in_box):
        """Heuristically finds a title within a boxed note."""
        if not lines_in_box or not "".join(line.get_text() for line in lines_in_box).strip():
            return "Note", []
        sizes = [
            size
            for line in lines_in_box
            if line.get_text().strip()
            if (size := self.extractor._get_font_size(line))
        ]
        if not sizes:
            return "Note", []
        box_font_size = Counter(sizes).most_common(1)[0][0]
        box_bbox = compute_bbox(lines_in_box)
        box_center_x = (box_bbox[0] + box_bbox[2]) / 2
        title_lines = []
        for line in lines_in_box[:4]:
            text = line.get_text().strip()
            if not text:
                continue
            fonts, size = self.extractor._get_line_fonts(line), self.extractor._get_font_size(
                line
            )
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
            title_text = " ".join(
                self.extractor.format_line_with_style(line) for line in title_lines
            )
            return title_text, title_lines
        return "Note", []

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
                    if v_dist < self.extractor._get_font_size(prev_line) * 1.5:
                        i += 1
                        title_lines.extend(blocks[i].lines)
                    else:
                        break
                merged_text = " ".join(
                    self.extractor.format_line_with_style(line) for line in title_lines
                )
                merged_blocks.append(Title(merged_text, title_lines))
            else:
                merged_blocks.append(blocks[i])
            i += 1
        return merged_blocks

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
