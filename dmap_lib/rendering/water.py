# --- dmap_lib/rendering/water.py ---
import logging
from typing import List, Tuple, Dict, Optional

import numpy as np
from shapely.geometry import Polygon

from dmap_lib import schema
from dmap_lib.rendering.constants import PIXELS_PER_GRID
from .geometry import polygon_to_svg_path

log = logging.getLogger("dmap.render")


def _catmull_rom_spline(
    points: List[Tuple[float, float]], num_points: int, tension: float
) -> List[Tuple[float, float]]:
    """
    Generates a smooth curve using a Catmull-Rom spline.

    Args:
        points: A list of (x, y) control points.
        num_points: The number of points to generate between each control point.
        tension: The "tightness" of the curve (0=loose, 1=tight).

    Returns:
        A list of (x, y) points representing the smooth spline.
    """
    if not points or len(points) < 4:
        return points  # Not enough points to form a spline

    out_points = []
    # Pad points for a closed loop by wrapping the list
    points_padded = [points[-2]] + points + [points[1]]

    for i in range(1, len(points_padded) - 2):
        p0 = np.array(points_padded[i - 1])
        p1 = np.array(points_padded[i])
        p2 = np.array(points_padded[i + 1])
        p3 = np.array(points_padded[i + 2])

        # Catmull-Rom to Cardinal matrix conversion
        t_matrix = np.array(
            [
                [0, 1, 0, 0],
                [-tension, 0, tension, 0],
                [2 * tension, tension - 3, 3 - 2 * tension, -tension],
                [-tension, 2 - tension, tension - 2, tension],
            ]
        )
        control_matrix = np.array([p0, p1, p2, p3])

        # Generate points for the current segment
        for t in np.linspace(0, 1, num_points):
            t_vector = np.array([1, t, t**2, t**3])
            new_point = t_vector @ t_matrix @ control_matrix
            out_points.append(tuple(new_point))

    return out_points


def _create_smooth_polygon(
    polygon: Polygon, tension: float, num_points: int, simplification_tolerance: float
) -> Polygon:
    """Generates a smooth, organic, curvy Shapely Polygon from an input Polygon."""
    if polygon.is_empty:
        return polygon

    # Preparatory Step: Simplify the polygon to prevent interpolation artifacts
    simplified_poly = polygon.simplify(simplification_tolerance, preserve_topology=True)
    if simplified_poly.is_empty or not hasattr(simplified_poly.exterior, "coords"):
        return polygon

    points = list(simplified_poly.exterior.coords)
    # Ensure the polygon is closed for the algorithm
    if len(points) > 1 and points[0] != points[-1]:
        points.append(points[0])

    smoothed_points = _catmull_rom_spline(points, num_points, tension)

    if not smoothed_points or len(smoothed_points) < 3:
        return polygon  # Return original if smoothing fails

    return Polygon(smoothed_points)


class WaterRenderer:
    """Encapsulates all logic for rendering water layers."""

    def __init__(self, styles: dict):
        self.styles = styles

    def render(
        self, layer: schema.EnvironmentalLayer, clip_polygon: Optional[Polygon] = None
    ) -> str:
        """
        Renders a water layer with a procedurally generated curvy effect, clipping
        it to the provided polygon.
        """
        if not layer.gridVertices:
            return ""

        base_color = self.styles.get("water_base_color", "#AEC6CF")
        tension = self.styles.get("water_tension", 0.5)
        num_points = self.styles.get("water_num_points", 10)
        simplification = self.styles.get("water_simplification_factor", 0.1)
        simplification_tolerance = PIXELS_PER_GRID * simplification

        poly = Polygon(
            [(v.x * PIXELS_PER_GRID, v.y * PIXELS_PER_GRID) for v in layer.gridVertices]
        )
        if poly.is_empty:
            return ""

        svg_parts = ['<g class="water-effect">']

        # 1. First, create the smoothed, curvy version of the polygon.
        smoothed_poly = _create_smooth_polygon(
            poly, tension, num_points, simplification_tolerance
        )

        # 2. Then, clip the *smoothed* polygon against the room's geometry.
        final_poly = smoothed_poly
        if clip_polygon and not clip_polygon.is_empty:
            final_poly = smoothed_poly.intersection(clip_polygon)

        # 3. Convert the final, clipped geometry to an SVG path.
        base_path_data = polygon_to_svg_path(final_poly, 1.0)  # Already in pixels
        if not base_path_data:
            return ""

        svg_parts.append(f'<path d="{base_path_data}" fill="{base_color}" />')
        svg_parts.append("</g>")
        return "".join(svg_parts)
