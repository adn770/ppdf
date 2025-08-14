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


def _stage3_discover_grid(region_image: np.ndarray) -> int:
    """
    (Placeholder) Stage 3: Discover the grid size within a region.
    """
    log.info("Executing Stage 3: Grid Discovery...")
    default_grid_size = 20
    log.debug("(Stub) Returning default grid size: %dpx", default_grid_size)
    return default_grid_size


def _get_floor_plan_contours(region_image: np.ndarray, grid_size: int) -> List[np.ndarray]:
    """Helper to get clean room contours for internal analysis."""
    gray = cv2.cvtColor(region_image, cv2.COLOR_BGR2GRAY)
    _, processed = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    contours, hierarchy = cv2.findContours(processed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    floor_mask = processed.copy()
    if hierarchy is not None:
        for i, contour in enumerate(contours):
            if hierarchy[0][i][3] != -1 and cv2.contourArea(contour) < 150:
                cv2.drawContours(floor_mask, [contour], -1, 255, cv2.FILLED)
    final_contours, _ = cv2.findContours(
        floor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    return [c for c in final_contours if cv2.contourArea(c) > (grid_size * grid_size)]


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
                    # Check north/south walls
                    if tile_grid.get((x, y - 1)) and tile_grid.get((x, y)):
                        if (
                            tile_grid[(x, y - 1)].feature_type == "empty"
                            and tile_grid[(x, y)].feature_type != "empty"
                        ):
                            tile_grid[(x, y)].north_wall = "door"
                            tile_grid[(x, y - 1)].south_wall = "door"
                    # Check west/east walls
                    if tile_grid.get((x - 1, y)) and tile_grid.get((x, y)):
                        if (
                            tile_grid[(x - 1, y)].feature_type == "empty"
                            and tile_grid[(x, y)].feature_type != "empty"
                        ):
                            tile_grid[(x, y)].west_wall = "door"
                            tile_grid[(x - 1, y)].east_wall = "door"


def _stage6_classify_features(
    region_image: np.ndarray, room_contours: List[np.ndarray], grid_size: int
) -> Dict[Tuple[int, int], _TileData]:
    """
    Stage 6: Perform tile-based classification of features and walls.
    """
    log.info("Executing Stage 6: Feature & Wall Classification...")
    gray = cv2.cvtColor(region_image, cv2.COLOR_BGR2GRAY)
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

    # Pass 1: Classify the primary feature type of each tile
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

            tile_img = gray[
                py_center - grid_size // 4 : py_center + grid_size // 4,
                px_center - grid_size // 4 : px_center + grid_size // 4,
            ]
            feature_type = "floor" if np.mean(tile_img) > 150 else "column"
            tile_grid[(x, y)] = _TileData(feature_type=feature_type)

    # Pass 2: Detect walls based on transitions between floor and empty tiles
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

    # Pass 3: Punch doors into the walls using geometric analysis
    _punch_doors_in_tile_grid(tile_grid, room_contours, grid_size)

    # Pass 4: Normalize the grid coordinates to be 1-based
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
            # A column is inside a room if its tile coordinate maps to that room.
            # However, columns replace a floor tile, so we check neighbors.
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                room_id = coord_to_room_id.get((gx + dx, gy + dy))
                if room_id and room_id in room_map:
                    if room_map[room_id].contents is None:
                        room_map[room_id].contents = []
                    # Avoid adding the same feature multiple times if it borders several tiles
                    if feature.id not in room_map[room_id].contents:
                        room_map[room_id].contents.append(feature.id)
    return features


def _extract_doors_from_grid(tile_grid, coord_to_room_id):
    """Finds all doors on tile edges and links the adjacent rooms."""
    doors = []
    processed_edges = set()  # To avoid creating two door objects for the same opening

    for (gx, gy), tile in tile_grid.items():
        # Check South wall for a horizontal door
        if tile.south_wall == "door":
            edge = tuple(sorted(((gx, gy), (gx, gy + 1))))
            if edge not in processed_edges:
                room1_id = coord_to_room_id.get((gx, gy))
                room2_id = coord_to_room_id.get((gx, gy + 1))
                if room1_id and room2_id and room1_id != room2_id:
                    pos = schema.GridPoint(
                        x=gx, y=gy + 1
                    )  # Convention: door is at top-left of southern tile
                    doors.append(
                        schema.Door(
                            id=f"door_{uuid.uuid4().hex[:8]}",
                            gridPos=pos,
                            orientation="h",
                            connects=[room1_id, room2_id],
                        )
                    )
                    processed_edges.add(edge)

        # Check East wall for a vertical door
        if tile.east_wall == "door":
            edge = tuple(sorted(((gx, gy), (gx + 1, gy))))
            if edge not in processed_edges:
                room1_id = coord_to_room_id.get((gx, gy))
                room2_id = coord_to_room_id.get((gx + 1, gy))
                if room1_id and room2_id and room1_id != room2_id:
                    pos = schema.GridPoint(
                        x=gx + 1, y=gy
                    )  # Convention: door is at top-left of eastern tile
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

    # Start on the North wall of the top-leftmost tile, heading East.
    # A vertex is a corner of a tile. Directions are vectors.
    direction = (1, 0)  # East
    current_vertex = (start_pos[0], start_pos[1])
    path = [schema.GridPoint(x=current_vertex[0], y=current_vertex[1])]

    for _ in range(len(tile_grid) * 4):  # Failsafe limit
        # The four tiles around the current vertex
        tile_NW = tile_grid.get((current_vertex[0] - 1, current_vertex[1] - 1))
        tile_NE = tile_grid.get((current_vertex[0], current_vertex[1] - 1))
        tile_SW = tile_grid.get((current_vertex[0] - 1, current_vertex[1]))
        tile_SE = tile_grid.get(current_vertex)

        # Right-hand rule from the vertex perspective
        if direction == (1, 0):  # Moving East
            if tile_NE and tile_NE.west_wall:
                direction = (0, 1)
                # Turn South
            elif tile_SE and tile_SE.north_wall:
                current_vertex = (current_vertex[0] + 1, current_vertex[1])
                # Move East
            else:
                direction = (0, -1)  # Turn North
        elif direction == (0, 1):  # Moving South
            if tile_SE and tile_SE.north_wall:
                direction = (-1, 0)
                # Turn West
            elif tile_SW and tile_SW.east_wall:
                current_vertex = (current_vertex[0], current_vertex[1] + 1)
                # Move South
            else:
                direction = (1, 0)  # Turn East
        elif direction == (-1, 0):  # Moving West
            if tile_SW and tile_SW.east_wall:
                direction = (0, -1)
                # Turn North
            elif tile_NW and tile_NW.south_wall:
                current_vertex = (current_vertex[0] - 1, current_vertex[1])
                # Move West
            else:
                direction = (0, 1)  # Turn South
        elif direction == (0, -1):  # Moving North
            if tile_NW and tile_NW.south_wall:
                direction = (1, 0)
                # Turn East
            elif tile_NE and tile_NE.west_wall:
                current_vertex = (current_vertex[0], current_vertex[1] - 1)
                # Move North
            else:
                direction = (-1, 0)  # Turn West

        # Add a new vertex to the path only when we turn
        if path[-1].x != current_vertex[0] or path[-1].y != current_vertex[1]:
            path.append(schema.GridPoint(x=current_vertex[0], y=current_vertex[1]))

        if (current_vertex[0], current_vertex[1]) == (start_pos[0], start_pos[1]):
            break  # We have returned to the start

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

    all_regions_data = []
    region_contexts = _stage1_detect_regions(img)
    metadata, region_contexts = _stage2_parse_text_metadata(region_contexts)

    dungeon_regions = [rc for rc in region_contexts if rc.get("type") == "dungeon"]

    for i, region_context in enumerate(dungeon_regions):
        region_img = region_context["bounds_img"]
        region_label = f"Dungeon Area {i+1}" if len(dungeon_regions) > 1 else "Main Dungeon"

        grid_size = _stage3_discover_grid(region_img)
        room_contours = _get_floor_plan_contours(region_img, grid_size)
        tile_grid = _stage6_classify_features(region_img, room_contours, grid_size)

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
