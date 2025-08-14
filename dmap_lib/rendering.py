import math
import random
import logging

import numpy as np
from dmap_lib import schema

log = logging.getLogger("dmap.render")

PIXELS_PER_GRID = 10
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
    """Generates a stylized SVG from a region-based MapData object."""
    log.info("Starting SVG rendering process...")
    # Flatten all objects from all regions for processing
    all_objects = [obj for region in map_data.regions for obj in region.mapObjects]
    objects = all_objects

    rooms_to_render_labels = style_options.pop("rooms", None)
    enable_hatching = style_options.pop("hatching", False)

    if rooms_to_render_labels:
        log.info("Filtering map to render only rooms: %s", rooms_to_render_labels)
        labels_set = set(rooms_to_render_labels)
        rooms = [
            o for o in all_objects if isinstance(o, schema.Room) and o.label in labels_set
        ]
        room_ids = {r.id for r in rooms}
        # Get doors connecting the filtered rooms
        doors = [
            o
            for o in all_objects
            if isinstance(o, schema.Door) and room_ids.intersection(o.connects)
        ]
        # Get features and layers contained within the filtered rooms
        child_ids = {cid for r in rooms if r.contents for cid in r.contents}
        children = [o for o in all_objects if o.id in child_ids]
        objects = rooms + doors + children
        log.debug("Filtered to %d total objects to render.", len(objects))

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
        "water_color": "#77AADD",
    }
    styles.update({k: v for k, v in style_options.items() if v is not None})
    log.debug("Using styles: %s", styles)

    room_verts = [v for o in objects if isinstance(o, schema.Room) for v in o.gridVertices]
    if not room_verts:
        log.warning("No rooms with vertices found to render.")
        return "<svg><text>No rooms to render.</text></svg>"

    min_x = min(v.x for v in room_verts)
    max_x = max(v.x for v in room_verts)
    min_y = min(v.y for v in room_verts)
    max_y = max(v.y for v in room_verts)
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
        "env_layers": [],
        "features": [],
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
            lt = styles["line_thickness"]
            dw, dh = (
                (lt, PIXELS_PER_GRID * 0.5)
                if obj.orientation == "v"
                else (PIXELS_PER_GRID * 0.5, lt)
            )
            dx = (obj.gridPos.x * PIXELS_PER_GRID) - dw / 2
            dy = (obj.gridPos.y * PIXELS_PER_GRID) - dh / 2
            layers["doors"].append(
                f'<rect x="{dx}" y="{dy}" width="{dw}" height="{dh}" fill="{styles["room_color"]}" stroke="{styles["wall_color"]}" stroke-width="1.5" />'
            )
        elif isinstance(obj, schema.EnvironmentalLayer):
            points = _get_polygon_points_str(obj.gridVertices, PIXELS_PER_GRID)
            color = styles.get(f"{obj.layerType}_color", "#808080")  # Default to gray
            layers["env_layers"].append(
                f'<polygon points="{points}" fill="{color}" fill-opacity="0.5" />'
            )
        elif isinstance(obj, schema.Feature):
            points = _get_polygon_points_str(obj.gridVertices, PIXELS_PER_GRID)
            layers["features"].append(
                f'<polygon points="{points}" fill="none" stroke="{styles["wall_color"]}" stroke-width="2.0"/>'
            )

    if unified_contours and enable_hatching:
        log.info(
            "Generating hatching for unified geometry (%d contours).", len(unified_contours)
        )
        for contour in unified_contours:
            layers["hatching"].extend(_generate_hatching(contour, styles["hatch_density"]))
        log.debug("Generated %d total hatching lines.", len(layers["hatching"]))
        svg.append(
            f'<g id="hatching" stroke="{styles["wall_color"]}" stroke-width="1.2">{"".join(layers["hatching"])}</g>'
        )

    # Render layers in specified order for correct visual appearance
    render_order = [
        "shadows",
        "glows",
        "room_fills",
        "env_layers",
        "features",
        "doors",
        "walls",
    ]
    for name in render_order:
        svg.append(f'<g id="{name}">{"".join(layers[name])}</g>')

    svg.extend(["</g>", "</svg>"])
    log.info("SVG rendering complete.")
    return "\n".join(svg)


