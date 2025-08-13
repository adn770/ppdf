# --- dmap_lib/analysis.py ---
import os
import uuid
from collections import Counter

import cv2
import easyocr
import numpy as np

from dmap_lib import schema

# Initialize the OCR reader once when the module is loaded.
# This may print a one-time warning about using the CPU, which is expected.
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
    """Loads and analyzes a map image to extract structured data, including labels."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Input image not found at: {image_path}")

    img = cv2.imread(image_path)
    if img is None:
        raise IOError(f"Failed to load image from: {image_path}")

    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, processed_img = cv2.threshold(
        gray_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    grid_size = _detect_grid_size(processed_img)
    contours, _ = cv2.findContours(
        processed_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    map_objects = []
    min_area = (grid_size * grid_size) * 0.75

    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            continue

        # --- Number Recognition Logic ---
        x, y, w, h = cv2.boundingRect(contour)
        mask = np.zeros((h, w), dtype=np.uint8)
        shifted_contour = contour - [x, y]
        cv2.drawContours(mask, [shifted_contour], -1, 255, cv2.FILLED)

        # Extract the room's content from the original grayscale image
        room_interior = cv2.bitwise_and(gray_img[y:y+h, x:x+w], mask)

        ocr_results = OCR_READER.readtext(room_interior, detail=1, paragraph=False)
        room_label = next((text for _, text, _ in ocr_results if text.isdigit()), None)
        # --- End Number Recognition ---

        perimeter = cv2.arcLength(contour, True)
        approx_poly = cv2.approxPolyDP(contour, 0.015 * perimeter, True)
        grid_vertices = [
            schema.GridPoint(x=round(p[0][0] / grid_size), y=round(p[0][1] / grid_size))
            for p in approx_poly
        ]

        map_objects.append(schema.Room(
            id=f"room_{uuid.uuid4().hex[:8]}",
            shape="polygon",
            gridVertices=grid_vertices,
            label=room_label
        ))

    meta = schema.Meta(
        title=os.path.splitext(os.path.basename(image_path))[0],
        sourceImage=os.path.basename(image_path),
        gridSizePx=grid_size
    )
    return schema.MapData(dmapVersion="1.0.0", meta=meta, mapObjects=map_objects)
