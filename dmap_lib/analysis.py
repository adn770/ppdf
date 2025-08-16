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


# The internal, pre-transformation data model for a single grid cell.
@dataclass
class _TileData:
    feature_type: str  # e.g., 'floor', 'empty'
    north_wall: Optional[str] = None  # e.g., 'stone', 'door', 'window', 'secret_door', 'iron_bar_door'
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


def _stage2_analyze_region_colors(
    img: np.ndarray, num_colors: int = 8
) -> Tuple[Dict[str, Any], KMeans]:
    """
    Stage 2: Quantize region colors and assign semantic roles using a multi-pass
    contextual analysis pipeline.
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
        potential_color = tuple(kmeans.cluster_centers_[label].astype("uint8")[::-1])
        if potential_color in unassigned_colors:
            floor_color = potential_color
            break
    if floor_color:
        roles[floor_color] = "floor"
        unassigned_colors.remove(floor_color)

    # --- Pass 2: Stroke Identification via Edge Sampling ---
    stroke_rgb = None
    if floor_color:
        floor_bgr = np.array(floor_color[::-1], dtype="uint8")
        floor_mask = cv2.inRange(img, floor_bgr, floor_bgr)
        contours, _ = cv2.findContours(floor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        edge_pixels = []
        for contour in contours:
            for point in contour:
                edge_pixels.append(img[point[0][1], point[0][0]])

        if edge_pixels:
            edge_labels = kmeans.predict(edge_pixels)
            valid_labels = [l for l in edge_labels if tuple(kmeans.cluster_centers_[l].astype("uint8")[::-1]) in unassigned_colors]
            if valid_labels:
                stroke_label = Counter(valid_labels).most_common(1)[0][0]
                stroke_rgb = tuple(kmeans.cluster_centers_[stroke_label].astype("uint8")[::-1])
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
    dilated_mask = cv2.dilate(stroke_mask, np.ones((3, 3), np.uint8), iterations=2)
    search_mask = dilated_mask - stroke_mask
    adjacent_labels = all_labels[search_mask == 1]
    valid_adjacent_labels = [l for l in adjacent_labels if tuple(kmeans.cluster_centers_[l].astype("uint8")[::-1]) in unassigned_colors]
    if len(valid_adjacent_labels) > 1:
        top_two_labels = [item[0] for item in Counter(valid_adjacent_labels).most_common(2)]
        color1 = tuple(kmeans.cluster_centers_[top_two_labels[0]].astype("uint8")[::-1])
        color2 = tuple(kmeans.cluster_centers_[top_two_labels[1]].astype("uint8")[::-1])
        if sum(color1) > sum(color2):
            glow_rgb, shadow_rgb = color1, color2
        else:
            glow_rgb, shadow_rgb = color2, color1
        roles[glow_rgb] = "glow"
        unassigned_colors.remove(glow_rgb)
        roles[shadow_rgb] = "shadow"
        unassigned_colors.remove(shadow_rgb)

    # --- Pass 4: Environmental Layer Identification (Water) ---
    if unassigned_colors:
        candidate_areas = []
        rgb_to_label = {tuple(c[::-1]): i for i, c in enumerate(palette_bgr)}
        for color in unassigned_colors:
            label = rgb_to_label[color]
            mask = (all_labels == label).astype(np.uint8) * 255
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            total_area = sum(cv2.contourArea(c) for c in contours)
            candidate_areas.append((total_area, color))
        if candidate_areas:
            # Assume the largest unassigned patch is water
            best_candidate = max(candidate_areas, key=lambda item: item[0])
            if best_candidate[0] > 500: # Threshold for minimum area
                water_color = best_candidate[1]
                roles[water_color] = "water"
                unassigned_colors.remove(water_color)
                log.debug("Identified water color: %s", str(water_color))

    # --- Pass 5: Final Alias Classification ---
    primary_roles = list(roles.items())
    if primary_roles:
        for alias_color in unassigned_colors:
            closest_primary = min(primary_roles, key=lambda item: np.linalg.norm(np.array(alias_color) - np.array(item[0])))
            roles[alias_color] = f"alias_{closest_primary[1]}"

    log.debug("--- Advanced Color Profile ---")
    for color, role in roles.items():
        log.debug("RGB: %-15s -> Role: %s", str(color), role)

    return color_profile, kmeans


def _stage1_detect_regions(img: np.ndarray) -> List[Dict[str, Any]]:
    """
    Stage 1: Detect distinct, separate content regions in the map image.
    """
    log.info("Executing Stage 1: Region Detection...")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    region_contexts = []
    min_area = img.shape[0] * img.shape[1] * 0.01
    for i, contour in enumerate(contours):
        if cv2.contourArea(contour) > min_area:
            x, y, w, h = cv2.boundingRect(contour)
            region_contexts.append(
                {
                    "id": f"region_{i}",
                    "contour": contour,
                    "bounds_rect": (x, y, w, h),
                    "bounds_img": img[y : y + h, x : x + w],
                }
            )
    log.info("Found %d potential content regions.", len(region_contexts))
    return region_contexts


def _stage2_parse_text_metadata(
    region_contexts: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Stage 2: Classify regions and parse text from non-dungeon areas for metadata.
    """
    log.info("Executing Stage 2: Text & Metadata Parsing...")
    if not region_contexts:
        return {}, []

    # Find the largest region by area to consider it the main dungeon
    try:
        main_dungeon_idx = max(
            range(len(region_contexts)),
            key=lambda i: cv2.contourArea(region_contexts[i]["contour"]),
        )
    except ValueError:
        return {}, []

    metadata = {"title": None, "notes": "", "legend": ""}
    text_blobs = []

    for i, context in enumerate(region_contexts):
        if i == main_dungeon_idx:
            context["type"] = "dungeon"
            log.debug("Region '%s' classified as 'dungeon'.", context["id"])
            continue

        context["type"] = "text"
        log.debug("Region '%s' classified as 'text', running OCR.", context["id"])
        ocr_results = OCR_READER.readtext(context["bounds_img"], detail=1, paragraph=False)
        for bbox, text, prob in ocr_results:
            h = bbox[2][1] - bbox[0][1]
            text_blobs.append({"text": text, "height": h})

    if text_blobs:
        title_blob_idx = max(range(len(text_blobs)), key=lambda i: text_blobs[i]["height"])
        metadata["title"] = text_blobs.pop(title_blob_idx)["text"]
        metadata["notes"] = " ".join([b["text"] for b in text_blobs])

    log_ocr.info("Extracted metadata: Title='%s'", metadata["title"])
    return metadata, region_contexts


