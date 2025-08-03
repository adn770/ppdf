# --- ppdf_lib/scanner.py ---
"""
ppdf_lib/scanner.py: Contains the MarginScanner for header/footer detection.
"""
import logging
import re
import statistics
from collections import defaultdict
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTChar, LTImage, LTRect, LTTextLine

log_prescan = logging.getLogger("ppdf.prescan")


def _levenshtein_distance(s1, s2):
    """Calculates the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]


class MarginScanner:
    """
    Analyzes document pages to detect and define header and footer boundaries.
    """

    def __init__(self, extractor):
        self.extractor = extractor
        self.pdf_path = extractor.pdf_path

    def scan(self, pages_to_process=None):
        """
        Performs the prescan analysis and returns header/footer cutoff coordinates.
        """
        log_prescan.info("--- Prescan: Detecting Page Types & Margins ---")
        all_pages = list(extract_pages(self.pdf_path))
        pages_to_scan = [
            p for p in all_pages if not pages_to_process or p.pageid in pages_to_process
        ]
        if len(pages_to_scan) < 3:
            log_prescan.info("  - Not enough pages for reliable analysis. Skipping.")
            return float("inf"), 0

        total_pages = all_pages[-1].pageid if all_pages else 0
        self._build_page_manifest(pages_to_scan, total_pages)
        self._apply_font_size_heuristic()

        content_page_ids = {
            pid
            for pid, data in self.extractor.page_manifest.items()
            if data["type"] == "content"
        }
        if len(content_page_ids) < 3:
            log_prescan.info("  - Not enough content pages for analysis. Skipping.")
            return float("inf"), 0

        candidate_lines, _ = self._gather_candidates_and_dividers(pages_to_scan)
        clusters = self._cluster_margin_lines(candidate_lines, all_pages[0])

        best_header, best_footer = self._find_best_clusters_by_score(
            clusters, content_page_ids, all_pages[0].height
        )

        header_cutoff = float("inf")
        if best_header:
            header_cutoff = min(line.y0 for line in best_header["lines"])
            log_prescan.info("  - Header detector: Found at y < %.2f", header_cutoff)
        else:
            log_prescan.info("  - Header detector: No consistent headers found.")

        footer_cutoff = 0
        if best_footer:
            footer_cutoff = max(line.y1 for line in best_footer["lines"])
            log_prescan.info("  - Footer detector: Found at y > %.2f", footer_cutoff)
        else:
            log_prescan.info("  - Footer detector: No consistent footers found.")

        if header_cutoff <= footer_cutoff:
            log_prescan.warning(
                "  - Illogical margins detected (header %.2f <= footer %.2f). "
                "Discarding global margins.",
                header_cutoff,
                footer_cutoff,
            )
            return float("inf"), 0

        return header_cutoff, footer_cutoff

    def _build_page_manifest(self, pages_to_scan, total_pages):
        """Builds a manifest of page types and font statistics."""
        for page_layout in pages_to_scan:
            lines = self.extractor._find_elements_by_type(page_layout, LTTextLine)
            images = self.extractor._find_elements_by_type(page_layout, LTImage)
            page_type = self.extractor._classify_page_type(
                page_layout, lines, images, total_pages
            )

            total_chars, size_sum = 0, 0
            for line in lines:
                for char in line:
                    if isinstance(char, LTChar) and hasattr(char, "size"):
                        size_sum += char.size
                        total_chars += 1
            self.extractor.page_manifest[page_layout.pageid] = {
                "type": page_type,
                "total_chars": total_chars,
                "size_sum": size_sum,
            }

    def _gather_candidates_and_dividers(self, pages_to_scan):
        """Gathers candidate lines and divider rects from pages."""
        candidate_lines, dividers = [], defaultdict(list)
        for page_layout in pages_to_scan:
            lines = self.extractor._find_elements_by_type(page_layout, LTTextLine)
            rects = self.extractor._find_elements_by_type(page_layout, LTRect)
            page_dividers = [
                r for r in rects if r.height < 5 and r.width > page_layout.width * 0.2
            ]
            dividers[page_layout.pageid].extend(page_dividers)

            if self.extractor.page_manifest[page_layout.pageid]["type"] != "content":
                continue

            sorted_by_y = sorted(lines, key=lambda l: -l.y1)
            top_lines = sorted_by_y[:3]
            bottom_lines = sorted_by_y[-3:]
            for line in top_lines + bottom_lines:
                has_divider = any(
                    abs(line.y0 - r.y1) < 10 or abs(line.y1 - r.y0) < 10 for r in page_dividers
                )
                candidate_lines.append(
                    {"line": line, "page_id": page_layout.pageid, "has_divider": has_divider}
                )
        log_prescan.debug(
            "Found %d candidate lines and %d pages with dividers.",
            len(candidate_lines),
            len(dividers),
        )
        return candidate_lines, dividers

    def _get_horizontal_alignment(self, line, page_layout):
        """Categorizes a line's horizontal alignment."""
        line_center = (line.x0 + line.x1) / 2
        page_center = (page_layout.x0 + page_layout.x1) / 2
        leeway = page_layout.width * 0.15
        if abs(line_center - page_center) < leeway:
            return "center"
        elif line_center < page_center:
            return "left"
        return "right"

    def _cluster_margin_lines(self, candidate_lines, page_layout):
        """Groups margin lines into clusters based on text, style, and alignment."""
        clusters = []
        for cand in candidate_lines:
            line = cand["line"]
            text = re.sub(r"\d+", "#", line.get_text().strip())
            if not text:
                continue

            # Use Levenshtein distance for fuzzy matching
            best_match_idx = None
            min_dist = float("inf")
            for i, cluster in enumerate(clusters):
                # Only compare against clusters with same style and alignment
                if cluster["key"][1] == round(self.extractor._get_font_size(line)) and cluster[
                    "key"
                ][2] == self._get_horizontal_alignment(line, page_layout):
                    dist = _levenshtein_distance(text, cluster["key"][0])
                    threshold = max(2, int(len(cluster["key"][0]) * 0.2))
                    if dist < threshold and dist < min_dist:
                        min_dist = dist
                        best_match_idx = i

            if best_match_idx is not None:
                # Add to existing cluster
                clusters[best_match_idx]["lines"].append(line)
                clusters[best_match_idx]["pages"].add(cand["page_id"])
                if cand["has_divider"]:
                    clusters[best_match_idx]["dividers"] += 1
            else:
                # Create a new cluster
                key = (
                    text,
                    round(self.extractor._get_font_size(line)),
                    self._get_horizontal_alignment(line, page_layout),
                )
                clusters.append(
                    {
                        "lines": [line],
                        "pages": {cand["page_id"]},
                        "dividers": 1 if cand["has_divider"] else 0,
                        "key": key,
                    }
                )

        log_prescan.debug("Found %d unique clusters for margin text.", len(clusters))
        return clusters

    def _find_best_clusters_by_score(self, clusters, content_page_ids, page_height):
        """Finds the best header and footer clusters using a confidence score."""
        best_header, best_footer = None, None
        max_header_score, max_footer_score = -1, -1

        for cluster in clusters:
            num_pages = len(cluster["pages"])
            if num_pages < 2:
                continue

            frequency = num_pages / len(content_page_ids)
            y_coords = [line.y0 for line in cluster["lines"]]
            y_stddev = statistics.stdev(y_coords) if len(y_coords) > 1 else 0
            pos_stability = 1 - min(1, y_stddev / (page_height * 0.05))
            divider_bonus = 1.25 if cluster["dividers"] / num_pages > 0.5 else 1.0

            score = (frequency * 0.5 + pos_stability * 0.5) * divider_bonus
            is_header = cluster["lines"][0].y0 > page_height * 0.5

            log_prescan.debug(
                "Cluster '%s' (align: %s) on %d pages. Score: %.2f (freq: %.2f, stab: %.2f, div: %.2f)",
                cluster["key"][0],
                cluster["key"][2],
                num_pages,
                score,
                frequency,
                pos_stability,
                divider_bonus,
            )

            if is_header and score > max_header_score:
                max_header_score = score
                best_header = cluster
            elif not is_header and score > max_footer_score:
                max_footer_score = score
                best_footer = cluster

        if best_header:
            log_prescan.debug(
                "WINNER (Header): '%s' with score %.2f",
                best_header["key"][0],
                max_header_score,
            )
        if best_footer:
            log_prescan.debug(
                "WINNER (Footer): '%s' with score %.2f",
                best_footer["key"][0],
                max_footer_score,
            )
        return best_header, best_footer

    def _apply_font_size_heuristic(self):
        """
        Applies a font-size heuristic to reclassify the first page as a cover
        if its average font size is significantly larger than the document's.
        """
        # Calculate document-wide average font size from 'content' pages
        total_chars, total_size_sum = 0, 0
        for data in self.extractor.page_manifest.values():
            if data["type"] == "content":
                total_chars += data["total_chars"]
                total_size_sum += data["size_sum"]
        doc_avg_size = (total_size_sum / total_chars) if total_chars > 0 else 0

        # Check first page
        first_page_data = self.extractor.page_manifest.get(1)
        if (
            first_page_data
            and first_page_data["type"] == "content"
            and first_page_data["total_chars"] > 0
            and doc_avg_size > 0
        ):
            first_page_avg_size = first_page_data["size_sum"] / first_page_data["total_chars"]
            if first_page_avg_size > (doc_avg_size * 1.5):
                log_prescan.info(
                    "  - Re-classifying Page 1 as 'cover' due to font size heuristic "
                    "(Page Avg: %.2f, Doc Avg: %.2f)",
                    first_page_avg_size,
                    doc_avg_size,
                )
                self.extractor.page_manifest[1]["type"] = "cover"
