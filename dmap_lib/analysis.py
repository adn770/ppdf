import logging
import os
import uuid
import itertools
import math
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

import cv2
import numpy as np
import easyocr
from shapely.geometry import Point, Polygon

from dmap_lib import schema, rendering

log = logging.getLogger("dmap.analysis")
log_ocr = logging.getLogger("dmap.ocr")
log_geom = logging.getLogger("dmap.geometry")

# The internal, pre-transformation data model for a single grid cell.
@dataclass
class _TileData:
    feature_type: str  # e.g., 'floor', 'column', 'pit', 'empty'
    north_wall: Optional[str] = None # e.g., 'stone', 'door', 'window'
    east_wall: Optional[str] = None
    south_wall: Optional[str] = None
    west_wall: Optional[str] = None


# Initialize the OCR reader once. This can take a moment on first run.
log_ocr.info("Initializing EasyOCR reader...")
OCR_READER = easyocr.Reader(['en'], gpu=False)
log_ocr.info("EasyOCR reader initialized.")


def _stage1_detect_regions(img: np.ndarray) -> List[Dict[str, Any]]:
    """
    Stage 1: Detect distinct, separate content regions in the map image.
    """
    log.info("Executing Stage 1: Region Detection...")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Invert threshold: find black shapes on a white background
    _, thresh = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)

    # Find external contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    region_contexts = []
    min_area = img.shape[0] * img.shape[1] * 0.01
    for i, contour in enumerate(contours):
        if cv2.contourArea(contour) > min_area:
            x, y, w, h = cv2.boundingRect(contour)
            region_contexts.append({
                "id": f"region_{i}",
                "contour": contour,
                "bounds_rect": (x, y, w, h),
                "bounds_img": img[y : y + h, x : x + w],
            })
    log.info("Found %d potential content regions.", len(region_contexts))
    return region_contexts


