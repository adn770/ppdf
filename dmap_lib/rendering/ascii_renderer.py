# --- dmap_lib/rendering/ascii_renderer.py ---
from typing import List
from shapely.geometry import Polygon, Point

from dmap_lib import schema
from dmap_lib.analysis.context import _TileData


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
        for y in range(int(min_y) - 1, int(max_y) + 2):
            for x in range(int(min_x) - 1, int(max_x) + 2):
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
            if tile.feature_type == "empty":
                continue
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
                x, y = int(obj.gridPos.x), int(obj.gridPos.y)
                door_type = "door"
                if obj.properties:
                    if obj.properties.get("secret"):
                        door_type = "secret_door"
                    elif obj.properties.get("type") == "iron_bar":
                        door_type = "iron_bar_door"
                    elif obj.properties.get("type") == "double":
                        door_type = "double_door"

                if obj.orientation == "h":
                    if tile_grid.get((x, y - 1)):
                        tile_grid[(x, y - 1)].south_wall = door_type
                    if tile_grid.get((x, y)):
                        tile_grid[(x, y)].north_wall = door_type
                else:
                    if tile_grid.get((x - 1, y)):
                        tile_grid[(x - 1, y)].east_wall = door_type
                    if tile_grid.get((x, y)):
                        tile_grid[(x, y)].west_wall = door_type

        self.render_from_tiles(tile_grid)

    def render_from_tiles(self, tile_grid: dict):
        if not tile_grid:
            return

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
            if tile.north_wall:
                self.canvas[cy_base][cx_base + 1 : cx_base + 4] = list("───")
            if tile.west_wall:
                self.canvas[cy_base + 1][cx_base] = "│"
            if tile.south_wall:
                self.canvas[cy_base + 2][cx_base + 1 : cx_base + 4] = list("───")
            if tile.east_wall:
                self.canvas[cy_base + 1][cx_base + 4] = "│"

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
        for gy in range(self.min_y, self.max_y + 2):
            for gx in range(self.min_x, self.max_x + 2):
                cx = (gx - self.min_x) * 4 + self.padding
                cy = (gy - self.min_y) * 2 + self.padding
                if not (0 <= cy < self.height and 0 <= cx < self.width):
                    continue
                n = self.canvas[cy - 1][cx] == "│" if cy > 0 else False
                s = self.canvas[cy + 1][cx] == "│" if cy < self.height - 1 else False
                w = self.canvas[cy][cx - 2] == "─" if cx > 1 else False
                e = self.canvas[cy][cx + 2] == "─" if cx < self.width - 2 else False
                key = (n, e, s, w)
                if key in junctions:
                    self.canvas[cy][cx] = junctions[key]
                elif sum(key) == 1:
                    if n:
                        self.canvas[cy][cx] = "╵"
                    elif s:
                        self.canvas[cy][cx] = "╷"
                    elif w:
                        self.canvas[cy][cx] = "╴"
                    elif e:
                        self.canvas[cy][cx] = "╶"

        door_chars = {
            "door": ("─+─", "+"),
            "secret_door": ("─S─", "S"),
            "iron_bar_door": ("─#─", "#"),
            "double_door": ("╌ ╌", "¦"),
        }
        for (gx, gy), tile in tile_grid.items():
            cx_base = (gx - self.min_x) * 4 + self.padding
            cy_base = (gy - self.min_y) * 2 + self.padding
            if tile.north_wall in door_chars:
                h_char, _ = door_chars[tile.north_wall]
                self.canvas[cy_base][cx_base + 1 : cx_base + 4] = list(h_char)
            if tile.west_wall in door_chars:
                _, v_char = door_chars[tile.west_wall]
                self.canvas[cy_base + 1][cx_base] = v_char
            if tile.south_wall in door_chars:
                h_char, _ = door_chars[tile.south_wall]
                self.canvas[cy_base + 2][cx_base + 1 : cx_base + 4] = list(h_char)
            if tile.east_wall in door_chars:
                _, v_char = door_chars[tile.east_wall]
                self.canvas[cy_base + 1][cx_base + 4] = v_char

    def get_output(self) -> str:
        if not self.canvas:
            return ""
        RULER_WIDTH = 4
        output_lines, h_ruler, d_ruler, u_ruler = (
            [],
            [" "] * self.width,
            [" "] * self.width,
            [" "] * self.width,
        )
        for gx in range(self.min_x, self.max_x + 1):
            cx = (gx - self.min_x) * 4 + 2 + self.padding
            if 0 <= cx < self.width:
                s_gx = str(abs(gx))
                if gx < 0 and cx > 0:
                    u_ruler[cx - 1] = "-"
                if len(s_gx) >= 3:
                    h_ruler[cx] = s_gx[-3]
                if len(s_gx) >= 2:
                    d_ruler[cx] = s_gx[-2]
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
