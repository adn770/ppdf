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
    if len(vertices) < 2: return []
    edges = vertices + [vertices[0]]
    for i in range(len(edges) - 1):
        p1, p2 = edges[i], edges[i+1]
        dx, dy = (p2.x - p1.x) * scale, (p2.y - p1.y) * scale
        edge_len = math.hypot(dx, dy)
        if edge_len == 0: continue
        norm_x, norm_y = -dy / edge_len, dx / edge_len
        for _ in range(int(edge_len / 15 * density)):
            r, angle, length, offset = random.uniform(0.1, 0.9), random.uniform(-0.2, 0.2), random.uniform(5, 15), random.uniform(2, 6)
            mid_x, mid_y = p1.x * scale + dx * r, p1.y * scale + dy * r
            sx, sy = mid_x + norm_x * offset, mid_y + norm_y * offset
            ex = sx + (norm_x * math.cos(angle) - norm_y * math.sin(angle)) * length
            ey = sy + (norm_x * math.sin(angle) + norm_y * math.cos(angle)) * length
            hatch_lines.append(f'<line x1="{sx:.2f}" y1="{sy:.2f}" x2="{ex:.2f}" y2="{ey:.2f}" />')
    return hatch_lines


def _render_feature(obj: schema.Feature, scale: float, styles: dict) -> str:
    """Renders a single Feature object based on its type."""
    points = _get_polygon_points_str(obj.gridVertices, scale)
    if obj.featureType == "column":
        # Render columns with a gray fill and thin outline
        return f'<polygon points="{points}" fill="#cccccc" stroke="{styles["wall_color"]}" stroke-width="1.5" />'
    # Generic fallback for other features
    return f'<polygon points="{points}" fill="none" stroke="{styles["wall_color"]}" stroke-width="3" />'


def render_svg(map_data: schema.MapData, style_options: dict) -> str:
    """Generates a final, fully detailed SVG from the map data."""
    labels_to_render = style_options.get('rooms')
    objects = map_data.mapObjects
    if labels_to_render:
        rooms = [o for o in objects if isinstance(o, schema.Room) and o.label in labels_to_render]
        r_ids = {r.id for r in rooms}
        doors = [o for o in objects if isinstance(o, schema.Door) and all(c in r_ids for c in o.connects)]
        features = [o for o in objects if isinstance(o, schema.Feature) and any(o.id in r.contents for r in rooms if r.contents)]
        objects = rooms + doors + features
    if not objects: return '<svg width="200" height="100"><text x="10" y="50">No objects to render.</text></svg>'

    styles = {"bg_color": "#EDE0CE", "room_color": "#F7EEDE", "wall_color": "#000000", "shadow_color": "#999999", "glow_color": "#C9C1B1", "line_thickness": 7.0, "hatch_density": 1.0, "water_color": "#77AADD"}
    styles.update({k: v for k, v in style_options.items() if v is not None})

    verts = [v for o in objects if isinstance(o, schema.Room) for v in o.gridVertices]
    if not verts: return '<svg width="200" height="100"><text x="10" y="50">No rooms to render.</text></svg>'
    min_x, max_x, min_y, max_y = min(v.x for v in verts), max(v.x for v in verts), min(v.y for v in verts), max(v.y for v in verts)
    width, height = (max_x - min_x) * PIXELS_PER_GRID + 2*PADDING, (max_y - min_y) * PIXELS_PER_GRID + 2*PADDING

    svg = [f'<svg width="{int(width)}" height="{int(height)}" xmlns="http://www.w3.org/2000/svg">', f'<defs><pattern id="water" patternUnits="userSpaceOnUse" width="20" height="20"><path d="M 0 5 Q 5 0, 10 5 T 20 5" stroke="{styles["water_color"]}" fill="none" opacity="0.5"/></pattern></defs>', f'<rect width="100%" height="100%" fill="{styles["bg_color"]}" />']
    tx, ty = PADDING - min_x * PIXELS_PER_GRID, PADDING - min_y * PIXELS_PER_GRID
    svg.append(f'<g transform="translate({tx:.2f} {ty:.2f})">')

    # Define layers
    layers = {"hatching": [], "shadows": [], "glows": [], "room_fills": [], "water": [], "features": [], "doors": [], "walls": []}
    rooms = [o for o in objects if isinstance(o, schema.Room)]
    for room in rooms:
        points = _get_polygon_points_str(room.gridVertices, PIXELS_PER_GRID)
        lt = styles["line_thickness"]
        layers["hatching"].extend(_generate_hatching(room.gridVertices, PIXELS_PER_GRID, styles["hatch_density"]))
        layers["shadows"].append(f'<polygon points="{points}" transform="translate(3,3)" fill="{styles["shadow_color"]}" stroke="{styles["shadow_color"]}" stroke-width="{lt}"/>')
        layers["glows"].append(f'<polygon points="{points}" fill="none" stroke="{styles["glow_color"]}" stroke-width="{lt*2.5}" stroke-opacity="0.4"/>')
        layers["room_fills"].append(f'<polygon points="{points}" fill="{styles["room_color"]}"/>')
        layers["walls"].append(f'<polygon points="{points}" fill="none" stroke="{styles["wall_color"]}" stroke-width="{lt}"/>')
        if room.properties.get('layer') == 'water':
            layers["water"].append(f'<polygon points="{points}" fill="url(#water)"/>')

    for obj in objects:
        if isinstance(obj, schema.Feature):
            layers["features"].append(_render_feature(obj, PIXELS_PER_GRID, styles))
        elif isinstance(obj, schema.Door):
            dw, dh = (4, PIXELS_PER_GRID*.4) if obj.orientation == "v" else (PIXELS_PER_GRID*.4, 4)
            dx, dy = (obj.gridPos.x*PIXELS_PER_GRID)-dw/2, (obj.gridPos.y*PIXELS_PER_GRID)-dh/2
            layers["doors"].append(f'<rect x="{dx}" y="{dy}" width="{dw}" height="{dh}" fill="{styles["wall_color"]}"/>')

    # Assemble SVG in render order
    svg.append(f'<g id="hatching" stroke="{styles["wall_color"]}" stroke-width="1.2">{"".join(layers["hatching"])}</g>')
    for name in ["shadows", "glows", "room_fills", "water", "features", "doors", "walls"]:
        svg.append(f'<g id="{name}">{"".join(layers[name])}</g>')
    svg.extend(['</g>', '</svg>'])
    return "\n".join(svg)
