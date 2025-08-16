import logging
import os
import uuid
import itertools
import math
import colorsys
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from collections import Counter

import cv2
import numpy as np
import easyocr
from shapely.geometry import Point, Polygon
# scikit-learn is a new dependency for color quantization
from sklearn.cluster import KMeans
# SciPy is a new dependency for peak finding in grid detection
from scipy.signal import find_peaks

from dmap_lib import schema, rendering

log = logging.getLogger("dmap.analysis")
log_ocr = logging.getLogger("dmap.ocr")
log_geom = logging.getLogger("dmap.geometry")
log_xfm = logging.getLogger("dmap.transform")
log_wall = logging.getLogger("dmap.wallscore")
log_grid = logging.getLogger("dmap.grid")


class ColorAnalyzer:
    """Encapsulates color quantization and semantic role assignment."""

    def analyze(
        self, img: np.ndarray, num_colors: int = 8
    ) -> Tuple[Dict[str, Any], KMeans]:
        """
        Analyzes image colors and returns a color profile.
        This is the refactored version of _stage2_analyze_region_colors.
        """
        log.info("Executing Stage 2: Multi-Pass Contextual Color Analysis...")
        pixels = img.reshape(-1, 3)
        kmeans = KMeans(n_clusters=num_colors, random_state=42, n_init=10).fit(pixels)
        palette_bgr = kmeans.cluster_centers_.astype("uint8")
        palette_rgb = [tuple(c[::-1]) for c in palette_bgr]

        color_profile = {"palette": palette_rgb, "roles": {}}
        roles = color_profile["roles"]
        unassigned_colors = list(palette_rgb)
        all_labels = kmeans.labels_.reshape(img.shape[:2])
        h, w, _ = img.shape

        # --- Pass 1: Anchor Color Identification (Floor) ---
        center_img = img[h // 4 : h * 3 // 4, w // 4 : w * 3 // 4, :]
        center_pixels = center_img.reshape(-1, 3)
        center_labels = kmeans.predict(center_pixels)
        center_counts = Counter(center_labels)
        floor_color = None
        for label, _ in center_counts.most_common():
            p_color = tuple(kmeans.cluster_centers_[label].astype("uint8")[::-1])
            if p_color in unassigned_colors:
                floor_color = p_color
                break
        if floor_color:
            roles[floor_color] = "floor"
            unassigned_colors.remove(floor_color)

        # --- Pass 2: Stroke Identification via Edge Sampling ---
        stroke_rgb = None
        if floor_color:
            floor_bgr = np.array(floor_color[::-1], dtype="uint8")
            floor_mask = cv2.inRange(img, floor_bgr, floor_bgr)
            contours, _ = cv2.findContours(
                floor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            edge_pixels = []
            for contour in contours:
                for point in contour:
                    edge_pixels.append(img[point[0][1], point[0][0]])

            if edge_pixels:
                edge_labels = kmeans.predict(edge_pixels)
                valid_labels = [
                    l
                    for l in edge_labels
                    if tuple(kmeans.cluster_centers_[l].astype("uint8")[::-1])
                    in unassigned_colors
                ]
                if valid_labels:
                    stroke_label = Counter(valid_labels).most_common(1)[0][0]
                    stroke_rgb = tuple(
                        kmeans.cluster_centers_[stroke_label].astype("uint8")[::-1]
                    )
                    roles[stroke_rgb] = "stroke"
                    unassigned_colors.remove(stroke_rgb)

        # Fallback if edge sampling fails
        if not stroke_rgb and unassigned_colors:
            stroke_rgb = min(unassigned_colors, key=sum)
            roles[stroke_rgb] = "stroke"
            unassigned_colors.remove(stroke_rgb)

        # --- Pass 3: Border Color Identification (Glow & Shadow) ---
        stroke_label = kmeans.predict([np.array(stroke_rgb[::-1])])[0]
        stroke_mask = (all_labels == stroke_label).astype(np.uint8)
        dilated_mask = cv2.dilate(
            stroke_mask, np.ones((3, 3), np.uint8), iterations=2
        )
        search_mask = dilated_mask - stroke_mask
        adjacent_labels = all_labels[search_mask == 1]
        valid_adj = [
            l
            for l in adjacent_labels
            if tuple(kmeans.cluster_centers_[l].astype("uint8")[::-1])
            in unassigned_colors
        ]
        if len(valid_adj) > 1:
            top_two = [item[0] for item in Counter(valid_adj).most_common(2)]
            c1 = tuple(kmeans.cluster_centers_[top_two[0]].astype("uint8")[::-1])
            c2 = tuple(kmeans.cluster_centers_[top_two[1]].astype("uint8")[::-1])
            if sum(c1) > sum(c2):
                glow_rgb, shadow_rgb = c1, c2
            else:
                glow_rgb, shadow_rgb = c2, c1
            roles[glow_rgb] = "glow"
            unassigned_colors.remove(glow_rgb)
            roles[shadow_rgb] = "shadow"
            unassigned_colors.remove(shadow_rgb)

        # --- Pass 4: Environmental Layer Identification (Water) ---
        if unassigned_colors:
            candidates = []
            rgb_to_label = {tuple(c[::-1]): i for i, c in enumerate(palette_bgr)}
            for color in unassigned_colors:
                label = rgb_to_label[color]
                mask = (all_labels == label).astype(np.uint8) * 255
                contours, _ = cv2.findContours(
                    mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                total_area = sum(cv2.contourArea(c) for c in contours)
                candidates.append((total_area, color))
            if candidates:
                best = max(candidates, key=lambda item: item[0])
                if best[0] > 500:  # Threshold for minimum area
                    water_color = best[1]
                    roles[water_color] = "water"
                    unassigned_colors.remove(water_color)
                    log.debug("Identified water color: %s", str(water_color))

        # --- Pass 5: Final Alias Classification ---
        primary_roles = list(roles.items())
        if primary_roles:
            for alias_color in unassigned_colors:
                closest = min(
                    primary_roles,
                    key=lambda i: np.linalg.norm(np.array(alias_color) - np.array(i[0])),
                )
                roles[alias_color] = f"alias_{closest[1]}"

        log.debug("--- Advanced Color Profile ---")
        for color, role in roles.items():
            log.debug("RGB: %-15s -> Role: %s", str(color), role)

        return color_profile, kmeans


class StructureAnalyzer:
    """Identifies the core grid-based structure of the map."""

    def discover_grid(
        self,
        structural_img: np.ndarray,
        color_profile: dict,
        room_bounds: List[Tuple[int, int, int, int]],
    ) -> "_GridInfo":
        """Discovers grid size via peak-finding and offset via room bounds."""
        log_grid.info("Executing Stage 4: Grid Discovery...")
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

            if len(peaks) < 3: continue
            distances = np.diff(peaks)
            mode_result = Counter(distances).most_common(1)
            if not mode_result: continue
            grid_size = mode_result[0][0]
            if not (10 < grid_size < 200): continue
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
            final_size, final_offset_x, final_offset_y
        )
        return _GridInfo(size=final_size, offset_x=final_offset_x, offset_y=final_offset_y)

    def classify_features(
        self,
        original_region_img: np.ndarray,
        structural_img: np.ndarray,
        room_contours: List[np.ndarray],
        grid_info: "_GridInfo",
        color_profile: Dict[str, Any],
        kmeans: KMeans,
        save_intermediate_path: Optional[str] = None,
        region_id: str = "",
    ) -> Dict[Tuple[int, int], "_TileData"]:
        """Perform score-based wall detection and core structure classification."""
        log.info("Executing Stage 6: Core Structure Classification...")
        tile_grid: Dict[Tuple[int, int], "_TileData"] = {}
        if not room_contours: return {}

        grid_size, offset_x, offset_y = grid_info.size, grid_info.offset_x, grid_info.offset_y
        all_pts = np.vstack(room_contours)
        min_gx, max_gx = math.floor(np.min(all_pts[:, :, 0]) / grid_size), math.ceil(np.max(all_pts[:, :, 0]) / grid_size)
        min_gy, max_gy = math.floor(np.min(all_pts[:, :, 1]) / grid_size), math.ceil(np.max(all_pts[:, :, 1]) / grid_size)

        for y in range(min_gy - 1, max_gy + 2):
            for x in range(min_gx - 1, max_gx + 2):
                px_c = (x * grid_size + offset_x + grid_size // 2, y * grid_size + offset_y + grid_size // 2)
                is_in = any(cv2.pointPolygonTest(c, px_c, False) >= 0 for c in room_contours)
                tile_grid[(x, y)] = _TileData(feature_type="floor" if is_in else "empty")

        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        stroke_bgr = np.array(roles_inv.get("stroke", (0, 0, 0))[::-1], dtype="uint8")
        WALL_CONFIDENCE_THRESHOLD = 0.3
        offset = grid_size // 4

        for (x, y), tile in tile_grid.items():
            if tile.feature_type == "empty": continue
            p_nw = (x * grid_size + offset_x, y * grid_size + offset_y)
            p_ne = ((x + 1) * grid_size + offset_x, y * grid_size + offset_y)
            p_sw = (x * grid_size + offset_x, (y + 1) * grid_size + offset_y)
            p_se = ((x + 1) * grid_size + offset_x, (y + 1) * grid_size + offset_y)

            if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
                r_pts = np.array([p_nw, p_ne, (p_ne[0], p_ne[1] + 4), (p_nw[0], p_nw[1] + 4)])
                tile.north_wall = self._process_boundary(p_nw, p_ne, r_pts, (0, -offset), False, structural_img, stroke_bgr, WALL_CONFIDENCE_THRESHOLD)
            if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
                r_pts = np.array([(p_ne[0] - 4, p_ne[1]), p_ne, p_se, (p_se[0] - 4, p_se[1])])
                tile.east_wall = self._process_boundary(p_ne, p_se, r_pts, (offset, 0), True, structural_img, stroke_bgr, WALL_CONFIDENCE_THRESHOLD)
            if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
                r_pts = np.array([(p_sw[0], p_sw[1] - 4), (p_se[0], p_se[1] - 4), p_se, p_sw])
                tile.south_wall = self._process_boundary(p_sw, p_se, r_pts, (0, offset), False, structural_img, stroke_bgr, WALL_CONFIDENCE_THRESHOLD)
            if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
                r_pts = np.array([p_nw, (p_nw[0] + 4, p_nw[1]), (p_sw[0] + 4, p_sw[1]), p_sw])
                tile.west_wall = self._process_boundary(p_nw, p_sw, r_pts, (-offset, 0), True, structural_img, stroke_bgr, WALL_CONFIDENCE_THRESHOLD)

        shifted_grid = {}
        c_min_gx = min((k[0] for k, v in tile_grid.items() if v.feature_type != "empty"), default=0)
        c_min_gy = min((k[1] for k, v in tile_grid.items() if v.feature_type != "empty"), default=0)
        for (gx, gy), tile_data in tile_grid.items():
            shifted_grid[(gx - c_min_gx, gy - c_min_gy)] = tile_data

        if save_intermediate_path:
            filename = os.path.join(save_intermediate_path, f"{region_id}_wall_detection.png")
            self._save_wall_detection_debug_image(original_region_img, grid_info, shifted_grid, filename)
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
        boundary_slice = structural_img[by : by + bh, bx : bx + bw] if bh > 0 and bw > 0 else np.array([])
        stroke_score = self._calculate_boundary_scores(p1, p2, exterior_offset, structural_img, stroke_bgr)
        return self._classify_boundary(boundary_slice, stroke_bgr, is_vertical, stroke_score, threshold)

    def _classify_boundary(
        self,
        boundary_slice: np.ndarray,
        stroke_bgr: np.ndarray,
        is_vertical: bool,
        stroke_score: float,
        threshold: float,
    ) -> Optional[str]:
        """Analyzes a boundary's pixel projection to classify it."""
        if boundary_slice.size == 0: return None

        binary_mask = np.all(boundary_slice == stroke_bgr, axis=2).astype(np.uint8)
        projection = np.sum(binary_mask, axis=1 if is_vertical else 0)
        seg_len = len(projection)

        peaks, _ = find_peaks(projection, prominence=1)
        if len(peaks) == 3: return "iron_bar_door"
        if len(peaks) == 2:
            peak_dist = abs(peaks[0] - peaks[1])
            trough_idx = np.argmin(projection[peaks[0] : peaks[1]]) + peaks[0]
            if peak_dist > seg_len * 0.75 and projection[trough_idx] <= 1:
                return "secret_door"
        if seg_len >= 10:
            third = seg_len // 3
            l_frame, r_frame = np.sum(projection[:third]), np.sum(projection[seg_len - third:])
            opening = np.sum(projection[third : seg_len - third])
            if l_frame > 5 and r_frame > 5 and opening < 2: return "door"

        if stroke_score > threshold: return "stone"
        return None

    def _calculate_boundary_scores(
        self,
        p1: Tuple[int, int],
        p2: Tuple[int, int],
        exterior_offset: Tuple[int, int],
        structural_img: np.ndarray,
        stroke_bgr: np.ndarray,
    ) -> float:
        """Calculates the stroke score for a boundary using dual area-based sampling."""
        thickness = 4
        p1_arr, p2_arr = np.array(p1), np.array(p2)
        vec, length = p2_arr - p1_arr, np.linalg.norm(p2_arr - p1_arr)

        centered_score = 0.0
        if length > 0:
            vec_norm = vec / length
            normal = np.array([-vec_norm[1], vec_norm[0]]) * (thickness / 2)
            rect_pts = np.array([p1_arr + normal, p2_arr + normal, p2_arr - normal, p1_arr - normal], dtype=np.int32)
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
                rect_pts_ext = np.array([p1_ext + normal, p2_ext + normal, p2_ext - normal, p1_ext - normal], dtype=np.int32)
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
        grid_info: "_GridInfo",
        tile_grid: Dict[Tuple[int, int], "_TileData"],
        output_path: str,
    ):
        """Saves a debug image visualizing the grid and wall scoring sample areas."""
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
            if tile.feature_type == "empty": continue
            p_nw = (x*grid_info.size+grid_info.offset_x, y*grid_info.size+grid_info.offset_y)
            p_ne = ((x+1)*grid_info.size+grid_info.offset_x, y*grid_info.size+grid_info.offset_y)
            p_sw = (x*grid_info.size+grid_info.offset_x, (y+1)*grid_info.size+grid_info.offset_y)
            p_se = ((x+1)*grid_info.size+grid_info.offset_x, (y+1)*grid_info.size+grid_info.offset_y)

            boundaries = []
            if tile_grid.get((x, y-1), _TileData("empty")).feature_type == "empty": boundaries.append({"p1":p_nw, "p2":p_ne, "off":(0,-offset)})
            if tile_grid.get((x+1, y), _TileData("empty")).feature_type == "empty": boundaries.append({"p1":p_ne, "p2":p_se, "off":(offset,0)})
            if tile_grid.get((x, y+1), _TileData("empty")).feature_type == "empty": boundaries.append({"p1":p_sw, "p2":p_se, "off":(0,offset)})
            if tile_grid.get((x-1, y), _TileData("empty")).feature_type == "empty": boundaries.append({"p1":p_nw, "p2":p_sw, "off":(-offset,0)})

            for b in boundaries:
                p1_arr, p2_arr = np.array(b["p1"]), np.array(b["p2"])
                s_vec, s_len = p2_arr - p1_arr, np.linalg.norm(p2_arr - p1_arr)
                if s_len > 0:
                    s_vn = s_vec / s_len
                    s_n = np.array([-s_vn[1], s_vn[0]]) * (thickness / 2)
                    s_pts = np.array([p1_arr+s_n, p2_arr+s_n, p2_arr-s_n, p1_arr-s_n], dtype=np.int32)
                    cv2.polylines(debug_img, [s_pts], True, stroke_centered_color, 1)
                    shift = np.array(b["off"])
                    if np.linalg.norm(shift) > 0:
                        shift = (shift/np.linalg.norm(shift)) * (thickness/2)
                        p1_e, p2_e = p1_arr + shift, p2_arr + shift
                        s_pts_e = np.array([p1_e+s_n, p2_e+s_n, p2_e-s_n, p1_e-s_n], dtype=np.int32)
                        cv2.polylines(debug_img, [s_pts_e], True, stroke_exterior_color, 1)

        cv2.imwrite(output_path, debug_img)
        log.info("Saved wall detection debug image to %s", output_path)


class FeatureExtractor:
    """Handles detection of non-grid-aligned features."""

    def extract(
        self,
        original_region_img: np.ndarray,
        room_contours: List[np.ndarray],
        grid_size: int,
        color_profile: Dict[str, Any],
        kmeans: KMeans,
    ) -> Dict[str, Any]:
        """Extracts high-resolution features like columns and water."""
        log.info("Executing Stage 5: High-Resolution Feature & Layer Detection...")
        enhancements: Dict[str, List] = {"features": [], "layers": []}
        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        labels = kmeans.predict(original_region_img.reshape(-1, 3))

        # --- 1. Detect Water Layers ---
        if "water" in roles_inv:
            w_rgb = roles_inv["water"]
            w_bgr = np.array(w_rgb[::-1], dtype="uint8")
            w_cen = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - w_bgr))
            w_lab = kmeans.predict([w_cen])[0]
            w_mask = (labels == w_lab).reshape(original_region_img.shape[:2])
            w_mask_u8 = w_mask.astype("uint8") * 255
            cnts, _ = cv2.findContours(w_mask_u8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                if cv2.contourArea(c) > grid_size * grid_size:
                    verts = [(v[0][0]/grid_size*8.0, v[0][1]/grid_size*8.0) for v in c]
                    enhancements["layers"].append({"layerType": "water", "high_res_vertices": verts, "properties": {"z-order": 0}})

        # --- 2. Detect Column Features ---
        if room_contours:
            s_rgb = roles_inv.get("stroke", (0,0,0))
            s_bgr = np.array(s_rgb[::-1], dtype="uint8")
            s_cen = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - s_bgr))
            s_lab = kmeans.predict([s_cen])[0]
            s_mask = (labels == s_lab).reshape(original_region_img.shape[:2])
            s_mask_u8 = s_mask.astype("uint8") * 255
            cnts, _ = cv2.findContours(s_mask_u8, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                area = cv2.contourArea(c)
                if not (20 < area < (grid_size * grid_size * 2)): continue
                M = cv2.moments(c)
                if M["m00"] == 0: continue
                cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                if any(cv2.pointPolygonTest(rc, (cx, cy), False) >= 0 for rc in room_contours):
                    verts = [(v[0][0]/grid_size*8.0, v[0][1]/grid_size*8.0) for v in c]
                    enhancements["features"].append({"featureType": "column", "high_res_vertices": verts, "properties": {"z-order": 1}})

        log.info("Detected %d features and %d layers.", len(enhancements["features"]), len(enhancements["layers"]))
        return enhancements


class MapTransformer:
    """Converts the intermediate tile_grid into the final schema.MapData object."""

    def transform(
        self, context: "_RegionAnalysisContext", grid_size: int
    ) -> List[Any]:
        """Transforms the context object into final MapObject entities."""
        log.info("Executing Stage 7: Transforming grid and layers to map data...")
        tile_grid = context.tile_grid
        if not tile_grid:
            return []

        coord_to_room_id, rooms, room_polygons = {}, [], {}
        room_areas = self._find_room_areas(tile_grid)
        log_xfm.debug("Step 1: Found %d distinct room areas.", len(room_areas))

        for i, area_tiles in enumerate(room_areas):
            verts = self._trace_room_perimeter(area_tiles, tile_grid)

            if len(verts) < 4:
                log_geom.debug("Discarding room %d: degenerate shape (verts < 4).", i)
                continue
            poly = Polygon([(v.x, v.y) for v in verts])
            if poly.area < 1.0:
                log_geom.debug("Discarding room %d: area < 1.0 grid tile.", i)
                continue

            room = schema.Room(id=f"room_{uuid.uuid4().hex[:8]}", shape="polygon", gridVertices=verts, roomType="chamber", contents=[])
            rooms.append(room)
            room_polygons[room.id] = poly
            for pos in area_tiles:
                coord_to_room_id[pos] = room.id
        log_xfm.debug("Step 2: Created %d valid Room objects from traced areas.", len(rooms))

        doors = self._extract_doors_from_grid(tile_grid, coord_to_room_id)
        log_xfm.debug("Step 3: Extracted %d Door objects.", len(doors))

        features, layers = [], []
        room_map = {r.id: r for r in rooms}

        for item in context.enhancement_layers.get("features", []):
            verts = [schema.GridPoint(x=int(v[0]/8), y=int(v[1]/8)) for v in item["high_res_vertices"]]
            feature = schema.Feature(id=f"feature_{uuid.uuid4().hex[:8]}", featureType=item["featureType"], shape="polygon", gridVertices=verts, properties=item["properties"])
            features.append(feature)
            center = Polygon([(v.x, v.y) for v in verts]).centroid
            for room_id, poly in room_polygons.items():
                if poly.contains(center):
                    if room_map[room_id].contents is not None:
                        room_map[room_id].contents.append(feature.id)
                    break

        for item in context.enhancement_layers.get("layers", []):
            verts = [schema.GridPoint(x=int(v[0]/8), y=int(v[1]/8)) for v in item["high_res_vertices"]]
            layer = schema.EnvironmentalLayer(id=f"layer_{uuid.uuid4().hex[:8]}", layerType=item["layerType"], gridVertices=verts, properties=item["properties"])
            layers.append(layer)
            center = Polygon([(v.x, v.y) for v in verts]).centroid
            for room_id, poly in room_polygons.items():
                if poly.contains(center):
                    if room_map[room_id].contents is not None:
                        room_map[room_id].contents.append(layer.id)
                    break
        log_xfm.debug(
            "Step 4: Created %d features and %d layers from enhancements.",
            len(features), len(layers)
        )

        all_objects: List[Any] = rooms + doors + features + layers
        log.info("Transformation complete. Found %d total map objects.", len(all_objects))
        return all_objects

    def _find_room_areas(self, tile_grid):
        """Finds all contiguous areas of floor tiles using BFS."""
        visited, all_areas = set(), []
        for (gx, gy), tile in tile_grid.items():
            if tile.feature_type == "floor" and (gx, gy) not in visited:
                current_area, q, head = set(), [(gx, gy)], 0
                visited.add((gx, gy))
                while head < len(q):
                    cx, cy = q[head]; head += 1
                    current_area.add((cx, cy))
                    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                        nx, ny = cx + dx, cy + dy
                        neighbor = tile_grid.get((nx, ny))
                        if (neighbor and neighbor.feature_type == "floor" and (nx, ny) not in visited):
                            visited.add((nx, ny))
                            q.append((nx, ny))
                all_areas.append(current_area)
        return all_areas

    def _extract_doors_from_grid(self, tile_grid, coord_to_room_id):
        """Finds all doors on tile edges and links the adjacent rooms."""
        doors = []
        processed_edges = set()
        door_types = ("door", "secret_door", "iron_bar_door")

        for (gx, gy), tile in tile_grid.items():
            # South Wall Check
            if tile.south_wall in door_types:
                edge = tuple(sorted(((gx, gy), (gx, gy + 1))))
                if edge not in processed_edges:
                    r1 = coord_to_room_id.get((gx, gy))
                    r2 = coord_to_room_id.get((gx, gy + 1))
                    if r1 and r2 and r1 != r2:
                        props = None
                        if tile.south_wall == "secret_door": props = {"secret": True}
                        elif tile.south_wall == "iron_bar_door": props = {"type": "iron_bar"}
                        pos = schema.GridPoint(x=gx, y=gy + 1)
                        doors.append(schema.Door(id=f"door_{uuid.uuid4().hex[:8]}", gridPos=pos, orientation="h", connects=[r1, r2], properties=props))
                        processed_edges.add(edge)

            # East Wall Check
            if tile.east_wall in door_types:
                edge = tuple(sorted(((gx, gy), (gx + 1, gy))))
                if edge not in processed_edges:
                    r1 = coord_to_room_id.get((gx, gy))
                    r2 = coord_to_room_id.get((gx + 1, gy))
                    if r1 and r2 and r1 != r2:
                        props = None
                        if tile.east_wall == "secret_door": props = {"secret": True}
                        elif tile.east_wall == "iron_bar_door": props = {"type": "iron_bar"}
                        pos = schema.GridPoint(x=gx + 1, y=gy)
                        doors.append(schema.Door(id=f"door_{uuid.uuid4().hex[:8]}", gridPos=pos, orientation="v", connects=[r1, r2], properties=props))
                        processed_edges.add(edge)
        return doors

    def _trace_room_perimeter(self, room_tiles, tile_grid):
        """Traces the perimeter of a room area using a wall-following algorithm."""
        if not room_tiles: return []
        start_pos = min(room_tiles, key=lambda p: (p[1], p[0]))
        direction, current_vertex = (1, 0), (start_pos[0], start_pos[1])
        path = [schema.GridPoint(x=current_vertex[0], y=current_vertex[1])]

        for _ in range(len(tile_grid) * 4):
            tile_NW = tile_grid.get((current_vertex[0] - 1, current_vertex[1] - 1))
            tile_NE = tile_grid.get((current_vertex[0], current_vertex[1] - 1))
            tile_SW = tile_grid.get((current_vertex[0] - 1, current_vertex[1]))
            tile_SE = tile_grid.get(current_vertex)

            if direction == (1, 0): # Moving East
                if tile_NE and tile_NE.west_wall: direction = (0, 1) # Turn South
                elif tile_SE and tile_SE.north_wall: current_vertex = (current_vertex[0] + 1, current_vertex[1]) # Continue East
                else: direction = (0, -1) # Turn North
            elif direction == (0, 1): # Moving South
                if tile_SE and tile_SE.north_wall: direction = (-1, 0) # Turn West
                elif tile_SW and tile_SW.east_wall: current_vertex = (current_vertex[0], current_vertex[1] + 1) # Continue South
                else: direction = (1, 0) # Turn East
            elif direction == (-1, 0): # Moving West
                if tile_SW and tile_SW.east_wall: direction = (0, -1) # Turn North
                elif tile_NW and tile_NW.south_wall: current_vertex = (current_vertex[0] - 1, current_vertex[1]) # Continue West
                else: direction = (0, 1) # Turn South
            elif direction == (0, -1): # Moving North
                if tile_NW and tile_NW.south_wall: direction = (1, 0) # Turn East
                elif tile_NE and tile_NE.west_wall: current_vertex = (current_vertex[0], current_vertex[1] - 1) # Continue North
                else: direction = (-1, 0) # Turn West

            if path[-1].x != current_vertex[0] or path[-1].y != current_vertex[1]:
                path.append(schema.GridPoint(x=current_vertex[0], y=current_vertex[1]))
            if (current_vertex[0], current_vertex[1]) == (start_pos[0], start_pos[1]):
                break
        return path


class MapAnalyzer:
    """Orchestrates the entire map analysis pipeline for a single region."""

    def __init__(self):
        self.color_analyzer = ColorAnalyzer()
        self.structure_analyzer = StructureAnalyzer()
        self.feature_extractor = FeatureExtractor()
        self.map_transformer = MapTransformer()

    def analyze_region(
        self,
        img: np.ndarray,
        region_context: Dict[str, Any],
        ascii_debug: bool = False,
        save_intermediate_path: Optional[str] = None,
    ) -> schema.Region:
        """Runs the full pipeline on a single cropped image region."""
        log.info("Running analysis pipeline on region: %s", region_context["id"])
        if img is None:
            raise ValueError("Input image to _run_analysis_on_region cannot be None")

        color_profile, kmeans_model = self.color_analyzer.analyze(img)

        context = _RegionAnalysisContext()

        structural_img = self._create_structural_image(img, color_profile, kmeans_model)
        floor_only_img = self._create_floor_only_image(img, color_profile, kmeans_model)

        context.room_bounds = self._find_room_bounds(self._create_stroke_only_image(img, color_profile, kmeans_model))
        grid_info = self.structure_analyzer.discover_grid(structural_img, color_profile, context.room_bounds)

        corrected_floor = floor_only_img.copy()
        temp_layers = self.feature_extractor.extract(img, [], grid_info.size, color_profile, kmeans_model)
        if temp_layers.get("layers"):
            log.info("Correcting floor plan with %d env layers.", len(temp_layers["layers"]))
            for layer in temp_layers["layers"]:
                px_verts = (np.array(layer["high_res_vertices"]) * grid_info.size / 8.0).astype(np.int32)
                cv2.fillPoly(corrected_floor, [px_verts], 255)

        if save_intermediate_path:
            cv2.imwrite(os.path.join(save_intermediate_path, f"{region_context['id']}_corrected_floor.png"), corrected_floor)

        room_contours = self._get_floor_plan_contours(corrected_floor, grid_info.size)

        context.enhancement_layers = self.feature_extractor.extract(img, room_contours, grid_info.size, color_profile, kmeans_model)

        context.tile_grid = self.structure_analyzer.classify_features(
            img, structural_img, room_contours, grid_info, color_profile, kmeans_model,
            save_intermediate_path=save_intermediate_path, region_id=region_context["id"]
        )

        if ascii_debug and context.tile_grid:
            log.info("--- ASCII Debug Output (Pre-Transformation) ---")
            renderer = rendering.ASCIIRenderer()
            renderer.render_from_tiles(context.tile_grid)
            log.info("\n%s", renderer.get_output(), extra={"raw": True})
            log.info("--- End ASCII Debug Output ---")

        all_objects = self.map_transformer.transform(context, grid_info.size)
        return schema.Region(
            id=region_context["id"],
            label=region_context.get("label", region_context["id"]),
            gridSizePx=grid_info.size,
            bounds=[],
            mapObjects=all_objects,
        )

    def _create_stroke_only_image(
        self, img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
    ) -> np.ndarray:
        """Creates a stroke-only image (black on white) for contour detection."""
        log.info("Executing Stage 3: Creating Stroke-Only Image...")
        stroke_roles = {r for r in color_profile["roles"].values() if r.endswith("stroke")}
        rgb_to_label = {tuple(c.astype("uint8")[::-1]): i for i,c in enumerate(kmeans.cluster_centers_)}
        stroke_labels = {rgb_to_label[rgb] for rgb, role in color_profile["roles"].items() if role in stroke_roles}

        all_labels = kmeans.labels_.reshape(img.shape[:2])
        stroke_mask = np.isin(all_labels, list(stroke_labels))

        canvas = np.full_like(img, 255, dtype=np.uint8)
        canvas[stroke_mask] = (0, 0, 0)
        return canvas

    def _create_structural_image(
        self, img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
    ) -> np.ndarray:
        """Creates a clean two-color image (stroke on floor) for analysis."""
        log.info("Executing Stage 3b: Creating Structural Analysis Image...")
        stroke_roles = {r for r in color_profile["roles"].values() if r.endswith("stroke")}
        rgb_to_label = {tuple(c.astype("uint8")[::-1]): i for i,c in enumerate(kmeans.cluster_centers_)}
        stroke_labels = {rgb_to_label[rgb] for rgb, role in color_profile["roles"].items() if role in stroke_roles}

        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        floor_rgb = roles_inv.get("floor", (255, 255, 255))
        stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
        floor_bgr = np.array(floor_rgb[::-1], dtype="uint8")
        stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")

        all_labels = kmeans.labels_.reshape(img.shape[:2])
        stroke_mask = np.isin(all_labels, list(stroke_labels))

        filtered_image = np.full_like(img, floor_bgr)
        filtered_image[stroke_mask] = stroke_bgr

        log.debug("Created structural image with all 'stroke' and 'floor' colors.")
        return filtered_image

    def _create_floor_only_image(
        self, img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
    ) -> np.ndarray:
        """Creates a binary mask of all floor pixels for accurate contouring."""
        log.info("Executing Stage 3c: Creating Floor-Only Image...")
        floor_roles = {r for r in color_profile["roles"].values() if "floor" in r or "water" in r}
        rgb_to_label = {tuple(c.astype("uint8")[::-1]): i for i,c in enumerate(kmeans.cluster_centers_)}
        floor_labels = {rgb_to_label[rgb] for rgb, role in color_profile["roles"].items() if role in floor_roles}

        all_labels = kmeans.labels_.reshape(img.shape[:2])
        floor_mask = np.isin(all_labels, list(floor_labels))

        canvas = np.zeros(img.shape[:2], dtype=np.uint8)
        canvas[floor_mask] = 255
        return canvas

    def _find_room_bounds(
        self,
        stroke_only_image: np.ndarray,
    ) -> List[Tuple[int, int, int, int]]:
        """Finds bounding boxes of all major shapes in the stroke-only image."""
        log.info("Executing Stage 3a: Finding Room Boundary Boxes from Strokes...")
        gray = cv2.cvtColor(stroke_only_image, cv2.COLOR_BGR2GRAY)
        _, binary_mask = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)

        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        bounds = []
        min_area = 1000
        for contour in contours:
            if cv2.contourArea(contour) > min_area:
                bounds.append(cv2.boundingRect(contour))
        log.info("Found %d potential room boundary boxes.", len(bounds))
        return bounds

    def _get_floor_plan_contours(
        self, floor_only_image: np.ndarray, grid_size: int
    ) -> List[np.ndarray]:
        """Helper to get clean room contours from the floor-only binary image."""
        log.debug("Extracting floor plan contours from floor-only image.")
        contours, _ = cv2.findContours(floor_only_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return [c for c in contours if cv2.contourArea(c) > (grid_size * grid_size)]


# The internal, pre-transformation data model for a single grid cell.
@dataclass
class _TileData:
    feature_type: str  # e.g., 'floor', 'empty'
    north_wall: Optional[str] = None
    east_wall: Optional[str] = None
    south_wall: Optional[str] = None
    west_wall: Optional[str] = None


@dataclass
class _GridInfo:
    """Internal data object for grid parameters."""
    size: int
    offset_x: int
    offset_y: int


@dataclass
class _RegionAnalysisContext:
    """Internal data carrier for a single region's analysis pipeline."""
    tile_grid: Dict[Tuple[int, int], _TileData] = field(default_factory=dict)
    enhancement_layers: Dict[str, Any] = field(default_factory=dict)
    room_bounds: List[Tuple[int, int, int, int]] = field(default_factory=list)


# Initialize the OCR reader once. This can take a moment on first run.
log_ocr.info("Initializing EasyOCR reader...")
OCR_READER = easyocr.Reader(["en"], gpu=False)
log_ocr.info("EasyOCR reader initialized.")


def analyze_image(
    image_path: str,
    ascii_debug: bool = False,
    save_intermediate_path: Optional[str] = None,
) -> Tuple[schema.MapData, Optional[List]]:
    """
    Top-level orchestrator for the analysis pipeline. It will load the image,
    find distinct regions, and then run the core analysis on each region.
    """
    def _stage1_detect_regions(img: np.ndarray) -> List[Dict[str, Any]]:
        """Stage 1: Detect distinct, separate content regions in the map image."""
        log.info("Executing Stage 1: Region Detection...")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        region_contexts = []
        min_area = img.shape[0] * img.shape[1] * 0.01
        for i, contour in enumerate(contours):
            if cv2.contourArea(contour) > min_area:
                x, y, w, h = cv2.boundingRect(contour)
                region_contexts.append({"id": f"region_{i}", "contour": contour, "bounds_rect": (x,y,w,h), "bounds_img": img[y:y+h, x:x+w]})
        log.info("Found %d potential content regions.", len(region_contexts))
        return region_contexts

    def _stage2_parse_text_metadata(
        region_contexts: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Stage 2: Classify regions and parse text for metadata."""
        log.info("Executing Stage 2: Text & Metadata Parsing...")
        if not region_contexts: return {}, []

        try:
            main_dungeon_idx = max(range(len(region_contexts)), key=lambda i: cv2.contourArea(region_contexts[i]["contour"]))
        except ValueError:
            return {}, []

        metadata: Dict[str, Any] = {"title": None, "notes": "", "legend": ""}
        text_blobs = []

        for i, context in enumerate(region_contexts):
            if i == main_dungeon_idx:
                context["type"] = "dungeon"
                log.debug("Region '%s' classified as 'dungeon'.", context["id"])
                continue

            context["type"] = "text"
            log.debug("Region '%s' classified as 'text', running OCR.", context["id"])
            ocr_res = OCR_READER.readtext(context["bounds_img"], detail=1, paragraph=False)
            for bbox, text, prob in ocr_res:
                h = bbox[2][1] - bbox[0][1]
                text_blobs.append({"text": text, "height": h})

        if text_blobs:
            title_idx = max(range(len(text_blobs)), key=lambda i: text_blobs[i]["height"])
            metadata["title"] = text_blobs.pop(title_idx)["text"]
            metadata["notes"] = " ".join([b["text"] for b in text_blobs])

        log_ocr.info("Extracted metadata: Title='%s'", metadata["title"])
        return metadata, region_contexts

    log.info("Starting analysis of image: '%s'", image_path)
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image at {image_path}")

    source_filename = os.path.basename(image_path)
    all_region_contexts = _stage1_detect_regions(img)
    metadata, all_region_contexts = _stage2_parse_text_metadata(all_region_contexts)

    dungeon_regions = [rc for rc in all_region_contexts if rc.get("type") == "dungeon"]
    if not dungeon_regions:
        log.warning("No dungeon regions found in the image.")
        meta = schema.Meta(title=source_filename, sourceImage=source_filename)
        return schema.MapData(dmapVersion="2.0.0", meta=meta, regions=[]), None

    log.info("Orchestrator found %d dungeon regions. Processing all.", len(dungeon_regions))
    final_regions = []
    analyzer = MapAnalyzer()
    for i, region_context in enumerate(dungeon_regions):
        region_img = region_context["bounds_img"]
        region_context["label"] = f"Dungeon Area {i+1}"
        processed_region = analyzer.analyze_region(
            region_img,
            region_context,
            ascii_debug=ascii_debug,
            save_intermediate_path=save_intermediate_path,
        )
        final_regions.append(processed_region)

    title = metadata.get("title") or os.path.splitext(source_filename)[0]
    meta_obj = schema.Meta(title=title, sourceImage=source_filename, notes=metadata.get("notes"), legend=metadata.get("legend"))
    map_data = schema.MapData(dmapVersion="2.0.0", meta=meta_obj, regions=final_regions)

    return map_data, None
