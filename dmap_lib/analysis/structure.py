# --- dmap_lib/analysis/structure.py ---
import logging
import math
import os
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional

import cv2
import numpy as np
from scipy.signal import find_peaks
from sklearn.cluster import KMeans

from .context import _GridInfo, _TileData, _RegionAnalysisContext

log = logging.getLogger("dmap.analysis")
log_grid = logging.getLogger("dmap.grid")


class StructureAnalyzer:
    """Identifies the core grid-based structure of the map."""

    def detect_passageway_doors(
        self,
        tile_grid: Dict[Tuple[int, int], _TileData],
        structural_img: np.ndarray,
        grid_info: _GridInfo,
        color_profile: Dict[str, Any],
        context: _RegionAnalysisContext,
        debug_canvas: Optional[np.ndarray] = None,
    ):
        """
        Scans for passageways and places perpendicular doors where door patterns
        are found within tiles. Operates on an ABSOLUTE grid.
        """
        log.info("Executing new pass: Passageway Door Classification...")
        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        stroke_bgr = np.array(roles_inv.get("stroke", (0, 0, 0))[::-1], dtype="uint8")

        processed_tiles = set()
        inset = int(grid_info.size * 0.05)
        door_search_color = (0, 255, 0)  # Green for door search areas

        for (x, y), tile in tile_grid.items():
            if (x, y) in processed_tiles or tile.feature_type != "floor":
                continue

            is_vertical_passageway = tile.west_wall == "stone" and tile.east_wall == "stone"
            is_horizontal_passageway = (
                tile.north_wall == "stone" and tile.south_wall == "stone"
            )

            if not (is_vertical_passageway or is_horizontal_passageway):
                continue

            if debug_canvas is not None:
                px_x1 = x * grid_info.size + grid_info.offset_x + inset
                py_y1 = y * grid_info.size + grid_info.offset_y + inset
                px_x2 = px_x1 + grid_info.size - (2 * inset)
                py_y2 = py_y1 + grid_info.size - (2 * inset)
                cv2.rectangle(
                    debug_canvas, (px_x1, py_y1), (px_x2, py_y2), door_search_color, 1
                )
                cv2.putText(
                    debug_canvas,
                    f"({x},{y})",
                    (px_x1, py_y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.4,
                    door_search_color,
                    1,
                )

            px_x = x * grid_info.size + grid_info.offset_x + inset
            px_y = y * grid_info.size + grid_info.offset_y + inset
            w = grid_info.size - (2 * inset)
            h = grid_info.size - (2 * inset)
            tile_slice = structural_img[px_y : px_y + h, px_x : px_x + w]

            # Create a mask for the specific stroke color and count those pixels.
            stroke_mask = cv2.inRange(tile_slice, stroke_bgr, stroke_bgr)
            if cv2.countNonZero(stroke_mask) > 10:
                door_type = "door"
            else:
                continue

            # The vertices for the pre-classified feature now reflect the inset pixel area.
            inset_factor = inset / grid_info.size
            verts = [
                {
                    "x": round(float(x + inset_factor), 2),
                    "y": round(float(y + inset_factor), 2),
                },
                {
                    "x": round(float(x + 1 - inset_factor), 2),
                    "y": round(float(y + inset_factor), 2),
                },
                {
                    "x": round(float(x + 1 - inset_factor), 2),
                    "y": round(float(y + 1 - inset_factor), 2),
                },
                {
                    "x": round(float(x + inset_factor), 2),
                    "y": round(float(y + 1 - inset_factor), 2),
                },
            ]
            door_feature = {
                "featureType": "door",
                "gridVertices": verts,
                "properties": {"z-order": 1, "detection_tile": (x, y)},
            }
            context.enhancement_layers.setdefault("features", []).append(door_feature)
            log.debug("Created pre-classified door feature at tile (%d, %d)", x, y)

            if is_vertical_passageway:
                neighbor_south = tile_grid.get((x, y + 1))
                if neighbor_south and neighbor_south.feature_type == "floor":
                    log.debug("%s created in vertical passageway at (%d, %d)", door_type, x, y)
                    tile.south_wall = door_type
                    neighbor_south.north_wall = door_type
                    processed_tiles.add((x, y))
                    processed_tiles.add((x, y + 1))

            elif is_horizontal_passageway:
                neighbor_east = tile_grid.get((x + 1, y))
                if neighbor_east and neighbor_east.feature_type == "floor":
                    log.debug(
                        "%s created in horizontal passageway at (%d, %d)", door_type, x, y
                    )
                    tile.east_wall = door_type
                    neighbor_east.west_wall = door_type
                    processed_tiles.add((x, y))
                    processed_tiles.add((x + 1, y))

    def classify_tile_content(
        self, feature_cleaned_img: np.ndarray, grid_info: _GridInfo
    ) -> Dict[Tuple[int, int], str]:
        """
        Pre-classifies each tile as either 'floor' or 'empty'. This simplified
        pass ensures room contiguity for the flood-fill algorithm.
        """
        log.info("Executing simplified pass: Base Tile Content Classification...")
        classifications = {}
        h, w = feature_cleaned_img.shape
        max_gx = w // grid_info.size
        max_gy = h // grid_info.size

        for gy in range(max_gy):
            for gx in range(max_gx):
                px_x, px_y = gx * grid_info.size, gy * grid_info.size
                cell_slice = feature_cleaned_img[
                    px_y : px_y + grid_info.size, px_x : px_x + grid_info.size
                ]
                if cell_slice.size == 0:
                    continue

                white_pixels = cv2.countNonZero(cell_slice)
                total_pixels = cell_slice.size
                white_ratio = white_pixels / total_pixels if total_pixels > 0 else 0

                if white_ratio < 0.20:
                    classifications[(gx, gy)] = "empty"
                else:
                    classifications[(gx, gy)] = "floor"
        return classifications

    def discover_grid(
        self,
        structural_img: np.ndarray,
        color_profile: dict,
        room_bounds: List[Tuple[int, int, int, int]],
    ) -> _GridInfo:
        """Discovers grid size via peak-finding and offset via room bounds."""
        log_grid.info("⚙️  Executing Stage 5: Grid Discovery...")
        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
        stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")
        binary_mask = cv2.inRange(structural_img, stroke_bgr, stroke_bgr)

        proj_x = np.sum(binary_mask, axis=0).astype(float)
        proj_y = np.sum(binary_mask, axis=1).astype(float)

        sizes = []
        for axis, proj in [("x", proj_x), ("y", proj_y)]:
            prominence = np.max(proj) * 0.25
            min_dist = min(len(proj) * 0.1, 50)
            peaks, _ = find_peaks(proj, prominence=prominence, distance=min_dist)

            if len(peaks) < 3:
                continue
            distances = np.diff(peaks)
            mode_result = Counter(distances).most_common(1)
            if not mode_result:
                continue
            grid_size = mode_result[0][0]
            if not (10 < grid_size < 200):
                continue
            sizes.append(grid_size)

        if not sizes:
            log_grid.warning("Grid size detection failed, falling back to default.")
            return _GridInfo(size=20, offset_x=0, offset_y=0)

        final_size = int(np.mean(sizes))
        log_grid.debug("Detected grid size: %dpx", final_size)

        if not room_bounds:
            log_grid.warning("No room bounds; cannot calculate offset. Using (0,0).")
            return _GridInfo(size=final_size, offset_x=0, offset_y=0)

        min_x = min(b[0] for b in room_bounds)
        min_y = min(b[1] for b in room_bounds)
        final_offset_x = min_x % final_size
        final_offset_y = min_y % final_size

        log_grid.info(
            "Detected grid: size=%dpx, offset=(%d,%d) (from room bounds)",
            final_size,
            final_offset_x,
            final_offset_y,
        )
        return _GridInfo(size=final_size, offset_x=final_offset_x, offset_y=final_offset_y)

    def classify_features(
        self,
        structural_img: np.ndarray,
        feature_cleaned_img: np.ndarray,
        grid_info: _GridInfo,
        color_profile: Dict[str, Any],
        tile_classifications: Dict[Tuple[int, int], str],
        debug_canvas: Optional[np.ndarray] = None,
    ) -> Dict[Tuple[int, int], _TileData]:
        """Perform score-based wall detection and core structure classification."""
        log.info("⚙️  Executing Stage 7: Core Structure Classification...")
        tile_grid: Dict[Tuple[int, int], _TileData] = {}
        if not tile_classifications:
            return {}

        all_coords = list(tile_classifications.keys())
        min_gx = min(c[0] for c in all_coords)
        max_gx = max(c[0] for c in all_coords)
        min_gy = min(c[1] for c in all_coords)
        max_gy = max(c[1] for c in all_coords)

        for y in range(min_gy, max_gy + 1):
            for x in range(min_gx, max_gx + 1):
                feature_type = tile_classifications.get((x, y), "empty")
                tile_grid[(x, y)] = _TileData(feature_type=feature_type)

        grid_size, offset_x, offset_y = (
            grid_info.size,
            grid_info.offset_x,
            grid_info.offset_y,
        )
        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        stroke_bgr = np.array(roles_inv.get("stroke", (0, 0, 0))[::-1], dtype="uint8")
        WALL_CONFIDENCE_THRESHOLD = 0.3

        search_thickness = max(4, grid_info.size // 4)
        half_thickness = search_thickness // 2
        inset = int(grid_info.size * 0.05)
        wall_search_color = (0, 255, 255)  # Yellow

        for (x, y), tile in tile_grid.items():
            if tile.feature_type == "empty":
                continue
            p_nw = (x * grid_info.size + offset_x, y * grid_info.size + offset_y)
            p_ne = ((x + 1) * grid_info.size + offset_x, y * grid_info.size + offset_y)
            p_sw = (x * grid_info.size + offset_x, (y + 1) * grid_info.size + offset_y)
            p_se = ((x + 1) * grid_size + offset_x, (y + 1) * grid_size + offset_y)

            if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
                x_start, x_end = p_nw[0] + inset, p_ne[0] - inset
                y_center = p_nw[1]
                r_pts = np.array(
                    [
                        (x_start, y_center - half_thickness),
                        (x_end, y_center - half_thickness),
                        (x_end, y_center + half_thickness),
                        (x_start, y_center + half_thickness),
                    ]
                )
                if debug_canvas is not None:
                    cv2.polylines(
                        debug_canvas, [r_pts.astype(np.int32)], True, wall_search_color, 1
                    )
                tile.north_wall = self._process_boundary(
                    p_nw,
                    p_ne,
                    r_pts,
                    (0, -half_thickness),
                    False,
                    structural_img,
                    stroke_bgr,
                    WALL_CONFIDENCE_THRESHOLD,
                )
            if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
                y_start, y_end = p_ne[1] + inset, p_se[1] - inset
                x_center = p_ne[0]
                r_pts = np.array(
                    [
                        (x_center - half_thickness, y_start),
                        (x_center + half_thickness, y_start),
                        (x_center + half_thickness, y_end),
                        (x_center - half_thickness, y_end),
                    ]
                )
                if debug_canvas is not None:
                    cv2.polylines(
                        debug_canvas, [r_pts.astype(np.int32)], True, wall_search_color, 1
                    )
                tile.east_wall = self._process_boundary(
                    p_ne,
                    p_se,
                    r_pts,
                    (half_thickness, 0),
                    True,
                    structural_img,
                    stroke_bgr,
                    WALL_CONFIDENCE_THRESHOLD,
                )
            if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
                x_start, x_end = p_sw[0] + inset, p_se[0] - inset
                y_center = p_sw[1]
                r_pts = np.array(
                    [
                        (x_start, y_center - half_thickness),
                        (x_end, y_center - half_thickness),
                        (x_end, y_center + half_thickness),
                        (x_start, y_center + half_thickness),
                    ]
                )
                if debug_canvas is not None:
                    cv2.polylines(
                        debug_canvas, [r_pts.astype(np.int32)], True, wall_search_color, 1
                    )
                tile.south_wall = self._process_boundary(
                    p_sw,
                    p_se,
                    r_pts,
                    (0, half_thickness),
                    False,
                    structural_img,
                    stroke_bgr,
                    WALL_CONFIDENCE_THRESHOLD,
                )
            if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
                y_start, y_end = p_nw[1] + inset, p_sw[1] - inset
                x_center = p_nw[0]
                r_pts = np.array(
                    [
                        (x_center - half_thickness, y_start),
                        (x_center + half_thickness, y_start),
                        (x_center + half_thickness, y_end),
                        (x_center - half_thickness, y_end),
                    ]
                )
                if debug_canvas is not None:
                    cv2.polylines(
                        debug_canvas, [r_pts.astype(np.int32)], True, wall_search_color, 1
                    )
                tile.west_wall = self._process_boundary(
                    p_nw,
                    p_sw,
                    r_pts,
                    (-half_thickness, 0),
                    True,
                    structural_img,
                    stroke_bgr,
                    WALL_CONFIDENCE_THRESHOLD,
                )
        return tile_grid

    def _process_boundary(
        self,
        p1: Tuple[int, int],
        p2: Tuple[int, int],
        rect_points: np.ndarray,
        exterior_offset: Tuple[int, int],
        is_vertical: bool,
        structural_img: np.ndarray,
        stroke_bgr: np.ndarray,
        threshold: float,
    ) -> Optional[str]:
        """Helper to process a single tile boundary."""
        bx, by, bw, bh = cv2.boundingRect(rect_points.astype(np.int32))

        h, w = structural_img.shape[:2]
        bx, by = max(0, bx), max(0, by)
        bw, bh = min(w - bx, bw), min(h - by, bh)

        boundary_slice = (
            structural_img[by : by + bh, bx : bx + bw] if bh > 0 and bw > 0 else np.array([])
        )
        stroke_score = self._calculate_boundary_scores(
            p1, p2, exterior_offset, structural_img, stroke_bgr
        )
        return self._classify_boundary(
            boundary_slice, stroke_bgr, is_vertical, stroke_score, threshold
        )

    def _classify_boundary(
        self,
        boundary_slice: np.ndarray,
        stroke_bgr: np.ndarray,
        is_vertical: bool,
        stroke_score: float,
        threshold: float,
    ) -> Optional[str]:
        """Analyzes a boundary's pixel projection to classify it."""
        if boundary_slice.size == 0:
            return None

        if stroke_score > threshold:
            return "stone"
        return None

    def _calculate_boundary_scores(
        self,
        p1: Tuple[int, int],
        p2: Tuple[int, int],
        exterior_offset: Tuple[int, int],
        structural_img: np.ndarray,
        stroke_bgr: np.ndarray,
    ) -> float:
        """Calculates stroke score for a boundary using dual area-based sampling."""
        thickness = 4
        p1_arr, p2_arr = np.array(p1), np.array(p2)
        vec, length = p2_arr - p1_arr, np.linalg.norm(p2_arr - p1_arr)

        centered_score = 0.0
        if length > 0:
            vec_norm = vec / length
            normal = np.array([-vec_norm[1], vec_norm[0]]) * (thickness / 2)
            rect_pts = np.array(
                [p1_arr + normal, p2_arr + normal, p2_arr - normal, p1_arr - normal],
                dtype=np.int32,
            )
            mask = np.zeros(structural_img.shape[:2], dtype=np.uint8)
            cv2.fillPoly(mask, [rect_pts], 255)
            pixels = structural_img[mask == 255]
            if pixels.size > 0:
                stroke_count = np.sum(np.all(pixels == stroke_bgr, axis=1))
                centered_score = stroke_count / pixels.shape[0]

        exterior_score = 0.0
        if length > 0:
            shift = np.array(exterior_offset)
            shift_norm = np.linalg.norm(shift)
            if shift_norm > 0:
                shift = (shift / shift_norm) * (thickness / 2)
                p1_ext, p2_ext = p1_arr + shift, p2_arr + shift
                vec_norm = (p2_ext - p1_ext) / np.linalg.norm(p2_ext - p1_ext)
                normal = np.array([-vec_norm[1], vec_norm[0]]) * (thickness / 2)
                rect_pts_ext = np.array(
                    [p1_ext + normal, p2_ext + normal, p2_ext - normal, p1_ext - normal],
                    dtype=np.int32,
                )
                mask_ext = np.zeros(structural_img.shape[:2], dtype=np.uint8)
                cv2.fillPoly(mask_ext, [rect_pts_ext], 255)
                pixels_ext = structural_img[mask_ext == 255]
                if pixels_ext.size > 0:
                    stroke_count = np.sum(np.all(pixels_ext == stroke_bgr, axis=1))
                    exterior_score = stroke_count / pixels_ext.shape[0]

        return max(centered_score, exterior_score)
