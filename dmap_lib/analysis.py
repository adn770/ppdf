import itertools
import os
import uuid
import logging

import cv2
import easyocr
import numpy as np
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from dmap_lib import schema

log = logging.getLogger("dmap.analysis")
log_ocr = logging.getLogger("dmap.ocr")
log_geom = logging.getLogger("dmap.geometry")

# Initialize the OCR reader once when the module is loaded.
log_ocr.info("Initializing EasyOCR reader... (This may take a moment)")
OCR_READER = easyocr.Reader(['en'], gpu=False)
log_ocr.info("EasyOCR reader initialized.")


def _shapely_to_contours(geometry) -> list:
    """Converts a Shapely Polygon or MultiPolygon to a list of OpenCV contours."""
    if geometry.is_empty: return []
    contours = []
    def extract(coords): return np.array(coords).round().astype(np.int32).reshape((-1, 1, 2))
    if geometry.geom_type == 'Polygon':
        if geometry.exterior: contours.append(extract(geometry.exterior.coords))
    elif geometry.geom_type == 'MultiPolygon':
        for polygon in geometry.geoms:
            if polygon.exterior: contours.append(extract(polygon.exterior.coords))
    log_geom.debug("Converted Shapely geometry to %d OpenCV contours.", len(contours))
    return contours


def _detect_doors(rooms_data: list, grid_size: int) -> list[schema.Door]:
    """Detects doors by finding small intersections between dilated room shapes."""
    log_geom.info("Starting geometric door detection...")
    doors = []
    buffer_dist = grid_size * 0.6
    max_door_area = (grid_size * grid_size) * 2.5

    num_pairs = len(list(itertools.combinations(rooms_data, 2)))
    log_geom.debug("Checking %d room pairs for connections.", num_pairs)
    for room_a, room_b in itertools.combinations(rooms_data, 2):
        dilated_a = room_a['polygon'].buffer(buffer_dist)
        dilated_b = room_b['polygon'].buffer(buffer_dist)

        if not dilated_a.intersects(dilated_b): continue
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
            log_geom.debug("Found door between %s and %s.", room_a['obj'].id, room_b['obj'].id)
            doors.append(door)
    log_geom.info("Found %d doors via geometric analysis.", len(doors))
    return doors


def _perform_ocr_on_walls(gray_img: np.ndarray, rooms_data: list, unified_poly):
    """Generates a wall mask, performs OCR, and labels the nearest rooms."""
    if not rooms_data or unified_poly.is_empty:
        log_ocr.warning("Cannot perform OCR: no rooms or unified geometry available.")
        return

    log_ocr.info("Generating wall mask for OCR...")
    wall_mask = np.zeros_like(gray_img)
    # Thicken the unified polygon to create wall areas
    wall_poly_dilated = unified_poly.buffer(10, cap_style=2, join_style=2)
    cv2.drawContours(wall_mask, _shapely_to_contours(wall_poly_dilated), -1, 255, -1)
    # Subtract the original room shapes to leave only walls
    cv2.drawContours(wall_mask, [rd['contour'] for rd in rooms_data], -1, 0, -1)

    log_ocr.info("Running OCR on wall mask...")
    ocr_results = OCR_READER.readtext(wall_mask)
    if not ocr_results:
        log_ocr.warning("OCR found no text in the wall mask.")
        return

    labeled_count = 0
    for bbox, text, prob in ocr_results:
        if not text.strip().isdigit(): continue # Ignore non-numeric results

        # Find the center of the detected text
        (tl, _, br, _) = bbox
        text_center = Point((tl[0] + br[0]) / 2, (tl[1] + br[1]) / 2)

        # Find the closest room to this text
        closest_room, min_dist = None, float('inf')
        for room_data in rooms_data:
            dist = room_data['polygon'].distance(text_center)
            if dist < min_dist:
                min_dist, closest_room = dist, room_data['obj']

        if closest_room:
            log_ocr.debug("Labeled room %s as '%s' (p=%.2f)", closest_room.id, text, prob)
            closest_room.label = text
            labeled_count += 1
    log_ocr.info("Applied %d numeric labels to rooms from OCR results.", labeled_count)


def analyze_image(image_path: str) -> tuple[schema.MapData, list | None]:
    """Loads and analyzes a map to extract all features and a unified geometry."""
    log.info("Starting analysis of image: '%s'", image_path)
    img = cv2.imread(image_path)
    if img is None: raise FileNotFoundError(f"Could not read image at {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    log.debug("Image loaded: %dx%d.", gray.shape[1], gray.shape[0])

    _, processed = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    log.debug("Applied binary threshold to isolate floor plan.")

    log.debug("Starting high-fidelity shape extraction (hole filling)...")
    contours, hierarchy = cv2.findContours(processed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    floor_mask = processed.copy()
    if hierarchy is not None:
        holes_filled = 0
        for i, contour in enumerate(contours):
            if hierarchy[0][i][3] != -1 and cv2.contourArea(contour) < 100:
                cv2.drawContours(floor_mask, [contour], -1, 255, cv2.FILLED)
                holes_filled += 1
        log.debug("Filled %d small holes (e.g., grid dots).", holes_filled)

    final_contours, _ = cv2.findContours(floor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    grid_size = 20
    log.info("Using fixed grid size of %dpx.", grid_size)
    log.info("Found %d clean external contours.", len(final_contours))

    rooms_data = []
    map_objects = []
    min_room_area = (grid_size * grid_size * 0.75)

    for contour in final_contours:
        if cv2.contourArea(contour) < min_room_area: continue
        poly_coords = contour.squeeze()
        if len(poly_coords) < 3: continue
        shapely_poly = Polygon(poly_coords).buffer(0)
        epsilon = 0.02 * cv2.arcLength(contour, True)
        approx_poly = cv2.approxPolyDP(contour, epsilon, True)
        verts = [schema.GridPoint(round(p[0][0]/grid_size), round(p[0][1]/grid_size)) for p in approx_poly]
        room = schema.Room(id=f"room_{uuid.uuid4().hex[:8]}", shape="polygon", gridVertices=verts)
        map_objects.append(room)
        rooms_data.append({'obj': room, 'polygon': shapely_poly, 'contour': contour})
    log.info("Identified %d contours as rooms.", len(rooms_data))

    log_geom.info("Performing geometric union on %d room polygons...", len(rooms_data))
    unified_geometry, unified_contours = None, None
    all_polygons = [rd['polygon'] for rd in rooms_data]
    if all_polygons:
        try:
            unified_geometry = unary_union(all_polygons)
            log_geom.debug("Unary union successful. Result type: %s", unified_geometry.geom_type)
            unified_contours = _shapely_to_contours(unified_geometry)
        except Exception as e: log.warning("Shapely union failed: %s", e)

    _perform_ocr_on_walls(gray, rooms_data, unified_geometry)
    detected_doors = _detect_doors(rooms_data, grid_size)
    map_objects.extend(detected_doors)

    meta = schema.Meta(title=os.path.splitext(os.path.basename(image_path))[0], sourceImage=os.path.basename(image_path), gridSizePx=grid_size)
    map_data = schema.MapData(dmapVersion="1.0.0", meta=meta, mapObjects=map_objects)

    return map_data, unified_contours
