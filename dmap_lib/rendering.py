# --- dmap_lib/rendering.py ---
import math
import random

from dmap_lib import schema

PIXELS_PER_GRID = 40
PADDING = PIXELS_PER_GRID * 2


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
    edges = vertices + [vertices[0]]
    for i in range(len(edges) - 1):
        p1, p2 = edges[i], edges[i+1]
        dx, dy, edge_len = (p2.x - p1.x) * scale, (p2.y - p1.y) * scale, 0
        edge_len = math.hypot(dx, dy)
        if edge_len == 0: continue
        norm_x, norm_y = -dy / edge_len, dx / edge_len
        for _ in range(int(edge_len / 20 * density)):
            r = random.uniform(0.1, 0.9)
            mid_x, mid_y = p1.x * scale + dx * r, p1.y * scale + dy * r
            angle, length, offset = random.uniform(-0.2, 0.2), random.uniform(5, 15), random.uniform(2, 6)
            h_start_x = mid_x + norm_x * offset
            h_start_y = mid_y + norm_y * offset
            h_end_x = h_start_x + (norm_x * math.cos(angle) - norm_y * math.sin(angle)) * length
            h_end_y = h_start_y + (norm_x * math.sin(angle) + norm_y * math.cos(angle)) * length
            hatch_lines.append(f'<line x1="{h_start_x:.2f}" y1="{h_start_y:.2f}" \
x2="{h_end_x:.2f}" y2="{h_end_y:.2f}" />')
    return hatch_lines


def render_svg(map_data: schema.MapData, style_options: dict) -> str:
    """Generates a stylized SVG string representing all or part of the map data."""
    room_labels_to_render = style_options.get('rooms')
    objects_to_render = map_data.mapObjects
    if room_labels_to_render:
        selected_rooms = [o for o in map_data.mapObjects if isinstance(o, schema.Room) and o.label in room_labels_to_render]
        selected_room_ids = {r.id for r in selected_rooms}
        selected_doors = [o for o in map_data.mapObjects if isinstance(o, schema.Door) and all(c in selected_room_ids for c in o.connects)]
        objects_to_render = selected_rooms + selected_doors

    if not objects_to_render:
        return '<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg"><text x="10" y="50">No matching objects to render.</text></svg>'

    styles = {"bg_color": "#EDE0CE", "room_color": "#F7EEDE", "wall_color": "#000000", "shadow_color": "#999999", "glow_color": "#C9C1B1", "line_thickness": 7.0, "hatch_density": 1.0}
    styles.update({k: v for k, v in style_options.items() if v is not None})

    all_verts = [v for o in objects_to_render if isinstance(o, schema.Room) for v in o.gridVertices]
    if not all_verts: return '<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg"><text x="10" y="50">No rooms to render.</text></svg>'

    min_x, max_x = min(v.x for v in all_verts), max(v.x for v in all_verts)
    min_y, max_y = min(v.y for v in all_verts), max(v.y for v in all_verts)
    width, height = (max_x - min_x) * PIXELS_PER_GRID + (2 * PADDING), (max_y - min_y) * PIXELS_PER_GRID + (2 * PADDING)

    svg = [f'<svg width="{int(width)}" height="{int(height)}" xmlns="http://www.w3.org/2000/svg">', f'<rect width="100%" height="100%" fill="{styles["bg_color"]}" />']
    tx, ty = PADDING - (min_x * PIXELS_PER_GRID), PADDING - (min_y * PIXELS_PER_GRID)
    svg.append(f'<g transform="translate({tx:.2f} {ty:.2f})">')

    hatching, shadows, glows, mains = [], [], [], []
    for obj in objects_to_render:
        if isinstance(obj, schema.Room):
            points = _get_polygon_points_str(obj.gridVertices, PIXELS_PER_GRID)
            lt = styles["line_thickness"]
            hatching.extend(_generate_hatching(obj.gridVertices, PIXELS_PER_GRID, styles["hatch_density"]))
            shadows.append(f'<polygon points="{points}" transform="translate(3, 3)" fill="{styles["shadow_color"]}" stroke="{styles["shadow_color"]}" stroke-width="{lt}" />')
            glows.append(f'<polygon points="{points}" fill="none" stroke="{styles["glow_color"]}" stroke-width="{lt * 2.5}" stroke-opacity="0.4" />')
            mains.append(f'<polygon points="{points}" fill="{styles["room_color"]}" stroke="{styles["wall_color"]}" stroke-width="{lt}" />')
        elif isinstance(obj, schema.Door):
            dw, dh = (4, PIXELS_PER_GRID * 0.4) if obj.orientation == "vertical" else (PIXELS_PER_GRID * 0.4, 4)
            dx, dy = (obj.gridPos.x * PIXELS_PER_GRID) - dw/2, (obj.gridPos.y * PIXELS_PER_GRID) - dh/2
            mains.append(f'<rect x="{dx}" y="{dy}" width="{dw}" height="{dh}" fill="{styles["wall_color"]}" />')

    svg.append(f'<g id="hatching" stroke="{styles["wall_color"]}" stroke-width="1.2">{"".join(hatching)}</g>')
    svg.extend([f'<g id="shadows">{"".join(shadows)}</g>', f'<g id="glows">{"".join(glows)}</g>', f'<g id="mains">{"".join(mains)}</g>'])
    svg.extend(['</g>', '</svg>'])
    return "\n".join(svg)