def _stage3_create_stroke_only_image(
    img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
) -> np.ndarray:
    """
    Stage 3: Creates a stroke-only image (black on white) for contour detection.
    """
    log.info("Executing Stage 3: Creating Stroke-Only Image...")
    # Get all labels for colors that are 'stroke' or 'alias_stroke'
    stroke_roles = {role for role in color_profile["roles"].values() if role.endswith("stroke")}
    rgb_to_label = {
        tuple(c.astype("uint8")[::-1]): i
        for i, c in enumerate(kmeans.cluster_centers_)
    }
    stroke_labels = {
        rgb_to_label[rgb]
        for rgb, role in color_profile["roles"].items()
        if role in stroke_roles
    }

    # Create a mask where pixel labels match any stroke label
    all_labels = kmeans.labels_.reshape(img.shape[:2])
    stroke_mask = np.isin(all_labels, list(stroke_labels))

    # Create a white canvas and draw only the stroke pixels in black
    canvas = np.full_like(img, 255, dtype=np.uint8)
    canvas[stroke_mask] = (0, 0, 0)
    return canvas


def _stage3b_create_structural_image(
    img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
) -> np.ndarray:
    """
    Stage 3b: Creates a clean two-color image (stroke on floor) for analysis.
    """
    log.info("Executing Stage 3b: Creating Structural Analysis Image...")

    # Get all stroke labels (primary and alias)
    stroke_roles = {role for role in color_profile["roles"].values() if role.endswith("stroke")}
    rgb_to_label = {
        tuple(c.astype("uint8")[::-1]): i
        for i, c in enumerate(kmeans.cluster_centers_)
    }
    stroke_labels = {
        rgb_to_label[rgb]
        for rgb, role in color_profile["roles"].items()
        if role in stroke_roles
    }

    # Get floor color
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


def _stage3c_create_floor_only_image(
    img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
) -> np.ndarray:
    """
    Stage 3c: Creates a binary mask of all floor pixels for accurate contouring.
    """
    log.info("Executing Stage 3c: Creating Floor-Only Image...")
    floor_roles = {role for role in color_profile["roles"].values() if "floor" in role or "water" in role}
    rgb_to_label = {
        tuple(c.astype("uint8")[::-1]): i
        for i, c in enumerate(kmeans.cluster_centers_)
    }
    floor_labels = {
        rgb_to_label[rgb]
        for rgb, role in color_profile["roles"].items()
        if role in floor_roles
    }

    all_labels = kmeans.labels_.reshape(img.shape[:2])
    floor_mask = np.isin(all_labels, list(floor_labels))

    canvas = np.zeros(img.shape[:2], dtype=np.uint8)
    canvas[floor_mask] = 255
    return canvas


