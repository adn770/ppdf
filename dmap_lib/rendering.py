# --- dmap_lib/rendering.py ---
import math
import random

from dmap_lib import schema

PIXELS_PER_GRID = 40
PADDING = PIXELS_PER_GRID * 2  # More padding for hatching and effects


def _get_polygon_points_str(vertices: list[schema.GridPoint], scale: float) -> str:
    """Converts a list of grid vertices to an SVG polygon points string."""
    return " ".join(f"{v.x * scale},{v.y * scale}" for v in vertices)


def _generate_hatching(
    vertices: list[schema.GridPoint], scale: float, density: float
) -> list[str]:
    """Generates procedural hatching lines around a single polygon."""
    hatch_lines = []
    if len(vertices) < 2:
        return []

    # Close the loop for iteration
    edges = vertices + [vertices[0]]

    for i in range(len(edges) - 1):
        p1 = edges[i]
        p2 = edges[i+1]

        # Edge vector and length
        dx, dy = (p2.x - p1.x) * scale, (p2.y - p1.y) * scale
        edge_len = math.hypot(dx, dy)
        if edge_len == 0:
            continue

        # Outward normal vector
        norm_x, norm_y = -dy / edge_len, dx / edge_len

        # Generate hatches along this edge
        num_hatches = int(edge_len / 20 * density)
        for _ in range(num_hatches):
            # Pick a random point along the edge
            r = random.uniform(0.1, 0.9)
            mid_x, mid_y = p1.x * scale + dx * r, p1.y * scale + dy * r

            # Randomize hatch properties
            angle = random.uniform(-0.2, 0.2)  # Angle deviation from normal
            length = random.uniform(5, 15)
            offset = random.uniform(2, 6)

            # Calculate hatch start and end points
            h_start_x = mid_x + norm_x * offset
            h_start_y = mid_y + norm_y * offset
            h_end_x = h_start_x + (norm_x * math.cos(angle) - norm_y * math.sin(angle)) * length
            h_end_y = h_start_y + (norm_x * math.sin(angle) + norm_y * math.cos(angle)) * length

            hatch_lines.append(
                f'<line x1="{h_start_x:.2f}" y1="{h_start_y:.2f}" \
x2="{h_end_x:.2f}" y2="{h_end_y:.2f}" />'
            )
    return hatch_lines


def render_svg(map_data: schema.MapData, style_options: dict) -> str:
    """Generates a stylized SVG string representing the map data."""
    if not map_data.mapObjects:
        return '<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg">\
<text x="10" y="50">No map objects to render.</text></svg>'

    all_points = [
        v for obj in map_data.mapObjects
        if isinstance(obj, schema.Room) and obj.gridVertices for v in obj.gridVertices
    ]
    if not all_points:
        return '<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg">\
<text x="10" y="50">Map objects have no vertices.</text></svg>'

    # Define default styles based on the design document
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

    min_x = min(p.x for p in all_points)
    max_x = max(p.x for p in all_points)
    min_y = min(p.y for p in all_points)
    max_y = max(p.y for p in all_points)

    width = (max_x - min_x) * PIXELS_PER_GRID + (2 * PADDING)
    height = (max_y - min_y) * PIXELS_PER_GRID + (2 * PADDING)

    svg = [f'<svg width="{int(width)}" height="{int(height)}" \
xmlns="http://www.w3.org/2000/svg">']
    svg.append(f'  <rect width="100%" height="100%" fill="{styles["bg_color"]}" />')

    tx = PADDING - (min_x * PIXELS_PER_GRID)
    ty = PADDING - (min_y * PIXELS_PER_GRID)
    svg.append(f'  <g transform="translate({tx:.2f} {ty:.2f})">')

    # --- RENDER LAYERS ---
    hatching, shadows, glows, mains = [], [], [], []
    for obj in map_data.mapObjects:
        if not isinstance(obj, schema.Room):
            continue

        points = _get_polygon_points_str(obj.gridVertices, PIXELS_PER_GRID)
        hatching.extend(_generate_hatching(
            obj.gridVertices, PIXELS_PER_GRID, styles["hatch_density"]
        ))

        lt = styles["line_thickness"]
        shadows.append(f'<polygon points="{points}" transform="translate(3, 3)" \
fill="{styles["shadow_color"]}" stroke="{styles["shadow_color"]}" stroke-width="{lt}" />')

        glows.append(f'<polygon points="{points}" fill="none" \
stroke="{styles["glow_color"]}" stroke-width="{lt * 2.5}" stroke-opacity="0.4" />')

        mains.append(f'<polygon points="{points}" fill="{styles["room_color"]}" \
stroke="{styles["wall_color"]}" stroke-width="{lt}" />')

    # Assemble layers in order
    svg.append(f'    <g id="hatching" stroke="{styles["wall_color"]}" \
stroke-width="1.2">')
    svg.extend(f"      {line}" for line in hatching)
    svg.append('    </g>')
    svg.append(f'    <g id="shadows">{"".join(shadows)}</g>')
    svg.append(f'    <g id="glows">{"".join(glows)}</g>')
    svg.append(f'    <g id="mains">{"".join(mains)}</g>')

    svg.append('  </g>')
    svg.append('</svg>')
    return "\n".join(svg)
