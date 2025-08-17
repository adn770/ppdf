# --- dmap_lib/rendering.py ---
import math
import random
import logging
import uuid
from typing import List, Tuple, Dict, Any
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import noise
from shapely.geometry import Point, Polygon, MultiPolygon, LineString
from shapely.ops import unary_union

from dmap_lib import schema
from dmap_lib.analysis.context import _TileData

log = logging.getLogger("dmap.render")

PIXELS_PER_GRID = 70
PADDING = PIXELS_PER_GRID * 2


@dataclass
class _RenderableShape:
    """An intermediate object to hold complex geometry for rendering."""
    id: str
    polygon: Polygon
    contents: List[str] | None = None
    roomType: str = "chamber"


def _get_polygon_points_str(vertices: list[schema.GridPoint], scale: float) -> str:
    """Converts a list of grid vertices to an SVG polygon points string."""
    return " ".join(f"{v.x * scale},{v.y * scale}" for v in vertices)


def _polygon_to_svg_path(polygon: Polygon, scale: float) -> str:
    """Converts a Shapely Polygon (with potential holes) to an SVG path string."""
    if polygon.is_empty:
        return ""

    # Exterior path
    path_data = " ".join(
        [
            f"{'M' if i == 0 else 'L'} {x * scale:.2f} {y * scale:.2f}"
            for i, (x, y) in enumerate(polygon.exterior.coords)
        ]
    )
    path_data += " Z"

    # Interior paths (holes)
    for interior in polygon.interiors:
        path_data += " "
        path_data += " ".join(
            [
                f"{'M' if i == 0 else 'L'} {x * scale:.2f} {y * scale:.2f}"
                for i, (x, y) in enumerate(interior.coords)
            ]
        )
        path_data += " Z"

    return path_data


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


def _create_curvy_path(
    polygon: Polygon,
    resolution: int,
    jitter: float,
    smoothing_strength: float,
    scale: float,
    seed: int,
) -> str:
    """Generates a smooth, organic, curvy SVG path from a Shapely Polygon."""
    if polygon.is_empty:
        return ""

    points = list(polygon.exterior.coords)

    # 1. Subdivide edges to create more vertices
    subdivided_points = []
    for i in range(len(points) - 1):
        p1 = np.array(points[i])
        p2 = np.array(points[i + 1])
        for j in range(resolution):
            subdivided_points.append(p1 + (p2 - p1) * (j / resolution))

    if not subdivided_points:
        return ""

    # 2. Perturb vertices using Perlin noise for a natural look
    perturbed_points = []
    octaves = 2
    freq = 10.0 / scale  # Noise frequency scales with the map

    for i, p in enumerate(subdivided_points):
        # Calculate normal vector
        p1 = np.array(p)
        p2 = np.array(subdivided_points[(i + 1) % len(subdivided_points)])
        edge_vec = p2 - p1
        if np.linalg.norm(edge_vec) == 0:
            continue
        normal_vec = np.array([-edge_vec[1], edge_vec[0]])
        normal_vec /= np.linalg.norm(normal_vec)

        # Get noise value (normalized from -1 to 1)
        noise_val = noise.pnoise2(p[0] * freq, p[1] * freq, octaves=octaves, base=seed)

        displacement = noise_val * jitter * scale
        perturbed_points.append(p1 + normal_vec * displacement)

    if not perturbed_points:
        return ""

    # 3. Apply a convolutional smoothing kernel (weighted moving average)
    smoothed_points = perturbed_points[:]
    num_points = len(perturbed_points)
    strength = max(0.0, min(1.0, smoothing_strength))

    for _ in range(3):  # Apply smoothing multiple times for a better effect
        for i in range(num_points):
            prev_pt = smoothed_points[(i - 1 + num_points) % num_points]
            curr_pt = smoothed_points[i]
            next_pt = smoothed_points[(i + 1) % num_points]

            # Weighted average: 25% previous, 50% current, 25% next
            new_pt = curr_pt * (1 - strength) + (prev_pt + next_pt) * (strength / 2)
            smoothed_points[i] = new_pt

    # 4. Create a smooth Catmull-Rom spline, converted to cubic Bézier for SVG
    path_data = f"M {smoothed_points[0][0]:.2f} {smoothed_points[0][1]:.2f}"
    pts = [smoothed_points[-1]] + smoothed_points + [smoothed_points[0], smoothed_points[1]]

    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        c1 = p1 + (p2 - p0) / 6.0
        c2 = p2 - (p3 - p1) / 6.0
        path_data += (
            f" C {c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {p2[0]:.2f},{p2[1]:.2f}"
        )

    return path_data


