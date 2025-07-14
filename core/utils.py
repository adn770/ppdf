#!/usr/bin/env python3
"""
core/utils.py: Provides auxiliary and utility classes for the main application.

This module contains:
- RichLogFormatter: A custom logging formatter for colorful console output.
- ASCIIRenderer: A debugging tool to visualize the detected page layout as
  ASCII art.
"""

import logging


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
            self.COLORS = {level: '' for level in [
                logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR,
                logging.CRITICAL
            ]}
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
            page_type_text = f"--- SKIPPED ({page_model.page_type.upper()}) ---"
            start_col = (self.width - len(page_type_text)) // 2
            for i, char in enumerate(page_type_text):
                if (0 <= self.height // 2 < self.height and
                        0 <= start_col + i < self.width):
                    canvas[self.height // 2][start_col + i] = char
            return '\n'.join(''.join(row) for row in canvas) + '\n'

        # Draw blocks first
        for zone in page_model.zones:
            for col in zone.columns:
                for block in col.blocks:
                    block_class_name = block.__class__.__name__
                    if block_class_name == 'ProseBlock':
                        self._draw_fill(
                            canvas, layout, block.bbox, 'a', col.bbox
                        )
                    elif block_class_name == 'TableBlock' and block.lines:
                        self._draw_fill(
                            canvas, layout, block.bbox, '=', col.bbox
                        )
                        header_bbox = self.extractor.compute_bbox(
                            [block.lines[0]]
                        )
                        self._draw_fill(
                            canvas, layout,
                            (block.bbox[0], header_bbox[1],
                             block.bbox[2], header_bbox[3]),
                            'h', col.bbox, force_single_line=True
                        )
                    elif block_class_name == 'BoxedNoteBlock':
                        self._draw_fill(
                            canvas, layout, block.bbox, '•', col.bbox
                        )
                        self._draw_text(
                            canvas, layout, block.title_lines, block.bbox,
                            centered=True, v_centered=True
                        )
                    elif block_class_name == 'Title':
                        self._draw_text(canvas, layout, block.lines, col.bbox)

        # Draw page title
        if page_model.title:
            self._draw_text(
                canvas, layout, page_model.title.lines,
                page_model.page_layout.bbox, centered=True
            )

        # Draw structural lines (columns, table separators) over the blocks
        for zone in page_model.zones:
            zone_coords = self._to_grid_coords(layout, zone.bbox)
            if not zone_coords:
                continue
            _, zone_sr, _, zone_er = zone_coords
            if len(zone.columns) > 1:
                for i in range(1, len(zone.columns)):
                    col_bbox = zone.columns[i - 1].bbox
                    sep_c = int(
                        (col_bbox[2] - layout.x0) / layout.width * self.width
                    )
                    if 0 < sep_c < self.width:
                        for r in range(zone_sr, zone_er + 1):
                            if 0 <= r < self.height:
                                canvas[r][sep_c] = '|'

            for col in zone.columns:
                for block in col.blocks:
                    if block.__class__.__name__ == 'TableBlock' and block.lines:
                        phrases = self.extractor.get_column_phrases_from_line(
                            block.lines[0], page_model.body_font_size
                        )
                        coords = self._to_grid_coords(
                            layout, block.bbox, col.bbox
                        )
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
        """Converts a PDF bounding box to canvas grid coordinates."""
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

    def _draw_text(self, canvas, page_layout, lines,
                   clip_box=None, centered=False, v_centered=False):
        """Draws text onto the canvas."""
        if not lines:
            return
        # Handle vertically centered text blocks (like in a BoxedNote)
        if v_centered and clip_box:
            clip_coords = self._to_grid_coords(page_layout, clip_box)
            if clip_coords:
                _, clip_sr, _, clip_er = clip_coords
                start_sr = (clip_sr + (clip_er-clip_sr)//2) - (len(lines)//2)
                for i, line in enumerate(lines):
                    current_sr = start_sr + i
                    self._draw_single_line(
                        canvas, page_layout, line, current_sr, clip_box, centered
                    )
                return

        # Handle standard text drawing
        for line in lines:
            coords = self._to_grid_coords(page_layout, line.bbox, clip_box)
            if coords:
                self._draw_single_line(
                    canvas, page_layout, line, coords[1], clip_box, centered
                )

    def _draw_single_line(self, canvas, page_layout, line, row, clip, center):
        """Helper to draw a single line of text at a specific row."""
        text = self.extractor.format_line_with_style(line)
        coords = self._to_grid_coords(page_layout, line.bbox, clip)
        if not coords:
            return
        sc, _, ec, _ = coords
        avail_w = ec - sc
        if avail_w <= 0:
            return
        trunc_text = text[:avail_w]
        start_col = sc
        if center:
            c_sc, _, c_ec, _ = self._to_grid_coords(page_layout, clip)
            c_w = c_ec - c_sc
            start_col = max(c_sc, c_sc + c_w//2 - len(trunc_text)//2)

        for i, char in enumerate(trunc_text):
            if 0 <= row < self.height and 0 <= start_col + i < self.width:
                canvas[row][start_col + i] = char
