# --- dmap_lib/analysis.py ---
import os
import uuid
from collections import Counter

import cv2
import easyocr
import numpy as np

from dmap_lib import schema

# Initialize the OCR reader once when the module is loaded.
print("Initializing EasyOCR reader... (This may take a moment)")
OCR_READER = easyocr.Reader(['en'], gpu=False)
print("EasyOCR reader initialized.")


def _classify_feature(contour: np.ndarray) -> str | None:
    """Classifies an interior contour based on shape heuristics. Returns feature type."""
    area = cv2.contourArea(contour)
    if area < 5:  # Filter out noise
        return None

    perimeter = cv2.arcLength(contour, True)
    if perimeter == 0:
        return None

    # Circularity check for columns/pillars
    circularity = (4 * np.pi * area) / (perimeter * perimeter)
    if 0.8 < circularity < 1.2:
        return "column"

    # Future classifications (stairs, statues) would be added here
    return "feature"  # Generic fallback


def _detect_water_layer(room_interior_img: np.ndarray) -> bool:
    """Detects if a room contains a water-like texture (e.g., wavy lines)."""
    # Threshold aggressively to isolate thin lines
    _, wavy_lines = cv2.threshold(room_interior_img, 180, 255, cv2.THRESH_BINARY_INV)

    # Find contours of these potential lines
    line_contours, _ = cv2.findContours(wavy_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Heuristic: If there are many small, thin contours, it's likely a texture
    small_line_count = sum(1 for c in line_contours if cv2.contourArea(c) < 100)

    return small_line_count > 10 # Threshold for what constitutes a water texture


def _find_most_common_spacing(lines: np.ndarray, is_vertical: bool) -> int:
    """Calculates the most common spacing between a set of parallel lines."""
    if lines is None or len(lines) < 2: return 0
    coords = lines[:, 0, 0] if is_vertical else lines[:, 0, 1]
    unique_coords = sorted(list(set(np.round(coords))))
    if len(unique_coords) < 2: return 0
    diffs = np.diff(unique_coords)
    rd = [int(d) for d in diffs if 5 < d < 100]
    return Counter(rd).most_common(1)[0][0] if rd else 0


def _detect_grid_size(image: np.ndarray) -> int:
    """Detects the grid size in pixels using Hough Line Transform."""
    edges = cv2.Canny(image, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, 50, minLineLength=30, maxLineGap=10)
    if lines is None: return 20
    v_lines = [l for l in lines if abs(l[0][0] - l[0][2]) < 5]
    h_lines = [l for l in lines if abs(l[0][1] - l[0][3]) < 5]
    grid_x = _find_most_common_spacing(np.array(v_lines), is_vertical=True)
    grid_y = _find_most_common_spacing(np.array(h_lines), is_vertical=False)
    if grid_x > 0 and grid_y > 0: return int((grid_x + grid_y) / 2)
    return grid_x or grid_y or 20


def analyze_image(image_path: str) -> schema.MapData:
    """Loads and analyzes a map to extract rooms, doors, features, and layers."""
    img = cv2.imread(image_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, processed = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    grid_size = _detect_grid_size(processed)

    # Use RETR_TREE to get the full contour hierarchy
    contours, hierarchy = cv2.findContours(processed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    hierarchy = hierarchy[0] if hierarchy is not None else []

    map_objects = []
    rooms_data = [] # Store room contour indices and objects

    # First pass: Identify all rooms and their interior features
    for i, contour in enumerate(contours):
        # A room is a top-level contour (no parent)
        if hierarchy[i][3] != -1: continue

        if cv2.contourArea(contour) < (grid_size * grid_size * 0.75): continue

        # --- Base Room Processing ---
        x, y, w, h = cv2.boundingRect(contour)
        poly = cv2.approxPolyDP(contour, 0.015 * cv2.arcLength(contour, True), True)
        verts = [schema.GridPoint(round(p[0][0]/grid_size), round(p[0][1]/grid_size)) for p in poly]
        room = schema.Room(id=f"room_{uuid.uuid4().hex[:8]}", shape="polygon", gridVertices=verts, contents=[], properties={})

        # --- OCR, Layer, and Feature Detection ---
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(mask, [contour - [x, y]], -1, 255, cv2.FILLED)
        interior = cv2.bitwise_and(gray[y:y+h, x:x+w], mask)

        ocr = OCR_READER.readtext(interior, detail=1, paragraph=False)
        room.label = next((text for _, text, _ in ocr if text.isdigit()), None)

        if _detect_water_layer(interior):
            room.properties['layer'] = 'water'

        # --- Find Child Contours (Interior Features) ---
        child_idx = hierarchy[i][2]
        while child_idx != -1:
            child_contour = contours[child_idx]
            feature_type = _classify_feature(child_contour)
            if feature_type:
                f_poly = cv2.approxPolyDP(child_contour, 0.02 * cv2.arcLength(child_contour, True), True)
                f_verts = [schema.GridPoint(round(p[0][0]/grid_size), round(p[0][1]/grid_size)) for p in f_poly]
                feature = schema.Feature(id=f"feature_{uuid.uuid4().hex[:8]}", featureType=feature_type, shape="polygon", gridVertices=f_verts)
                room.contents.append(feature.id)
                map_objects.append(feature)
            child_idx = hierarchy[child_idx][0] # Move to next sibling

        map_objects.append(room)
        rooms_data.append({'obj': room, 'contour': contour})

    # Second pass: Detect doors (same as before)
    door_contours = [c for i,c in enumerate(contours) if hierarchy[i][3] == -1 and (grid_size*0.25) < cv2.contourArea(c) < (grid_size*grid_size*0.75)]
    for contour in door_contours:
        M = cv2.moments(contour)
        if M["m00"] == 0: continue
        cx, cy = int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])
        dists = sorted([{'d': abs(cv2.pointPolygonTest(r['contour'], (cx, cy), True)), 'id': r['obj'].id} for r in rooms_data], key=lambda i: i['d'])
        if len(dists) >= 2 and dists[0]['d'] < (2 * grid_size):
            _,_,w,h = cv2.boundingRect(contour)
            map_objects.append(schema.Door(id=f"door_{uuid.uuid4().hex[:8]}", gridPos=schema.GridPoint(round(cx/grid_size), round(cy/grid_size)), orientation="v" if h>w else "h", connects=[dists[0]['id'], dists[1]['id']]))

    meta = schema.Meta(title=os.path.splitext(os.path.basename(image_path))[0], sourceImage=os.path.basename(image_path), gridSizePx=grid_size)
    return schema.MapData(dmapVersion="1.0.0", meta=meta, mapObjects=map_objects)
