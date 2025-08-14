# --- dmap_lib/rendering.py ---
import math
import random
import logging

import numpy as np
from dmap_lib import schema

log = logging.getLogger("dmap.render")

PIXELS_PER_GRID = 40
PADDING = PIXELS_PER_GRID * 2


def _get_polygon_points_str(vertices: list[schema.GridPoint], scale: float) -> str:
    """Converts a list of grid vertices to an SVG polygon points string."""
    return " ".join(f"{v.x * scale},{v.y * scale}" for v in vertices)


def _generate_hatching(pixel_contour: np.ndarray, density: float) -> list[str]:
    """Generates procedural hatching lines around a single pixel-based contour."""
    hatch_lines = []
    contour_points = pixel_contour.squeeze()
    if len(contour_points) < 2:
        return []

    edges = np.append(contour_points, [contour_points[0]], axis=0)
    for i in range(len(edges) - 1):
        p1, p2 = edges[i], edges[i + 1]
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        edge_len = math.hypot(dx, dy)
        if edge_len < 1:
            continue

        norm_x, norm_y = -dy / edge_len, dx / edge_len
        num_hatches = int(edge_len / 15 * density)
        for _ in range(num_hatches):
            r, angle, length, offset = (
                random.uniform(0.1, 0.9),
                random.uniform(-0.2, 0.2),
                random.uniform(5, 15),
                random.uniform(2, 6),
            )
            sx, sy = p1[0] + dx * r + norm_x * offset, p1[1] + dy * r + norm_y * offset
            ex = sx + (norm_x * math.cos(angle) - norm_y * math.sin(angle)) * length
            ey = sy + (norm_x * math.sin(angle) + norm_y * math.cos(angle)) * length
            hatch_lines.append(
                f'<line x1="{sx:.2f}" y1="{sy:.2f}" x2="{ex:.2f}" y2="{ey:.2f}" />'
            )
    return hatch_lines


def render_svg(
    map_data: schema.MapData, unified_contours: list | None, style_options: dict
) -> str:
    """Generates a stylized SVG, using unified geometry for hatching."""
    log.info("Starting SVG rendering process...")
    objects = map_data.mapObjects
    if not objects:
        log.warning("No map objects to render.")
        return "<svg><text>No objects to render.</text></svg>"

    styles = {
        "bg_color": "#EDE0CE",
        "room_color": "#F7EEDE",
        "wall_color": "#000000",
        "shadow_color": "#999999",
        "glow_color": "#C9C1B1",
        "line_thickness": 7.0,
        "hatch_density": 1.0,
    }
    styles.update({k: v for k, v in style_options.items() if v is not None})
    log.debug("Using styles: %s", styles)

    verts = [v for o in objects if isinstance(o, schema.Room) for v in o.gridVertices]
    if not verts:
        log.warning("No rooms with vertices found to render.")
        return "<svg><text>No rooms to render.</text></svg>"

    min_x, max_x = min(v.x for v in verts), max(v.x for v in verts)
    min_y, max_y = min(v.y for v in verts), max(v.y for v in verts)
    width = (max_x - min_x) * PIXELS_PER_GRID + 2 * PADDING
    height = (max_y - min_y) * PIXELS_PER_GRID + 2 * PADDING
    log.debug("Calculated SVG canvas dimensions: %dx%d", width, height)

    svg = [
        f'<svg width="{int(width)}" height="{int(height)}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="100%" height="100%" fill="{styles["bg_color"]}" />',
    ]
    tx, ty = PADDING - min_x * PIXELS_PER_GRID, PADDING - min_y * PIXELS_PER_GRID
    svg.append(f'<g transform="translate({tx:.2f} {ty:.2f})">')

    layers = {
        "hatching": [],
        "shadows": [],
        "glows": [],
        "room_fills": [],
        "doors": [],
        "walls": [],
    }

    for obj in objects:
        if isinstance(obj, schema.Room):
            points = _get_polygon_points_str(obj.gridVertices, PIXELS_PER_GRID)
            lt = styles["line_thickness"]
            layers["shadows"].append(
                f'<polygon points="{points}" transform="translate(3,3)" fill="{styles["shadow_color"]}" stroke="{styles["shadow_color"]}" stroke-width="{lt}"/>'
            )
            layers["glows"].append(
                f'<polygon points="{points}" fill="none" stroke="{styles["glow_color"]}" stroke-width="{lt*2.5}" stroke-opacity="0.4"/>'
            )
            layers["room_fills"].append(
                f'<polygon points="{points}" fill="{styles["room_color"]}"/>'
            )
            layers["walls"].append(
                f'<polygon points="{points}" fill="none" stroke="{styles["wall_color"]}" stroke-width="{lt}"/>'
            )
        elif isinstance(obj, schema.Door):
            dw, dh = (
                (lt, PIXELS_PER_GRID * 0.5)
                if obj.orientation == "v"
                else (PIXELS_PER_GRID * 0.5, lt)
            )
            dx, dy = (obj.gridPos.x * PIXELS_PER_GRID) - dw / 2, (
                obj.gridPos.y * PIXELS_PER_GRID
            ) - dh / 2
            layers["doors"].append(
                f'<rect x="{dx}" y="{dy}" width="{dw}" height="{dh}" fill="{styles["room_color"]}" stroke="{styles["wall_color"]}" stroke-width="1.5" />'
            )

    if unified_contours:
        log.info(
            "Generating hatching for unified geometry (%d contours).", len(unified_contours)
        )
        for contour in unified_contours:
            layers["hatching"].extend(_generate_hatching(contour, styles["hatch_density"]))
    log.debug("Generated %d total hatching lines.", len(layers["hatching"]))

    svg.append(
        f'<g id="hatching" stroke="{styles["wall_color"]}" stroke-width="1.2">{"".join(layers["hatching"])}</g>'
    )
    for name in ["shadows", "glows", "room_fills", "doors", "walls"]:
        svg.append(f'<g id="{name}">{"".join(layers[name])}</g>')

    svg.extend(["</g>", "</svg>"])
    log.info("SVG rendering complete.")
    return "\n".join(svg)
