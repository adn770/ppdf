# --- dmap_lib/rendering/water.py ---
from typing import List, Tuple, Dict

import numpy as np
from shapely.geometry import Polygon

from dmap_lib import schema
from dmap_lib.rendering.constants import PIXELS_PER_GRID


def _chaikin_smoothing(points: List[Tuple[float, float]], iterations: int) -> List[Tuple[float, float]]:
    """Smooths a polygon's vertices using Chaikin's corner-cutting algorithm."""
    for _ in range(iterations):
        new_points = []
        if not points:
            return []
        # Ensure the polygon is closed for the algorithm
        if points[0] != points[-1]:
            points.append(points[0])

        for i in range(len(points) - 1):
            p1 = np.array(points[i])
            p2 = np.array(points[i + 1])
            q = p1 * 0.75 + p2 * 0.25
            r = p1 * 0.25 + p2 * 0.75
            new_points.extend([tuple(q), tuple(r)])
        points = new_points
    return points


def _create_curvy_path(polygon: Polygon, iterations: int) -> str:
    """Generates a smooth, organic, curvy SVG path from a Shapely Polygon."""
    if polygon.is_empty:
        return ""

    points = list(polygon.exterior.coords)
    smoothed_points = _chaikin_smoothing(points, iterations)

    if not smoothed_points:
        return ""

    path_data = " ".join(
        [
            f"{'M' if i == 0 else 'L'} {x:.2f} {y:.2f}"
            for i, (x, y) in enumerate(smoothed_points)
        ]
    )
    return path_data


class WaterRenderer:
    """Encapsulates all logic for rendering water layers."""

    def __init__(self, styles: dict):
        self.styles = styles

    def render(self, layer: schema.EnvironmentalLayer) -> str:
        """Renders a water layer with a procedurally generated curvy effect."""
        if not layer.gridVertices:
            return ""

        base_color = self.styles.get("water_base_color", "#AEC6CF")
        smoothing_iterations = self.styles.get("water_smoothing_iterations", 4)

        poly = Polygon(
            [(v.x * PIXELS_PER_GRID, v.y * PIXELS_PER_GRID) for v in layer.gridVertices]
        )
        if poly.is_empty:
            return ""

        svg_parts = ['<g class="water-effect">']

        # Use buffer(0) to fix any invalid geometry before smoothing
        base_poly = poly.buffer(0)
        base_path_data = _create_curvy_path(base_poly, smoothing_iterations)
        if not base_path_data:
            return ""
        svg_parts.append(f'<path d="{base_path_data} Z" fill="{base_color}" />')
        svg_parts.append("</g>")
        return "".join(svg_parts)