def _stage3a_find_room_bounds(
    stroke_only_image: np.ndarray,
) -> List[Tuple[int, int, int, int]]:
    """
    Stage 3a: Finds bounding boxes of all major shapes in the stroke-only image.
    """
    log.info("Executing Stage 3a: Finding Room Boundary Boxes from Strokes...")
    gray = cv2.cvtColor(stroke_only_image, cv2.COLOR_BGR2GRAY)
    _, binary_mask = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(
        binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    bounds = []
    # Filter out contours that are too small to be rooms (e.g., noise)
    min_area = 1000
    for contour in contours:
        if cv2.contourArea(contour) > min_area:
            bounds.append(cv2.boundingRect(contour))

    log.info("Found %d potential room boundary boxes.", len(bounds))
    return bounds


def _stage4_discover_grid(
    structural_img: np.ndarray,
    color_profile: dict,
    room_bounds: List[Tuple[int, int, int, int]],
) -> _GridInfo:
    """
    Stage 4: Discovers grid size via peak-finding and offset via room bounds.
    """
    log_grid.info("Executing Stage 4: Grid Discovery...")
    roles_inv = {v: k for k, v in color_profile["roles"].items()}
    stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
    stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")
    binary_mask = cv2.inRange(structural_img, stroke_bgr, stroke_bgr)

    proj_x = np.sum(binary_mask, axis=0).astype(float)
    proj_y = np.sum(binary_mask, axis=1).astype(float)

    # --- Step 1: Calculate Grid Size using peak finding (retained logic) ---
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

    # --- Step 2: Calculate Grid Offset using room bounds (new logic) ---
    if not room_bounds:
        log_grid.warning("No room bounds found; cannot calculate offset. Defaulting to (0,0).")
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


def _stage5_detect_enhancement_features(
    original_region_img: np.ndarray,
    room_contours: List[np.ndarray],
    grid_size: int,
    color_profile: Dict[str, Any],
    kmeans: KMeans,
) -> Dict[str, Any]:
    """
    Stage 5: Detects non-grid-aligned features from the original image.
    """
    log.info("Executing Stage 5: High-Resolution Feature & Layer Detection...")
    enhancements: Dict[str, List] = {"features": [], "layers": []}
    roles_inv = {v: k for k, v in color_profile["roles"].items()}
    labels = kmeans.predict(original_region_img.reshape(-1, 3))

    # --- 1. Detect Water Layers ---
    if "water" in roles_inv:
        water_rgb = roles_inv["water"]
        water_bgr = np.array(water_rgb[::-1], dtype="uint8")
        water_center = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - water_bgr))
        water_label = kmeans.predict([water_center])[0]
        water_mask = (labels == water_label).reshape(original_region_img.shape[:2])
        water_mask_u8 = water_mask.astype("uint8") * 255
        contours, _ = cv2.findContours(water_mask_u8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            if cv2.contourArea(contour) > grid_size * grid_size:
                high_res_verts = [ (v[0][0] / grid_size * 8.0, v[0][1] / grid_size * 8.0) for v in contour ]
                enhancements["layers"].append( { "layerType": "water", "high_res_vertices": high_res_verts, "properties": {"z-order": 0}, } )

    # --- 2. Detect Column Features ---
    if room_contours:
        stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
        stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")
        stroke_center = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - stroke_bgr))
        stroke_label = kmeans.predict([stroke_center])[0]
        stroke_mask = (labels == stroke_label).reshape(original_region_img.shape[:2])
        stroke_mask_u8 = stroke_mask.astype("uint8") * 255
        contours, _ = cv2.findContours( stroke_mask_u8, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE )
        for contour in contours:
            area = cv2.contourArea(contour)
            if not (20 < area < (grid_size * grid_size * 2)):
                continue
            M = cv2.moments(contour)
            if M["m00"] == 0:
                continue
            cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
            if any(cv2.pointPolygonTest(rc, (cx, cy), False) >= 0 for rc in room_contours):
                high_res_verts = [ (v[0][0] / grid_size * 8.0, v[0][1] / grid_size * 8.0) for v in contour ]
                enhancements["features"].append( { "featureType": "column", "high_res_vertices": high_res_verts, "properties": {"z-order": 1}, } )

    log.info( "Detected %d features and %d environmental layers.", len(enhancements["features"]), len(enhancements["layers"]) )
    return enhancements


