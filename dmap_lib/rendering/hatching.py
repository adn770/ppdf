# --- dmap_lib/rendering/hatching.py ---
import math
import random
from typing import List, Tuple, Dict

import noise
import numpy as np
from shapely.geometry import Point, Polygon, MultiPolygon, LineString


class HatchingRenderer:
    """Encapsulates all logic for procedural hatching effects."""

    def __init__(self, styles: dict):
        self.styles = styles

    def generate_sketch_hatching(
        self,
        width: float,
        height: float,
        grid_size: int,
        tx: float,
        ty: float,
        unified_geometry: Polygon | MultiPolygon,
    ) -> tuple[list[str], list[str]]:
        """
        Generates a high-fidelity, tile-based cross-hatching effect with a grey
        underlay, based on the user's final design.
        """
        hatch_lines = []
        hatch_tile_fills = []
        grid_min_x = -tx / grid_size
        grid_min_y = -ty / grid_size
        grid_max_x = (width - tx) / grid_size
        grid_max_y = (height - ty) / grid_size

        hatch_distance_limit = 2.0 * grid_size
        underlay_color = self.styles.get("hatching_underlay_color", "#C0C0C0")
        min_stroke = self.styles.get("hatching_stroke_width_min", 1.5)
        max_stroke = self.styles.get("hatching_stroke_width_max", 2.0)

        for gx in range(math.floor(grid_min_x), math.ceil(grid_max_x)):
            for gy in range(math.floor(grid_min_y), math.ceil(grid_max_y)):
                tile_center_px = Point((gx + 0.5) * grid_size, (gy + 0.5) * grid_size)
                if unified_geometry.contains(tile_center_px):
                    continue

                distance_to_dungeon = unified_geometry.boundary.distance(tile_center_px)
                if distance_to_dungeon > hatch_distance_limit:
                    continue

                # Add a grey fill for the tile before adding hatches
                hatch_tile_fills.append(
                    f'<rect x="{gx * grid_size}" y="{gy * grid_size}" width="{grid_size}" height="{grid_size}" fill="{underlay_color}" />'
                )

                noise_radius = grid_size * 0.1
                disp_x = noise.pnoise2(gx * 0.5, gy * 0.5, base=1) * noise_radius
                disp_y = noise.pnoise2(gx * 0.5, gy * 0.5, base=2) * noise_radius
                cluster_anchor = (
                    (gx + 0.5) * grid_size + disp_x,
                    (gy + 0.5) * grid_size + disp_y,
                )

                tile_corners = [
                    (gx * grid_size, gy * grid_size),  # Top-Left (0)
                    ((gx + 1) * grid_size, gy * grid_size),  # Top-Right (1)
                    ((gx + 1) * grid_size, (gy + 1) * grid_size),  # Bottom-Right (2)
                    (gx * grid_size, (gy + 1) * grid_size),  # Bottom-Left (3)
                ]

                def get_edge_index(p, gx, gy):
                    gs = grid_size
                    if abs(p[1] - gy * gs) < 1e-6:
                        return 0
                    if abs(p[0] - (gx + 1) * gs) < 1e-6:
                        return 1
                    if abs(p[1] - (gy + 1) * gs) < 1e-6:
                        return 2
                    return 3

                def walk_perimeter(start_point, start_edge, distance):
                    current_pos = start_point
                    current_edge = start_edge

                    dist_to_corner = 0
                    if current_edge == 0:
                        dist_to_corner = tile_corners[1][0] - current_pos[0]
                    elif current_edge == 1:
                        dist_to_corner = tile_corners[2][1] - current_pos[1]
                    elif current_edge == 2:
                        dist_to_corner = current_pos[0] - tile_corners[3][0]
                    elif current_edge == 3:
                        dist_to_corner = current_pos[1] - tile_corners[0][1]

                    while distance > dist_to_corner:
                        distance -= dist_to_corner
                        current_edge = (current_edge + 1) % 4
                        current_pos = tile_corners[current_edge]
                        dist_to_corner = grid_size

                    if current_edge == 0:
                        return (current_pos[0] + distance, current_pos[1])
                    if current_edge == 1:
                        return (current_pos[0], current_pos[1] + distance)
                    if current_edge == 2:
                        return (current_pos[0] - distance, current_pos[1])
                    return (current_pos[0], current_pos[1] - distance)

                start_edge = random.randint(0, 3)
                p1_coord = random.uniform(0, grid_size)

                if start_edge == 0:
                    p1 = (tile_corners[0][0] + p1_coord, tile_corners[0][1])
                elif start_edge == 1:
                    p1 = (tile_corners[1][0], tile_corners[1][1] + p1_coord)
                elif start_edge == 2:
                    p1 = (tile_corners[2][0] - p1_coord, tile_corners[2][1])
                else:
                    p1 = (tile_corners[3][0], tile_corners[3][1] - p1_coord)

                walk_dist = 1.20 * grid_size
                p2 = walk_perimeter(p1, start_edge, walk_dist)
                p3 = walk_perimeter(p2, get_edge_index(p2, gx, gy), walk_dist)

                section_points = sorted(
                    [p1, p2, p3],
                    key=lambda p: math.atan2(
                        p[1] - cluster_anchor[1], p[0] - cluster_anchor[0]
                    ),
                )

                sections = []
                for i in range(3):
                    p1_sec = section_points[i]
                    p2_sec = section_points[(i + 1) % 3]
                    path_vertices = [cluster_anchor, p1_sec]

                    idx1, idx2 = get_edge_index(p1_sec, gx, gy), get_edge_index(p2_sec, gx, gy)

                    j = idx1
                    while j != idx2:
                        path_vertices.append(tile_corners[(j + 1) % 4])
                        j = (j + 1) % 4

                    path_vertices.append(p2_sec)
                    sections.append(Polygon(path_vertices))

                for i, section in enumerate(sections):
                    if i == 0:
                        p1_sec = section_points[0]
                        p2_sec = section_points[1]
                        angle = math.atan2(p2_sec[1] - p1_sec[1], p2_sec[0] - p1_sec[0])
                    else:
                        angle = random.uniform(0, math.pi)

                    section_bounds = section.bounds
                    sec_width = section_bounds[2] - section_bounds[0]
                    sec_height = section_bounds[3] - section_bounds[1]
                    diag = math.hypot(sec_width, sec_height)

                    spacing = grid_size * 0.20
                    num_lines_in_cluster = max(3, int(diag / spacing))

                    for j in range(num_lines_in_cluster):
                        offset = (j - (num_lines_in_cluster - 1) / 2) * spacing

                        line_start = (
                            section.centroid.x + math.cos(angle + math.pi / 2) * offset,
                            section.centroid.y + math.sin(angle + math.pi / 2) * offset,
                        )
                        long_line = LineString(
                            [
                                (
                                    line_start[0] - math.cos(angle) * diag,
                                    line_start[1] - math.sin(angle) * diag,
                                ),
                                (
                                    line_start[0] + math.cos(angle) * diag,
                                    line_start[1] + math.sin(angle) * diag,
                                ),
                            ]
                        )

                        clipped_line = section.intersection(long_line)
                        if not clipped_line.is_empty and isinstance(clipped_line, LineString):
                            p1, p2 = list(clipped_line.coords)
                            wobble_strength = grid_size * 0.03
                            p1 = (
                                p1[0]
                                + noise.pnoise2(p1[0] * 0.1, p1[1] * 0.1, base=10)
                                * wobble_strength,
                                p1[1]
                                + noise.pnoise2(p1[0] * 0.1, p1[1] * 0.1, base=11)
                                * wobble_strength,
                            )
                            p2 = (
                                p2[0]
                                + noise.pnoise2(p2[0] * 0.1, p2[1] * 0.1, base=12)
                                * wobble_strength,
                                p2[1]
                                + noise.pnoise2(p2[0] * 0.1, p2[1] * 0.1, base=13)
                                * wobble_strength,
                            )
                            stroke_w = (
                                f'stroke-width="{random.uniform(min_stroke, max_stroke):.2f}"'
                            )
                            hatch_lines.append(
                                f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" {stroke_w}/>'
                            )
        return hatch_lines, hatch_tile_fills

    def generate_stipple_hatching(
        self, pixel_contour: np.ndarray, density: float, grid_size: int
    ) -> list[str]:
        """Generates a stippled, dotted effect along the perimeter."""
        stipples = []
        contour_points = pixel_contour.squeeze()
        if len(contour_points) < 2:
            return []

        edges = np.append(contour_points, [contour_points[0]], axis=0)
        for i in range(len(edges) - 1):
            p1, p2 = edges[i], edges[i + 1]
            edge_len = np.linalg.norm(p2 - p1)
            if edge_len < 1:
                continue
            norm = np.array([-(p2[1] - p1[1]), p2[0] - p1[0]]) / edge_len
            num_dots = int(edge_len / 2 * density)
            for _ in range(num_dots):
                r = random.uniform(0.0, 1.0)
                offset = random.gauss(8, 3)  # Gaussian distribution for offset
                radius = random.uniform(0.5, 1.5)
                cx, cy = p1 + (p2 - p1) * r + norm * offset
                stipples.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{radius:.2f}" />')
        return stipples
