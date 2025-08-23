# --- dmap_lib/rendering/geometry.py ---
import logging
import uuid
from typing import List, Any, Dict
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union

from dmap_lib import schema

log = logging.getLogger("dmap.render")


@dataclass
class _RenderableShape:
    """An intermediate object to hold complex geometry for rendering."""

    id: str
    polygon: Polygon
    contents: List[str] | None = None
    roomType: str = "chamber"


def get_polygon_points_str(vertices: list[schema.GridPoint], scale: float) -> str:
    """Converts a list of grid vertices to an SVG polygon points string."""
    return " ".join(f"{v.x * scale},{v.y * scale}" for v in vertices)


def polygon_to_svg_path(polygon: Polygon, scale: float) -> str:
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


def merge_adjacent_rooms(
    rooms: List[schema.Room], doors: List[schema.Door]
) -> List[_RenderableShape]:
    """Merges adjacent rooms, preserving holes, into _RenderableShape objects."""
    if not rooms:
        return []

    log.info("Performing pre-render merge of %d rooms...", len(rooms))
    polygons = {room.id: Polygon([(v.x, v.y) for v in room.gridVertices]) for room in rooms}
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

        geoms = merged_poly.geoms if hasattr(merged_poly, "geoms") else [merged_poly]
        for geom in geoms:
            if isinstance(geom, Polygon) and not geom.is_empty:
                shape = _RenderableShape(
                    id=f"merged_{root_id}_{uuid.uuid4().hex[:4]}",
                    polygon=geom,
                    contents=list(set(all_contents)) or None,
                )
                final_shapes.append(shape)

    log.info("Pre-render merge complete. Resulted in %d final shapes.", len(final_shapes))
    return final_shapes


def shapely_to_contours(geometry: Polygon | MultiPolygon) -> List[np.ndarray]:
    """Converts a Shapely geometry object to a list of OpenCV-style contours."""
    contours = []
    geoms = geometry.geoms if hasattr(geometry, "geoms") else [geometry]
    for geom in geoms:
        if isinstance(geom, Polygon) and not geom.is_empty:
            exterior = np.array(geom.exterior.coords, dtype=np.int32).reshape((-1, 1, 2))
            contours.append(exterior)
            for interior in geom.interiors:
                hole = np.array(interior.coords, dtype=np.int32).reshape((-1, 1, 2))
                contours.append(hole)
    return contours
