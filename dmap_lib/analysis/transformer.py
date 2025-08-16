import logging
import uuid
from typing import List, Any

from shapely.geometry import Polygon

from dmap_lib import schema
from .context import _RegionAnalysisContext, _TileData

log = logging.getLogger("dmap.analysis")
log_geom = logging.getLogger("dmap.geometry")
log_xfm = logging.getLogger("dmap.transform")


class MapTransformer:
    """Converts the intermediate tile_grid into the final schema.MapData object."""

    def transform(
        self, context: _RegionAnalysisContext, grid_size: int
    ) -> List[Any]:
        """Transforms the context object into final MapObject entities."""
        log.info("Executing Stage 8: Transformation to MapData...")
        tile_grid = context.tile_grid
        if not tile_grid:
            return []

        coord_to_room_id, rooms, room_polygons = {}, [], {}
        room_areas = self._find_room_areas(tile_grid)
        log_xfm.debug("Step 1: Found %d distinct room areas.", len(room_areas))

        for i, area_tiles in enumerate(room_areas):
            verts = self._trace_room_perimeter(area_tiles, tile_grid)

            if len(verts) < 4:
                log_geom.debug("Discarding room %d: degenerate shape (verts < 4).", i)
                continue
            poly = Polygon([(v.x, v.y) for v in verts])
            if poly.area < 0.5:
                log_geom.debug("Discarding room %d: area < 0.5 grid tiles.", i)
                continue

            room_id = f"room_{uuid.uuid4().hex[:8]}"
            room = schema.Room(id=room_id, shape="polygon", gridVertices=verts,
                               roomType="chamber", contents=[])
            rooms.append(room)
            room_polygons[room.id] = poly
            for pos in area_tiles:
                coord_to_room_id[pos] = room.id
        log_xfm.debug(
            "Step 2: Created %d valid Room objects from traced areas.", len(rooms)
        )

        doors = self._extract_doors_from_grid(tile_grid, coord_to_room_id)
        log_xfm.debug("Step 3: Extracted %d Door objects.", len(doors))

        features, layers = [], []
        room_map = {r.id: r for r in rooms}

        for item in context.enhancement_layers.get("features", []):
            verts = [schema.GridPoint(x=int(v[0]/8), y=int(v[1]/8))
                     for v in item["high_res_vertices"]]
            feature = schema.Feature(id=f"feature_{uuid.uuid4().hex[:8]}",
                                     featureType=item["featureType"], shape="polygon",
                                     gridVertices=verts, properties=item["properties"])
            features.append(feature)
            center = Polygon([(v.x, v.y) for v in verts]).centroid
            for room_id, poly in room_polygons.items():
                if poly.contains(center):
                    if room_map[room_id].contents is not None:
                        room_map[room_id].contents.append(feature.id)
                    break

        for item in context.enhancement_layers.get("layers", []):
            verts = [schema.GridPoint(x=int(v[0]/8), y=int(v[1]/8))
                     for v in item["high_res_vertices"]]
            layer = schema.EnvironmentalLayer(id=f"layer_{uuid.uuid4().hex[:8]}",
                                              layerType=item["layerType"],
                                              gridVertices=verts,
                                              properties=item["properties"])
            layers.append(layer)
            center = Polygon([(v.x, v.y) for v in verts]).centroid
            for room_id, poly in room_polygons.items():
                if poly.contains(center):
                    if room_map[room_id].contents is not None:
                        room_map[room_id].contents.append(layer.id)
                    break
        log_xfm.debug(
            "Step 4: Created %d features and %d layers from enhancements.",
            len(features), len(layers)
        )

        all_objects: List[Any] = rooms + doors + features + layers
        num_r, num_d, num_f, num_l = len(rooms), len(doors), len(features), len(layers)
        log.info(
            "Transformation complete. Created: %d Rooms, %d Doors, %d Features, %d Layers.",
            num_r, num_d, num_f, num_l
        )
        return all_objects

    def _find_room_areas(self, tile_grid):
        """Finds all contiguous areas of floor tiles using BFS."""
        visited, all_areas = set(), []
        for (gx, gy), tile in tile_grid.items():
            if tile.feature_type == "floor" and (gx, gy) not in visited:
                current_area, q, head = set(), [(gx, gy)], 0
                visited.add((gx, gy))
                while head < len(q):
                    cx, cy = q[head]
                    head += 1
                    current_area.add((cx, cy))
                    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                        nx, ny = cx + dx, cy + dy
                        neighbor = tile_grid.get((nx, ny))
                        if (neighbor and neighbor.feature_type == "floor"
                                and (nx, ny) not in visited):
                            visited.add((nx, ny))
                            q.append((nx, ny))
                all_areas.append(current_area)
        return all_areas

    def _extract_doors_from_grid(self, tile_grid, coord_to_room_id):
        """Finds all doors on tile edges and links the adjacent rooms."""
        doors = []
        processed_edges = set()
        door_types = ("door", "secret_door", "iron_bar_door", "double_door")

        for (gx, gy), tile in tile_grid.items():
            # South Wall Check
            wall_type = tile.south_wall
            if wall_type in door_types:
                edge = tuple(sorted(((gx, gy), (gx, gy + 1))))
                if edge not in processed_edges:
                    r1 = coord_to_room_id.get((gx, gy))
                    r2 = coord_to_room_id.get((gx, gy + 1))
                    if r1 and r2 and r1 != r2:
                        props = {}
                        if wall_type == "secret_door": props["secret"] = True
                        elif wall_type == "iron_bar_door": props["type"] = "iron_bar"
                        elif wall_type == "double_door": props["type"] = "double"

                        pos = schema.GridPoint(x=gx, y=gy + 1)
                        doors.append(schema.Door(id=f"door_{uuid.uuid4().hex[:8]}",
                                                 gridPos=pos, orientation="h",
                                                 connects=[r1, r2],
                                                 properties=props if props else None))
                        processed_edges.add(edge)

            # East Wall Check
            wall_type = tile.east_wall
            if wall_type in door_types:
                edge = tuple(sorted(((gx, gy), (gx + 1, gy))))
                if edge not in processed_edges:
                    r1 = coord_to_room_id.get((gx, gy))
                    r2 = coord_to_room_id.get((gx + 1, gy))
                    if r1 and r2 and r1 != r2:
                        props = {}
                        if wall_type == "secret_door": props["secret"] = True
                        elif wall_type == "iron_bar_door": props["type"] = "iron_bar"
                        elif wall_type == "double_door": props["type"] = "double"

                        pos = schema.GridPoint(x=gx + 1, y=gy)
                        doors.append(schema.Door(id=f"door_{uuid.uuid4().hex[:8]}",
                                                 gridPos=pos, orientation="v",
                                                 connects=[r1, r2],
                                                 properties=props if props else None))
                        processed_edges.add(edge)
        return doors

    def _trace_room_perimeter(self, room_tiles, tile_grid):
        """Traces the perimeter of a room area using a wall-following algorithm."""
        if not room_tiles:
            return []
        start_pos = min(room_tiles, key=lambda p: (p[1], p[0]))
        direction, current_vertex = (1, 0), (start_pos[0], start_pos[1])
        path = [schema.GridPoint(x=current_vertex[0], y=current_vertex[1])]

        for _ in range(len(tile_grid) * 4):
            tile_NW = tile_grid.get((current_vertex[0] - 1, current_vertex[1] - 1))
            tile_NE = tile_grid.get((current_vertex[0], current_vertex[1] - 1))
            tile_SW = tile_grid.get((current_vertex[0] - 1, current_vertex[1]))
            tile_SE = tile_grid.get(current_vertex)

            if direction == (1, 0):  # Moving East
                if tile_NE and tile_NE.west_wall == "stone": direction = (0, 1)
                elif tile_SE and tile_SE.north_wall == "stone":
                    current_vertex = (current_vertex[0] + 1, current_vertex[1])
                else: direction = (0, -1)
            elif direction == (0, 1):  # Moving South
                if tile_SE and tile_SE.north_wall == "stone": direction = (-1, 0)
                elif tile_SW and tile_SW.east_wall == "stone":
                    current_vertex = (current_vertex[0], current_vertex[1] + 1)
                else: direction = (1, 0)
            elif direction == (-1, 0):  # Moving West
                if tile_SW and tile_SW.east_wall == "stone": direction = (0, -1)
                elif tile_NW and tile_NW.south_wall == "stone":
                    current_vertex = (current_vertex[0] - 1, current_vertex[1])
                else: direction = (0, 1)
            elif direction == (0, -1):  # Moving North
                if tile_NW and tile_NW.south_wall == "stone": direction = (1, 0)
                elif tile_NE and tile_NE.west_wall == "stone":
                    current_vertex = (current_vertex[0], current_vertex[1] - 1)
                else: direction = (-1, 0)

            if path[-1].x != current_vertex[0] or path[-1].y != current_vertex[1]:
                path.append(schema.GridPoint(x=current_vertex[0], y=current_vertex[1]))
            if (current_vertex[0], current_vertex[1]) == (start_pos[0], start_pos[1]):
                break
        return path