def _render_water_layer(layer: schema.EnvironmentalLayer, styles: dict) -> str:
    """Renders a water layer with a procedurally generated curvy ripple effect."""
    if not layer.gridVertices:
        return ""

    base_color = styles.get("water_base_color", "#AEC6CF")
    ripple_color = styles.get("water_ripple_color", "#77AADD")
    ripple_steps = styles.get("water_ripple_steps", 4)
    ripple_spacing = styles.get("water_ripple_spacing", 0.1) * PIXELS_PER_GRID
    resolution = styles.get("water_curve_resolution", 10)
    jitter = styles.get("water_curve_jitter", 0.3)
    smoothing = styles.get("water_curve_smoothing_strength", 0.5)

    poly = Polygon(
        [(v.x * PIXELS_PER_GRID, v.y * PIXELS_PER_GRID) for v in layer.gridVertices]
    )
    if poly.is_empty:
        return ""

    svg_parts = ['<g class="water-effect">']
    # Use a consistent seed for each water body for stable output
    seed = int(poly.centroid.x + poly.centroid.y)

    base_path_data = _create_curvy_path(
        poly, resolution, jitter, smoothing, PIXELS_PER_GRID, seed
    )
    if not base_path_data:
        return ""
    svg_parts.append(f'<path d="{base_path_data} Z" fill="{base_color}" />')

    for i in range(ripple_steps):
        ripple_jitter = jitter * (1 - (i + 1) / (ripple_steps + 1))
        inner_poly = poly.buffer(-(ripple_spacing * (i + 1)))
        if inner_poly.is_empty:
            break

        geoms = inner_poly.geoms if hasattr(inner_poly, "geoms") else [inner_poly]
        for geom in geoms:
            if geom.is_empty or not isinstance(geom, Polygon):
                continue
            ripple_path_data = _create_curvy_path(
                geom,
                resolution // (i + 1),
                ripple_jitter,
                smoothing,
                PIXELS_PER_GRID,
                seed + i + 1,
            )
            if ripple_path_data:
                svg_parts.append(
                    f'<path d="{ripple_path_data} Z" fill="none" stroke="{ripple_color}" stroke-width="1.5"/>'
                )

    svg_parts.append("</g>")
    return "".join(svg_parts)


def _merge_adjacent_rooms(
    rooms: List[schema.Room], doors: List[schema.Door]
) -> List[_RenderableShape]:
    """Merges adjacent rooms, preserving holes, into _RenderableShape objects."""
    if not rooms:
        return []

    log.info("Performing pre-render merge of %d rooms...", len(rooms))
    polygons = {
        room.id: Polygon([(v.x, v.y) for v in room.gridVertices]) for room in rooms
    }
    room_map = {room.id: room for room in rooms}

    # Build a set of all wall segments that contain a door
    door_walls = set()
    for door in doors:
        p = (door.gridPos.x, door.gridPos.y)
        if door.orientation == "h":
            wall = tuple(sorted(((p[0], p[1]), (p[0] + 1, p[1]))))
        else:  # 'v'
            wall = tuple(sorted(((p[0], p[1]), (p[0], p[1] + 1))))
        door_walls.add(wall)

    # Use a disjoint set union (DSU) data structure to track merged room groups
    parent = {room.id: room.id for room in rooms}

    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        root_i = find(i)
        root_j = find(j)
        if root_i != root_j:
            parent[root_j] = root_i

    # Iterate through all pairs of rooms to check for adjacency without doors
    room_ids = list(room_map.keys())
    for i in range(len(room_ids)):
        for j in range(i + 1, len(room_ids)):
            id1, id2 = room_ids[i], room_ids[j]
            if find(id1) == find(id2):
                continue
            poly1, poly2 = polygons[id1], polygons[id2]
            if poly1.touches(poly2):
                intersection = poly1.intersection(poly2)
                if isinstance(intersection, LineString) and intersection.length > 0.1:
                    coords = list(intersection.coords)
                    has_door = False
                    for k in range(len(coords) - 1):
                        wall = tuple(sorted((coords[k], coords[k + 1])))
                        if wall in door_walls:
                            has_door = True
                            break
                    if not has_door:
                        union(id1, id2)

    # Group rooms by their root parent in the DSU structure
    merged_groups = defaultdict(list)
    for room_id in room_ids:
        root = find(room_id)
        merged_groups[root].append(room_id)

    # Create the new list of renderable shapes
    final_shapes = []
    for root_id, group_ids in merged_groups.items():
        polys_to_merge = [polygons[rid] for rid in group_ids]
        merged_poly = unary_union(polys_to_merge).buffer(0)

        all_contents = []
        for rid in group_ids:
            if room_map[rid].contents:
                all_contents.extend(room_map[rid].contents)

        geometries = merged_poly.geoms if hasattr(merged_poly, "geoms") else [merged_poly]
        for geom in geometries:
            if isinstance(geom, Polygon) and not geom.is_empty:
                shape = _RenderableShape(
                    id=f"merged_{root_id}_{uuid.uuid4().hex[:4]}",
                    polygon=geom,
                    contents=list(set(all_contents)) or None,
                )
                final_shapes.append(shape)

    log.info(
        "Pre-render merge complete. Resulted in %d final shapes.", len(final_shapes)
    )
    return final_shapes


