import logging
import os
import uuid
from typing import List, Dict, Any, Tuple, Optional

import cv2
import numpy as np
import easyocr

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
    # Invert threshold: find black shapes on a white background
    _, thresh = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)

    # Find external contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    region_contexts = []
    min_area = img.shape[0] * img.shape[1] * 0.01  # Ignore tiny noise
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

    # Heuristic: The largest region is the dungeon, others are text/legends.
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
        # OCR on the isolated region image
        ocr_results = OCR_READER.readtext(context["bounds_img"], detail=1, paragraph=False)
        for bbox, text, prob in ocr_results:
            # Get the height of the text's bounding box to estimate font size
            h = bbox[2][1] - bbox[0][1]
            text_blobs.append({"text": text, "height": h})

    if text_blobs:
        # Heuristic: The text with the largest height is the title.
        title_blob_idx = max(range(len(text_blobs)), key=lambda i: text_blobs[i]["height"])
        metadata["title"] = text_blobs.pop(title_blob_idx)["text"]
        # Concatenate remaining text into notes.
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
    # Use a high threshold to get only the floor plan (assumed to be white/light).
    _, processed = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    log.debug("Filling holes in floor plan to get solid shapes...")
    contours, hierarchy = cv2.findContours(
        processed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    floor_mask = processed.copy()
    if hierarchy is not None:
        for i, contour in enumerate(contours):
            # A contour with a parent is a hole. Fill small ones.
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

        # Simplify the polygon to have fewer vertices
        epsilon = 0.01 * cv2.arcLength(contour, True)
        approx_poly = cv2.approxPolyDP(contour, epsilon, True)

        verts = [
            schema.GridPoint(round(p[0][0] / grid_size), round(p[0][1] / grid_size))
            for p in approx_poly
        ]

        # Heuristic for room type classification based on aspect ratio
        _, _, w, h = cv2.boundingRect(contour)
        aspect_ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 0
        room_type = "corridor" if aspect_ratio > 3.5 else "chamber"

        room = schema.Room(
            id=f"room_{uuid.uuid4().hex[:8]}",
            shape="polygon",
            gridVertices=verts,
            roomType=room_type,
        )
        rooms.append(room)
        log.debug(
            "Created Room %s (type: %s) with %d vertices.",
            room.id, room.roomType, len(verts)
        )
    return rooms


def _stage6_classify_features(
    region_image: np.ndarray, rooms: list, grid_size: int
) -> Tuple[List[schema.Feature], List[schema.EnvironmentalLayer], List[schema.Door]]:
    """
    (Placeholder) Stage 6: Perform tile-based classification of features.
    """
    log.info("Executing Stage 6: Feature Classification...")
    log.debug("(Stub) Returning empty lists of features, layers, and doors.")
    return [], [], []


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
