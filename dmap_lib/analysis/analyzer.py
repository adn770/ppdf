# --- dmap_lib/analysis/analyzer.py ---
import logging
import os
from typing import List, Dict, Any, Tuple, Optional

import cv2
import numpy as np
from sklearn.cluster import KMeans

from dmap_lib import schema, rendering
from .color import ColorAnalyzer
from .structure import StructureAnalyzer
from .features import FeatureExtractor, LLaVAFeatureEnhancer
from .transformer import MapTransformer
from .context import _RegionAnalysisContext
from .regions import detect_content_regions, parse_text_metadata

log = logging.getLogger("dmap.analysis")


class MapAnalyzer:
    """Orchestrates the entire map analysis pipeline for a single region."""

    def __init__(self):
        self.color_analyzer = ColorAnalyzer()
        self.structure_analyzer = StructureAnalyzer()
        self.feature_extractor = FeatureExtractor()
        self.map_transformer = MapTransformer()
        self.llava_enhancer = None

    def _save_feature_detection_debug_image(
        self,
        img: np.ndarray,
        enhancements: Dict[str, Any],
        grid_size: int,
        region_id: str,
        save_path: str,
        suffix: str,
    ):
        """Saves a debug image visualizing detected features and layers."""
        debug_img = img.copy()
        layer_color, feature_color = (255, 0, 0), (0, 0, 255)  # Blue, Red

        for layer in enhancements.get("layers", []):
            px_verts = (
                np.array(layer["high_res_vertices"]) * grid_size / 8.0
            ).astype(np.int32)
            cv2.drawContours(debug_img, [px_verts], -1, layer_color, 2)

        for feature in enhancements.get("features", []):
            px_verts = (
                np.array(feature["high_res_vertices"]) * grid_size / 8.0
            ).astype(np.int32)
            cv2.drawContours(debug_img, [px_verts], -1, feature_color, 1)

        filename = os.path.join(save_path, f"{region_id}_{suffix}.png")
        cv2.imwrite(filename, debug_img)
        log.info("Saved feature detection debug image to %s", filename)

    def analyze_region(
        self,
        img: np.ndarray,
        region_context: Dict[str, Any],
        ascii_debug: bool = False,
        save_intermediate_path: Optional[str] = None,
        llava_mode: Optional[str] = None,
        ollama_url: Optional[str] = None,
        ollama_model: Optional[str] = None,
    ) -> schema.Region:
        """Runs the full pipeline on a single cropped image region."""
        log.info("Running analysis pipeline on region: %s", region_context["id"])
        if img is None:
            raise ValueError("Input image to analyze_region cannot be None")

        color_profile, kmeans_model = self.color_analyzer.analyze(img)
        context = _RegionAnalysisContext()

        log.info("Executing Stage 4: Structural Image Preparation...")
        structural_img = self._create_structural_image(img, color_profile, kmeans_model)
        floor_only_img = self._create_floor_only_image(img, color_profile, kmeans_model)
        stroke_only_img = self._create_stroke_only_image(
            img, color_profile, kmeans_model
        )

        context.room_bounds = self._find_room_bounds(stroke_only_img)
        grid_info = self.structure_analyzer.discover_grid(
            structural_img, color_profile, context.room_bounds
        )

        # --- Refactored Debug Image Handling ---
        debug_canvas = None
        if save_intermediate_path:
            # Create the base canvas for debugging structure analysis
            h, w, _ = structural_img.shape
            overlay = structural_img.copy()
            cv2.rectangle(overlay, (0, 0), (w, h), (0, 0, 0), -1)
            debug_canvas = cv2.addWeighted(overlay, 0.4, structural_img, 0.6, 0)
            # Draw grid lines
            grid_color = (255, 255, 0)
            for x_coord in range(0, w, grid_info.size):
                px = x_coord + grid_info.offset_x
                cv2.line(debug_canvas, (px, 0), (px, h), grid_color, 1)
            for y_coord in range(0, h, grid_info.size):
                py = y_coord + grid_info.offset_y
                cv2.line(debug_canvas, (0, py), (w, py), grid_color, 1)

        log.info("Executing Stage 6: High-Resolution Feature & Layer Detection...")
        corrected_floor = floor_only_img.copy()
        temp_layers = self.feature_extractor.extract(
            img, [], grid_info.size, color_profile, kmeans_model
        )
        if save_intermediate_path:
            self._save_feature_detection_debug_image(
                img,
                temp_layers,
                grid_info.size,
                region_context["id"],
                save_intermediate_path,
                "pass1_layers",
            )

        if temp_layers.get("layers"):
            log.info(
                "Refining floor plan using %d detected environmental layer(s).",
                len(temp_layers["layers"]),
            )
            for layer in temp_layers["layers"]:
                px_verts = (
                    np.array(layer["high_res_vertices"]) * grid_info.size / 8.0
                ).astype(np.int32)
                cv2.fillPoly(corrected_floor, [px_verts], 255)

        if save_intermediate_path:
            fname = f"{region_context['id']}_corrected_floor.png"
            cv2.imwrite(os.path.join(save_intermediate_path, fname), corrected_floor)

        room_contours = self._get_floor_plan_contours(corrected_floor, grid_info.size)
        context.enhancement_layers = self.feature_extractor.extract(
            img, room_contours, grid_info.size, color_profile, kmeans_model
        )
        if save_intermediate_path:
            self._save_feature_detection_debug_image(
                img,
                context.enhancement_layers,
                grid_info.size,
                region_context["id"],
                save_intermediate_path,
                "pass2_features",
            )

        if llava_mode and ollama_url and ollama_model:
            log.debug("Calling LLaVA feature enhancement in '%s' mode.", llava_mode)
            self.llava_enhancer = LLaVAFeatureEnhancer(
                ollama_url, ollama_model, llava_mode
            )
            context.enhancement_layers = self.llava_enhancer.enhance(
                context.enhancement_layers, img, grid_info.size
            )

        feature_cleaned_img = corrected_floor.copy()
        for feature in context.enhancement_layers.get("features", []):
            px_verts = (
                np.array(feature["high_res_vertices"]) * grid_info.size / 8.0
            ).astype(np.int32)
            cv2.fillPoly(feature_cleaned_img, [px_verts], 0)  # Erase feature
        if save_intermediate_path:
            fname = f"{region_context['id']}_pass3_feature_cleaned.png"
            cv2.imwrite(
                os.path.join(save_intermediate_path, fname), feature_cleaned_img
            )

        tile_classifications = self.structure_analyzer.classify_tile_content(
            feature_cleaned_img, grid_info
        )

        context.tile_grid = self.structure_analyzer.classify_features(
            structural_img,
            feature_cleaned_img,
            grid_info,
            color_profile,
            tile_classifications,
            debug_canvas=debug_canvas,
        )

        # Save the completed debug canvas if it was created
        if debug_canvas is not None and save_intermediate_path:
            filename = os.path.join(
                save_intermediate_path, f"{region_context['id']}_wall_detection.png"
            )
            cv2.imwrite(filename, debug_canvas)
            log.info("Saved wall detection debug image to %s", filename)

        if ascii_debug and context.tile_grid:
            log.info("--- ASCII Debug Output (Pre-Transformation) ---")
            renderer = rendering.ASCIIRenderer()
            renderer.render_from_tiles(context.tile_grid)
            log.info("\n%s", renderer.get_output(), extra={"raw": True})
            log.info("--- End ASCII Debug Output ---")

        all_objects = self.map_transformer.transform(context, grid_info.size)
        return schema.Region(
            id=region_context["id"],
            label=region_context.get("label", region_context["id"]),
            gridSizePx=grid_info.size,
            bounds=[],
            mapObjects=all_objects,
        )

    def _create_stroke_only_image(
        self, img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
    ) -> np.ndarray:
        """Creates a stroke-only image (black on white) for contour detection."""
        log.debug("Creating stroke-only image for boundary analysis.")
        stroke_roles = {
            r for r in color_profile["roles"].values() if r.endswith("stroke")
        }
        rgb_to_label = {
            tuple(c.astype("uint8")[::-1]): i
            for i, c in enumerate(kmeans.cluster_centers_)
        }
        stroke_labels = {
            rgb_to_label[rgb]
            for rgb, role in color_profile["roles"].items()
            if role in stroke_roles
        }

        all_labels = kmeans.labels_.reshape(img.shape[:2])
        stroke_mask = np.isin(all_labels, list(stroke_labels))

        canvas = np.full_like(img, 255, dtype=np.uint8)
        canvas[stroke_mask] = (0, 0, 0)
        return canvas

    def _create_structural_image(
        self, img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
    ) -> np.ndarray:
        """Creates a clean two-color image (stroke on floor) for analysis."""
        log.debug("Creating two-color structural image (stroke on floor).")
        stroke_roles = {
            r for r in color_profile["roles"].values() if r.endswith("stroke")
        }
        rgb_to_label = {
            tuple(c.astype("uint8")[::-1]): i
            for i, c in enumerate(kmeans.cluster_centers_)
        }
        stroke_labels = {
            rgb_to_label[rgb]
            for rgb, role in color_profile["roles"].items()
            if role in stroke_roles
        }

        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        floor_rgb = roles_inv.get("floor", (255, 255, 255))
        stroke_rgb = roles_inv.get("stroke", (0, 0, 0))
        floor_bgr = np.array(floor_rgb[::-1], dtype="uint8")
        stroke_bgr = np.array(stroke_rgb[::-1], dtype="uint8")

        all_labels = kmeans.labels_.reshape(img.shape[:2])
        stroke_mask = np.isin(all_labels, list(stroke_labels))

        filtered_image = np.full_like(img, floor_bgr)
        filtered_image[stroke_mask] = stroke_bgr

        return filtered_image

    def _create_floor_only_image(
        self, img: np.ndarray, color_profile: Dict[str, Any], kmeans: KMeans
    ) -> np.ndarray:
        """Creates a binary mask of all floor pixels for accurate contouring."""
        log.debug("Creating binary floor-only image mask.")
        floor_roles = {r for r in color_profile["roles"].values() if "floor" in r}
        rgb_to_label = {
            tuple(c.astype("uint8")[::-1]): i
            for i, c in enumerate(kmeans.cluster_centers_)
        }
        floor_labels = {
            rgb_to_label[rgb]
            for rgb, role in color_profile["roles"].items()
            if role in floor_roles
        }

        all_labels = kmeans.labels_.reshape(img.shape[:2])
        floor_mask = np.isin(all_labels, list(floor_labels))

        canvas = np.zeros(img.shape[:2], dtype=np.uint8)
        canvas[floor_mask] = 255
        return canvas

    def _find_room_bounds(
        self,
        stroke_only_image: np.ndarray,
    ) -> List[Tuple[int, int, int, int]]:
        """Finds bounding boxes of all major shapes in the stroke-only image."""
        log.debug("Finding room boundary boxes from strokes.")
        gray = cv2.cvtColor(stroke_only_image, cv2.COLOR_BGR2GRAY)
        _, binary_mask = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)

        contours, _ = cv2.findContours(
            binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        bounds = []
        min_area = 1000
        for contour in contours:
            if cv2.contourArea(contour) > min_area:
                bounds.append(cv2.boundingRect(contour))
        log.debug("Found %d potential room boundary boxes.", len(bounds))
        return bounds

    def _get_floor_plan_contours(
        self, floor_only_image: np.ndarray, grid_size: int
    ) -> List[np.ndarray]:
        """Helper to get clean room contours from the floor-only binary image."""
        log.debug("Extracting floor plan contours from floor-only image.")
        contours, _ = cv2.findContours(
            floor_only_image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        return [c for c in contours if cv2.contourArea(c) > (grid_size * grid_size)]


def analyze_image(
    image_path: str,
    ascii_debug: bool = False,
    save_intermediate_path: Optional[str] = None,
    llava_mode: Optional[str] = None,
    llm_url: Optional[str] = None,
    llm_model: Optional[str] = None,
) -> schema.MapData:
    """
    Top-level orchestrator for the analysis pipeline. It will load the image,
    find distinct regions, and then run the core analysis on each region.
    """
    log.info("Starting analysis of image: '%s'", image_path)
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not read image at {image_path}")

    source_filename = os.path.basename(image_path)
    all_region_contexts = detect_content_regions(img)
    metadata, all_region_contexts = parse_text_metadata(all_region_contexts)

    dungeon_regions = [rc for rc in all_region_contexts if rc.get("type") == "dungeon"]
    if not dungeon_regions:
        log.warning("No dungeon regions found in the image.")
        meta = schema.Meta(title=source_filename, sourceImage=source_filename)
        return schema.MapData(dmapVersion="2.0.0", meta=meta, regions=[])

    log.info(
        "Orchestrator found %d dungeon regions. Processing all.", len(dungeon_regions)
    )
    final_regions = []
    analyzer = MapAnalyzer()
    for i, region_context in enumerate(dungeon_regions):
        region_img = region_context["bounds_img"]
        region_context["label"] = f"Dungeon Area {i+1}"
        processed_region = analyzer.analyze_region(
            region_img,
            region_context,
            ascii_debug=ascii_debug,
            save_intermediate_path=save_intermediate_path,
            llava_mode=llava_mode,
            ollama_url=llm_url,
            ollama_model=llm_model,
        )
        final_regions.append(processed_region)

    title = metadata.get("title") or os.path.splitext(source_filename)[0]
    meta_obj = schema.Meta(
        title=title,
        sourceImage=source_filename,
        notes=metadata.get("notes"),
        legend=metadata.get("legend"),
    )
    map_data = schema.MapData(dmapVersion="2.0.0", meta=meta_obj, regions=final_regions)

    return map_data
