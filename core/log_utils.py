#!/usr/bin/env python3
"""
core/utils.py: Provides auxiliary and utility classes for the main application.

This module contains:
- RichLogFormatter: A custom logging formatter for colorful console output.
- ContextFilter: A logging filter to add contextual data (like preset names)
  to log records.
- ASCIIRenderer: A debugging tool to visualize the detected page layout as
  ASCII art.
"""

import logging


class ContextFilter(logging.Filter):
    """
    A logging filter that injects contextual information into log records.
    """
    def __init__(self, context_str=""):
        super().__init__()
        self.context_str = context_str

    def filter(self, record):
        record.context = self.context_str
        return True


# --- CUSTOM LOGGING FORMATTER ---
class RichLogFormatter(logging.Formatter):
    """A custom logging formatter for rich, colorful, and aligned console output.

    This formatter uses ANSI escape codes to produce colored and structured log
    messages, making it easier to distinguish between log levels and topics,
    especially during debugging.

    Args:
        use_color (bool): If True, ANSI color codes are used. Defaults to False.
    """

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
            self.COLORS = {
                level: '' for level in [
                    logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR,
                    logging.CRITICAL
                ]
            }
            self.BOLD = ''
            self.RESET = ''

    def format(self, record):
        """Formats a log record into a colored, aligned string.

        Each line of the log message is prefixed with a color-coded level and
        a bolded topic name for easy scanning.

        Args:
            record (logging.LogRecord): The log record to format.

        Returns:
            str: The formatted log message string.
        """
        color = self.COLORS.get(record.levelno, self.RESET)
        level_name = record.levelname[:5]
        topic = record.name.split('.')[-1][:5]

        has_ctx = hasattr(record, 'context') and record.context
        context_str = f"[{getattr(record, 'context', '')}]" if has_ctx else ""

        prefix = (f"{color}{level_name:<5}{self.RESET}:"
                  f"{self.BOLD}{topic:<5}{self.RESET}{context_str}: ")
        message = record.getMessage()
        lines = message.split('\n')
        return "\n".join([f"{prefix}{line}" for line in lines])


