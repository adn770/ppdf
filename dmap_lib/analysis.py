# --- dmap_lib/analysis.py ---
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
    if geometry.is_empty:
        return []

    contours = []

    def extract_coords(coords):
        return np.array(coords).round().astype(np.int32).reshape((-1, 1, 2))

    if geometry.geom_type == 'Polygon':
        if geometry.exterior:
            contours.append(extract_coords(geometry.exterior.coords))
        for interior in geometry.interiors:
            contours.append(extract_coords(interior.coords))
    elif geometry.geom_type == 'MultiPolygon':
        for polygon in geometry.geoms:
            if polygon.exterior:
                contours.append(extract_coords(polygon.exterior.coords))
            for interior in polygon.interiors:
                contours.append(extract_coords(interior.coords))
    return contours


def analyze_image(image_path: str) -> tuple[schema.MapData, list | None]:
    """
    Loads and analyzes a map to extract structured data and a unified geometry.
    Returns a tuple of (MapData, unified_contours).
    """
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    grid_size = 20  # Using a fixed grid size for now

    contours, hierarchy = cv2.findContours(processed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    hierarchy = hierarchy[0] if hierarchy is not None else []

    map_objects = []
    rooms_data = []
    all_room_contours = []

    # First pass: Identify rooms and features
    for i, contour in enumerate(contours):
        if hierarchy[i][3] != -1 or cv2.contourArea(contour) < (grid_size * grid_size * 0.75):
            continue

        all_room_contours.append(contour)
        poly = cv2.approxPolyDP(contour, 0.015 * cv2.arcLength(contour, True), True)
        verts = [schema.GridPoint(round(p[0][0]/grid_size), round(p[0][1]/grid_size)) for p in poly]
        room = schema.Room(id=f"room_{uuid.uuid4().hex[:8]}", shape="polygon", gridVertices=verts, contents=[], properties={})

        # (Feature/Layer detection logic would go here)

        map_objects.append(room)
        rooms_data.append({'obj': room, 'contour': contour})

    # (Door detection logic would go here)

    # --- Polygon Union Step ---
    unified_contours = None
    try:
        shapely_polygons = [Polygon(c.squeeze()) for c in all_room_contours if len(c) >= 3]
        if shapely_polygons:
            unified_geometry = unary_union(shapely_polygons)
            unified_contours = _shapely_to_contours(unified_geometry)
    except Exception as e:
        print(f"Warning: Shapely union failed. {e}")
    # --- End Polygon Union Step ---

    meta = schema.Meta(
        title=os.path.splitext(os.path.basename(image_path))[0],
        sourceImage=os.path.basename(image_path),
        gridSizePx=grid_size
    )
    map_data = schema.MapData(dmapVersion="1.0.0", meta=meta, mapObjects=map_objects)

    return map_data, unified_contours
