# --- dmap_lib/analysis/transformer.py ---
import logging
import uuid
from typing import List, Any, Dict, Tuple

from shapely.geometry import box, Polygon, MultiPolygon, Point
from shapely.ops import unary_union

from dmap_lib import schema
from .context import _RegionAnalysisContext, _TileData

log = logging.getLogger("dmap.analysis")
log_geom = logging.getLogger("dmap.geometry")
log_xfm = logging.getLogger("dmap.transform")


class MapTransformer:
    """Converts the intermediate tile_grid into the final schema.MapData object."""

    def _classify_floor_tiles(
        self, tile_grid: Dict[Tuple[int, int], _TileData]
    ) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """Classifies each floor tile as part of a chamber or a passageway."""
        chamber_tiles, passageway_tiles = [], []

        for (gx, gy), tile in tile_grid.items():
            if tile.feature_type != "floor":
                continue

            # Check neighbors to determine tile type
            n = tile_grid.get((gx, gy - 1))
            s = tile_grid.get((gx, gy + 1))
            w = tile_grid.get((gx - 1, gy))
            e = tile_grid.get((gx + 1, gy))

            has_n = n and n.feature_type == "floor"
            has_s = s and s.feature_type == "floor"
            has_w = w and w.feature_type == "floor"
            has_e = e and e.feature_type == "floor"

            is_vertical_passage = has_n and has_s and not has_w and not has_e
            is_horizontal_passage = has_w and has_e and not has_n and not has_s

            if is_vertical_passage or is_horizontal_passage:
                passageway_tiles.append((gx, gy))
            else:
                chamber_tiles.append((gx, gy))

        return chamber_tiles, passageway_tiles

    def transform(self, context: _RegionAnalysisContext, grid_size: int) -> List[Any]:
        """Transforms the context object into final MapObject entities."""
        log.info("⚙️  Executing Stage 10: Transformation to MapData...")
        tile_grid = context.tile_grid
        if not tile_grid:
            return []

        chamber_tiles, passageway_tiles = self._classify_floor_tiles(tile_grid)
        log_xfm.debug(
            "Classified floor tiles: %d chamber, %d passageway.",
            len(chamber_tiles),
            len(passageway_tiles),
        )

        rooms = []

        # Create 1x1 rooms for each passageway tile
        for gx, gy in passageway_tiles:
            verts = [
                schema.GridPoint(x=float(gx), y=float(gy)),
                schema.GridPoint(x=float(gx + 1), y=float(gy)),
                schema.GridPoint(x=float(gx + 1), y=float(gy + 1)),
                schema.GridPoint(x=float(gx), y=float(gy + 1)),
            ]
            room_id = f"room_{uuid.uuid4().hex[:8]}"
            rooms.append(
                schema.Room(
                    id=room_id,
                    shape="polygon",
                    gridVertices=verts,
                    roomType="corridor",
                    contents=[],
                )
            )

        # Merge all chamber tiles into larger room polygons
        if chamber_tiles:
            chamber_polygons = [box(gx, gy, gx + 1, gy + 1) for gx, gy in chamber_tiles]
            merged_geometry = unary_union(chamber_polygons)

            geometries = []
            if isinstance(merged_geometry, MultiPolygon):
                geometries.extend(merged_geometry.geoms)
            elif isinstance(merged_geometry, Polygon):
                geometries.append(merged_geometry)

            for geom in geometries:
                if geom.area < 0.5:
                    continue
                verts = [
                    schema.GridPoint(x=float(x), y=float(y)) for x, y in geom.exterior.coords
                ]
                room_id = f"room_{uuid.uuid4().hex[:8]}"
                rooms.append(
                    schema.Room(
                        id=room_id,
                        shape="polygon",
                        gridVertices=verts,
                        roomType="chamber",
                        contents=[],
                    )
                )

        log_xfm.debug("Created %d valid Room objects.", len(rooms))

        # Rebuild coord_to_room_id map for door/feature linking
        coord_to_room_id = {}
        for room in rooms:
            poly = Polygon([(v.x, v.y) for v in room.gridVertices])
            min_x, min_y, max_x, max_y = [int(b) for b in poly.bounds]
            for gy in range(min_y, max_y):
                for gx in range(min_x, max_x):
                    if poly.contains(Point(gx + 0.5, gy + 0.5)):
                        coord_to_room_id[(gx, gy)] = room.id

        doors = self._extract_doors_from_grid(tile_grid, coord_to_room_id)
        log_xfm.debug("Extracted %d Door objects.", len(doors))

        features, layers = [], []
        room_map = {r.id: r for r in rooms}
        room_polygons = {r.id: Polygon([(v.x, v.y) for v in room.gridVertices]) for r in rooms}

        for item in context.enhancement_layers.get("features", []):
            # Coordinates are now absolute, no grid shift needed
            verts = [schema.GridPoint(x=v["x"], y=v["y"]) for v in item["gridVertices"]]
            min_x = round(min(v.x for v in verts), 1)
            min_y = round(min(v.y for v in verts), 1)
            max_x = round(max(v.x for v in verts), 1)
            max_y = round(max(v.y for v in verts), 1)
            bounds = schema.BoundingBox(
                x=min_x, y=min_y, width=round(max_x - min_x, 1), height=round(max_y - min_y, 1)
            )

            feature = schema.Feature(
                id=f"feature_{uuid.uuid4().hex[:8]}",
                featureType=item["featureType"],
                shape="polygon",
                gridVertices=verts,
                properties=item["properties"],
                bounds=bounds,
            )
            features.append(feature)
            center = Polygon([(v.x, v.y) for v in verts]).centroid
            for room_id, poly in room_polygons.items():
                if poly.contains(center):
                    if room_map[room_id].contents is not None:
                        room_map[room_id].contents.append(feature.id)
                    break

        for item in context.enhancement_layers.get("layers", []):
            # Coordinates are now absolute, no grid shift needed
            verts = [schema.GridPoint(x=v["x"], y=v["y"]) for v in item["gridVertices"]]
            min_x = round(min(v.x for v in verts), 1)
            min_y = round(min(v.y for v in verts), 1)
            max_x = round(max(v.x for v in verts), 1)
            max_y = round(max(v.y for v in verts), 1)
            bounds = schema.BoundingBox(
                x=min_x, y=min_y, width=round(max_x - min_x, 1), height=round(max_y - min_y, 1)
            )

            layer = schema.EnvironmentalLayer(
                id=f"layer_{uuid.uuid4().hex[:8]}",
                layerType=item["layerType"],
                gridVertices=verts,
                properties=item["properties"],
                bounds=bounds,
            )
            layers.append(layer)
            center = Polygon([(v.x, v.y) for v in verts]).centroid
            for room_id, poly in room_polygons.items():
                if poly.contains(center):
                    if room_map[room_id].contents is not None:
                        room_map[room_id].contents.append(layer.id)
                    break
        log_xfm.debug(
            "Created %d features and %d layers from enhancements.", len(features), len(layers)
        )

        all_objects: List[Any] = rooms + doors + features + layers
        num_r, num_d, num_f, num_l = len(rooms), len(doors), len(features), len(layers)
        log.info(
            "Transformation complete. Created: %d Rooms, %d Doors, %d Features, %d Layers.",
            num_r,
            num_d,
            num_f,
            num_l,
        )
        return all_objects

    def _extract_doors_from_grid(self, tile_grid, coord_to_room_id):
        """Finds all doors on tile edges and links the adjacent rooms."""
        doors = []
        processed_edges = set()
        door_types = ("door", "secret_door", "iron_bar_door", "double_door")

        for (gx, gy), tile in tile_grid.items():
            if tile.feature_type != "floor":
                continue

            # South Wall Check
            wall_type = tile.south_wall
            if wall_type in door_types:
                edge = tuple(sorted(((gx, gy), (gx, gy + 1))))
                if edge not in processed_edges:
                    r1 = coord_to_room_id.get((gx, gy))
                    r2 = coord_to_room_id.get((gx, gy + 1))
                    if r1 and r2 and r1 != r2:
                        props = {}
                        if wall_type == "secret_door":
                            props["secret"] = True
                        elif wall_type == "iron_bar_door":
                            props["type"] = "iron_bar"
                        elif wall_type == "double_door":
                            props["type"] = "double"

                        pos = schema.GridPoint(x=float(gx), y=float(gy + 1))
                        doors.append(
                            schema.Door(
                                id=f"door_{uuid.uuid4().hex[:8]}",
                                gridPos=pos,
                                orientation="h",
                                connects=[r1, r2],
                                properties=props if props else None,
                            )
                        )
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
                        if wall_type == "secret_door":
                            props["secret"] = True
                        elif wall_type == "iron_bar_door":
                            props["type"] = "iron_bar"
                        elif wall_type == "double_door":
                            props["type"] = "double"

                        pos = schema.GridPoint(x=float(gx + 1), y=float(gy))
                        doors.append(
                            schema.Door(
                                id=f"door_{uuid.uuid4().hex[:8]}",
                                gridPos=pos,
                                orientation="v",
                                connects=[r1, r2],
                                properties=props if props else None,
                            )
                        )
                        processed_edges.add(edge)
        return doors