class ASCIIRenderer:
    """Renders an ASCII art diagram of a PageModel for debugging.

    This class provides a visual representation of the detected layout structure
    of a page, including zones, columns, and different types of content blocks.
    It is used in 'dry-run' mode to help debug the layout analysis stage.

    Args:
        extractor (PDFTextExtractor): An instance of the extractor to access
            its public helper methods.
        width (int): The width of the ASCII canvas.
        height (int): The height of the ASCII canvas.
    """
    def __init__(self, extractor, width=80, height=50):
        self.extractor = extractor
        self.width = width
        self.height = height

    def render(self, page_model):
        """Renders a single PageModel to an ASCII string.

        Args:
            page_model (PageModel): The page model to render.

        Returns:
            str: The ASCII art representation of the page layout.
        """
        canvas = [['.' for _ in range(self.width)] for _ in range(self.height)]
        layout = page_model.page_layout

        if page_model.page_type != 'content':
            text = f"--- SKIPPED ({page_model.page_type.upper()}) ---"
            start_col = (self.width - len(text)) // 2
            for i, char in enumerate(text):
                in_bounds = (0 <= self.height // 2 < self.height and
                             0 <= start_col + i < self.width)
                if in_bounds:
                    canvas[self.height // 2][start_col + i] = char
            return '\n'.join(''.join(row) for row in canvas) + '\n'

        # --- Block Rendering Pass ---
        for zone in page_model.zones:
            for col in zone.columns:
                for block in col.blocks:
                    self._render_block(canvas, layout, block, col.bbox)

        # --- Page Title and Separator Pass ---
        if page_model.title:
            self._draw_text(
                canvas, layout, page_model.title.lines, layout.bbox, centered=True
            )

        # Draw structural lines (columns, table separators) over the blocks
        for zone in page_model.zones:
            self._draw_zone_separators(canvas, layout, zone)
            for col in zone.columns:
                self._draw_table_separators(canvas, layout, page_model, col)

        return '\n'.join(''.join(row) for row in canvas) + '\n'

    def _render_block(self, canvas, layout, block, clip_box):
        """Recursively renders a block and its children."""
        b_class = block.__class__.__name__

        if b_class == 'BoxedNoteBlock':
            self._draw_fill(canvas, layout, block.bbox, '•', clip_box)
            self._draw_text(
                canvas, layout, block.title_lines, block.bbox, centered=True
            )
            for internal_block in block.internal_blocks:
                self._render_block(canvas, layout, internal_block, block.bbox)
        elif b_class == 'ProseBlock':
            self._draw_fill(canvas, layout, block.bbox, 'a', clip_box)
        elif b_class == 'TableBlock':
            self._draw_fill(canvas, layout, block.bbox, '=', clip_box)
            if block.lines:
                h_bbox = self.extractor.compute_bbox([block.lines[0]])
                bbox = (block.bbox[0], h_bbox[1], block.bbox[2], h_bbox[3])
                self._draw_fill(
                    canvas, layout, bbox, 'h', clip_box, force_single_line=True
                )
        elif b_class == 'Title':
            self._draw_text(canvas, layout, block.lines, clip_box)

    def _draw_zone_separators(self, canvas, layout, zone):
        """Draws vertical lines for multi-column zones."""
        if len(zone.columns) <= 1:
            return
        z_coords = self._to_grid_coords(layout, zone.bbox)
        if not z_coords:
            return
        _, z_sr, _, z_er = z_coords
        for i in range(1, len(zone.columns)):
            col_bbox = zone.columns[i - 1].bbox
            sep_c = int((col_bbox[2] - layout.x0) / layout.width * self.width)
            if 0 < sep_c < self.width:
                for r in range(z_sr, z_er + 1):
                    if 0 <= r < self.height:
                        canvas[r][sep_c] = '|'

    def _draw_table_separators(self, canvas, layout, page_model, col):
        """Draws vertical separators inside tables."""
        blocks_to_check = list(col.blocks)
        for block in col.blocks:
            if block.__class__.__name__ == 'BoxedNoteBlock':
                blocks_to_check.extend(block.internal_blocks)

        for block in blocks_to_check:
            if block.__class__.__name__ != 'TableBlock' or not block.lines:
                continue

            parent_box = col.bbox
            for b in col.blocks:
                is_parent = (b.__class__.__name__ == 'BoxedNoteBlock' and
                             block in b.internal_blocks)
                if is_parent:
                    parent_box = b.bbox
                    break

            phrases = self.extractor.get_column_phrases_from_line(
                block.lines[0], page_model.body_font_size
            )
            b_coords = self._to_grid_coords(layout, block.bbox, parent_box)
            if not b_coords or len(phrases) < 2:
                continue

            b_sc, b_sr, b_ec, b_er = b_coords
            col_width_on_canvas = b_ec - b_sc
            phrase_starts = []
            for _, x0, _ in phrases:
                rel_start = (x0 - block.bbox[0]) / (block.bbox[2] - block.bbox[0])
                phrase_starts.append(b_sc + int(rel_start * col_width_on_canvas))

            for i in range(len(phrases) - 1):
                midpoint = phrase_starts[i+1] - 1
                for r in range(max(0, b_sr), min(self.height, b_er + 1)):
                    if b_sc <= midpoint < b_ec and canvas[r][midpoint] in ('=', 'h'):
                        canvas[r][midpoint] = ':'

    def _to_grid_coords(self, page_layout, bbox, clip_box=None):
        """Converts a PDF bounding box to canvas grid coordinates."""
        if not bbox or page_layout.width == 0 or page_layout.height == 0:
            return None
        x0, y0, x1, y1 = bbox
        if clip_box:
            x0, y0 = max(x0, clip_box[0]), max(y0, clip_box[1])
            x1, y1 = min(x1, clip_box[2]), min(y1, clip_box[3])
        if x1 <= x0 or y1 <= y0:
            return None

        sc = int((x0 - page_layout.x0) / page_layout.width * self.width)
        sr = int((page_layout.y1 - y1) / page_layout.height * self.height)
        ec = int((x1 - page_layout.x0) / page_layout.width * self.width)
        er = int((page_layout.y1 - y0) / page_layout.height * self.height)
        return (sc, sr, ec, er)

    def _draw_fill(self, canvas, page_layout, bbox, char, clip_box=None,
                   force_single_line=False):
        """Fills a region of the canvas with a character."""
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

    def _draw_text(self, canvas, page_layout, lines, clip_box=None,
                   centered=False, v_centered=False):
        """Draws text onto the canvas, respecting clip_box boundaries."""
        if not lines:
            return

        if v_centered and clip_box:
            clip_coords = self._to_grid_coords(page_layout, clip_box)
            if clip_coords:
                _, clip_sr, _, clip_er = clip_coords
                v_center = clip_sr + (clip_er - clip_sr) // 2
                start_sr = v_center - (len(lines) // 2)
                for i, line in enumerate(lines):
                    self._draw_single_line(
                        canvas, page_layout, line, start_sr + i, clip_box, centered
                    )
                return

        # Handle standard text drawing
        for line in lines:
            line_coords = self._to_grid_coords(page_layout, line.bbox)
            if line_coords:
                self._draw_single_line(
                    canvas, page_layout, line, line_coords[1], clip_box, centered
                )

    def _draw_single_line(self, canvas, page_layout, line, row, clip_box, centered):
        """Helper to draw a single line of text, clipped and optionally centered."""
        text = self.extractor.format_line_with_style(line)
        if not text or not clip_box:
            return

        clip_coords = self._to_grid_coords(page_layout, clip_box)
        line_coords = self._to_grid_coords(page_layout, line.bbox)
        if not clip_coords or not line_coords:
            return

        clip_sc, _, clip_ec, _ = clip_coords
        line_sc, _, line_ec, _ = line_coords

        start_col = max(clip_sc, line_sc)
        end_col = min(clip_ec, line_ec)

        if centered:
            clip_width = clip_ec - clip_sc
            start_col = max(clip_sc, clip_sc + (clip_width - len(text)) // 2)

        available_width = end_col - start_col
        if available_width <= 0:
            return

        drawable_text = text[:available_width]

        for i, char in enumerate(drawable_text):
            c = start_col + i
            if 0 <= row < self.height and clip_sc <= c < clip_ec:
                canvas[row][c] = char
