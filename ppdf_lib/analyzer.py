# --- ppdf_lib/analyzer.py ---
"""
ppdf_lib/analyzer.py: Contains the PageLayoutAnalyzer for Stage 1 processing.
"""
import logging
import re
from pdfminer.layout import LTTextLine, LTRect, LTChar
from .models import PageModel, LayoutZone, Column, Title

log_layout = logging.getLogger("ppdf.layout")


class PageLayoutAnalyzer:
    """
    Analyzes the physical layout of a single PDF page to produce a PageModel.
    """

    def __init__(self, extractor):
        self.extractor = extractor

    def analyze_page(self, layout, total_pages):
        """Analyzes a single page's layout to produce a PageModel."""
        page = PageModel(layout)
        logging.getLogger("ppdf").info("Analyzing Page Layout %d...", page.page_num)
        all_lines_raw = sorted(
            self.extractor._find_elements_by_type(layout, LTTextLine),
            key=lambda x: (-x.y1, x.x0),
        )

        # Use the manifest if available, otherwise this is a no-op
        page.page_type = self.extractor.page_manifest.get(page.page_num, {}).get(
            "type", "content"
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
            if line.y1 < self.extractor.header_cutoff
            and line.y0 > self.extractor.footer_cutoff
        ]
        page.rects = [
            r
            for r in self.extractor._find_elements_by_type(layout, LTRect)
            if r.linewidth > 0 and r.width > 10 and r.height > 10
        ]
        if not all_lines:
            return page

        page.body_font_size = self.extractor._get_page_body_font_size(all_lines)
        # Use dynamic footer detection as a fallback if prescan found nothing
        if self.extractor.remove_footers and self.extractor.footer_cutoff == 0:
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

        # Use the determined cutoffs as the main content boundaries
        top_boundary = (
            self.extractor.header_cutoff
            if self.extractor.header_cutoff != float("inf")
            else layout.y1
        )
        bottom_boundary = (
            self.extractor.footer_cutoff if self.extractor.footer_cutoff > 0 else layout.y0
        )
        breakpoints = {bottom_boundary, top_boundary, *rect_breaks}

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
            if self.extractor.num_columns_str != "auto":
                num_cols = int(self.extractor.num_columns_str)
            else:
                num_cols = self._detect_column_count(zone.lines, layout)

            logging.getLogger("ppdf").info(
                "Page %d, Zone %d: Detected %d column(s).",
                page.page_num,
                len(page.zones) + 1,
                num_cols,
            )
            col_groups = self.extractor._group_lines_into_columns(zone.lines, layout, num_cols)
            col_w = zone.bbox[2] / num_cols if num_cols > 0 else zone.bbox[2]
            for i in range(num_cols):
                c_lines = col_groups[i] if i < len(col_groups) else []
                cx0 = zone.bbox[0] + (i * col_w)
                col_bbox = (cx0, zone.bbox[1], cx0 + col_w, zone.bbox[3])
                zone.columns.append(Column(c_lines, col_bbox))
            page.zones.append(zone)
        return page

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
                or self.extractor._get_font_size(line) < (font_size * 0.85)
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
            if self.extractor._get_font_size(line) <= (font_size * 1.4):
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
            same_level = (
                abs(self.extractor._get_font_size(line) - self.extractor._get_font_size(prev))
                < 0.1
            )

            # Case 2: A subtitle or byline (font is smaller, text is shorter)
            is_subtitle = (
                self.extractor._get_font_size(line) < self.extractor._get_font_size(prev)
                and len(line.get_text()) < len(prev.get_text()) * 0.9
                and not line.get_text().strip().endswith(".")
            )

            if (
                v_dist < (self.extractor._get_font_size(prev) * 1.5)
                and h_align_ok
                and (same_level or is_subtitle)
            ):
                title_lines.append(line)
            else:
                break

        if title_lines:
            text = " ".join(
                self.extractor.format_line_with_style(line) for line in title_lines
            )
            return Title(text, title_lines), title_lines
        return None, []
