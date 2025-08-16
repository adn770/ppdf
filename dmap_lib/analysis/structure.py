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

    def _is_stair_tile_fft(self, tile_image: np.ndarray) -> bool:
        """
        Detects stairs in a tile by looking for the signature of parallel lines
        in the 2D Fourier Transform of the image.
        """
        if tile_image.size < 16 * 16:
            return False

        # 1. Normalize the tile image
        normalized_tile = cv2.resize(tile_image, (16, 16))
        if len(normalized_tile.shape) > 2:
            normalized_tile = cv2.cvtColor(normalized_tile, cv2.COLOR_BGR2GRAY)

        # 2. Compute the 2D FFT and shift the zero-frequency component to the center
        f = np.fft.fft2(normalized_tile)
        fshift = np.fft.fftshift(f)
        magnitude_spectrum = np.log(np.abs(fshift) + 1)

        # 3. Zero out the center DC component and low frequencies to find high peaks
        cy, cx = magnitude_spectrum.shape[0] // 2, magnitude_spectrum.shape[1] // 2
        magnitude_spectrum[cy - 1 : cy + 2, cx - 1 : cx + 2] = 0

        # 4. Check if the brightest remaining point (a high-frequency signal) is
        # strong enough to indicate a repeating pattern like stairs.
        max_val = np.max(magnitude_spectrum)
        mean_val = np.mean(magnitude_spectrum)
        # A strong peak will be significantly brighter than the average
        is_stairs = max_val > (mean_val * 3.5) and max_val > 5.0

        if is_stairs:
            log.debug("Stair tile detected via FFT (Peak: %.2f, Mean: %.2f)",
                      max_val, mean_val)
        return is_stairs

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

                # If a tile is less than 20% floor, it's considered empty space.
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
        structural_img: np.ndarray,
        feature_cleaned_img: np.ndarray,
        grid_info: _GridInfo,
        color_profile: Dict[str, Any],
        tile_classifications: Dict[Tuple[int, int], str],
        save_intermediate_path: Optional[str] = None,
        region_id: str = "",
    ) -> Dict[Tuple[int, int], _TileData]:
        """Perform score-based wall detection and core structure classification."""
        log.info("Executing Stage 7: Core Structure Classification...")
        tile_grid: Dict[Tuple[int, int], _TileData] = {}
        if not tile_classifications:
            return {}

        all_coords = list(tile_classifications.keys())
        min_gx = min(c[0] for c in all_coords)
        max_gx = max(c[0] for c in all_coords)
        min_gy = min(c[1] for c in all_coords)
        max_gy = max(c[1] for c in all_coords)

        # Initialize the grid based on the simplified pre-classification pass
        for y in range(min_gy, max_gy + 1):
            for x in range(min_gx, max_gx + 1):
                feature_type = tile_classifications.get((x, y), "empty")
                tile_grid[(x, y)] = _TileData(feature_type=feature_type)

        # Second pass: Re-classify floor tiles to find stairs using robust FFT
        for (gx, gy), tile in tile_grid.items():
            if tile.feature_type == "floor":
                px_x = gx * grid_info.size
                px_y = gy * grid_info.size
                cell_slice = feature_cleaned_img[
                    px_y : px_y + grid_info.size, px_x : px_x + grid_info.size
                ]
                if self._is_stair_tile_fft(cell_slice):
                    tile.feature_type = "stairs"

        grid_size, offset_x, offset_y = (
            grid_info.size,
            grid_info.offset_x,
            grid_info.offset_y,
        )
        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        stroke_bgr = np.array(
            roles_inv.get("stroke", (0, 0, 0))[::-1], dtype="uint8"
        )
        WALL_CONFIDENCE_THRESHOLD = 0.3

        # Define dynamic search area thickness and inset
        search_thickness = max(4, grid_info.size // 4)
        half_thickness = search_thickness // 2
        inset = int(grid_info.size * 0.05)


        for (x, y), tile in tile_grid.items():
            if tile.feature_type == "empty":
                continue
            p_nw = (x * grid_size + offset_x, y * grid_size + offset_y)
            p_ne = ((x + 1) * grid_size + offset_x, y * grid_size + offset_y)
            p_sw = (x * grid_size + offset_x, (y + 1) * grid_size + offset_y)
            p_se = ((x + 1) * grid_size + offset_x, (y + 1) * grid_size + offset_y)

            if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
                x_start, x_end = p_nw[0] + inset, p_ne[0] - inset
                y_center = p_nw[1]
                r_pts = np.array([(x_start, y_center - half_thickness),
                                  (x_end, y_center - half_thickness),
                                  (x_end, y_center + half_thickness),
                                  (x_start, y_center + half_thickness)])
                tile.north_wall = self._process_boundary(
                    p_nw, p_ne, r_pts, (0, -half_thickness), False, structural_img,
                    stroke_bgr, WALL_CONFIDENCE_THRESHOLD
                )
            if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
                y_start, y_end = p_ne[1] + inset, p_se[1] - inset
                x_center = p_ne[0]
                r_pts = np.array([(x_center - half_thickness, y_start),
                                  (x_center + half_thickness, y_start),
                                  (x_center + half_thickness, y_end),
                                  (x_center - half_thickness, y_end)])
                tile.east_wall = self._process_boundary(
                    p_ne, p_se, r_pts, (half_thickness, 0), True, structural_img,
                    stroke_bgr, WALL_CONFIDENCE_THRESHOLD
                )
            if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
                x_start, x_end = p_sw[0] + inset, p_se[0] - inset
                y_center = p_sw[1]
                r_pts = np.array([(x_start, y_center - half_thickness),
                                  (x_end, y_center - half_thickness),
                                  (x_end, y_center + half_thickness),
                                  (x_start, y_center + half_thickness)])
                tile.south_wall = self._process_boundary(
                    p_sw, p_se, r_pts, (0, half_thickness), False, structural_img,
                    stroke_bgr, WALL_CONFIDENCE_THRESHOLD
                )
            if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
                y_start, y_end = p_nw[1] + inset, p_sw[1] - inset
                x_center = p_nw[0]
                r_pts = np.array([(x_center - half_thickness, y_start),
                                  (x_center + half_thickness, y_start),
                                  (x_center + half_thickness, y_end),
                                  (x_center - half_thickness, y_end)])
                tile.west_wall = self._process_boundary(
                    p_nw, p_sw, r_pts, (-half_thickness, 0), True, structural_img,
                    stroke_bgr, WALL_CONFIDENCE_THRESHOLD
                )

        # The debug image must be saved *before* the grid is shifted, using the
        # original `tile_grid` coordinates to ensure correct alignment.
        if save_intermediate_path:
            filename = os.path.join(
                save_intermediate_path, f"{region_id}_wall_detection.png"
            )
            self._save_wall_detection_debug_image(
                structural_img, grid_info, tile_grid, filename
            )

        # Create a shifted grid for the transformer, so its coordinates start at (0,0)
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

        # Ensure slice coordinates are within image bounds
        h, w = structural_img.shape[:2]
        bx, by = max(0, bx), max(0, by)
        bw, bh = min(w - bx, bw), min(h - by, bh)

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
        base_img: np.ndarray,
        grid_info: _GridInfo,
        tile_grid: Dict[Tuple[int, int], _TileData],
        output_path: str,
    ):
        """Saves a debug image visualizing the grid and wall sample areas."""
        if len(base_img.shape) == 2:
            debug_img = cv2.cvtColor(base_img, cv2.COLOR_GRAY2BGR)
        else:
            debug_img = base_img.copy()
        h, w, _ = debug_img.shape

        overlay = debug_img.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
        debug_img = cv2.addWeighted(overlay, 0.4, debug_img, 0.6, 0)

        grid_color = (255, 255, 0)
        for x_coord in range(0, w, grid_info.size):
            px = x_coord + grid_info.offset_x
            cv2.line(debug_img, (px, 0), (px, h), grid_color, 1)
        for y_coord in range(0, h, grid_info.size):
            py = y_coord + grid_info.offset_y
            cv2.line(debug_img, (0, py), (w, py), grid_color, 1)

        search_area_color = (0, 255, 255) # Bright Yellow for sample areas
        search_thickness = max(4, grid_info.size // 4)
        half_thickness = search_thickness // 2
        inset = int(grid_info.size * 0.05)

        for (x, y), tile in tile_grid.items():
            if tile.feature_type == "empty":
                continue

            p_nw = (x * grid_info.size + grid_info.offset_x,
                    y * grid_info.size + grid_info.offset_y)
            p_ne = ((x + 1) * grid_info.size + grid_info.offset_x,
                    y * grid_info.size + grid_info.offset_y)
            p_sw = (x * grid_info.size + grid_info.offset_x,
                    (y + 1) * grid_info.size + grid_info.offset_y)
            p_se = ((x + 1) * grid_info.size + grid_info.offset_x,
                    (y + 1) * grid_info.size + grid_info.offset_y)

            if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
                x_start, x_end = p_nw[0] + inset, p_ne[0] - inset
                y_center = p_nw[1]
                r_pts = np.array([(x_start, y_center - half_thickness),
                                  (x_end, y_center - half_thickness),
                                  (x_end, y_center + half_thickness),
                                  (x_start, y_center + half_thickness)], dtype=np.int32)
                cv2.polylines(debug_img, [r_pts], True, search_area_color, 1)

            if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
                y_start, y_end = p_ne[1] + inset, p_se[1] - inset
                x_center = p_ne[0]
                r_pts = np.array([(x_center - half_thickness, y_start),
                                  (x_center + half_thickness, y_start),
                                  (x_center + half_thickness, y_end),
                                  (x_center - half_thickness, y_end)], dtype=np.int32)
                cv2.polylines(debug_img, [r_pts], True, search_area_color, 1)

            if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
                x_start, x_end = p_sw[0] + inset, p_se[0] - inset
                y_center = p_sw[1]
                r_pts = np.array([(x_start, y_center - half_thickness),
                                  (x_end, y_center - half_thickness),
                                  (x_end, y_center + half_thickness),
                                  (x_start, y_center + half_thickness)], dtype=np.int32)
                cv2.polylines(debug_img, [r_pts], True, search_area_color, 1)

            if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
                y_start, y_end = p_nw[1] + inset, p_sw[1] - inset
                x_center = p_nw[0]
                r_pts = np.array([(x_center - half_thickness, y_start),
                                  (x_center + half_thickness, y_start),
                                  (x_center + half_thickness, y_end),
                                  (x_center - half_thickness, y_end)], dtype=np.int32)
                cv2.polylines(debug_img, [r_pts], True, search_area_color, 1)

        cv2.imwrite(output_path, debug_img)
        log.info("Saved wall detection debug image to %s", output_path)
