# --- dmap_lib/analysis.py ---
import os
import uuid
from collections import Counter

import cv2
import numpy as np

from dmap_lib import schema


def _find_most_common_spacing(lines: np.ndarray, is_vertical: bool) -> int:
    """Calculates the most common spacing between a set of parallel lines."""
    if lines is None or len(lines) < 2:
        return 0

    # For vertical lines, get x-coords; for horizontal, get y-coords.
    coords = lines[:, 0, 0] if is_vertical else lines[:, 0, 1]

    # Get unique sorted coordinates
    unique_coords = sorted(list(set(np.round(coords))))
    if len(unique_coords) < 2:
        return 0

    # Calculate the differences between consecutive coordinates
    diffs = np.diff(unique_coords)

    # Filter for realistic grid spacings (e.g., between 5 and 100 pixels)
    reasonable_diffs = [int(d) for d in diffs if 5 < d < 100]
    if not reasonable_diffs:
        return 0

    # Find the most common difference
    count = Counter(reasonable_diffs)
    return count.most_common(1)[0][0]


def _detect_grid_size(image: np.ndarray) -> int:
    """
    Detects the grid size in pixels using Hough Line Transform.
    Returns a default value of 20 if detection is unsuccessful.
    """
    # Use Canny edge detection before Hough transform for better line finding
    edges = cv2.Canny(image, 50, 150, apertureSize=3)

    # Detect line segments in the image
    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=50,
        minLineLength=30, maxLineGap=10
    )

    if lines is None:
        return 20  # Default fallback grid size

    # Separate lines into vertical and horizontal lists
    v_lines = [l for l in lines if abs(l[0][0] - l[0][2]) < 5]
    h_lines = [l for l in lines if abs(l[0][1] - l[0][3]) < 5]

    # Calculate grid size from both orientations
    grid_x = _find_most_common_spacing(np.array(v_lines), is_vertical=True)
    grid_y = _find_most_common_spacing(np.array(h_lines), is_vertical=False)

    # Use the more reliable (non-zero) spacing, or average them
    if grid_x > 0 and grid_y > 0:
        return int((grid_x + grid_y) / 2)
    if grid_x > 0:
        return grid_x
    if grid_y > 0:
        return grid_y

    return 20  # Default fallback grid size


def analyze_image(image_path: str) -> schema.MapData:
    """
    Loads a map image, detects rooms, and creates a structured representation.

    Args:
        image_path: The path to the input map image.

    Returns:
        A MapData object populated with metadata and detected room polygons.
    """
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

    # Find contours for all distinct shapes in the image
    contours, _ = cv2.findContours(
        processed_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    map_objects = []
    min_area = (grid_size * grid_size) * 0.75  # Room must be >= 75% of a grid cell

    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            continue  # Skip small, noisy contours

        # Simplify the contour into a polygon
        perimeter = cv2.arcLength(contour, True)
        epsilon = 0.015 * perimeter
        approx_poly = cv2.approxPolyDP(contour, epsilon, True)

        # Convert pixel vertices to the map's grid coordinate system
        grid_vertices = []
        for point in approx_poly:
            px, py = point[0]
            grid_vertices.append(
                schema.GridPoint(x=round(px / grid_size), y=round(py / grid_size))
            )

        # Create a Room object
        room = schema.Room(
            id=f"room_{uuid.uuid4().hex[:8]}",
            shape="polygon",
            gridVertices=grid_vertices
        )
        map_objects.append(room)

    meta = schema.Meta(
        title=os.path.splitext(os.path.basename(image_path))[0],
        sourceImage=os.path.basename(image_path),
        gridSizePx=grid_size
    )

    return schema.MapData(
        dmapVersion="1.0.0",
        meta=meta,
        mapObjects=map_objects
    )
