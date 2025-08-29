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

    def _classify_features(
        self, features: List[Dict[str, Any]], grid_size: int
    ) -> List[Dict[str, Any]]:
        """
        Performs geometric classification on the final, consolidated feature shapes.
        """
        log.debug("Performing geometric classification on %d features...", len(features))
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
            log.debug("No room contours provided, skipping feature extraction.")
            return enhancement_layers

        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        grid_size = grid_info.size
        h, w = original_region_img.shape[:2]

        # 1. Create a mask of all stroke pixels
        s_rgb = roles_inv.get("stroke", (0, 0, 0))
        s_bgr = np.array(s_rgb[::-1], dtype="uint8")
        s_cen = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - s_bgr))
        s_lab = kmeans.predict([s_cen])[0]
        s_mask = (labels == s_lab).reshape(h, w).astype("uint8") * 255

        # 2. Create a mask of the floor plan
        floor_mask = np.zeros((h, w), dtype="uint8")
        cv2.drawContours(floor_mask, room_contours, -1, 255, -1)

        # 3. Create the final feature mask by finding strokes *inside* the floor plan
        feature_mask = cv2.bitwise_and(s_mask, floor_mask)

        # 4. Find contours of the features directly
        contours, _ = cv2.findContours(
            feature_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        feature_candidates = []
        min_area = (grid_size * grid_size) * 0.05
        padding = grid_size * 0.1  # Add 10% of a grid cell as padding

        for c in contours:
            if cv2.contourArea(c) < min_area:
                continue

            # 5. Generate rectangular bounding box with padding
            x, y, w, h = cv2.boundingRect(c)
            x_pad, y_pad = max(0, x - padding), max(0, y - padding)
            w_pad, h_pad = w + (2 * padding), h + (2 * padding)

            verts = [
                {
                    "x": round((x_pad - grid_info.offset_x) / grid_size, 1),
                    "y": round((y_pad - grid_info.offset_y) / grid_size, 1),
                },
                {
                    "x": round((x_pad + w_pad - grid_info.offset_x) / grid_size, 1),
                    "y": round((y_pad - grid_info.offset_y) / grid_size, 1),
                },
                {
                    "x": round((x_pad + w_pad - grid_info.offset_x) / grid_size, 1),
                    "y": round((y_pad + h_pad - grid_info.offset_y) / grid_size, 1),
                },
                {
                    "x": round((x_pad - grid_info.offset_x) / grid_size, 1),
                    "y": round((y_pad + h_pad - grid_info.offset_y) / grid_size, 1),
                },
            ]
            feature_candidates.append(
                {"gridVertices": verts, "properties": {"z-order": 1}}
            )

        classified = self._classify_features(feature_candidates, grid_size)

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

            # Calculate and draw the 7x7 grid area for classifier
            M = cv2.moments(px_verts)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])

                crop_size = grid_size * 7
                crop_x1 = max(0, cx - crop_size // 2)
                crop_y1 = max(0, cy - crop_size // 2)
                crop_x2 = min(img.shape[1], cx + crop_size // 2)
                crop_y2 = min(img.shape[0], cy + crop_size // 2)

                # Draw a semi-transparent rectangle for the crop area
                cv2.rectangle(overlay, (crop_x1, crop_y1), (crop_x2, crop_y2), crop_area_color, -1)

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
            img_h, img_w = img.shape[:2]
            x1 = int(bbox.get("x1", 0) * img_w)
            y1 = int(bbox.get("y1", 0) * img_h)
            x2 = int(bbox.get("x2", 0) * img_w)
            y2 = int(bbox.get("y2", 0) * img_h)

            cv2.rectangle(debug_img, (x1, y1), (x2, y2), llm_color, 2)
            cv2.putText(
                debug_img,
                feature.get("feature_type", "unknown"),
                (x1, y1 - 10),
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

        img_h, img_w = original_region_img.shape[:2]

        for feature in features:
            px_verts = (
                np.array(
                    [(v["x"] * grid_size, v["y"] * grid_size) for v in feature["gridVertices"]]
                )
            ).astype(np.int32)

            # 1. Get the feature's precise bounding box and center
            x, y, w, h = cv2.boundingRect(px_verts)
            center_x, center_y = x + w // 2, y + h // 2
            gx, gy = center_x // grid_size, center_y // grid_size
            preclassified_type = feature.get("featureType", "unknown")

            # 2. Define the crop window size (7x7 grid cells)
            crop_size = grid_size * 7
            half_crop = crop_size // 2

            # 3. Create a padded canvas to ensure the feature is always centered
            # Using a neutral gray color for padding.
            padded_canvas = np.full((crop_size, crop_size, 3), (128, 128, 128), dtype=np.uint8)

            # 4. Calculate source (from original image) and destination (on canvas) rects
            src_x1 = max(0, center_x - half_crop)
            src_y1 = max(0, center_y - half_crop)
            src_x2 = min(img_w, center_x + half_crop)
            src_y2 = min(img_h, center_y + half_crop)

            dest_x1 = half_crop - (center_x - src_x1)
            dest_y1 = half_crop - (center_y - src_y1)
            dest_x2 = dest_x1 + (src_x2 - src_x1)
            dest_y2 = dest_y1 + (src_y2 - src_y1)

            # 5. Extract the region from the original image and paste it centrally
            source_crop = original_region_img[src_y1:src_y2, src_x1:src_x2]
            if source_crop.size > 0:
                padded_canvas[dest_y1:dest_y2, dest_x1:dest_x2] = source_crop

            cropped_img = padded_canvas

            log_llm.debug(
                "  📤  Sending request to LLM for pre-classified '%s' at tile (%d, %d).",
                preclassified_type, gx, gy
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
                log_llm.warning("LLM analysis failed for feature at (%d, %d).", gx, gy)
                continue

            try:
                new_type = response_str.strip().lower().split(",")[0]
                if not new_type or new_type == "null":
                    continue # Skip if the LLM thinks it's empty space

                log_llm.info(
                    "    📦  LLM classified feature at tile (%d, %d) as '%s'.",
                    gx, gy, new_type
                )
                feature["featureType"] = new_type

            except (ValueError, IndexError) as e:
                log_llm.warning(
                    "Failed to parse response from LLM for feature at tile (%d, %d): %s. Response: '%s'",
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
                feature_type = parts[0].strip().lower()
                bbox_vals = [float(p.strip()) for p in parts[1:]]
                llm_features.append(
                    {
                        "feature_type": feature_type,
                        "bounding_box": {
                            "x1": bbox_vals[0],
                            "y1": bbox_vals[1],
                            "x2": bbox_vals[2],
                            "y2": bbox_vals[3],
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

            px_x1 = bbox.get("x1", 0) * img_w
            px_y1 = bbox.get("y1", 0) * img_h
            px_x2 = bbox.get("x2", 0) * img_w
            px_y2 = bbox.get("y2", 0) * img_h
            llm_cx = (px_x1 + px_x2) / 2
            llm_cy = (px_y1 + px_y2) / 2

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
