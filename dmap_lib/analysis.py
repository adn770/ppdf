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


def _find_most_common_spacing(lines: np.ndarray, is_vertical: bool) -> int:
    """Calculates the most common spacing between a set of parallel lines."""
    if lines is None or len(lines) < 2:
        return 0
    coords = lines[:, 0, 0] if is_vertical else lines[:, 0, 1]
    unique_coords = sorted(list(set(np.round(coords))))
    if len(unique_coords) < 2:
        return 0
    diffs = np.diff(unique_coords)
    reasonable_diffs = [int(d) for d in diffs if 5 < d < 100]
    if not reasonable_diffs:
        return 0
    return Counter(reasonable_diffs).most_common(1)[0][0]


def _detect_grid_size(image: np.ndarray) -> int:
    """Detects the grid size in pixels using Hough Line Transform."""
    edges = cv2.Canny(image, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=50,
        minLineLength=30, maxLineGap=10
    )
    if lines is None:
        return 20
    v_lines = [l for l in lines if abs(l[0][0] - l[0][2]) < 5]
    h_lines = [l for l in lines if abs(l[0][1] - l[0][3]) < 5]
    grid_x = _find_most_common_spacing(np.array(v_lines), is_vertical=True)
    grid_y = _find_most_common_spacing(np.array(h_lines), is_vertical=False)
    if grid_x > 0 and grid_y > 0:
        return int((grid_x + grid_y) / 2)
    return grid_x or grid_y or 20


def analyze_image(image_path: str) -> schema.MapData:
    """Loads and analyzes a map image to extract rooms, doors, and their links."""
    img = cv2.imread(image_path)
    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, processed_img = cv2.threshold(
        gray_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    grid_size = _detect_grid_size(processed_img)
    contours, _ = cv2.findContours(
        processed_img, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE
    )

    # Separate contours into rooms and potential doors based on area
    min_room_area = (grid_size * grid_size) * 0.75
    min_door_area = grid_size * 0.25
    max_door_area = grid_size * grid_size * 2.0
    room_contours, door_contours = [], []
    for c in contours:
        area = cv2.contourArea(c)
        if area >= min_room_area:
            room_contours.append(c)
        elif min_door_area <= area <= max_door_area:
            door_contours.append(c)

    # First pass: process all rooms
    rooms_with_contours = []
    for contour in room_contours:
        x, y, w, h = cv2.boundingRect(contour)
        mask = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(mask, [contour - [x, y]], -1, 255, cv2.FILLED)
        room_interior = cv2.bitwise_and(gray_img[y:y+h, x:x+w], mask)
        ocr = OCR_READER.readtext(room_interior, detail=1, paragraph=False)
        label = next((text for _, text, _ in ocr if text.isdigit()), None)

        poly = cv2.approxPolyDP(contour, 0.015 * cv2.arcLength(contour, True), True)
        verts = [schema.GridPoint(round(p[0][0]/grid_size), round(p[0][1]/grid_size)) for p in poly]

        room = schema.Room(id=f"room_{uuid.uuid4().hex[:8]}", label=label,
                           shape="polygon", gridVertices=verts)
        rooms_with_contours.append({'obj': room, 'contour': contour})

    # Second pass: process doors and link to the two nearest rooms
    doors = []
    for contour in door_contours:
        M = cv2.moments(contour)
        if M["m00"] == 0: continue
        cx, cy = int(M["m10"]/M["m00"]), int(M["m01"]/M["m00"])

        # Find distance to every room
        distances = [{
            'dist': abs(cv2.pointPolygonTest(rc['contour'], (cx, cy), True)),
            'room_id': rc['obj'].id
        } for rc in rooms_with_contours]
        distances.sort(key=lambda item: item['dist'])

        # If the door is close to at least two rooms, it's a valid connection
        if len(distances) >= 2 and distances[0]['dist'] < (2 * grid_size):
            _, _, w, h = cv2.boundingRect(contour)
            doors.append(schema.Door(
                id=f"door_{uuid.uuid4().hex[:8]}",
                gridPos=schema.GridPoint(round(cx/grid_size), round(cy/grid_size)),
                orientation="vertical" if h > w else "horizontal",
                connects=[distances[0]['room_id'], distances[1]['room_id']]
            ))

    map_objects = [rc['obj'] for rc in rooms_with_contours] + doors
    meta = schema.Meta(
        title=os.path.splitext(os.path.basename(image_path))[0],
        sourceImage=os.path.basename(image_path),
        gridSizePx=grid_size
    )
    return schema.MapData(dmapVersion="1.0.0", meta=meta, mapObjects=map_objects)