def render_svg(
    map_data: schema.MapData, unified_contours: list | None, style_options: dict
) -> str:
    """Generates a stylized SVG from a region-based MapData object."""
    log.info("Starting SVG rendering process...")
    all_objects = [obj for region in map_data.regions for obj in region.mapObjects]

    # --- Pre-processing Step: Merge open rooms before rendering ---
    original_rooms = [o for o in all_objects if isinstance(o, schema.Room)]
    doors = [o for o in all_objects if isinstance(o, schema.Door)]
    renderable_shapes = _merge_adjacent_rooms(original_rooms, doors)

    # Combine renderable shapes with other non-room objects
    non_room_objects = [o for o in all_objects if not isinstance(o, schema.Room)]
    objects_to_render = renderable_shapes + non_room_objects
    # --- End of pre-processing ---

    rooms_to_render_labels = style_options.pop("rooms", None)
    enable_hatching = style_options.pop("hatching", False)
    no_features = style_options.pop("no_features", False)

    if rooms_to_render_labels:
        # Note: Filtering by label is not supported with the new renderable shapes
        log.warning("Filtering by room labels is not currently supported with merged geometry.")

    if no_features:
        objects_to_render = [o for o in objects_to_render if not isinstance(o, schema.Feature)]
        log.info("Feature rendering disabled. Rendering %d objects.", len(objects_to_render))

    if not objects_to_render:
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
        "water_base_color": "#AEC6CF",
        "water_ripple_color": "#77AADD",
        "water_ripple_steps": 4,
        "water_ripple_spacing": 0.1,
        "water_curve_resolution": 10,
        "water_curve_jitter": 0.3,
        "water_curve_smoothing_strength": 0.5,
    }
    styles.update({k: v for k, v in style_options.items() if v is not None})
    log.debug("Using styles: %s", styles)

    all_verts = []
    for o in objects_to_render:
        if isinstance(o, _RenderableShape):
            all_verts.extend(o.polygon.exterior.coords)
        elif hasattr(o, "gridVertices"):
            all_verts.extend([(v.x, v.y) for v in o.gridVertices])

    if not all_verts:
        log.warning("No vertices found to render.")
        return "<svg><text>No rooms to render.</text></svg>"

    min_x = min(v[0] for v in all_verts)
    max_x = max(v[0] for v in all_verts)
    min_y = min(v[1] for v in all_verts)
    max_y = max(v[1] for v in all_verts)
    width = (max_x - min_x) * PIXELS_PER_GRID + 2 * PADDING
    height = (max_y - min_y) * PIXELS_PER_GRID + 2 * PADDING
    log.debug("Calculated SVG canvas dimensions: %dx%d", width, height)

    svg = [
        f'<svg width="{int(width)}" height="{int(height)}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="100%" height="100%" fill="{styles["bg_color"]}" />',
    ]
    tx, ty = PADDING - min_x * PIXELS_PER_GRID, PADDING - min_y * PIXELS_PER_GRID

    svg.append("<defs></defs>")
    svg.append(f'<g transform="translate({tx:.2f} {ty:.2f})">')

    layers = { "hatching": [], "shadows": [], "glows": [], "room_fills": [],
               "contents": [], "doors": [], "walls": [] }
    z_ordered_objects = []

    for obj in objects_to_render:
        if isinstance(obj, _RenderableShape):
            path_data = _polygon_to_svg_path(obj.polygon, PIXELS_PER_GRID)
            lt = styles["line_thickness"]
            layers["shadows"].append(
                f'<path d="{path_data}" transform="translate(3,3)" fill="{styles["shadow_color"]}" stroke="{styles["shadow_color"]}" stroke-width="{lt}" fill-rule="evenodd"/>'
            )
            layers["glows"].append(
                f'<path d="{path_data}" fill="none" stroke="{styles["glow_color"]}" stroke-width="{lt*2.5}" stroke-opacity="0.4"/>'
            )
            layers["room_fills"].append(
                f'<path d="{path_data}" fill="{styles["room_color"]}" fill-rule="evenodd"/>'
            )
            layers["walls"].append(
                f'<path d="{path_data}" fill="none" stroke="{styles["wall_color"]}" stroke-width="{lt}"/>'
            )
        elif isinstance(obj, schema.Door):
            lt = styles["line_thickness"]
            dw, dh = ( (lt, PIXELS_PER_GRID * 0.5) if obj.orientation == "v"
                       else (PIXELS_PER_GRID * 0.5, lt) )
            if obj.orientation == "v":
                dx = (obj.gridPos.x * PIXELS_PER_GRID) - dw / 2
                dy = ((obj.gridPos.y + 0.5) * PIXELS_PER_GRID) - dh / 2
            else:
                dx = ((obj.gridPos.x + 0.5) * PIXELS_PER_GRID) - dw / 2
                dy = (obj.gridPos.y * PIXELS_PER_GRID) - dh / 2
            layers["doors"].append(
                f'<rect x="{dx}" y="{dy}" width="{dw}" height="{dh}" fill="{styles["room_color"]}" stroke="{styles["wall_color"]}" stroke-width="5.0" />'
            )
        elif isinstance(obj, (schema.EnvironmentalLayer, schema.Feature)):
            z_ordered_objects.append(obj)

    z_ordered_objects.sort(key=lambda o: o.properties.get("z-order", 0) if o.properties else 0)
    for obj in z_ordered_objects:
        if isinstance(obj, schema.EnvironmentalLayer):
            if obj.layerType == "water":
                layers["contents"].append(_render_water_layer(obj, styles))
            else:
                points = _get_polygon_points_str(obj.gridVertices, PIXELS_PER_GRID)
                color = styles.get(f"{obj.layerType}_color", "#808080")
                layers["contents"].append(
                    f'<polygon points="{points}" fill="{color}" fill-opacity="0.5" />'
                )
        elif isinstance(obj, schema.Feature):
            points = _get_polygon_points_str(obj.gridVertices, PIXELS_PER_GRID)
            layers["contents"].append(
                f'<polygon points="{points}" fill="none" stroke="{styles["wall_color"]}" stroke-width="2.0"/>'
            )

    if unified_contours and enable_hatching:
        log.info("Generating hatching for unified geometry (%d contours).", len(unified_contours))
        for contour in unified_contours:
            layers["hatching"].extend(_generate_hatching(contour, styles["hatch_density"]))
        svg.append(f'<g id="hatching" stroke="{styles["wall_color"]}" stroke-width="1.2">{"".join(layers["hatching"])}</g>')

    render_order = ["shadows", "glows", "room_fills", "contents", "doors", "walls"]
    for name in render_order:
        svg.append(f'<g id="{name}">{"".join(layers[name])}</g>')

    svg.append("</g>")
    svg.append(f'<g id="grid" stroke="#AEC6CF" stroke-width="1" stroke-opacity="0.5">')
    x = tx % PIXELS_PER_GRID
    while x < width:
        svg.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{height}" />')
        x += PIXELS_PER_GRID
    y = ty % PIXELS_PER_GRID
    while y < height:
        svg.append(f'<line x1="0" y1="{y}" x2="{width}" y2="{y}" />')
        y += PIXELS_PER_GRID
    svg.append("</g>")
    svg.append("</svg>")
    log.info("SVG rendering complete.")
    return "\n".join(svg)


