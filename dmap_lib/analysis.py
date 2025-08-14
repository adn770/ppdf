import logging
import os
import uuid
import itertools
from typing import List, Dict, Any, Tuple, Optional

import cv2
import numpy as np
import easyocr
from shapely.geometry import Point, Polygon

from dmap_lib import schema

log = logging.getLogger("dmap.analysis")
log_ocr = logging.getLogger("dmap.ocr")
log_geom = logging.getLogger("dmap.geometry")

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
    _, thresh = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)

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


def _stage4_5_detect_rooms_and_corridors(
    region_image: np.ndarray, grid_size: int
) -> List[schema.Room]:
    """
    Stage 4 & 5: Detect all rooms and corridors from a region's image.
    """
    log.info("Executing Stage 4/5: Room & Corridor Detection...")
    gray = cv2.cvtColor(region_image, cv2.COLOR_BGR2GRAY)
    _, processed = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    log.debug("Filling holes in floor plan to get solid shapes...")
    contours, hierarchy = cv2.findContours(
        processed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    floor_mask = processed.copy()
    if hierarchy is not None:
        for i, contour in enumerate(contours):
            if hierarchy[0][i][3] != -1 and cv2.contourArea(contour) < 150:
                cv2.drawContours(floor_mask, [contour], -1, 255, cv2.FILLED)

    final_contours, _ = cv2.findContours(
        floor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    log.info("Found %d distinct floor plan shapes.", len(final_contours))

    rooms = []
    min_room_area = (grid_size * grid_size)
    for contour in final_contours:
        if cv2.contourArea(contour) < min_room_area:
            continue

        epsilon = 0.01 * cv2.arcLength(contour, True)
        approx_poly = cv2.approxPolyDP(contour, epsilon, True)

        verts = [
            schema.GridPoint(round(p[0][0] / grid_size), round(p[0][1] / grid_size))
            for p in approx_poly
        ]
        pixel_verts = [p[0] for p in approx_poly]

        _, _, w, h = cv2.boundingRect(contour)
        aspect_ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 0
        room_type = "corridor" if aspect_ratio > 3.5 else "chamber"

        room = schema.Room(
            id=f"room_{uuid.uuid4().hex[:8]}",
            shape="polygon",
            gridVertices=verts,
            roomType=room_type,
            properties={"pixel_contour": np.array(pixel_verts)} # Temp storage
        )
        rooms.append(room)
    return rooms


def _detect_doors_between_rooms(rooms: List[schema.Room], grid_size: int):
    """Detects doors by finding small intersections between dilated room shapes."""
    log_geom.info("Starting geometric door detection for %d rooms...", len(rooms))
    doors = []
    # Convert rooms to a temporary structure with shapely polygons for analysis
    room_geoms = [
        {
            "obj": room,
            "polygon": Polygon(room.properties.pop("pixel_contour"))
        }
        for room in rooms if room.properties and "pixel_contour" in room.properties
    ]

    buffer_dist = grid_size * 0.6
    max_door_area = (grid_size * grid_size) * 2.5

    for room_a, room_b in itertools.combinations(room_geoms, 2):
        dilated_a = room_a['polygon'].buffer(buffer_dist)
        dilated_b = room_b['polygon'].buffer(buffer_dist)

        if not dilated_a.intersects(dilated_b):
            continue
        intersection = dilated_a.intersection(dilated_b)

        if 0 < intersection.area < max_door_area:
            centroid = intersection.centroid
            minx, miny, maxx, maxy = intersection.bounds
            orientation = "v" if (maxy - miny) > (maxx - minx) else "h"
            door = schema.Door(
                id=f"door_{uuid.uuid4().hex[:8]}",
                gridPos=schema.GridPoint(round(centroid.x/grid_size), round(centroid.y/grid_size)),
                orientation=orientation,
                connects=[room_a['obj'].id, room_b['obj'].id]
            )
            doors.append(door)
    log_geom.info("Found %d doors via geometric analysis.", len(doors))
    return doors

def _stage6_classify_features(
    region_image: np.ndarray, rooms: List[schema.Room], grid_size: int
) -> Tuple[List[schema.Feature], List[schema.EnvironmentalLayer], List[schema.Door]]:
    """
    Stage 6: Perform classification of intra-room features, layers, and doors.
    """
    log.info("Executing Stage 6: Feature Classification...")
    gray = cv2.cvtColor(region_image, cv2.COLOR_BGR2GRAY)
    all_features, all_layers = [], []

    # Part 1: Find doors between rooms
    doors = _detect_doors_between_rooms(rooms, grid_size)

    # Part 2: Find features and layers within each room
    for room in rooms:
        if room.properties is None or "pixel_contour" not in room.properties:
            continue

        # Create a mask for just this room
        mask = np.zeros(gray.shape, dtype=np.uint8)
        cv2.drawContours(mask, [room.properties["pixel_contour"]], -1, 255, -1)
        room_content_img = cv2.bitwise_and(gray, gray, mask=mask)

        # Find dark features (columns, statues, etc.)
        _, feat_thresh = cv2.threshold(room_content_img, 1, 180, cv2.THRESH_BINARY_INV)
        feat_contours, _ = cv2.findContours(feat_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if room.contents is None: room.contents = []
        for fc in feat_contours:
            if 10 < cv2.contourArea(fc) < (grid_size * grid_size * 2):
                verts = [schema.GridPoint(round(p[0][0]/grid_size), round(p[0][1]/grid_size)) for p in fc]
                feature = schema.Feature(
                    id=f"feature_{uuid.uuid4().hex[:8]}",
                    featureType="column", # Default classification
                    shape="polygon",
                    gridVertices=verts,
                )
                all_features.append(feature)
                room.contents.append(feature.id)

    log.info("Found %d internal features and %d env. layers.", len(all_features), len(all_layers))
    return all_features, all_layers, doors


def _stage7_transform_to_mapdata(
    image_path: str, all_regions_data: List[Dict], metadata: Dict[str, Any]
) -> schema.MapData:
    """
    Stage 7: Transform intermediate data into the final MapData object.
    """
    log.info("Executing Stage 7: Final Transformation...")

    title = metadata.get("title") or os.path.splitext(os.path.basename(image_path))[0]
    meta_obj = schema.Meta(
        title=title,
        sourceImage=os.path.basename(image_path),
        notes=metadata.get("notes"),
        legend=metadata.get("legend"),
        gridSizePx=0,
    )

    regions = []
    for region_data in all_regions_data:
        x, y, w, h = region_data["bounds_rect"]
        bounds = [
            schema.GridPoint(x=x, y=y),
            schema.GridPoint(x=x + w, y=y),
            schema.GridPoint(x=x + w, y=y + h),
            schema.GridPoint(x=x, y=y + h),
        ]
        # Clean up temporary properties from Room objects
        for obj in region_data["mapObjects"]:
            if isinstance(obj, schema.Room) and obj.properties:
                obj.properties.pop("pixel_contour", None)
                if not obj.properties: obj.properties = None

        region = schema.Region(
            id=region_data["id"],
            label=region_data["label"],
            gridSizePx=region_data["gridSizePx"],
            bounds=bounds,
            mapObjects=region_data["mapObjects"],
        )
        regions.append(region)

    log.debug("Packaged %d regions into final MapData object.", len(regions))
    return schema.MapData(dmapVersion="2.0.0", meta=meta_obj, regions=regions)


def analyze_image(image_path: str) -> Tuple[schema.MapData, Optional[List]]:
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
        region_label = f"Dungeon Area {i+1}"
        if len(dungeon_regions) == 1:
            region_label = "Main Dungeon"

        grid_size = _stage3_discover_grid(region_img)
        rooms = _stage4_5_detect_rooms_and_corridors(region_img, grid_size)
        features, layers, doors = _stage6_classify_features(region_img, rooms, grid_size)

        all_regions_data.append({
            "id": region_context["id"],
            "label": region_label,
            "gridSizePx": grid_size,
            "bounds_rect": region_context["bounds_rect"],
            "mapObjects": rooms + features + layers + doors,
        })

    map_data = _stage7_transform_to_mapdata(image_path, all_regions_data, metadata)

    return map_data, None
