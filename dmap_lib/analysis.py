# --- dmap_lib/analysis.py ---
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

from dmap_lib import schema, rendering

log = logging.getLogger("dmap.analysis")
log_ocr = logging.getLogger("dmap.ocr")
log_geom = logging.getLogger("dmap.geometry")
log_xfm = logging.getLogger("dmap.transform")


# The internal, pre-transformation data model for a single grid cell.
@dataclass
class _TileData:
    feature_type: str  # e.g., 'floor', 'empty'
    north_wall: Optional[str] = None  # e.g., 'stone', 'door', 'window'
    east_wall: Optional[str] = None
    south_wall: Optional[str] = None
    west_wall: Optional[str] = None


@dataclass
class _RegionAnalysisContext:
    """Internal data carrier for a single region's analysis pipeline."""

    tile_grid: Dict[Tuple[int, int], _TileData] = field(default_factory=dict)
    enhancement_layers: Dict[str, Any] = field(default_factory=dict)


# Initialize the OCR reader once. This can take a moment on first run.
log_ocr.info("Initializing EasyOCR reader...")
OCR_READER = easyocr.Reader(["en"], gpu=False)
log_ocr.info("EasyOCR reader initialized.")


def _stage0_analyze_colors(
    img: np.ndarray, num_colors: int = 8
) -> Tuple[Dict[str, Any], KMeans]:
    """
    Stage 0: Quantize image colors and assign semantic roles using a multi-pass
    contextual analysis pipeline.
    """
    log.info("Executing Stage 0: Multi-Pass Contextual Color Analysis...")
    pixels = img.reshape(-1, 3)
    kmeans = KMeans(n_clusters=num_colors, random_state=42, n_init=10).fit(pixels)
    palette_bgr = kmeans.cluster_centers_.astype("uint8")
    palette_rgb = [tuple(c[::-1]) for c in palette_bgr]

    color_profile = {"palette": palette_rgb, "roles": {}}
    roles = color_profile["roles"]
    unassigned_colors = list(palette_rgb)

    # --- Pass 1: Anchor Color Identification ---
    bg_color_bgr = img[0, 0]
    bg_rgb_color = tuple(bg_color_bgr[::-1])
    bg_palette_color = min(unassigned_colors, key=lambda c: np.linalg.norm(np.array(c) - bg_rgb_color))
    roles[bg_palette_color] = "background"
    unassigned_colors.remove(bg_palette_color)

    h, w, _ = img.shape
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
    all_labels = kmeans.labels_.reshape((h, w))
    stroke_label = kmeans.predict([np.array(stroke_rgb[::-1])])[0]

    stroke_mask = (all_labels == stroke_label).astype(np.uint8)
    dilated_mask = cv2.dilate(stroke_mask, np.ones((3, 3), np.uint8), iterations=2)
    search_mask = dilated_mask - stroke_mask

    adjacent_labels = all_labels[search_mask == 1]
    valid_adjacent_labels = [l for l in adjacent_labels if tuple(kmeans.cluster_centers_[l].astype("uint8")[::-1]) in unassigned_colors]

    if len(valid_adjacent_labels) > 1:
        # Find the two most common adjacent colors
        top_two_labels = [item[0] for item in Counter(valid_adjacent_labels).most_common(2)]
        color1 = tuple(kmeans.cluster_centers_[top_two_labels[0]].astype("uint8")[::-1])
        color2 = tuple(kmeans.cluster_centers_[top_two_labels[1]].astype("uint8")[::-1])

        # The lighter one is glow, the darker is shadow
        if sum(color1) > sum(color2):
            glow_rgb, shadow_rgb = color1, color2
        else:
            glow_rgb, shadow_rgb = color2, color1

        roles[glow_rgb] = "glow"
        unassigned_colors.remove(glow_rgb)
        roles[shadow_rgb] = "shadow"
        unassigned_colors.remove(shadow_rgb)

    # --- Pass 4: Interior Pattern Identification (Water) ---
    if unassigned_colors and floor_color:
        floor_label = kmeans.predict([np.array(floor_color[::-1])])[0]
        floor_pixels_mask = all_labels == floor_label

        # Dilate and then erode the floor mask to get a mask of the interior
        kernel = np.ones((5,5), np.uint8)
        interior_mask = cv2.erode(floor_pixels_mask.astype(np.uint8), kernel, iterations=2)
        interior_labels = all_labels[interior_mask == 1]

        valid_interior_labels = [l for l in interior_labels if tuple(kmeans.cluster_centers_[l].astype("uint8")[::-1]) in unassigned_colors]
        if valid_interior_labels:
            water_label = Counter(valid_interior_labels).most_common(1)[0][0]
            water_rgb = tuple(kmeans.cluster_centers_[water_label].astype("uint8")[::-1])
            roles[water_rgb] = "water_pattern"
            unassigned_colors.remove(water_rgb)

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

    main_dungeon_idx = max(
        range(len(region_contexts)),
        key=lambda i: cv2.contourArea(region_contexts[i]["contour"]),
    )

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


