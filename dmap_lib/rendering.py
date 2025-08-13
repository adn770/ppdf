# --- dmap_lib/rendering.py ---
from dmap_lib import schema

# Constants for rendering. These will be made configurable later.
PIXELS_PER_GRID = 40
PADDING = PIXELS_PER_GRID  # An empty margin around the map


def render_svg(map_data: schema.MapData, style_options: dict) -> str:
    """
    Generates an SVG string representing the map data.

    Args:
        map_data: The structured map data to render.
        style_options: A dictionary of styling parameters (unused in this milestone).

    Returns:
        A string containing the complete SVG file content.
    """
    if not map_data.mapObjects:
        return '<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg">\
<text x="10" y="50">No map objects to render.</text></svg>'

    # Find the bounding box of the entire map in grid coordinates
    all_points = [
        v for obj in map_data.mapObjects
        if isinstance(obj, schema.Room) and obj.gridVertices
        for v in obj.gridVertices
    ]
    if not all_points:
        return '<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg">\
<text x="10" y="50">Map objects have no vertices.</text></svg>'

    min_x = min(p.x for p in all_points)
    max_x = max(p.x for p in all_points)
    min_y = min(p.y for p in all_points)
    max_y = max(p.y for p in all_points)

    # Calculate final SVG dimensions in pixels
    width = (max_x - min_x + 1) * PIXELS_PER_GRID + (2 * PADDING)
    height = (max_y - min_y + 1) * PIXELS_PER_GRID + (2 * PADDING)

    svg_parts = [
        f'<svg width="{int(width)}" height="{int(height)}" \
xmlns="http://www.w3.org/2000/svg">'
    ]
    svg_parts.append(f'  <rect width="100%" height="100%" fill="#F7EEDE" />')

    # Use a group transform to shift the map away from the SVG origin (0,0)
    transform_x = PADDING - (min_x * PIXELS_PER_GRID)
    transform_y = PADDING - (min_y * PIXELS_PER_GRID)
    svg_parts.append(f'  <g transform="translate({transform_x} {transform_y})">')

    # Draw each room as a simple polygon
    for obj in map_data.mapObjects:
        if isinstance(obj, schema.Room):
            points_str = " ".join(
                f"{v.x * PIXELS_PER_GRID},{v.y * PIXELS_PER_GRID}"
                for v in obj.gridVertices
            )
            svg_parts.append(
                f'    <polygon points="{points_str}" '
                'fill="#cccccc" stroke="black" stroke-width="2" />'
            )

    svg_parts.append('  </g>')
    svg_parts.append('</svg>')
    return "\n".join(svg_parts)
