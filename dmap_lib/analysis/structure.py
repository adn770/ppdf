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

from .context import _GridInfo, _TileData

log = logging.getLogger("dmap.analysis")
log_grid = logging.getLogger("dmap.grid")


class StructureAnalyzer:
    """Identifies the core grid-based structure of the map."""

    def discover_grid(
        self,
        structural_img: np.ndarray,
        color_profile: dict,
        room_bounds: List[Tuple[int, int, int, int]],
    ) -> _GridInfo:
        """Discovers grid size via peak-finding and offset via room bounds."""
        log_grid.info("Executing Stage 5: Grid Discovery...")
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
        return _GridInfo(
            size=final_size, offset_x=final_offset_x, offset_y=final_offset_y
        )

    def classify_features(
        self,
        original_region_img: np.ndarray,
        structural_img: np.ndarray,
        room_contours: List[np.ndarray],
        grid_info: _GridInfo,
        color_profile: Dict[str, Any],
        kmeans: KMeans,
        save_intermediate_path: Optional[str] = None,
        region_id: str = "",
    ) -> Dict[Tuple[int, int], _TileData]:
        """Perform score-based wall detection and core structure classification."""
        log.info("Executing Stage 7: Core Structure Classification...")
        tile_grid: Dict[Tuple[int, int], _TileData] = {}
        if not room_contours:
            return {}

        grid_size, offset_x, offset_y = (
            grid_info.size,
            grid_info.offset_x,
            grid_info.offset_y,
        )
        all_pts = np.vstack(room_contours)
        min_gx, max_gx = (
            math.floor(np.min(all_pts[:, :, 0]) / grid_size),
            math.ceil(np.max(all_pts[:, :, 0]) / grid_size),
        )
        min_gy, max_gy = (
            math.floor(np.min(all_pts[:, :, 1]) / grid_size),
            math.ceil(np.max(all_pts[:, :, 1]) / grid_size),
        )

        for y in range(min_gy - 1, max_gy + 2):
            for x in range(min_gx - 1, max_gx + 2):
                px_c = (
                    x * grid_size + offset_x + grid_size // 2,
                    y * grid_size + offset_y + grid_size // 2,
                )
                is_in = any(
                    cv2.pointPolygonTest(c, px_c, False) >= 0 for c in room_contours
                )
                tile_grid[(x, y)] = _TileData(
                    feature_type="floor" if is_in else "empty"
                )

        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        stroke_bgr = np.array(roles_inv.get("stroke", (0, 0, 0))[::-1], dtype="uint8")
        WALL_CONFIDENCE_THRESHOLD = 0.3
        offset = grid_size // 4

        for (x, y), tile in tile_grid.items():
            if tile.feature_type == "empty":
                continue
            p_nw = (x * grid_size + offset_x, y * grid_size + offset_y)
            p_ne = ((x + 1) * grid_size + offset_x, y * grid_size + offset_y)
            p_sw = (x * grid_size + offset_x, (y + 1) * grid_size + offset_y)
            p_se = ((x + 1) * grid_size + offset_x, (y + 1) * grid_size + offset_y)

            if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
                r_pts = np.array([p_nw, p_ne, (p_ne[0], p_ne[1]+4), (p_nw[0], p_nw[1]+4)])
                tile.north_wall = self._process_boundary(
                    p_nw, p_ne, r_pts, (0, -offset), False, structural_img, stroke_bgr,
                    WALL_CONFIDENCE_THRESHOLD
                )
            if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
                r_pts = np.array([(p_ne[0]-4, p_ne[1]), p_ne, p_se, (p_se[0]-4, p_se[1])])
                tile.east_wall = self._process_boundary(
                    p_ne, p_se, r_pts, (offset, 0), True, structural_img, stroke_bgr,
                    WALL_CONFIDENCE_THRESHOLD
                )
            if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
                r_pts = np.array([(p_sw[0],p_sw[1]-4),(p_se[0],p_se[1]-4),p_se,p_sw])
                tile.south_wall = self._process_boundary(
                    p_sw, p_se, r_pts, (0, offset), False, structural_img, stroke_bgr,
                    WALL_CONFIDENCE_THRESHOLD
                )
            if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
                r_pts = np.array([p_nw, (p_nw[0]+4, p_nw[1]), (p_sw[0]+4, p_sw[1]), p_sw])
                tile.west_wall = self._process_boundary(
                    p_nw, p_sw, r_pts, (-offset, 0), True, structural_img, stroke_bgr,
                    WALL_CONFIDENCE_THRESHOLD
                )

        shifted_grid = {}
        c_min_gx = min(
            (k[0] for k, v in tile_grid.items() if v.feature_type != "empty"),
            default=0,
        )
        c_min_gy = min(
            (k[1] for k, v in tile_grid.items() if v.feature_type != "empty"),
            default=0,
        )
        for (gx, gy), tile_data in tile_grid.items():
            shifted_grid[(gx - c_min_gx, gy - c_min_gy)] = tile_data

        if save_intermediate_path:
            filename = os.path.join(
                save_intermediate_path, f"{region_id}_wall_detection.png"
            )
            self._save_wall_detection_debug_image(
                original_region_img, grid_info, shifted_grid, filename
            )
        return shifted_grid

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
        boundary_slice = (
            structural_img[by : by + bh, bx : bx + bw]
            if bh > 0 and bw > 0
            else np.array([])
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

        binary_mask = np.all(boundary_slice == stroke_bgr, axis=2).astype(np.uint8)
        projection = np.sum(binary_mask, axis=1 if is_vertical else 0)
        seg_len = len(projection)

        peaks, _ = find_peaks(projection, prominence=1)
        if len(peaks) == 3:
            return "iron_bar_door"
        if len(peaks) == 2:
            peak_dist = abs(peaks[0] - peaks[1])
            trough_idx = np.argmin(projection[peaks[0] : peaks[1]]) + peaks[0]
            if peak_dist > seg_len * 0.75 and projection[trough_idx] <= 1:
                return "secret_door"
        if seg_len >= 10:
            third = seg_len // 3
            l_frame, r_frame = np.sum(projection[:third]), np.sum(
                projection[seg_len - third :]
            )
            opening = np.sum(projection[third : seg_len - third])
            if l_frame > 5 and r_frame > 5 and opening < 2:
                return "door"

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
                    [p1_ext+normal, p2_ext+normal, p2_ext-normal, p1_ext-normal],
                    dtype=np.int32,
                )
                mask_ext = np.zeros(structural_img.shape[:2], dtype=np.uint8)
                cv2.fillPoly(mask_ext, [rect_pts_ext], 255)
                pixels_ext = structural_img[mask_ext == 255]
                if pixels_ext.size > 0:
                    stroke_count = np.sum(np.all(pixels_ext == stroke_bgr, axis=1))
                    exterior_score = stroke_count / pixels_ext.shape[0]

        return max(centered_score, exterior_score)

    def _save_wall_detection_debug_image(
        self,
        original_region_img: np.ndarray,
        grid_info: _GridInfo,
        tile_grid: Dict[Tuple[int, int], _TileData],
        output_path: str,
    ):
        """Saves a debug image visualizing the grid and wall sample areas."""
        h, w, _ = original_region_img.shape
        debug_img = original_region_img.copy()
        thickness = 4

        overlay = debug_img.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
        debug_img = cv2.addWeighted(overlay, 0.4, debug_img, 0.6, 0)

        grid_color = (255, 255, 0)
        for x in range(0, w, grid_info.size):
            px = x + grid_info.offset_x
            cv2.line(debug_img, (px, 0), (px, h), grid_color, 1)
        for y in range(0, h, grid_info.size):
            py = y + grid_info.offset_y
            cv2.line(debug_img, (0, py), (w, py), grid_color, 1)

        stroke_centered_color, stroke_exterior_color = (0, 255, 255), (0, 165, 255)
        offset = grid_info.size // 4

        for (x, y), tile in tile_grid.items():
            if tile.feature_type == "empty":
                continue
            p_nw = (x*grid_info.size+grid_info.offset_x, y*grid_info.size+grid_info.offset_y)
            p_ne = ((x+1)*grid_info.size+grid_info.offset_x, y*grid_info.size+grid_info.offset_y)
            p_sw = (x*grid_info.size+grid_info.offset_x, (y+1)*grid_info.size+grid_info.offset_y)
            p_se = ((x+1)*grid_info.size+grid_info.offset_x, (y+1)*grid_info.size+grid_info.offset_y)

            boundaries = []
            if tile_grid.get((x,y-1),_TileData("empty")).feature_type=="empty":
                boundaries.append({"p1":p_nw, "p2":p_ne, "off":(0,-offset)})
            if tile_grid.get((x+1,y),_TileData("empty")).feature_type=="empty":
                boundaries.append({"p1":p_ne, "p2":p_se, "off":(offset,0)})
            if tile_grid.get((x,y+1),_TileData("empty")).feature_type=="empty":
                boundaries.append({"p1":p_sw, "p2":p_se, "off":(0,offset)})
            if tile_grid.get((x-1,y),_TileData("empty")).feature_type=="empty":
                boundaries.append({"p1":p_nw, "p2":p_sw, "off":(-offset,0)})

            for b in boundaries:
                p1_arr, p2_arr = np.array(b["p1"]), np.array(b["p2"])
                s_vec, s_len = p2_arr - p1_arr, np.linalg.norm(p2_arr - p1_arr)
                if s_len > 0:
                    s_vn = s_vec / s_len
                    s_n = np.array([-s_vn[1], s_vn[0]]) * (thickness / 2)
                    s_pts = np.array([p1_arr+s_n, p2_arr+s_n, p2_arr-s_n, p1_arr-s_n],
                                     dtype=np.int32)
                    cv2.polylines(debug_img, [s_pts], True, stroke_centered_color, 1)
                    shift = np.array(b["off"])
                    if np.linalg.norm(shift) > 0:
                        shift = (shift/np.linalg.norm(shift)) * (thickness/2)
                        p1_e, p2_e = p1_arr + shift, p2_arr + shift
                        s_pts_e = np.array([p1_e+s_n,p2_e+s_n,p2_e-s_n,p1_e-s_n],
                                           dtype=np.int32)
                        cv2.polylines(debug_img, [s_pts_e], True, stroke_exterior_color, 1)

        cv2.imwrite(output_path, debug_img)
        log.info("Saved wall detection debug image to %s", output_path)
