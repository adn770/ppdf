# --- dmap_lib/rendering/svg_renderer.py ---
import logging
import math
from typing import List, Dict, Any
from collections import defaultdict
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union

from dmap_lib import schema
from .geometry import (
    _RenderableShape,
    get_polygon_points_str,
    polygon_to_svg_path,
    merge_adjacent_rooms,
    shapely_to_contours,
)
from .hatching import HatchingRenderer
from .water import WaterRenderer
from .constants import PIXELS_PER_GRID, PADDING

log = logging.getLogger("dmap.render")


class SVGRenderer:
    """Orchestrates the generation of the final SVG document."""

    def __init__(self, map_data: schema.MapData, style_options: dict):
        self.map_data = map_data
        self.style_options = style_options
        self.styles = self._initialize_styles()
        self.hatching_renderer = HatchingRenderer(self.styles)
        self.water_renderer = WaterRenderer(self.styles)
        self.PIXELS_PER_GRID = PIXELS_PER_GRID

    def _initialize_styles(self) -> Dict[str, Any]:
        """Sets up the default and user-provided styles."""
        styles = {
            "bg_color": "#EDE0CE",
            "room_color": "#FFFFFF",
            "wall_color": "#000000",
            "shadow_color": "#999999",
            "glow_color": "#C0C0C0",
            "line_thickness": 7.0,
            "hatch_density": 1.0,
            "water_base_color": "#AEC6CF",
            "water_smoothing_iterations": 4,
        }
        styles.update({k: v for k, v in self.style_options.items() if v is not None})
        log.debug("Using styles: %s", styles)
        return styles

    def render(self) -> str:
        """Main method to generate the full SVG string."""
        all_objects = [obj for r in self.map_data.regions for obj in r.mapObjects]
        original_rooms = [o for o in all_objects if isinstance(o, schema.Room)]
        doors = [o for o in all_objects if isinstance(o, schema.Door)]
        renderable_shapes = merge_adjacent_rooms(original_rooms, doors)

        non_room_objects = [o for o in all_objects if not isinstance(o, schema.Room)]
        objects_to_render = renderable_shapes + non_room_objects

        if self.style_options.get("no_features", False):
            objects_to_render = [
                o for o in objects_to_render if not isinstance(o, schema.Feature)
            ]
            log.info("Feature rendering disabled. Rendering %d objects.", len(objects_to_render))

        if not objects_to_render:
            log.warning("No map objects to render.")
            return "<svg><text>No objects to render.</text></svg>"

        # Calculate canvas size
        all_verts = []
        for o in objects_to_render:
            if isinstance(o, _RenderableShape):
                all_verts.extend(o.polygon.exterior.coords)
            elif hasattr(o, "gridVertices"):
                all_verts.extend([(v.x, v.y) for v in o.gridVertices])

        if not all_verts:
            log.warning("No vertices found to render.")
            return "<svg><text>No rooms to render.</text></svg>"

        min_x, max_x = min(v[0] for v in all_verts), max(v[0] for v in all_verts)
        min_y, max_y = min(v[1] for v in all_verts), max(v[1] for v in all_verts)
        width = (max_x - min_x) * self.PIXELS_PER_GRID + 2 * PADDING
        height = (max_y - min_y) * self.PIXELS_PER_GRID + 2 * PADDING
        log.debug("Calculated SVG canvas dimensions: %dx%d", width, height)

        svg = [
            f'<svg width="{int(width)}" height="{int(height)}" xmlns="http://www.w3.org/2000/svg">',
            f'<rect width="100%" height="100%" fill="{self.styles["bg_color"]}" />',
            "<defs></defs>",
        ]
        tx = PADDING - min_x * self.PIXELS_PER_GRID
        ty = PADDING - min_y * self.PIXELS_PER_GRID
        svg.append(f'<g transform="translate({tx:.2f} {ty:.2f})">')

        # This method will now internally handle all the layer logic
        self._render_layers(svg, objects_to_render, width, height, tx, ty)

        svg.append("</g>")  # Close transform group
        self._render_grid(svg, width, height, tx, ty)
        svg.append("</svg>")
        log.info("SVG rendering complete.")
        return "\n".join(svg)

    def _render_layers(
        self,
        svg: List[str],
        objects_to_render: List[Any],
        width: float,
        height: float,
        tx: float,
        ty: float,
    ):
        """Organizes and renders all SVG layers."""
        layers: Dict[str, List[Any]] = defaultdict(list)
        z_ordered_objects = []

        for obj in objects_to_render:
            if isinstance(obj, _RenderableShape):
                path_data = polygon_to_svg_path(obj.polygon, self.PIXELS_PER_GRID)
                lt = self.styles["line_thickness"]
                layers["shadows"].append(
                    f'<path d="{path_data}" transform="translate(3,3)" fill="{self.styles["shadow_color"]}" stroke="{self.styles["shadow_color"]}" stroke-width="{lt}" fill-rule="evenodd"/>'
                )
                layers["glows"].append(
                    f'<path d="{path_data}" fill="none" stroke="{self.styles["glow_color"]}" stroke-width="{lt*2.5}" stroke-opacity="0.4"/>'
                )
                layers["room_fills"].append(
                    f'<path d="{path_data}" fill="{self.styles["room_color"]}" fill-rule="evenodd"/>'
                )
                layers["walls"].append(
                    f'<path d="{path_data}" fill="none" stroke="{self.styles["wall_color"]}" stroke-width="{lt}"/>'
                )
            elif isinstance(obj, schema.Door):
                lt = self.styles["line_thickness"]
                dw, dh = (
                    (lt, self.PIXELS_PER_GRID * 0.5)
                    if obj.orientation == "v"
                    else (self.PIXELS_PER_GRID * 0.5, lt)
                )
                dx = (
                    (obj.gridPos.x * self.PIXELS_PER_GRID) - dw / 2
                    if obj.orientation == "v"
                    else ((obj.gridPos.x + 0.5) * self.PIXELS_PER_GRID) - dw / 2
                )
                dy = (
                    ((obj.gridPos.y + 0.5) * self.PIXELS_PER_GRID) - dh / 2
                    if obj.orientation == "v"
                    else (obj.gridPos.y * self.PIXELS_PER_GRID) - dh / 2
                )
                layers["doors"].append(
                    f'<rect x="{dx}" y="{dy}" width="{dw}" height="{dh}" fill="{self.styles["room_color"]}" stroke="{self.styles["wall_color"]}" stroke-width="5.0" />'
                )
            elif isinstance(obj, (schema.EnvironmentalLayer, schema.Feature)):
                z_ordered_objects.append(obj)

        z_ordered_objects.sort(
            key=lambda o: o.properties.get("z-order", 0) if o.properties else 0
        )
        for obj in z_ordered_objects:
            if isinstance(obj, schema.EnvironmentalLayer):
                if obj.layerType == "water":
                    layers["contents"].append(self.water_renderer.render(obj))
                else:
                    points = get_polygon_points_str(obj.gridVertices, self.PIXELS_PER_GRID)
                    color = self.styles.get(f"{obj.layerType}_color", "#808080")
                    layers["contents"].append(
                        f'<polygon points="{points}" fill="{color}" fill-opacity="0.5" />'
                    )
            elif isinstance(obj, schema.Feature):
                if "door" in obj.featureType:
                    continue
                points = get_polygon_points_str(obj.gridVertices, self.PIXELS_PER_GRID)
                layers["contents"].append(
                    f'<polygon points="{points}" fill="none" stroke="{self.styles["wall_color"]}" stroke-width="2.0"/>'
                )

        self._render_hatching(layers, objects_to_render, width, height, tx, ty)

        render_order = [
            "shadows", "glows", "hole_fills", "hatching_underlay", "hatching",
            "room_fills", "contents", "doors", "walls",
        ]
        for name in render_order:
            if layers[name]:
                if name == "hatching":
                    svg.append(
                        f'<g id="hatching" stroke="{self.styles["wall_color"]}" stroke-width="1.0">{"".join(layers[name])}</g>'
                    )
                else:
                    svg.append(f'<g id="{name}">{"".join(layers[name])}</g>')

    def _render_hatching(
        self,
        layers: Dict[str, List[Any]],
        objects_to_render: List[Any],
        width: float,
        height: float,
        tx: float,
        ty: float,
    ):
        """Delegates to HatchingRenderer if a hatching style is selected."""
        hatching_style = self.style_options.get("hatching")
        if not hatching_style:
            return

        renderable_shapes = [o for o in objects_to_render if isinstance(o, _RenderableShape)]
        all_polys = [s.polygon for s in renderable_shapes]
        pixel_polys = [
            Polygon(
                [(v[0] * self.PIXELS_PER_GRID, v[1] * self.PIXELS_PER_GRID) for v in p.exterior.coords],
                [
                    [(v[0] * self.PIXELS_PER_GRID, v[1] * self.PIXELS_PER_GRID) for v in hole.coords]
                    for hole in p.interiors
                ],
            )
            for p in all_polys
        ]
        unified_pixel_geometry = unary_union(pixel_polys).buffer(0)

        geoms_to_fill = (
            unified_pixel_geometry.geoms
            if hasattr(unified_pixel_geometry, "geoms")
            else [unified_pixel_geometry]
        )
        for geom in geoms_to_fill:
            if isinstance(geom, Polygon):
                for interior in geom.interiors:
                    hole_path = polygon_to_svg_path(Polygon(interior), 1.0)
                    layers["hole_fills"].append(
                        f'<path d="{hole_path}" fill="{self.styles["glow_color"]}" />'
                    )

        if hatching_style == "sketch":
            log.info("Generating final tile-based sketch hatching...")
            hatch_lines, hatch_fills = self.hatching_renderer.generate_sketch_hatching(
                width, height, self.PIXELS_PER_GRID, tx, ty, unified_pixel_geometry
            )
            layers["hatching_underlay"].extend(hatch_fills)
            layers["hatching"].extend(hatch_lines)
        else:
            log.info("Generating unified geometry for contour hatching...")
            unified_contours = shapely_to_contours(unified_pixel_geometry)
            if hatching_style == "stipple":
                for contour in unified_contours:
                    layers["hatching"].extend(
                        self.hatching_renderer.generate_stipple_hatching(
                            contour, self.styles["hatch_density"], self.PIXELS_PER_GRID
                        )
                    )

    def _render_grid(self, svg: List[str], width: float, height: float, tx: float, ty: float):
        """Renders the debug grid lines."""
        svg.append(f'<g id="grid" stroke="#AEC6CF" stroke-width="1" stroke-opacity="0.5">')
        x = tx % self.PIXELS_PER_GRID
        while x < width:
            svg.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{height}" />')
            x += self.PIXELS_PER_GRID
        y = ty % self.PIXELS_PER_GRID
        while y < height:
            svg.append(f'<line x1="0" y1="{y}" x2="{width}" y2="{y}" />')
            y += self.PIXELS_PER_GRID
        svg.append("</g>")


def render_svg(map_data: schema.MapData, style_options: dict) -> str:
    """Generates a stylized SVG from a region-based MapData object."""
    log.info("Starting SVG rendering process...")
    renderer = SVGRenderer(map_data, style_options)
    return renderer.render()