def _stage2_parse_text_metadata(
    region_contexts: List[Dict[str, Any]]
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


def _stage3_discover_grid(region_image: np.ndarray) -> int:
    """
    (Placeholder) Stage 3: Discover the grid size within a region.
    """
    log.info("Executing Stage 3: Grid Discovery...")
    default_grid_size = 20
    log.debug("(Stub) Returning default grid size: %dpx", default_grid_size)
    return default_grid_size


def _get_room_contours(
    region_image: np.ndarray, grid_size: int
) -> List[np.ndarray]:
    """Helper to get clean room contours for internal analysis."""
    gray = cv2.cvtColor(region_image, cv2.COLOR_BGR2GRAY)
    _, processed = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, hierarchy = cv2.findContours(processed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    floor_mask = processed.copy()
    if hierarchy is not None:
        for i, contour in enumerate(contours):
            if hierarchy[0][i][3] != -1 and cv2.contourArea(contour) < 150:
                cv2.drawContours(floor_mask, [contour], -1, 255, cv2.FILLED)
    final_contours, _ = cv2.findContours(floor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return [c for c in final_contours if cv2.contourArea(c) > (grid_size*grid_size)]


def _punch_doors_in_tile_grid(
    tile_grid: Dict[Tuple[int, int], _TileData], room_contours: List[np.ndarray], grid_size: int
):
    """Detects doors geometrically and updates the wall attributes in the tile_grid."""
    log_geom.info("Detecting doors to punch into tile grid...")
    room_polygons = [Polygon(c.squeeze()) for c in room_contours]
    buffer_dist, max_door_area = grid_size * 0.6, (grid_size * grid_size) * 2.5

    for poly_a, poly_b in itertools.combinations(room_polygons, 2):
        intersection = poly_a.buffer(buffer_dist).intersection(poly_b.buffer(buffer_dist))
        if 0 < intersection.area < max_door_area:
            min_gx, min_gy = math.floor(intersection.bounds[0]/grid_size), math.floor(intersection.bounds[1]/grid_size)
            max_gx, max_gy = math.ceil(intersection.bounds[2]/grid_size), math.ceil(intersection.bounds[3]/grid_size)

            for y in range(min_gy, max_gy + 1):
                for x in range(min_gx, max_gx + 1):
                    # Check north/south walls
                    if tile_grid.get((x,y-1)) and tile_grid.get((x,y)):
                        if tile_grid[(x,y-1)].feature_type == 'empty' and tile_grid[(x,y)].feature_type != 'empty':
                            tile_grid[(x,y)].north_wall = 'door'
                            tile_grid[(x,y-1)].south_wall = 'door'
                    # Check west/east walls
                    if tile_grid.get((x-1,y)) and tile_grid.get((x,y)):
                        if tile_grid[(x-1,y)].feature_type == 'empty' and tile_grid[(x,y)].feature_type != 'empty':
                            tile_grid[(x,y)].west_wall = 'door'
                            tile_grid[(x-1,y)].east_wall = 'door'

def _stage6_classify_features(
    region_image: np.ndarray, room_contours: List[np.ndarray], grid_size: int
) -> Dict[Tuple[int, int], _TileData]:
    """
    Stage 6: Perform tile-based classification of features and walls.
    """
    log.info("Executing Stage 6: Feature & Wall Classification...")
    gray = cv2.cvtColor(region_image, cv2.COLOR_BGR2GRAY)
    tile_grid = {}
    if not room_contours: return {}

    all_points = np.vstack(room_contours)
    min_gx, max_gx = math.floor(np.min(all_points[:,:,0])/grid_size), math.ceil(np.max(all_points[:,:,0])/grid_size)
    min_gy, max_gy = math.floor(np.min(all_points[:,:,1])/grid_size), math.ceil(np.max(all_points[:,:,1])/grid_size)

    # Pass 1: Classify the primary feature type of each tile
    for y in range(min_gy - 1, max_gy + 2):
        for x in range(min_gx - 1, max_gx + 2):
            px_center, py_center = x * grid_size + grid_size//2, y * grid_size + grid_size//2
            is_inside = any(cv2.pointPolygonTest(c, (px_center, py_center), False) >= 0 for c in room_contours)
            if not is_inside:
                tile_grid[(x, y)] = _TileData(feature_type='empty')
                continue

            tile_img = gray[py_center-grid_size//4:py_center+grid_size//4, px_center-grid_size//4:px_center+grid_size//4]
            feature_type = 'floor' if np.mean(tile_img) > 150 else 'column'
            tile_grid[(x, y)] = _TileData(feature_type=feature_type)

    # Pass 2: Detect walls based on transitions between floor and empty tiles
    for (x,y), tile in tile_grid.items():
        if tile.feature_type == 'empty': continue
        north_tile = tile_grid.get((x, y - 1))
        if north_tile and north_tile.feature_type == 'empty':
            tile.north_wall = 'stone'
            north_tile.south_wall = 'stone'
        east_tile = tile_grid.get((x + 1, y))
        if east_tile and east_tile.feature_type == 'empty':
            tile.east_wall = 'stone'
            east_tile.west_wall = 'stone'
        south_tile = tile_grid.get((x, y + 1))
        if south_tile and south_tile.feature_type == 'empty':
            tile.south_wall = 'stone'
            south_tile.north_wall = 'stone'
        west_tile = tile_grid.get((x - 1, y))
        if west_tile and west_tile.feature_type == 'empty':
            tile.west_wall = 'stone'
            west_tile.east_wall = 'stone'

    # Pass 3: Punch doors into the walls using geometric analysis
    _punch_doors_in_tile_grid(tile_grid, room_contours, grid_size)

    # Pass 4: Normalize the grid coordinates to be 1-based
    shifted_grid = {}
    for (gx, gy), tile_data in tile_grid.items():
        new_key = (gx - min_gx + 1, gy - min_gy + 1)
        shifted_grid[new_key] = tile_data

    return shifted_grid


def _stage7_transform_to_mapdata(
    tile_grid: Dict[Tuple[int, int], _TileData], grid_size: int
) -> List[Any]:
    """Stage 7: Transforms the detailed tile_grid into final MapObject entities."""
    log.info("Executing Stage 7: Wall-Tracing Transformation...")
    if not tile_grid: return []

    # ... placeholder for wall-tracing logic ...
    # For now, we return an empty list as the full algorithm is complex.
    # A complete implementation would trace walls to form Room polygons.
    log.warning("Wall-tracing transformation is not yet fully implemented.")

    return []


def analyze_image(image_path: str, ascii_debug: bool = False) -> Tuple[schema.MapData, Optional[List]]:
    """
    Loads and analyzes a map image using a multi-stage pipeline to extract
    its structure and features into a MapData object.
    """
    log.info("Starting analysis of image: '%s'", image_path)
    img = cv2.imread(image_path)
    if img is None: raise FileNotFoundError(f"Could not read image at {image_path}")

    all_regions_data = []
    region_contexts = _stage1_detect_regions(img)
    metadata, region_contexts = _stage2_parse_text_metadata(region_contexts)

    dungeon_regions = [rc for rc in region_contexts if rc.get("type") == "dungeon"]

    for i, region_context in enumerate(dungeon_regions):
        region_img = region_context["bounds_img"]
        region_label = f"Dungeon Area {i+1}" if len(dungeon_regions) > 1 else "Main Dungeon"

        grid_size = _stage3_discover_grid(region_img)
        room_contours = _get_room_contours(region_img, grid_size)
        tile_grid = _stage6_classify_features(region_img, room_contours, grid_size)

        all_objects = _stage7_transform_to_mapdata(tile_grid, grid_size)

        if ascii_debug and tile_grid:
            log.info("--- ASCII Debug Output (Pre-Transformation) ---")
            if (1, 1) in tile_grid:
                log_geom.debug("Data for tile (1,1): %s", tile_grid.get((1,1)))
            else:
                log_geom.debug("Tile (1,1) not found in tile_grid.")
            renderer = rendering.ASCIIRenderer()
            renderer.render_from_tiles(tile_grid)
            log.info("\n%s", renderer.get_output(), extra={'raw': True})
            log.info("--- End ASCII Debug Output ---")

        all_regions_data.append({
            "id": region_context["id"],
            "label": region_label,
            "gridSizePx": grid_size,
            "bounds_rect": region_context["bounds_rect"],
            "mapObjects": all_objects,
        })

    # Final assembly of the MapData object
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