class ASCIIRenderer:
    """Renders a high-fidelity ASCII art diagram of a map for debugging."""

    def __init__(self):
        self.canvas: List[List[str]] = []
        self.width = 0
        self.height = 0
        self.min_x, self.max_x = 0, 0
        self.min_y, self.max_y = 0, 0
        self.padding = 1

    def render_from_json(self, map_data: schema.MapData):
        all_objects = [obj for r in map_data.regions for obj in r.mapObjects]
        if not all_objects: return

        all_verts = [v for o in all_objects if hasattr(o, "gridVertices") for v in o.gridVertices]
        if not all_verts: return

        min_x, max_x = min(v.x for v in all_verts), max(v.x for v in all_verts)
        min_y, max_y = min(v.y for v in all_verts), max(v.y for v in all_verts)

        tile_grid = {}
        for y in range(min_y - 1, max_y + 2):
            for x in range(min_x - 1, max_x + 2):
                tile_grid[(x, y)] = _TileData(feature_type="empty")

        for obj in all_objects:
            if isinstance(obj, schema.Room):
                poly = Polygon([(v.x, v.y) for v in obj.gridVertices])
                r_min_x, r_min_y, r_max_x, r_max_y = [int(b) for b in poly.bounds]
                for y in range(r_min_y, r_max_y + 1):
                    for x in range(r_min_x, r_max_x + 1):
                        if poly.contains(Point(x + 0.5, y + 0.5)):
                            if (x, y) in tile_grid:
                                tile_grid[(x, y)].feature_type = "floor"

        for (x, y), tile in tile_grid.items():
            if tile.feature_type == "empty": continue
            if tile_grid.get((x, y - 1), _TileData("empty")).feature_type == "empty":
                tile.north_wall = "stone"
            if tile_grid.get((x + 1, y), _TileData("empty")).feature_type == "empty":
                tile.east_wall = "stone"
            if tile_grid.get((x, y + 1), _TileData("empty")).feature_type == "empty":
                tile.south_wall = "stone"
            if tile_grid.get((x - 1, y), _TileData("empty")).feature_type == "empty":
                tile.west_wall = "stone"

        for obj in all_objects:
            if isinstance(obj, schema.Door):
                x, y = obj.gridPos.x, obj.gridPos.y
                door_type = "door"
                if obj.properties:
                    if obj.properties.get("secret"): door_type = "secret_door"
                    elif obj.properties.get("type") == "iron_bar": door_type = "iron_bar_door"
                    elif obj.properties.get("type") == "double": door_type = "double_door"

                if obj.orientation == "h":
                    if tile_grid.get((x, y - 1)): tile_grid[(x, y - 1)].south_wall = door_type
                    if tile_grid.get((x, y)): tile_grid[(x, y)].north_wall = door_type
                else:
                    if tile_grid.get((x - 1, y)): tile_grid[(x - 1, y)].east_wall = door_type
                    if tile_grid.get((x, y)): tile_grid[(x, y)].west_wall = door_type

        self.render_from_tiles(tile_grid)

    def render_from_tiles(self, tile_grid: dict):
        if not tile_grid: return

        all_x = [p[0] for p in tile_grid.keys()]
        all_y = [p[1] for p in tile_grid.keys()]
        self.min_x, self.max_x = min(all_x), max(all_x)
        self.min_y, self.max_y = min(all_y), max(all_y)

        self.width = (self.max_x - self.min_x + 1) * 4 + 1 + (self.padding * 2)
        self.height = (self.max_y - self.min_y + 1) * 2 + 1 + (self.padding * 2)
        self.canvas = [[" " for _ in range(self.width)] for _ in range(self.height)]

        content_map = {"floor": " . ", "column": "(O)", "empty": "   ", "stairs": " # "}
        for (gx, gy), tile in tile_grid.items():
            cx = (gx - self.min_x) * 4 + 2 + self.padding
            cy = (gy - self.min_y) * 2 + 1 + self.padding
            if 0 <= cy < self.height and 0 <= cx < self.width - 1:
                content = content_map.get(tile.feature_type, " ? ")
                self.canvas[cy][cx - 1 : cx + 2] = list(content)

        for (gx, gy), tile in tile_grid.items():
            cx_base = (gx - self.min_x) * 4 + self.padding
            cy_base = (gy - self.min_y) * 2 + self.padding
            if tile.north_wall: self.canvas[cy_base][cx_base+1:cx_base+4] = list("───")
            if tile.west_wall: self.canvas[cy_base + 1][cx_base] = "│"
            if tile.south_wall: self.canvas[cy_base+2][cx_base+1:cx_base+4] = list("───")
            if tile.east_wall: self.canvas[cy_base + 1][cx_base + 4] = "│"

        junctions = {
            (0,1,1,0):"┌",(0,0,1,1):"┐",(1,1,0,0):"└",(1,0,0,1):"┘",(1,1,1,0):"├",
            (1,0,1,1):"┤",(0,1,1,1):"┬",(1,1,0,1):"┴",(1,1,1,1):"┼",(0,1,0,1):"─",
            (1,0,1,0):"│",
        }
        for gy in range(self.min_y, self.max_y + 2):
            for gx in range(self.min_x, self.max_x + 2):
                cx = (gx - self.min_x) * 4 + self.padding
                cy = (gy - self.min_y) * 2 + self.padding
                if not (0 <= cy < self.height and 0 <= cx < self.width): continue
                n = self.canvas[cy-1][cx] == "│" if cy>0 else False
                s = self.canvas[cy+1][cx] == "│" if cy<self.height-1 else False
                w = self.canvas[cy][cx-2] == "─" if cx>1 else False
                e = self.canvas[cy][cx+2] == "─" if cx<self.width-2 else False
                key = (n, e, s, w)
                if key in junctions: self.canvas[cy][cx] = junctions[key]
                elif sum(key) == 1:
                    if n:self.canvas[cy][cx]="╵"
                    elif s:self.canvas[cy][cx]="╷"
                    elif w:self.canvas[cy][cx]="╴"
                    elif e:self.canvas[cy][cx]="╶"

        door_chars = { "door": ("─+─", "+"), "secret_door": ("─S─", "S"),
                       "iron_bar_door": ("─#─", "#"), "double_door": ("╌ ╌", "¦")}
        for (gx, gy), tile in tile_grid.items():
            cx_base = (gx - self.min_x) * 4 + self.padding
            cy_base = (gy - self.min_y) * 2 + self.padding
            if tile.north_wall in door_chars:
                h_char, _ = door_chars[tile.north_wall]
                self.canvas[cy_base][cx_base+1:cx_base+4] = list(h_char)
            if tile.west_wall in door_chars:
                _, v_char = door_chars[tile.west_wall]
                self.canvas[cy_base+1][cx_base] = v_char
            if tile.south_wall in door_chars:
                h_char, _ = door_chars[tile.south_wall]
                self.canvas[cy_base+2][cx_base+1:cx_base+4] = list(h_char)
            if tile.east_wall in door_chars:
                _, v_char = door_chars[tile.east_wall]
                self.canvas[cy_base+1][cx_base+4] = v_char

    def get_output(self) -> str:
        if not self.canvas: return ""
        RULER_WIDTH = 4
        output_lines, h_ruler, d_ruler, u_ruler = [], [" "] * self.width, [" "] * self.width, [" "] * self.width
        for gx in range(self.min_x, self.max_x + 1):
            cx = (gx - self.min_x) * 4 + 2 + self.padding
            if 0 <= cx < self.width:
                s_gx = str(abs(gx))
                if gx < 0 and cx > 0: u_ruler[cx - 1] = "-"
                if len(s_gx) >= 3: h_ruler[cx] = s_gx[-3]
                if len(s_gx) >= 2: d_ruler[cx] = s_gx[-2]
                u_ruler[cx] = s_gx[-1]
        ruler_prefix = " " * RULER_WIDTH
        output_lines.append(ruler_prefix + "".join(h_ruler))
        output_lines.append(ruler_prefix + "".join(d_ruler))
        output_lines.append(ruler_prefix + "".join(u_ruler))
        for cy, row in enumerate(self.canvas):
            v_ruler = " " * RULER_WIDTH
            is_center_row = (cy - self.padding - 1) % 2 == 0
            if is_center_row:
                gy = self.min_y + (cy - self.padding - 1) // 2
                v_ruler = f"{gy:>3}|"
            output_lines.append(v_ruler + "".join(row))
        return "\n".join(output_lines)
