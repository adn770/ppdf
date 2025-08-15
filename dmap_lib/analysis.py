# --- dmap_lib/analysis.py ---
import logging
import os
import uuid
import itertools
import math
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
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
    feature_type: str  # e.g., 'floor', 'column', 'pit', 'empty'
    north_wall: Optional[str] = None  # e.g., 'stone', 'door', 'window'
    east_wall: Optional[str] = None
    south_wall: Optional[str] = None
    west_wall: Optional[str] = None


# Initialize the OCR reader once. This can take a moment on first run.
log_ocr.info("Initializing EasyOCR reader...")
OCR_READER = easyocr.Reader(["en"], gpu=False)
log_ocr.info("EasyOCR reader initialized.")


def _stage0_analyze_colors(
    img: np.ndarray, num_colors: int = 8
) -> Tuple[Dict[str, Any], KMeans]:
    """
    Stage 0: Quantize image colors and assign semantic roles. Returns the color
    profile and the fitted KMeans model for later use.
    """
    log.info("Executing Stage 0: Palette & Semantic Analysis...")
    pixels = img.reshape(-1, 3)
    kmeans = KMeans(n_clusters=num_colors, random_state=42, n_init=10).fit(pixels)
    palette_bgr = kmeans.cluster_centers_.astype("uint8")

    # Sort palette from darkest to lightest for easier processing
    palette_bgr = sorted(palette_bgr, key=lambda c: sum(c))
    palette_rgb = [tuple(c[::-1]) for c in palette_bgr]

    # Heuristics for semantic classification
    color_profile = {"palette": palette_rgb, "roles": {}}
    roles = color_profile["roles"]
    unassigned_colors = list(palette_rgb)

    # 1. Stroke color is the darkest
    roles[unassigned_colors.pop(0)] = "stroke"

    # 2. Background is assumed to be the color of the top-left corner pixel
    bg_color_bgr = img[0, 0]
    bg_palette_color = min(
        unassigned_colors,
        key=lambda c: np.linalg.norm(np.array(c) - np.array(bg_color_bgr)[::-1]),
    )
    roles[bg_palette_color] = "background"
    unassigned_colors.remove(bg_palette_color)

    # 3. Shadow is the darkest remaining color
    if unassigned_colors:
        roles[unassigned_colors.pop(0)] = "shadow"

    # 4. Floor is the most common color in the central 50% of the image that
    # is not already assigned.
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
    else:
        if unassigned_colors:
            log.warning("Could not determine floor color from center; using fallback.")
            floor_color = unassigned_colors.pop(-1)
            roles[floor_color] = "floor"

    log.debug("--- Color Profile ---")
    for color, role in roles.items():
        log.debug("RGB: %-15s -> Role: %s", str(color), role)
    log.debug("Unassigned Palette Colors: %s", unassigned_colors)

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

    # Create a binary mask where the floor color is present
    floor_mask = cv2.inRange(filtered_img, floor_bgr, floor_bgr)

    # Find the external contours of the floor areas
    contours, _ = cv2.findContours(
        floor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # Filter out very small contours that are likely noise
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


def _stage6_classify_features(
    filtered_img: np.ndarray,
    room_contours: List[np.ndarray],
    grid_size: int,
    color_profile: Dict[str, Any],
) -> Dict[Tuple[int, int], _TileData]:
    """
    Stage 6: Perform tile-based classification using the filtered image.
    """
    log.info("Executing Stage 6: Feature & Wall Classification...")
    tile_grid = {}
    if not room_contours:
        return {}

    roles_inv = {v: k for k, v in color_profile["roles"].items()}
    stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
    stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")

    all_points = np.vstack(room_contours)
    min_gx, max_gx = math.floor(np.min(all_points[:, :, 0]) / grid_size), math.ceil(
        np.max(all_points[:, :, 0]) / grid_size
    )
    min_gy, max_gy = math.floor(np.min(all_points[:, :, 1]) / grid_size), math.ceil(
        np.max(all_points[:, :, 1]) / grid_size
    )

    for y in range(min_gy - 1, max_gy + 2):
        for x in range(min_gx - 1, max_gx + 2):
            px_center, py_center = (
                x * grid_size + grid_size // 2,
                y * grid_size + grid_size // 2,
            )
            is_inside = any(
                cv2.pointPolygonTest(c, (px_center, py_center), False) >= 0
                for c in room_contours
            )
            if not is_inside:
                tile_grid[(x, y)] = _TileData(feature_type="empty")
                continue

            # Sample the central pixel of the tile from the filtered image
            tile_color = filtered_img[py_center, px_center]
            is_stroke = np.array_equal(tile_color, stroke_bgr)
            feature_type = "column" if is_stroke else "floor"
            tile_grid[(x, y)] = _TileData(feature_type=feature_type)

    for (x, y), tile in tile_grid.items():
        if tile.feature_type == "empty":
            continue
        if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
            tile.north_wall = "stone"
        if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
            tile.east_wall = "stone"
        if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
            tile.south_wall = "stone"
        if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
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


def _extract_features(tile_grid, rooms, coord_to_room_id):
    """Extracts features (e.g., columns) from the tile grid and links them to rooms."""
    features = []
    room_map = {r.id: r for r in rooms}
    for (gx, gy), tile in tile_grid.items():
        if tile.feature_type == "column":
            feature = schema.Feature(
                id=f"feature_{uuid.uuid4().hex[:8]}",
                featureType="column",
                shape="polygon",
                gridVertices=[
                    schema.GridPoint(x=gx, y=gy),
                    schema.GridPoint(x=gx + 1, y=gy),
                    schema.GridPoint(x=gx + 1, y=gy + 1),
                    schema.GridPoint(x=gx, y=gy + 1),
                ],
            )
            features.append(feature)
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                room_id = coord_to_room_id.get((gx + dx, gy + dy))
                if room_id and room_id in room_map:
                    if room_map[room_id].contents is None:
                        room_map[room_id].contents = []
                    if feature.id not in room_map[room_id].contents:
                        room_map[room_id].contents.append(feature.id)
    return features


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
    tile_grid: Dict[Tuple[int, int], _TileData], grid_size: int
) -> List[Any]:
    """Stage 7: Transforms the detailed tile_grid into final MapObject entities."""
    log.info("Executing Stage 7: Transforming tile grid to map data...")
    if not tile_grid:
        return []

    if log_xfm.isEnabledFor(logging.DEBUG):
        dump_lines = ["--- Pre-Transformation Tile Grid Dump (Content Only) ---"]
        sorted_keys = sorted(tile_grid.keys(), key=lambda k: (k[1], k[0]))
        for key in sorted_keys:
            tile = tile_grid[key]
            if tile.feature_type != "empty":
                dump_lines.append(f"({key[0]: >2},{key[1]: >2}): {tile}")
        log_xfm.debug("\n".join(dump_lines))

    coord_to_room_id, rooms = {}, []

    room_areas = _find_room_areas(tile_grid)
    log_xfm.debug("Step 1: Found %d distinct room areas.", len(room_areas))

    for i, area_tiles in enumerate(room_areas):
        log_geom.debug("Tracing perimeter for room area %d...", i + 1)
        verts = _trace_room_perimeter(area_tiles, tile_grid)
        log_geom.debug("Found %d vertices for room area %d.", len(verts), i + 1)

        room = schema.Room(
            id=f"room_{uuid.uuid4().hex[:8]}",
            shape="polygon",
            gridVertices=verts,
            roomType="chamber",
        )
        rooms.append(room)
        for pos in area_tiles:
            coord_to_room_id[pos] = room.id
    log_xfm.debug("Step 2: Created %d Room objects from traced areas.", len(rooms))

    features = _extract_features(tile_grid, rooms, coord_to_room_id)
    log_xfm.debug("Step 3: Extracted %d Feature objects.", len(features))

    doors = _extract_doors_from_grid(tile_grid, coord_to_room_id)
    log_xfm.debug("Step 4: Extracted %d Door objects.", len(doors))

    log.info(
        "Found %d rooms, %d features, and %d doors.", len(rooms), len(features), len(doors)
    )
    return rooms + features + doors


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
        region_img = region_context["bounds_img"]
        region_label = f"Dungeon Area {i+1}" if len(dungeon_regions) > 1 else "Main Dungeon"

        filtered_img = _stage3_create_filtered_image(region_img, color_profile, kmeans_model)
        grid_size = _stage4_discover_grid(filtered_img)

        room_contours = _get_floor_plan_contours(filtered_img, grid_size, color_profile)
        tile_grid = _stage6_classify_features(
            filtered_img, room_contours, grid_size, color_profile
        )

        if ascii_debug and tile_grid:
            log.info("--- ASCII Debug Output (Pre-Transformation) ---")
            renderer = rendering.ASCIIRenderer()
            renderer.render_from_tiles(tile_grid)
            log.info("\n%s", renderer.get_output(), extra={"raw": True})
            log.info("--- End ASCII Debug Output ---")

        all_objects = _stage7_transform_to_mapdata(tile_grid, grid_size)

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
