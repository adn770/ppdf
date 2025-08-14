# --- dmap_lib/analysis.py ---
import itertools
import os
import uuid
from collections import Counter

import cv2
import easyocr
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from dmap_lib import schema

# Initialize the OCR reader once when the module is loaded.
print("Initializing EasyOCR reader... (This may take a moment)")
OCR_READER = easyocr.Reader(['en'], gpu=False)
print("EasyOCR reader initialized.")


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
    return contours


def _detect_doors(rooms_data: list, grid_size: int) -> list[schema.Door]:
    """Detects doors by finding small intersections between dilated room shapes."""
    doors = []
    buffer_dist = grid_size * 0.2  # How much to 'grow' rooms to find overlaps
    max_door_area = (grid_size * grid_size) * 2.5

    for room_a, room_b in itertools.combinations(rooms_data, 2):
        # Create slightly larger versions of the room polygons
        dilated_a = room_a['polygon'].buffer(buffer_dist)
        dilated_b = room_b['polygon'].buffer(buffer_dist)

        if not dilated_a.intersects(dilated_b):
            continue

        intersection = dilated_a.intersection(dilated_b)

        # A valid door is a small, shared area
        if 0 < intersection.area < max_door_area:
            centroid = intersection.centroid
            minx, miny, maxx, maxy = intersection.bounds
            orientation = "vertical" if (maxy - miny) > (maxx - minx) else "horizontal"

            doors.append(schema.Door(
                id=f"door_{uuid.uuid4().hex[:8]}",
                gridPos=schema.GridPoint(round(centroid.x/grid_size), round(centroid.y/grid_size)),
                orientation=orientation,
                connects=[room_a['obj'].id, room_b['obj'].id]
            ))
    return doors


def analyze_image(image_path: str) -> tuple[schema.MapData, list | None]:
    """Loads and analyzes a map to extract all features and a unified geometry."""
    img = cv2.imread(image_path)
    if img is None: raise FileNotFoundError(f"Could not read image at {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    grid_size = 20  # For stronghold.png, grid is consistently 20px

    contours, _ = cv2.findContours(processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rooms_data = []
    map_objects = []

    for contour in contours:
        if cv2.contourArea(contour) < (grid_size * grid_size * 0.75):
            continue

        # Create shapely polygon for geometric analysis
        poly_coords = contour.squeeze()
        if len(poly_coords) < 3: continue
        shapely_poly = Polygon(poly_coords)

        # Create the Room object for the schema
        approx_poly = cv2.approxPolyDP(contour, 0.015 * cv2.arcLength(contour, True), True)
        verts = [schema.GridPoint(round(p[0][0]/grid_size), round(p[0][1]/grid_size)) for p in approx_poly]
        room = schema.Room(id=f"room_{uuid.uuid4().hex[:8]}", shape="polygon", gridVertices=verts)

        map_objects.append(room)
        rooms_data.append({'obj': room, 'polygon': shapely_poly})

    # --- New Door Detection Step ---
    detected_doors = _detect_doors(rooms_data, grid_size)
    map_objects.extend(detected_doors)

    # --- Polygon Union Step ---
    unified_contours = None
    all_polygons = [rd['polygon'] for rd in rooms_data]
    if all_polygons:
        try:
            unified_geometry = unary_union(all_polygons)
            unified_contours = _shapely_to_contours(unified_geometry)
        except Exception as e:
            print(f"Warning: Shapely union failed. {e}")

    meta = schema.Meta(title=os.path.splitext(os.path.basename(image_path))[0], sourceImage=os.path.basename(image_path), gridSizePx=grid_size)
    map_data = schema.MapData(dmapVersion="1.0.0", meta=meta, mapObjects=map_objects)

    return map_data, unified_contours
