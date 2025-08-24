# --- dmap_lib/analysis/features.py ---
import logging
import os
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union
from sklearn.cluster import KMeans

from dmap_lib.llm import query_llm
from dmap_lib.prompts import LLM_PROMPT_CLASSIFIER, LLM_PROMPT_ORACLE
from .context import _GridInfo

log = logging.getLogger("dmap.analysis")
log_llm = logging.getLogger("dmap.llm")


class FeatureExtractor:
    """Handles detection of non-grid-aligned features."""

    def _consolidate_features(self, features: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merges overlapping or very close feature polygons."""
        if not features:
            return []

        log.debug("Consolidating %d raw feature candidates...", len(features))
        polygons = []
        for i, f in enumerate(features):
            verts = [(v["x"], v.get("y", v["y"])) for v in f["gridVertices"]]
            if len(verts) < 3:
                continue
            polygons.append(
                {"poly": Polygon(verts), "original_feature": f, "id": i, "grouped": False}
            )

        groups = []
        for i, p1_data in enumerate(polygons):
            if p1_data["grouped"]:
                continue

            current_group = [p1_data]
            p1_data["grouped"] = True

            for j, p2_data in enumerate(polygons):
                if i == j or p2_data["grouped"]:
                    continue

                # Merge if polygons are very close (e.g., within half a grid unit)
                if p1_data["poly"].distance(p2_data["poly"]) < 0.5:
                    current_group.append(p2_data)
                    p2_data["grouped"] = True

            groups.append(current_group)

        consolidated = []
        for group in groups:
            if not group:
                continue

            # Merge all polygons in the group
            merged_poly = unary_union([g["poly"] for g in group])

            # Find the largest original feature to determine the type
            largest_feature = max(group, key=lambda g: g["poly"].area)["original_feature"]

            main_geom = (
                max(merged_poly.geoms, key=lambda p: p.area)
                if hasattr(merged_poly, "geoms")
                else merged_poly
            )

            if main_geom.is_empty or not isinstance(main_geom, Polygon):
                continue

            new_verts = [
                {"x": round(v[0], 1), "y": round(v[1], 1)} for v in main_geom.exterior.coords
            ]

            consolidated.append(
                {
                    "gridVertices": new_verts,
                    "properties": largest_feature["properties"],
                }
            )

        log.info(
            "Consolidated %d candidates into %d final features.",
            len(features),
            len(consolidated),
        )
        return consolidated

    def _classify_consolidated_features(
        self, features: List[Dict[str, Any]], grid_size: int
    ) -> List[Dict[str, Any]]:
        """
        Performs geometric classification on the final, consolidated feature shapes.
        """
        log.debug(
            "Performing geometric classification on %d consolidated features...", len(features)
        )
        max_area_compact = (grid_size * grid_size) * 1.5
        max_area_elongated = (grid_size * grid_size) * 4.0

        for feature in features:
            px_verts = np.array(
                [(v["x"] * grid_size, v["y"] * grid_size) for v in feature["gridVertices"]]
            ).astype(np.int32)
            area = cv2.contourArea(px_verts)

            _, (w, h), _ = cv2.minAreaRect(px_verts)
            aspect_ratio = max(w, h) / min(w, h) if min(w, h) > 0 else 0

            if aspect_ratio > 2.5:
                if area > max_area_elongated:
                    continue
                feature_type = "stairs"
            else:
                if area > max_area_compact:
                    continue
                feature_type = "column"

            feature["featureType"] = feature_type

            M = cv2.moments(px_verts)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                gx, gy = cx // grid_size, cy // grid_size
                log.debug(
                    "Pre-classified feature at tile (%d, %d) as '%s' (area: %.2f, aspect: %.2f)",
                    gx,
                    gy,
                    feature_type,
                    area,
                    aspect_ratio,
                )
        return [f for f in features if "featureType" in f]

    def extract_layers(
        self,
        original_region_img: np.ndarray,
        grid_info: _GridInfo,
        color_profile: Dict[str, Any],
        kmeans: KMeans,
        labels: np.ndarray,
    ) -> Dict[str, Any]:
        """Detects environmental layers (e.g., water) in the image."""
        enhancement_layers = {"layers": []}
        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        grid_size = grid_info.size

        # --- 1. Detect Water Layers ---
        if "water" in roles_inv:
            w_rgb = roles_inv["water"]
            w_bgr = np.array(w_rgb[::-1], dtype="uint8")
            w_cen = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - w_bgr))
            w_lab = kmeans.predict([w_cen])[0]
            w_mask = (labels == w_lab).reshape(original_region_img.shape[:2])
            w_mask_u8 = w_mask.astype("uint8") * 255
            cnts, _ = cv2.findContours(w_mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                if cv2.contourArea(c) > grid_size * grid_size:
                    # Create a Shapely Polygon and clean it to ensure validity
                    poly = Polygon(c.squeeze()).buffer(0)
                    if poly.is_empty or not isinstance(poly, Polygon):
                        continue

                    verts = [
                        {
                            "x": round((v[0] - grid_info.offset_x) / grid_size, 1),
                            "y": round((v[1] - grid_info.offset_y) / grid_size, 1),
                        }
                        for v in poly.exterior.coords
                    ]
                    enhancement_layers["layers"].append(
                        {
                            "layerType": "water",
                            "gridVertices": verts,
                            "properties": {"z-order": 0},
                        }
                    )
        log.info("Detected %d environmental layers.", len(enhancement_layers["layers"]))
        return enhancement_layers

    def extract_features(
        self,
        original_region_img: np.ndarray,
        room_contours: List[np.ndarray],
        grid_info: _GridInfo,
        color_profile: Dict[str, Any],
        kmeans: KMeans,
        enhancement_layers: Dict[str, Any],
        labels: np.ndarray,
    ) -> Dict[str, Any]:
        """Extracts and classifies high-resolution features like columns and stairs."""
        if not room_contours:
            return enhancement_layers

        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        grid_size = grid_info.size

        feature_candidates = []
        processed_parents = set()
        s_rgb = roles_inv.get("stroke", (0, 0, 0))
        s_bgr = np.array(s_rgb[::-1], dtype="uint8")
        s_cen = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - s_bgr))
        s_lab = kmeans.predict([s_cen])[0]
        s_mask = (labels == s_lab).reshape(original_region_img.shape[:2])
        s_mask_u8 = s_mask.astype("uint8") * 255
        cnts, hierarchy = cv2.findContours(s_mask_u8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        min_area = (grid_size * grid_size) * 0.05

        if hierarchy is not None:
            for i, c in enumerate(cnts):
                parent_idx = hierarchy[0][i][3]
                # A contour is a hole (and thus its parent is a feature) if it has a parent.
                if parent_idx != -1 and parent_idx not in processed_parents:
                    parent_contour = cnts[parent_idx]
                    if cv2.contourArea(parent_contour) < min_area:
                        continue
                    verts = [
                        {
                            "x": round((v[0][0] - grid_info.offset_x) / grid_size, 1),
                            "y": round((v[0][1] - grid_info.offset_y) / grid_size, 1),
                        }
                        for v in parent_contour
                    ]
                    feature_candidates.append(
                        {"gridVertices": verts, "properties": {"z-order": 1}}
                    )
                    processed_parents.add(parent_idx)

        consolidated = self._consolidate_features(feature_candidates)
        classified = self._classify_consolidated_features(consolidated, grid_size)

        enhancement_layers.setdefault("features", []).extend(classified)
        log.info("Extracted %d final features.", len(classified))
        return enhancement_layers


class LLMFeatureEnhancer:
    """Enhances feature classification using a multimodal LLM."""

    def __init__(
        self,
        ollama_url: str,
        ollama_model: str,
        llm_mode: str,
        temperature: float,
        context_size: int,
    ):
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.llm_mode = llm_mode
        self.temperature = temperature
        self.context_size = context_size
        log_llm.info("LLM Feature Enhancer initialized in '%s' mode.", self.llm_mode)

    def _save_pre_llm_debug_image(
        self,
        img: np.ndarray,
        enhancements: Dict[str, Any],
        grid_size: int,
        region_id: str,
        save_path: str,
    ):
        """Saves a debug image visualizing all feature bounding boxes before LLM."""
        debug_img = img.copy()
        overlay = debug_img.copy()
        feature_color = (0, 165, 255)
        crop_area_color = (255, 0, 255)

        for feature in enhancements.get("features", []):
            px_verts = (
                np.array(
                    [(v["x"] * grid_size, v["y"] * grid_size) for v in feature["gridVertices"]]
                )
            ).astype(np.int32)

            # Draw the feature's primary bounding box
            x, y, w, h = cv2.boundingRect(px_verts)
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), feature_color, 2)
            cv2.putText(
                debug_img,
                feature.get("featureType", "unknown"),
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                feature_color,
                2,
            )

            # Calculate and draw the 3x3 grid area for classifier
            M = cv2.moments(px_verts)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                gx, gy = cx // grid_size, cy // grid_size

                x1 = max(0, (gx - 1) * grid_size)
                y1 = max(0, (gy - 1) * grid_size)
                x2 = min(img.shape[1], (gx + 2) * grid_size)
                y2 = min(img.shape[0], (gy + 2) * grid_size)

                # Draw a semi-transparent rectangle for the crop area
                cv2.rectangle(overlay, (x1, y1), (x2, y2), crop_area_color, -1)

        # Apply the transparent overlay
        alpha = 0.3
        cv2.addWeighted(overlay, alpha, debug_img, 1 - alpha, 0, debug_img)

        filename = os.path.join(save_path, f"{region_id}_pre_llm_features.png")
        cv2.imwrite(filename, debug_img)
        log.info("Saved pre-LLM feature bounding box debug image to %s", filename)

    def enhance(
        self,
        enhancement_layers: Dict[str, Any],
        original_region_img: np.ndarray,
        grid_size: int,
        region_id: str,
        save_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Crops features and sends them to LLM for analysis."""
        if save_path:
            self._save_pre_llm_debug_image(
                original_region_img, enhancement_layers, grid_size, region_id, save_path
            )

        if self.llm_mode == "classifier":
            return self._enhance_classifier(
                enhancement_layers, original_region_img, grid_size, region_id, save_path
            )
        elif self.llm_mode == "oracle":
            return self._enhance_oracle(
                enhancement_layers, original_region_img, grid_size, region_id, save_path
            )
        return enhancement_layers

    def _save_oracle_debug_image(
        self,
        img: np.ndarray,
        geom_features: List[Dict[str, Any]],
        llm_features: List[Dict[str, Any]],
        grid_size: int,
        region_id: str,
        save_path: str,
    ):
        debug_img = img.copy()
        geom_color, llm_color = (255, 0, 0), (0, 0, 255)

        for feature in geom_features:
            px_verts = (
                np.array(
                    [(v["x"] * grid_size, v["y"] * grid_size) for v in feature["gridVertices"]]
                )
            ).astype(np.int32)
            x, y, w, h = cv2.boundingRect(px_verts)
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), geom_color, 2)

        for feature in llm_features:
            bbox = feature.get("bounding_box")
            if not bbox:
                continue
            x, y, w, h = (
                bbox.get("x", 0),
                bbox.get("y", 0),
                bbox.get("width", 0),
                bbox.get("height", 0),
            )
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), llm_color, 2)
            cv2.putText(
                debug_img,
                feature.get("feature_type", "unknown"),
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                llm_color,
                2,
            )

        filename = os.path.join(save_path, f"{region_id}_llm_oracle_reconciliation.png")
        cv2.imwrite(filename, debug_img)
        log.info("Saved LLM oracle debug image to %s", filename)

    def _save_classifier_debug_image(
        self,
        img: np.ndarray,
        classified_features: List[Dict[str, Any]],
        grid_size: int,
        region_id: str,
        save_path: str,
    ):
        debug_img = img.copy()
        feature_color = (0, 255, 0)

        for feature in classified_features:
            px_verts = (
                np.array(
                    [(v["x"] * grid_size, v["y"] * grid_size) for v in feature["gridVertices"]]
                )
            ).astype(np.int32)
            x, y, w, h = cv2.boundingRect(px_verts)
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), feature_color, 2)
            cv2.putText(
                debug_img,
                feature.get("featureType", "unknown"),
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                feature_color,
                2,
            )

        filename = os.path.join(save_path, f"{region_id}_llm_classifier_results.png")
        cv2.imwrite(filename, debug_img)
        log.info("Saved LLM classifier debug image to %s", filename)

    def _enhance_classifier(
        self,
        enhancement_layers: Dict[str, Any],
        original_region_img: np.ndarray,
        grid_size: int,
        region_id: str,
        save_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs the per-feature classification enhancement."""
        features = enhancement_layers.get("features", [])
        if not features:
            return enhancement_layers

        for feature in features:
            verts = np.array(
                [(v["x"] * grid_size, v["y"] * grid_size) for v in feature["gridVertices"]]
            ).astype(np.int32)
            M = cv2.moments(verts)
            if M["m00"] == 0:
                continue

            # 1. Find the centroid and the grid tile it belongs to
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            gx, gy = cx // grid_size, cy // grid_size

            # 2. Calculate the 3x3 grid area for the crop
            crop_x1 = max(0, (gx - 1) * grid_size)
            crop_y1 = max(0, (gy - 1) * grid_size)
            crop_x2 = min(original_region_img.shape[1], (gx + 2) * grid_size)
            crop_y2 = min(original_region_img.shape[0], (gy + 2) * grid_size)

            cropped_img = original_region_img[crop_y1:crop_y2, crop_x1:crop_x2]
            if cropped_img.size == 0:
                continue

            log_llm.debug(
                "📤  Sending request to LLM for tile (%d, %d).", gx, gy
            )
            response_str = query_llm(
                self.ollama_url,
                self.ollama_model,
                cropped_img,
                LLM_PROMPT_CLASSIFIER,
                temperature=self.temperature,
                context_size=self.context_size,
            )

            if not response_str:
                log_llm.warning("LLM analysis failed for tile (%d, %d).", gx, gy)
                continue

            try:
                parts = response_str.strip().split(",")
                if len(parts) != 5:
                    raise ValueError("Expected 5 parts in CSV response.")

                new_type = parts[0].strip()
                bbox_vals = [float(p.strip()) for p in parts[1:]]
                bbox = {
                    "x": bbox_vals[0],
                    "y": bbox_vals[1],
                    "width": bbox_vals[2],
                    "height": bbox_vals[3],
                }

                img_h, img_w = cropped_img.shape[:2]
                px_x = bbox["x"] * img_w
                px_y = bbox["y"] * img_h
                px_w = bbox["width"] * img_w
                px_h = bbox["height"] * img_h

                x = (px_x + crop_x1) / grid_size
                y = (px_y + crop_y1) / grid_size
                w = px_w / grid_size
                h = px_h / grid_size

                log_llm.info(
                    "📦  LLM classified feature at tile (%d, %d) as '%s' [grid_bbox: x=%.1f, y=%.1f, w=%.1f, h=%.1f].",
                    gx, gy, new_type, x, y, w, h
                )
                feature["featureType"] = new_type
                feature["gridVertices"] = [
                    {"x": round(x, 1), "y": round(y, 1)},
                    {"x": round(x + w, 1), "y": round(y, 1)},
                    {"x": round(x + w, 1), "y": round(y + h, 1)},
                    {"x": round(x, 1), "y": round(y + h, 1)},
                ]
            except (ValueError, IndexError) as e:
                log_llm.warning(
                    "Failed to parse CSV response from LLM for tile (%d, %d): %s. Response: '%s'",
                    gx, gy, e, response_str
                )

        if save_path:
            self._save_classifier_debug_image(
                original_region_img, features, grid_size, region_id, save_path
            )
        return enhancement_layers

    def _enhance_oracle(
        self,
        enhancement_layers: Dict[str, Any],
        original_region_img: np.ndarray,
        grid_size: int,
        region_id: str,
        save_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs the full-region oracle enhancement."""
        log_llm.info("Querying LLM in oracle mode...")
        response_str = query_llm(
            self.ollama_url,
            self.ollama_model,
            original_region_img,
            LLM_PROMPT_ORACLE,
            temperature=self.temperature,
            context_size=self.context_size,
        )

        if not response_str:
            log_llm.warning("LLM oracle analysis failed or returned empty.")
            return enhancement_layers

        llm_features = []
        for line in response_str.strip().split("\n"):
            try:
                parts = line.strip().split(",")
                if len(parts) != 5:
                    continue
                feature_type = parts[0].strip()
                bbox_vals = [float(p.strip()) for p in parts[1:]]
                llm_features.append(
                    {
                        "feature_type": feature_type,
                        "bounding_box": {
                            "x": bbox_vals[0],
                            "y": bbox_vals[1],
                            "width": bbox_vals[2],
                            "height": bbox_vals[3],
                        },
                    }
                )
            except (ValueError, IndexError):
                log_llm.warning("Skipping malformed CSV line from oracle: '%s'", line)
                continue

        geom_features = enhancement_layers.get("features", [])
        if not geom_features:
            if save_path:
                self._save_oracle_debug_image(
                    original_region_img, [], llm_features, grid_size, region_id, save_path
                )
            return enhancement_layers

        # Pre-calculate centroids of geometrically detected features
        geom_centroids = []
        for feature in geom_features:
            verts = np.array(
                [(v["x"] * grid_size, v["y"] * grid_size) for v in feature["gridVertices"]]
            )
            M = cv2.moments(verts.astype(np.int32))
            geom_centroids.append(
                (M["m10"] / M["m00"], M["m01"] / M["m00"]) if M["m00"] != 0 else None
            )

        reconciliation_count = 0
        img_h, img_w = original_region_img.shape[:2]
        for llm_feature in llm_features:
            bbox = llm_feature.get("bounding_box")
            if not bbox:
                continue

            px_x = bbox.get("x", 0) * img_w
            px_y = bbox.get("y", 0) * img_h
            px_w = bbox.get("width", 0) * img_w
            px_h = bbox.get("height", 0) * img_h
            llm_cx = px_x + px_w / 2
            llm_cy = px_y + px_h / 2

            closest_geom_idx, min_dist = -1, float("inf")
            for i, centroid in enumerate(geom_centroids):
                if centroid is None:
                    continue
                dist = np.linalg.norm(np.array(centroid) - np.array((llm_cx, llm_cy)))
                if dist < min_dist:
                    min_dist = dist
                    closest_geom_idx = i

            # Reconcile if a close match is found (e.g., within a grid unit)
            if closest_geom_idx != -1 and min_dist < grid_size:
                new_type = llm_feature.get("feature_type")
                if isinstance(new_type, str):
                    old_type = geom_features[closest_geom_idx]["featureType"]
                    geom_features[closest_geom_idx]["featureType"] = new_type

                    x = px_x / grid_size
                    y = px_y / grid_size
                    w = px_w / grid_size
                    h = px_h / grid_size
                    geom_features[closest_geom_idx]["gridVertices"] = [
                        {"x": round(x, 1), "y": round(y, 1)},
                        {"x": round(x + w, 1), "y": round(y, 1)},
                        {"x": round(x + w, 1), "y": round(y + h, 1)},
                        {"x": round(x, 1), "y": round(y + h, 1)},
                    ]

                    log_llm.info(
                        "Reconciled feature: '%s' -> '%s' (dist: %.2f px)",
                        old_type,
                        new_type,
                        min_dist,
                    )
                    reconciliation_count += 1

        log_llm.info("Reconciliation complete. Updated %d features.", reconciliation_count)
        if save_path:
            self._save_oracle_debug_image(
                original_region_img,
                geom_features,
                llm_features,
                grid_size,
                region_id,
                save_path,
            )
        return enhancement_layers
