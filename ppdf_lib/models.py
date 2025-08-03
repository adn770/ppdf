# --- ppdf_lib/models.py ---
"""
ppdf_lib/models.py: Data models for representing a structured PDF document.
"""
import logging

log_reconstruct = logging.getLogger("ppdf.reconstruct")


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


# --- DOCUMENT MODEL CLASSES (LOGICAL HIERARCHY) ---
class BoundedElement:
    """Base class for any layout element with a computed bounding box."""


class ContentBlock(BoundedElement):
    """A generic block of content lines from the PDF."""

    def __init__(self, lines):
        self.lines = lines
        self.bbox = compute_bbox(lines) if lines else (0, 0, 0, 0)


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
        self.bbox = compute_bbox(lines)


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