class ASCIIRenderer:
    """Renders a high-fidelity ASCII art diagram of a map for debugging."""

    def __init__(self):
        """Initializes the renderer."""
        self.canvas = []
        self.width = 0
        self.height = 0

    def render_from_json(self, map_data: schema.MapData):
        """Renders the map from the final MapData structure."""
        from dmap_lib.analysis import _TileData  # Avoid circular import at top level

        all_objects = [obj for r in map_data.regions for obj in r.mapObjects]
        if not all_objects:
            return

        all_verts = [
            v for o in all_objects if hasattr(o, "gridVertices") for v in o.gridVertices
        ]
        if not all_verts:
            return

        min_x, max_x = min(v.x for v in all_verts), max(v.x for v in all_verts)
        min_y, max_y = min(v.y for v in all_verts), max(v.y for v in all_verts)

        tile_grid = {}
        for y in range(min_y - 1, max_y + 2):
            for x in range(min_x - 1, max_x + 2):
                tile_grid[(x, y)] = _TileData(feature_type="empty")

        for obj in all_objects:
            if isinstance(obj, schema.Room):
                r_min_x = min(v.x for v in obj.gridVertices)
                r_max_x = max(v.x for v in obj.gridVertices)
                r_min_y = min(v.y for v in obj.gridVertices)
                r_max_y = max(v.y for v in obj.gridVertices)
                for y in range(r_min_y, r_max_y + 1):
                    for x in range(r_min_x, r_max_x + 1):
                        if (x, y) in tile_grid:
                            tile_grid[(x, y)].feature_type = "floor"

        for (x, y), tile in tile_grid.items():
            if tile.feature_type == "empty":
                continue
            if tile_grid.get((x, y - 1)).feature_type == "empty":
                tile.north_wall = "stone"
            if tile_grid.get((x + 1, y)).feature_type == "empty":
                tile.east_wall = "stone"
            if tile_grid.get((x, y + 1)).feature_type == "empty":
                tile.south_wall = "stone"
            if tile_grid.get((x - 1, y)).feature_type == "empty":
                tile.west_wall = "stone"

        for obj in all_objects:
            if isinstance(obj, schema.Door):
                x, y = obj.gridPos.x, obj.gridPos.y
                if tile_grid.get((x, y)):
                    tile_grid[(x, y)].feature_type = "door"

        self.render_from_tiles(tile_grid)

    def render_from_tiles(self, tile_grid: dict):
        """Renders the map from an intermediate tile grid using box-drawing characters."""
        if not tile_grid:
            return

        # Grid is now 1-based, so min_x and min_y are 1.
        max_x = max(p[0] for p in tile_grid.keys())
        max_y = max(p[1] for p in tile_grid.keys())

        padding = 1
        self.width = max_x * 2 + 1 + (2 * padding)
        self.height = max_y * 2 + 1 + (2 * padding)
        self.canvas = [[" " for _ in range(self.width)] for _ in range(self.height)]

        char_map = {"floor": ".", "column": "O", "empty": " ", "door": "+"}

        # Pass 1: Draw features
        for (gx, gy), tile in tile_grid.items():
            cx = (gx - 1) * 2 + 1 + padding
            cy = (gy - 1) * 2 + 1 + padding
            if 0 <= cy < self.height and 0 <= cx < self.width:
                self.canvas[cy][cx] = char_map.get(tile.feature_type, "?")

        # Pass 2: Draw walls and doors
        for (gx, gy), tile in tile_grid.items():
            cx_base = (gx - 1) * 2 + padding
            cy_base = (gy - 1) * 2 + padding
            if tile.north_wall:
                self.canvas[cy_base][cx_base + 1] = "+" if tile.north_wall == "door" else "─"
            if tile.west_wall:
                self.canvas[cy_base + 1][cx_base] = "+" if tile.west_wall == "door" else "│"
            if tile.south_wall:
                self.canvas[cy_base + 2][cx_base + 1] = (
                    "+" if tile.south_wall == "door" else "─"
                )
            if tile.east_wall:
                self.canvas[cy_base + 1][cx_base + 2] = (
                    "+" if tile.east_wall == "door" else "│"
                )

        # Pass 3: Draw intersections
        junctions = {
            (0, 1, 1, 0): "┌",
            (0, 0, 1, 1): "┐",
            (1, 1, 0, 0): "└",
            (1, 0, 0, 1): "┘",
            (1, 1, 1, 0): "├",
            (1, 0, 1, 1): "┤",
            (0, 1, 1, 1): "┬",
            (1, 1, 0, 1): "┴",
            (1, 1, 1, 1): "┼",
            (0, 1, 0, 1): "─",
            (1, 0, 1, 0): "│",
        }
        for gy in range(1, max_y + 2):
            for gx in range(1, max_x + 2):
                cx = (gx - 1) * 2 + padding
                cy = (gy - 1) * 2 + padding
                if not (0 <= cy < self.height and 0 <= cx < self.width):
                    continue

                n = self.canvas[cy - 1][cx] in "│+" if cy > 0 else False
                s = self.canvas[cy + 1][cx] in "│+" if cy < self.height - 1 else False
                w = self.canvas[cy][cx - 1] in "─+" if cx > 0 else False
                e = self.canvas[cy][cx + 1] in "─+" if cx < self.width - 1 else False

                key = (n, e, s, w)
                if key in junctions:
                    self.canvas[cy][cx] = junctions[key]
                elif sum(key) == 1:  # End caps
                    if n:
                        self.canvas[cy][cx] = "╵"
                    elif s:
                        self.canvas[cy][cx] = "╷"
                    elif w:
                        self.canvas[cy][cx] = "╴"
                    elif e:
                        self.canvas[cy][cx] = "╶"

    def get_output(self) -> str:
        """Returns the final, rendered ASCII map as a single string."""
        return "\n".join("".join(row) for row in self.canvas)