def _get_floor_plan_contours(
    floor_only_image: np.ndarray, grid_size: int
) -> List[np.ndarray]:
    """
    Helper to get clean room contours from the floor-only binary image.
    """
    log.debug("Extracting floor plan contours from floor-only image.")
    contours, _ = cv2.findContours(
        floor_only_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    return [c for c in contours if cv2.contourArea(c) > (grid_size * grid_size)]


def _classify_boundary(
    boundary_slice: np.ndarray,
    stroke_bgr: np.ndarray,
    is_vertical: bool,
    stroke_score: float,
    threshold: float,
) -> Optional[str]:
    """
    Analyzes a boundary's pixel projection to classify it as a wall or a door type.
    """
    if boundary_slice.size == 0:
        return None

    # --- 1. Check for door patterns using pixel projections ---
    binary_mask = np.all(boundary_slice == stroke_bgr, axis=2).astype(np.uint8)
    projection_axis = 1 if is_vertical else 0
    projection = np.sum(binary_mask, axis=projection_axis)
    segment_len = len(projection)

    # Heuristic for iron bar doors (3 distinct peaks)
    peaks, _ = find_peaks(projection, prominence=1)
    if len(peaks) == 3:
        return "iron_bar_door"

    # Heuristic for secret doors (2 peaks, far apart, deep trough)
    if len(peaks) == 2:
        peak_dist = abs(peaks[0] - peaks[1])
        trough_idx = np.argmin(projection[peaks[0] : peaks[1]]) + peaks[0]
        # Peaks are far apart and the middle is empty
        if peak_dist > segment_len * 0.75 and projection[trough_idx] <= 1:
            return "secret_door"

    # Heuristic for normal doors (U-shape: strong frames, empty middle)
    if segment_len >= 10:
        third = segment_len // 3
        left_frame = np.sum(projection[0:third])
        right_frame = np.sum(projection[segment_len - third : segment_len])
        opening = np.sum(projection[third : segment_len - third])
        if left_frame > 5 and right_frame > 5 and opening < 2:
            return "door"

    # --- 2. Fallback to solid wall check ---
    if stroke_score > threshold:
        return "stone"

    return None


def _calculate_boundary_scores(
    p1: Tuple[int, int],
    p2: Tuple[int, int],
    exterior_offset: Tuple[int, int],
    structural_img: np.ndarray,
    stroke_bgr: np.ndarray,
) -> float:
    """
    Calculates the stroke score for a boundary using dual area-based sampling.
    """
    thickness = 4  # Use a 4px thick line for sampling
    p1_arr, p2_arr = np.array(p1), np.array(p2)
    vec = p2_arr - p1_arr
    length = np.linalg.norm(vec)

    # Calculate centered score
    centered_score = 0.0
    if length > 0:
        vec_norm = vec / length
        normal = np.array([-vec_norm[1], vec_norm[0]]) * (thickness / 2)
        rect_points = np.array(
            [p1_arr + normal, p2_arr + normal, p2_arr - normal, p1_arr - normal],
            dtype=np.int32,
        )
        mask = np.zeros(structural_img.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [rect_points], 255)
        pixels_in_area = structural_img[mask == 255]
        if pixels_in_area.size > 0:
            stroke_pixel_count = np.sum(
                np.all(pixels_in_area == stroke_bgr, axis=1)
            )
            centered_score = stroke_pixel_count / (pixels_in_area.shape[0])

    # Calculate exterior score
    exterior_score = 0.0
    if length > 0:
        # Shift the center of the rectangle by a few pixels to the exterior
        shift_vec = np.array(exterior_offset)
        shift_norm = np.linalg.norm(shift_vec)
        if shift_norm > 0:
            shift_vec = (shift_vec / shift_norm) * (thickness / 2)
            p1_ext, p2_ext = p1_arr + shift_vec, p2_arr + shift_vec
            vec_ext = p2_ext - p1_ext
            vec_norm_ext = vec_ext / np.linalg.norm(vec_ext)
            normal_ext = np.array([-vec_norm_ext[1], vec_norm_ext[0]]) * (thickness / 2)
            rect_points_ext = np.array(
                [p1_ext + normal_ext, p2_ext + normal_ext, p2_ext - normal_ext, p1_ext - normal_ext],
                dtype=np.int32,
            )
            mask_ext = np.zeros(structural_img.shape[:2], dtype=np.uint8)
            cv2.fillPoly(mask_ext, [rect_points_ext], 255)
            pixels_in_area_ext = structural_img[mask_ext == 255]
            if pixels_in_area_ext.size > 0:
                stroke_pixel_count_ext = np.sum(
                    np.all(pixels_in_area_ext == stroke_bgr, axis=1)
                )
                exterior_score = stroke_pixel_count_ext / (pixels_in_area_ext.shape[0])

    return max(centered_score, exterior_score)


def _save_wall_detection_debug_image(
    original_region_img: np.ndarray,
    grid_info: _GridInfo,
    tile_grid: Dict[Tuple[int, int], _TileData],
    output_path: str,
):
    """Saves a debug image visualizing the grid and wall scoring sample areas."""
    h, w, _ = original_region_img.shape
    debug_img = original_region_img.copy()

    # Add a dark overlay to make debug lines stand out
    overlay = debug_img.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
    debug_img = cv2.addWeighted(overlay, 0.4, debug_img, 0.6, 0)

    # Draw grid lines
    grid_color = (255, 255, 0)  # Cyan
    for x in range(0, w, grid_info.size):
        px = x + grid_info.offset_x
        cv2.line(debug_img, (px, 0), (px, h), grid_color, 1)
    for y in range(0, h, grid_info.size):
        py = y + grid_info.offset_y
        cv2.line(debug_img, (0, py), (w, py), grid_color, 1)

    stroke_centered_color = (0, 255, 255)  # Yellow
    stroke_exterior_color = (0, 165, 255)  # Orange
    offset = grid_info.size // 4

    for (x, y), tile in tile_grid.items():
        if tile.feature_type == "empty":
            continue

        p_nw = (x * grid_info.size + grid_info.offset_x, y * grid_info.size + grid_info.offset_y)
        p_ne = ((x + 1) * grid_info.size + grid_info.offset_x, y * grid_info.size + grid_info.offset_y)
        p_sw = (x * grid_info.size + grid_info.offset_x, (y + 1) * grid_info.size + grid_info.offset_y)
        p_se = ((x + 1) * grid_info.size + grid_info.offset_x, (y + 1) * grid_info.size + grid_info.offset_y)

        boundaries = []
        if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
            boundaries.append({"p1": p_nw, "p2": p_ne, "off": (0, -offset)})
        if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
            boundaries.append({"p1": p_ne, "p2": p_se, "off": (offset, 0)})
        if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
            boundaries.append({"p1": p_sw, "p2": p_se, "off": (0, offset)})
        if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
            boundaries.append({"p1": p_nw, "p2": p_sw, "off": (-offset, 0)})

        for b in boundaries:
            p1, p2, ex_off = b["p1"], b["p2"], b["off"]

            # Draw the stroke search area outlines
            stroke_thickness = 4
            p1_arr, p2_arr = np.array(p1), np.array(p2)
            s_vec = p2_arr - p1_arr
            s_length = np.linalg.norm(s_vec)
            if s_length > 0:
                s_vec_norm = s_vec / s_length
                s_normal = np.array([-s_vec_norm[1], s_vec_norm[0]]) * (stroke_thickness / 2)
                # Centered rectangle
                s_rect_points = np.array( [p1_arr + s_normal, p2_arr + s_normal, p2_arr - s_normal, p1_arr - s_normal], dtype=np.int32)
                cv2.polylines(debug_img, [s_rect_points], True, stroke_centered_color, 1)

                # Exterior rectangle
                shift_vec = np.array(ex_off)
                shift_norm = np.linalg.norm(shift_vec)
                if shift_norm > 0:
                    shift_vec = (shift_vec / shift_norm) * (stroke_thickness / 2)
                    p1_ext, p2_ext = p1_arr + shift_vec, p2_arr + shift_vec
                    s_rect_points_ext = np.array( [p1_ext + s_normal, p2_ext + s_normal, p2_ext - s_normal, p1_ext - s_normal], dtype=np.int32)
                    cv2.polylines(debug_img, [s_rect_points_ext], True, stroke_exterior_color, 1)

    cv2.imwrite(output_path, debug_img)
    log.info("Saved wall detection debug image to %s", output_path)


def _stage6_classify_features(
    original_region_img: np.ndarray,
    structural_img: np.ndarray,
    room_contours: List[np.ndarray],
    grid_info: _GridInfo,
    color_profile: Dict[str, Any],
    kmeans: KMeans,
    save_intermediate_path: Optional[str] = None,
    region_id: str = "",
) -> Dict[Tuple[int, int], _TileData]:
    """
    Stage 6: Perform score-based wall detection and core structure classification.
    """
    log.info("Executing Stage 6: Core Structure Classification...")
    tile_grid = {}
    if not room_contours:
        return {}

    grid_size = grid_info.size
    offset_x, offset_y = grid_info.offset_x, grid_info.offset_y

    all_points = np.vstack(room_contours)
    min_gx, max_gx = math.floor(np.min(all_points[:, :, 0]) / grid_size), math.ceil(
        np.max(all_points[:, :, 0]) / grid_size
    )
    min_gy, max_gy = math.floor(np.min(all_points[:, :, 1]) / grid_size), math.ceil(
        np.max(all_points[:, :, 1]) / grid_size
    )
    for y in range(min_gy - 1, max_gy + 2):
        for x in range(min_gx - 1, max_gx + 2):
            px_center = (x * grid_size + offset_x + grid_size // 2, y * grid_size + offset_y + grid_size // 2)
            is_inside = any(
                cv2.pointPolygonTest(c, px_center, False) >= 0 for c in room_contours
            )
            feature_type = "floor" if is_inside else "empty"
            tile_grid[(x, y)] = _TileData(feature_type=feature_type)

    roles_inv = {v: k for k, v in color_profile["roles"].items()}
    stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
    stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")
    WALL_CONFIDENCE_THRESHOLD = 0.3
    offset = grid_size // 4

    for (x, y), tile in tile_grid.items():
        if tile.feature_type == "empty":
            continue
        p_nw = (x * grid_size + offset_x, y * grid_size + offset_y)
        p_ne = ((x + 1) * grid_size + offset_x, y * grid_size + offset_y)
        p_sw = (x * grid_size + offset_x, (y + 1) * grid_size + offset_y)
        p_se = ((x + 1) * grid_size + offset_x, (y + 1) * grid_size + offset_y)

        # Check NORTH boundary
        if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
            rect_points = np.array([p_nw, p_ne, (p_ne[0], p_ne[1] + 4), (p_nw[0], p_nw[1] + 4)], dtype=np.int32)
            bx, by, bw, bh = cv2.boundingRect(rect_points)
            boundary_slice = structural_img[by:by+bh, bx:bx+bw] if bh > 0 and bw > 0 else np.array([])
            stroke_score = _calculate_boundary_scores(p_nw, p_ne, (0, -offset), structural_img, stroke_bgr)
            wall_type = _classify_boundary(boundary_slice, stroke_bgr, False, stroke_score, WALL_CONFIDENCE_THRESHOLD)
            if wall_type: tile.north_wall = wall_type

        # Check EAST boundary
        if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
            rect_points = np.array([(p_ne[0] - 4, p_ne[1]), p_ne, p_se, (p_se[0] - 4, p_se[1])], dtype=np.int32)
            bx, by, bw, bh = cv2.boundingRect(rect_points)
            boundary_slice = structural_img[by:by+bh, bx:bx+bw] if bh > 0 and bw > 0 else np.array([])
            stroke_score = _calculate_boundary_scores(p_ne, p_se, (offset, 0), structural_img, stroke_bgr)
            wall_type = _classify_boundary(boundary_slice, stroke_bgr, True, stroke_score, WALL_CONFIDENCE_THRESHOLD)
            if wall_type: tile.east_wall = wall_type

        # Check SOUTH boundary
        if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
            rect_points = np.array([(p_sw[0], p_sw[1] - 4), (p_se[0], p_se[1] - 4), p_se, p_sw], dtype=np.int32)
            bx, by, bw, bh = cv2.boundingRect(rect_points)
            boundary_slice = structural_img[by:by+bh, bx:bx+bw] if bh > 0 and bw > 0 else np.array([])
            stroke_score = _calculate_boundary_scores(p_sw, p_se, (0, offset), structural_img, stroke_bgr)
            wall_type = _classify_boundary(boundary_slice, stroke_bgr, False, stroke_score, WALL_CONFIDENCE_THRESHOLD)
            if wall_type: tile.south_wall = wall_type

        # Check WEST boundary
        if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
            rect_points = np.array([p_nw, (p_nw[0] + 4, p_nw[1]), (p_sw[0] + 4, p_sw[1]), p_sw], dtype=np.int32)
            bx, by, bw, bh = cv2.boundingRect(rect_points)
            boundary_slice = structural_img[by:by+bh, bx:bx+bw] if bh > 0 and bw > 0 else np.array([])
            stroke_score = _calculate_boundary_scores(p_nw, p_sw, (-offset, 0), structural_img, stroke_bgr)
            wall_type = _classify_boundary(boundary_slice, stroke_bgr, True, stroke_score, WALL_CONFIDENCE_THRESHOLD)
            if wall_type: tile.west_wall = wall_type

    shifted_grid = {}
    content_min_gx = min(
        (k[0] for k, v in tile_grid.items() if v.feature_type != "empty"), default=0
    )
    content_min_gy = min(
        (k[1] for k, v in tile_grid.items() if v.feature_type != "empty"), default=0
    )
    for (gx, gy), tile_data in tile_grid.items():
        new_key = (gx - content_min_gx, gy - content_min_gy)
        shifted_grid[new_key] = tile_data

    if save_intermediate_path:
        filename = os.path.join(save_intermediate_path, f"{region_id}_wall_detection.png")
        _save_wall_detection_debug_image(
            original_region_img, grid_info, shifted_grid, output_path=filename
        )

    return shifted_grid


def _find_room_areas(tile_grid):
    """Finds all contiguous areas of floor tiles using BFS."""
    visited, all_areas = set(), []
    for (gx, gy), tile in tile_grid.items():
        if tile.feature_type == "floor" and (gx, gy) not in visited:
            current_area, q, head = set(), [(gx, gy)], 0
            visited.add((gx, gy))
            while head < len(q):
                cx, cy = q[head]
                head += 1
                current_area.add((cx, cy))
                for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                    nx, ny = cx + dx, cy + dy
                    neighbor = tile_grid.get((nx, ny))
                    if (
                        neighbor
                        and neighbor.feature_type == "floor"
                        and (nx, ny) not in visited
                    ):
                        visited.add((nx, ny))
                        q.append((nx, ny))
            all_areas.append(current_area)
    return all_areas


def _extract_doors_from_grid(tile_grid, coord_to_room_id):
    """Finds all doors on tile edges and links the adjacent rooms."""
    doors = []
    processed_edges = set()
    door_types = ("door", "secret_door", "iron_bar_door")

    for (gx, gy), tile in tile_grid.items():
        # South Wall Check
        if tile.south_wall in door_types:
            edge = tuple(sorted(((gx, gy), (gx, gy + 1))))
            if edge not in processed_edges:
                room1_id = coord_to_room_id.get((gx, gy))
                room2_id = coord_to_room_id.get((gx, gy + 1))
                if room1_id and room2_id and room1_id != room2_id:
                    props = None
                    if tile.south_wall == "secret_door": props = {"secret": True}
                    elif tile.south_wall == "iron_bar_door": props = {"type": "iron_bar"}
                    pos = schema.GridPoint(x=gx, y=gy + 1)
                    doors.append(
                        schema.Door(
                            id=f"door_{uuid.uuid4().hex[:8]}",
                            gridPos=pos,
                            orientation="h",
                            connects=[room1_id, room2_id],
                            properties=props,
                        )
                    )
                    processed_edges.add(edge)

        # East Wall Check
        if tile.east_wall in door_types:
            edge = tuple(sorted(((gx, gy), (gx + 1, gy))))
            if edge not in processed_edges:
                room1_id = coord_to_room_id.get((gx, gy))
                room2_id = coord_to_room_id.get((gx + 1, gy))
                if room1_id and room2_id and room1_id != room2_id:
                    props = None
                    if tile.east_wall == "secret_door": props = {"secret": True}
                    elif tile.east_wall == "iron_bar_door": props = {"type": "iron_bar"}
                    pos = schema.GridPoint(x=gx + 1, y=gy)
                    doors.append(
                        schema.Door(
                            id=f"door_{uuid.uuid4().hex[:8]}",
                            gridPos=pos,
                            orientation="v",
                            connects=[room1_id, room2_id],
                            properties=props,
                        )
                    )
                    processed_edges.add(edge)
    return doors


def _trace_room_perimeter(room_tiles, tile_grid):
    """Traces the perimeter of a room area using a wall-following algorithm."""
    if not room_tiles:
        return []
    start_pos = min(room_tiles, key=lambda p: (p[1], p[0]))

    direction = (1, 0)
    current_vertex = (start_pos[0], start_pos[1])
    path = [schema.GridPoint(x=current_vertex[0], y=current_vertex[1])]

    for _ in range(len(tile_grid) * 4):
        tile_NW = tile_grid.get((current_vertex[0] - 1, current_vertex[1] - 1))
        tile_NE = tile_grid.get((current_vertex[0], current_vertex[1] - 1))
        tile_SW = tile_grid.get((current_vertex[0] - 1, current_vertex[1]))
        tile_SE = tile_grid.get(current_vertex)

        if direction == (1, 0):
            if tile_NE and tile_NE.west_wall:
                direction = (0, 1)
            elif tile_SE and tile_SE.north_wall:
                current_vertex = (current_vertex[0] + 1, current_vertex[1])
            else:
                direction = (0, -1)
        elif direction == (0, 1):
            if tile_SE and tile_SE.north_wall:
                direction = (-1, 0)
            elif tile_SW and tile_SW.east_wall:
                current_vertex = (current_vertex[0], current_vertex[1] + 1)
            else:
                direction = (1, 0)
        elif direction == (-1, 0):
            if tile_SW and tile_SW.east_wall:
                direction = (0, -1)
            elif tile_NW and tile_NW.south_wall:
                current_vertex = (current_vertex[0] - 1, current_vertex[1])
            else:
                direction = (0, 1)
        elif direction == (0, -1):
            if tile_NW and tile_NW.south_wall:
                direction = (1, 0)
            elif tile_NE and tile_NE.west_wall:
                current_vertex = (current_vertex[0], current_vertex[1] - 1)
            else:
                direction = (-1, 0)

        if path[-1].x != current_vertex[0] or path[-1].y != current_vertex[1]:
            path.append(schema.GridPoint(x=current_vertex[0], y=current_vertex[1]))

        if (current_vertex[0], current_vertex[1]) == (start_pos[0], start_pos[1]):
            break

    return path


def _stage7_transform_to_mapdata(
    context: _RegionAnalysisContext, grid_size: int
) -> List[Any]:
    """Stage 7: Transforms the context object into final MapObject entities."""
    log.info("Executing Stage 7: Transforming grid and layers to map data...")
    tile_grid = context.tile_grid
    if not tile_grid:
        return []

    coord_to_room_id, rooms, room_polygons = {}, [], {}
    room_areas = _find_room_areas(tile_grid)
    log_xfm.debug("Step 1: Found %d distinct room areas.", len(room_areas))

    for i, area_tiles in enumerate(room_areas):
        verts = _trace_room_perimeter(area_tiles, tile_grid)

        if len(verts) < 4:
            log_geom.debug("Discarding room %d: degenerate shape (verts < 4).", i)
            continue
        poly = Polygon([(v.x, v.y) for v in verts])
        if poly.area < 1.0:
            log_geom.debug("Discarding room %d: area < 1.0 grid tile.", i)
            continue

        room = schema.Room(
            id=f"room_{uuid.uuid4().hex[:8]}",
            shape="polygon",
            gridVertices=verts,
            roomType="chamber",
            contents=[],
        )
        rooms.append(room)
        room_polygons[room.id] = poly
        for pos in area_tiles:
            coord_to_room_id[pos] = room.id
    log_xfm.debug("Step 2: Created %d valid Room objects from traced areas.", len(rooms))

    doors = _extract_doors_from_grid(tile_grid, coord_to_room_id)
    log_xfm.debug("Step 3: Extracted %d Door objects.", len(doors))

    features, layers = [], []
    room_map = {r.id: r for r in rooms}

    for item in context.enhancement_layers.get("features", []):
        verts = [schema.GridPoint(x=int(v[0] / 8), y=int(v[1] / 8)) for v in item["high_res_vertices"]]
        feature = schema.Feature(
            id=f"feature_{uuid.uuid4().hex[:8]}",
            featureType=item["featureType"],
            shape="polygon",
            gridVertices=verts,
            properties=item["properties"],
        )
        features.append(feature)
        center = Polygon([(v.x, v.y) for v in verts]).centroid
        for room_id, poly in room_polygons.items():
            if poly.contains(center):
                if room_map[room_id].contents is not None:
                    room_map[room_id].contents.append(feature.id)
                break

    for item in context.enhancement_layers.get("layers", []):
        verts = [schema.GridPoint(x=int(v[0] / 8), y=int(v[1] / 8)) for v in item["high_res_vertices"]]
        layer = schema.EnvironmentalLayer(
            id=f"layer_{uuid.uuid4().hex[:8]}",
            layerType=item["layerType"],
            gridVertices=verts,
            properties=item["properties"],
        )
        layers.append(layer)
        center = Polygon([(v.x, v.y) for v in verts]).centroid
        for room_id, poly in room_polygons.items():
            if poly.contains(center):
                if room_map[room_id].contents is not None:
                    room_map[room_id].contents.append(layer.id)
                break
    log_xfm.debug(
        "Step 4: Created %d features and %d layers from enhancements.",
        len(features),
        len(layers),
    )

    all_objects = rooms + doors + features + layers
    log.info("Transformation complete. Found %d total map objects.", len(all_objects))
    return all_objects


def _run_analysis_on_region(
    img: np.ndarray,
    region_context: Dict[str, Any],
    ascii_debug: bool = False,
    save_intermediate_path: Optional[str] = None,
) -> schema.Region:
    """
    (Internal) Analyzes a single, pre-cropped map image region and returns a
    list of schema.Region objects found within it.
    """
    log.info("Running analysis pipeline on region: %s", region_context["id"])
    if img is None:
        raise ValueError("Input image to _run_analysis_on_region cannot be None")

    color_profile, kmeans_model = _stage2_analyze_region_colors(img)

    context = _RegionAnalysisContext()

    # Stage 3: Create filtered images for different purposes
    stroke_only_img = _stage3_create_stroke_only_image(img, color_profile, kmeans_model)
    structural_img = _stage3b_create_structural_image(
        img, color_profile, kmeans_model
    )
    floor_only_img = _stage3c_create_floor_only_image(
        img, color_profile, kmeans_model
    )

    # Stage 3a & 4: Use the stroke-only image to get accurate grid alignment
    context.room_bounds = _stage3a_find_room_bounds(stroke_only_img)
    grid_info = _stage4_discover_grid(
        structural_img, color_profile, context.room_bounds
    )

    # Correct the floor plan using detected layers
    corrected_floor_image = floor_only_img.copy()
    temp_layers = _stage5_detect_enhancement_features(img, [], grid_info.size, color_profile, kmeans_model)
    if temp_layers.get("layers"):
        log.info("Correcting floor plan with %d environmental layers.", len(temp_layers["layers"]))
        for layer in temp_layers["layers"]:
            pixel_verts = (np.array(layer["high_res_vertices"]) * grid_info.size / 8.0).astype(np.int32)
            cv2.fillPoly(corrected_floor_image, [pixel_verts], 255)

    if save_intermediate_path:
        cv2.imwrite(os.path.join(save_intermediate_path, f"{region_context['id']}_stroke_only.png"), stroke_only_img)
        cv2.imwrite(os.path.join(save_intermediate_path, f"{region_context['id']}_floor_only.png"), floor_only_img)
        cv2.imwrite(os.path.join(save_intermediate_path, f"{region_context['id']}_corrected_floor.png"), corrected_floor_image)
        cv2.imwrite(os.path.join(save_intermediate_path, f"{region_context['id']}_structural.png"), structural_img)
        log.info("Saved all intermediate images.")


    room_contours = _get_floor_plan_contours(corrected_floor_image, grid_info.size)

    # Stage 5: Detect all enhancement features with final room contours
    context.enhancement_layers = _stage5_detect_enhancement_features(
        img, room_contours, grid_info.size, color_profile, kmeans_model
    )


    context.tile_grid = _stage6_classify_features(
        img,
        structural_img,
        room_contours,
        grid_info,
        color_profile,
        kmeans_model,
        save_intermediate_path=save_intermediate_path,
        region_id=region_context["id"],
    )

    if ascii_debug and context.tile_grid:
        log.info("--- ASCII Debug Output (Pre-Transformation) ---")
        renderer = rendering.ASCIIRenderer()
        renderer.render_from_tiles(context.tile_grid)
        log.info("\n%s", renderer.get_output(), extra={"raw": True})
        log.info("--- End ASCII Debug Output ---")

    all_objects = _stage7_transform_to_mapdata(context, grid_info.size)
    return schema.Region(
        id=region_context["id"],
        label=region_context.get("label", region_context["id"]),
        gridSizePx=grid_info.size,
        bounds=[],
        mapObjects=all_objects,
    )


def analyze_image(
    image_path: str,
    ascii_debug: bool = False,
    save_intermediate_path: Optional[str] = None,
) -> Tuple[schema.MapData, Optional[List]]:
    """
    Top-level orchestrator for the analysis pipeline. It will load the image,
    find distinct regions, and then run the core analysis on each region.
    """
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

    log.info(
        "Orchestrator found %d dungeon regions. Processing all.", len(dungeon_regions)
    )
    final_regions = []
    for i, region_context in enumerate(dungeon_regions):
        region_img = region_context["bounds_img"]
        # Give the region a simple label for now.
        region_context["label"] = f"Dungeon Area {i+1}"
        processed_region = _run_analysis_on_region(
            region_img,
            region_context,
            ascii_debug=ascii_debug,
            save_intermediate_path=save_intermediate_path,
        )
        final_regions.append(processed_region)

    title = metadata.get("title") or os.path.splitext(source_filename)[0]
    meta_obj = schema.Meta(
        title=title,
        sourceImage=source_filename,
        notes=metadata.get("notes"),
        legend=metadata.get("legend"),
    )
    map_data = schema.MapData(dmapVersion="2.0.0", meta=meta_obj, regions=final_regions)

    return map_data, None