def _stage3_create_filtered_image(
    img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
) -> np.ndarray:
    """
    Stage 3: Creates a clean two-color image using the semantic color profile.
    """
    log.info("Executing Stage 3: Structural Analysis Filtering...")

    roles_inv = {v: k for k, v in color_profile["roles"].items()}
    floor_rgb = roles_inv.get("floor", (255, 255, 255))
    stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
    floor_bgr = np.array(floor_rgb[::-1], dtype="uint8")
    stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")

    stroke_bgr_center = min(
        kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - stroke_bgr)
    )
    stroke_label = kmeans.predict([stroke_bgr_center])[0]

    labels = kmeans.predict(img.reshape(-1, 3)).reshape(img.shape[:2])

    filtered_image = np.full_like(img, floor_bgr)
    stroke_mask = labels == stroke_label
    filtered_image[stroke_mask] = stroke_bgr

    log.debug("Created filtered image with 'stroke' and 'floor' colors.")
    return filtered_image


def _stage4_discover_grid(region_image: np.ndarray) -> int:
    """
    (Placeholder) Stage 4: Discover the grid size within a region.
    """
    log.info("Executing Stage 4: Grid Discovery...")
    default_grid_size = 20
    log.debug("(Stub) Returning default grid size: %dpx", default_grid_size)
    return default_grid_size


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
    if not room_contours:
        return enhancements

    roles_inv = {v: k for k, v in color_profile["roles"].items()}
    labels = kmeans.predict(original_region_img.reshape(-1, 3))

    # --- 1. Detect Column Features from 'stroke' color ---
    stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
    stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")
    stroke_center = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - stroke_bgr))
    stroke_label = kmeans.predict([stroke_center])[0]
    stroke_mask = (labels == stroke_label).reshape(original_region_img.shape[:2])
    stroke_mask_u8 = stroke_mask.astype("uint8") * 255
    contours, _ = cv2.findContours(
        stroke_mask_u8, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    for contour in contours:
        area = cv2.contourArea(contour)
        if not (20 < area < (grid_size * grid_size * 2)):
            continue
        M = cv2.moments(contour)
        if M["m00"] == 0:
            continue
        cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
        if any(cv2.pointPolygonTest(rc, (cx, cy), False) >= 0 for rc in room_contours):
            high_res_verts = [
                (v[0][0] / grid_size * 8.0, v[0][1] / grid_size * 8.0) for v in contour
            ]
            enhancements["features"].append(
                {
                    "featureType": "column",
                    "high_res_vertices": high_res_verts,
                    "properties": {"z-order": 1},
                }
            )

    # --- 2. Detect Water Layers from 'water_pattern' color ---
    if "water_pattern" in roles_inv:
        water_rgb = roles_inv["water_pattern"]
        water_bgr = np.array(water_rgb[::-1], dtype="uint8")
        water_center = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - water_bgr))
        water_label = kmeans.predict([water_center])[0]
        water_mask = (labels == water_label).reshape(original_region_img.shape[:2])
        water_mask_u8 = water_mask.astype("uint8") * 255
        contours, _ = cv2.findContours(
            water_mask_u8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in contours:
            if cv2.contourArea(contour) > grid_size * grid_size:
                high_res_verts = [
                    (v[0][0] / grid_size * 8.0, v[0][1] / grid_size * 8.0) for v in contour
                ]
                enhancements["layers"].append(
                    {
                        "layerType": "water",
                        "high_res_vertices": high_res_verts,
                        "properties": {"z-order": 0},
                    }
                )

    log.info(
        "Detected %d features and %d environmental layers.",
        len(enhancements["features"]),
        len(enhancements["layers"]),
    )
    return enhancements


def _get_floor_plan_contours(
    filtered_img: np.ndarray, grid_size: int, color_profile: Dict[str, Any]
) -> List[np.ndarray]:
    """
    Helper to get clean room contours from the two-color filtered image.
    """
    log.debug("Extracting floor plan contours from filtered image.")
    roles_inv = {v: k for k, v in color_profile["roles"].items()}
    floor_rgb = roles_inv.get("floor", (255, 255, 255))
    floor_bgr = np.array(floor_rgb[::-1], dtype="uint8")

    floor_mask = cv2.inRange(filtered_img, floor_bgr, floor_bgr)
    contours, _ = cv2.findContours(
        floor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    return [c for c in contours if cv2.contourArea(c) > (grid_size * grid_size)]


def _punch_doors_in_tile_grid(
    tile_grid: Dict[Tuple[int, int], _TileData],
    room_contours: List[np.ndarray],
    grid_size: int,
):
    """Detects doors geometrically and updates the wall attributes in the tile_grid."""
    log_geom.info("Detecting doors to punch into tile grid...")
    room_polygons = [Polygon(c.squeeze()) for c in room_contours]
    buffer_dist, max_door_area = grid_size * 0.6, (grid_size * grid_size) * 2.5

    for poly_a, poly_b in itertools.combinations(room_polygons, 2):
        intersection = poly_a.buffer(buffer_dist).intersection(poly_b.buffer(buffer_dist))
        if 0 < intersection.area < max_door_area:
            min_gx, min_gy = math.floor(intersection.bounds[0] / grid_size), math.floor(
                intersection.bounds[1] / grid_size
            )
            max_gx, max_gy = math.ceil(intersection.bounds[2] / grid_size), math.ceil(
                intersection.bounds[3] / grid_size
            )

            for y in range(min_gy, max_gy + 1):
                for x in range(min_gx, max_gx + 1):
                    if tile_grid.get((x, y - 1)) and tile_grid.get((x, y)):
                        if (
                            tile_grid[(x, y - 1)].feature_type == "empty"
                            and tile_grid[(x, y)].feature_type != "empty"
                        ):
                            tile_grid[(x, y)].north_wall = "door"
                            tile_grid[(x, y - 1)].south_wall = "door"
                    if tile_grid.get((x - 1, y)) and tile_grid.get((x, y)):
                        if (
                            tile_grid[(x - 1, y)].feature_type == "empty"
                            and tile_grid[(x, y)].feature_type != "empty"
                        ):
                            tile_grid[(x, y)].west_wall = "door"
                            tile_grid[(x - 1, y)].east_wall = "door"


def _calculate_boundary_scores(
    p1: Tuple[int, int],
    p2: Tuple[int, int],
    exterior_offset: Tuple[int, int],
    original_img: np.ndarray,
    filtered_img: np.ndarray,
    stroke_bgr: np.ndarray,
    shadow_label: int,
    glow_label: int,
    kmeans: KMeans,
) -> Dict[str, float]:
    """
    Calculates scores for stroke, shadow, and glow for a boundary.
    """
    scores = {"stroke": 0.0, "shadow": 0.0, "glow": 0.0}
    num_samples = 10
    h, w, _ = original_img.shape

    # 1. Stroke Thickness Score
    line_points = np.linspace(p1, p2, num_samples).astype(int)
    # Clamp coordinates to be within image bounds
    line_points[:, 0] = np.clip(line_points[:, 0], 0, w - 1)
    line_points[:, 1] = np.clip(line_points[:, 1], 0, h - 1)
    stroke_pixels = sum(
        1
        for p in line_points
        if np.array_equal(filtered_img[p[1], p[0]], stroke_bgr)
    )
    scores["stroke"] = stroke_pixels / num_samples

    # 2. Shadow and Glow Scores
    patch_size = 4

    # Exterior patch for shadow
    ex_center = (int((p1[0] + p2[0]) / 2 + exterior_offset[0]), int((p1[1] + p2[1]) / 2 + exterior_offset[1]))
    ex_x1, ex_y1 = max(0, ex_center[0] - patch_size), max(0, ex_center[1] - patch_size)
    ex_x2, ex_y2 = min(w, ex_center[0] + patch_size), min(h, ex_center[1] + patch_size)

    if ex_x1 < ex_x2 and ex_y1 < ex_y2 and shadow_label != -1:
        patch = original_img[ex_y1:ex_y2, ex_x1:ex_x2]
        labels = kmeans.predict(patch.reshape(-1, 3))
        scores["shadow"] = np.count_nonzero(labels == shadow_label) / len(labels)

    # Interior patch for glow
    in_center = (int((p1[0] + p2[0]) / 2 - exterior_offset[0]), int((p1[1] + p2[1]) / 2 - exterior_offset[1]))
    in_x1, in_y1 = max(0, in_center[0] - patch_size), max(0, in_center[1] - patch_size)
    in_x2, in_y2 = min(w, in_center[0] + patch_size), min(h, in_center[1] + patch_size)

    if in_x1 < in_x2 and in_y1 < in_y2 and glow_label != -1:
        patch = original_img[in_y1:in_y2, in_x1:in_x2]
        labels = kmeans.predict(patch.reshape(-1, 3))
        scores["glow"] = np.count_nonzero(labels == glow_label) / len(labels)

    return scores


def _stage6_classify_features(
    original_region_img: np.ndarray,
    filtered_img: np.ndarray,
    room_contours: List[np.ndarray],
    grid_size: int,
    color_profile: Dict[str, Any],
    kmeans: KMeans,
) -> Dict[Tuple[int, int], _TileData]:
    """
    Stage 6: Perform score-based wall detection and core structure classification.
    """
    log.info("Executing Stage 6: Core Structure Classification...")
    tile_grid = {}
    if not room_contours:
        return {}

    all_points = np.vstack(room_contours)
    min_gx, max_gx = math.floor(np.min(all_points[:, :, 0]) / grid_size), math.ceil(
        np.max(all_points[:, :, 0]) / grid_size
    )
    min_gy, max_gy = math.floor(np.min(all_points[:, :, 1]) / grid_size), math.ceil(
        np.max(all_points[:, :, 1]) / grid_size
    )
    for y in range(min_gy - 1, max_gy + 2):
        for x in range(min_gx - 1, max_gx + 2):
            px_center = (x * grid_size + grid_size // 2, y * grid_size + grid_size // 2)
            is_inside = any(
                cv2.pointPolygonTest(c, px_center, False) >= 0 for c in room_contours
            )
            feature_type = "floor" if is_inside else "empty"
            tile_grid[(x, y)] = _TileData(feature_type=feature_type)

    roles_inv = {v: k for k, v in color_profile["roles"].items()}
    stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
    stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")

    shadow_rgb = roles_inv.get("shadow")
    shadow_label = -1
    if shadow_rgb:
        shadow_bgr = np.array(shadow_rgb[::-1], dtype="uint8")
        shadow_label = kmeans.predict([shadow_bgr])[0]

    glow_rgb = roles_inv.get("glow")
    glow_label = -1
    if glow_rgb:
        glow_bgr = np.array(glow_rgb[::-1], dtype="uint8")
        glow_label = kmeans.predict([glow_bgr])[0]

    WALL_CONFIDENCE_THRESHOLD = 2.5
    offset = grid_size // 4

    for (x, y), tile in tile_grid.items():
        if tile.feature_type == "empty":
            continue
        p_nw = (x * grid_size, y * grid_size)
        p_ne = ((x + 1) * grid_size, y * grid_size)
        p_sw = (x * grid_size, (y + 1) * grid_size)
        p_se = ((x + 1) * grid_size, (y + 1) * grid_size)

        args = {
            "original_img": original_region_img, "filtered_img": filtered_img,
            "stroke_bgr": stroke_bgr, "shadow_label": shadow_label,
            "glow_label": glow_label, "kmeans": kmeans
        }

        if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
            scores = _calculate_boundary_scores(p_nw, p_ne, (0, -offset), **args)
            if (scores["stroke"] * 3.0 + scores["shadow"] * 1.5 + scores["glow"] * 1.0) > WALL_CONFIDENCE_THRESHOLD:
                tile.north_wall = "stone"
        if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
            scores = _calculate_boundary_scores(p_ne, p_se, (offset, 0), **args)
            if (scores["stroke"] * 3.0 + scores["shadow"] * 1.5 + scores["glow"] * 1.0) > WALL_CONFIDENCE_THRESHOLD:
                tile.east_wall = "stone"
        if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
            scores = _calculate_boundary_scores(p_sw, p_se, (0, offset), **args)
            if (scores["stroke"] * 3.0 + scores["shadow"] * 1.5 + scores["glow"] * 1.0) > WALL_CONFIDENCE_THRESHOLD:
                tile.south_wall = "stone"
        if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
            scores = _calculate_boundary_scores(p_nw, p_sw, (-offset, 0), **args)
            if (scores["stroke"] * 3.0 + scores["shadow"] * 1.5 + scores["glow"] * 1.0) > WALL_CONFIDENCE_THRESHOLD:
                tile.west_wall = "stone"

    _punch_doors_in_tile_grid(tile_grid, room_contours, grid_size)
    shifted_grid = {}
    content_min_gx = min(
        (k[0] for k, v in tile_grid.items() if v.feature_type != "empty"), default=0
    )
    content_min_gy = min(
        (k[1] for k, v in tile_grid.items() if v.feature_type != "empty"), default=0
    )
    for (gx, gy), tile_data in tile_grid.items():
        new_key = (gx - content_min_gx + 1, gy - content_min_gy + 1)
        shifted_grid[new_key] = tile_data

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

    for (gx, gy), tile in tile_grid.items():
        if tile.south_wall == "door":
            edge = tuple(sorted(((gx, gy), (gx, gy + 1))))
            if edge not in processed_edges:
                room1_id = coord_to_room_id.get((gx, gy))
                room2_id = coord_to_room_id.get((gx, gy + 1))
                if room1_id and room2_id and room1_id != room2_id:
                    pos = schema.GridPoint(x=gx, y=gy + 1)
                    doors.append(
                        schema.Door(
                            id=f"door_{uuid.uuid4().hex[:8]}",
                            gridPos=pos,
                            orientation="h",
                            connects=[room1_id, room2_id],
                        )
                    )
                    processed_edges.add(edge)

        if tile.east_wall == "door":
            edge = tuple(sorted(((gx, gy), (gx + 1, gy))))
            if edge not in processed_edges:
                room1_id = coord_to_room_id.get((gx, gy))
                room2_id = coord_to_room_id.get((gx + 1, gy))
                if room1_id and room2_id and room1_id != room2_id:
                    pos = schema.GridPoint(x=gx + 1, y=gy)
                    doors.append(
                        schema.Door(
                            id=f"door_{uuid.uuid4().hex[:8]}",
                            gridPos=pos,
                            orientation="v",
                            connects=[room1_id, room2_id],
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


def analyze_image(
    image_path: str, ascii_debug: bool = False
) -> Tuple[schema.MapData, Optional[List]]:
    """
    Loads and analyzes a map image using a multi-stage pipeline to extract
    its structure and features into a MapData object.
    """
    log.info("Starting analysis of image: '%s'", image_path)
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image at {image_path}")

    color_profile, kmeans_model = _stage0_analyze_colors(img)

    all_regions_data = []
    region_contexts = _stage1_detect_regions(img)
    metadata, region_contexts = _stage2_parse_text_metadata(region_contexts)

    dungeon_regions = [rc for rc in region_contexts if rc.get("type") == "dungeon"]

    for i, region_context in enumerate(dungeon_regions):
        context = _RegionAnalysisContext()
        region_img = region_context["bounds_img"]
        region_label = f"Dungeon Area {i+1}" if len(dungeon_regions) > 1 else "Main Dungeon"

        filtered_img = _stage3_create_filtered_image(region_img, color_profile, kmeans_model)
        grid_size = _stage4_discover_grid(filtered_img)
        room_contours = _get_floor_plan_contours(filtered_img, grid_size, color_profile)

        context.enhancement_layers = _stage5_detect_enhancement_features(
            region_img, room_contours, grid_size, color_profile, kmeans_model
        )
        context.tile_grid = _stage6_classify_features(
            region_img, filtered_img, room_contours, grid_size, color_profile, kmeans_model
        )

        if ascii_debug and context.tile_grid:
            log.info("--- ASCII Debug Output (Pre-Transformation) ---")
            renderer = rendering.ASCIIRenderer()
            renderer.render_from_tiles(context.tile_grid)
            log.info("\n%s", renderer.get_output(), extra={"raw": True})
            log.info("--- End ASCII Debug Output ---")

        all_objects = _stage7_transform_to_mapdata(context, grid_size)

        all_regions_data.append(
            {
                "id": region_context["id"],
                "label": region_label,
                "gridSizePx": grid_size,
                "bounds_rect": region_context["bounds_rect"],
                "mapObjects": all_objects,
            }
        )

    title = metadata.get("title") or os.path.splitext(os.path.basename(image_path))[0]
    meta_obj = schema.Meta(
        title=title,
        sourceImage=os.path.basename(image_path),
        notes=metadata.get("notes"),
        legend=metadata.get("legend"),
    )
    regions = [
        schema.Region(
            id=rd["id"],
            label=rd["label"],
            gridSizePx=rd["gridSizePx"],
            bounds=[],
            mapObjects=rd["mapObjects"],
        )
        for rd in all_regions_data
    ]
    map_data = schema.MapData(dmapVersion="2.0.0", meta=meta_obj, regions=regions)

    return map_data, None
