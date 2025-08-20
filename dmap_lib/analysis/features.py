# --- dmap_lib/analysis/features.py ---
import logging
import os
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
from sklearn.cluster import KMeans

from dmap_lib.llm import query_llava
from dmap_lib.prompts import LLAVA_PROMPT_CLASSIFIER, LLAVA_PROMPT_ORACLE

log = logging.getLogger("dmap.analysis")
log_llm = logging.getLogger("dmap.llm")


class FeatureExtractor:
    """Handles detection of non-grid-aligned features."""

    def extract(
        self,
        original_region_img: np.ndarray,
        room_contours: List[np.ndarray],
        grid_size: int,
        color_profile: Dict[str, Any],
        kmeans: KMeans,
    ) -> Dict[str, Any]:
        """Extracts high-resolution features like columns and water."""
        log.debug("Extracting high-resolution features and layers...")
        enhancements: Dict[str, List] = {"features": [], "layers": []}
        roles_inv = {v: k for k, v in color_profile["roles"].items()}
        labels = kmeans.predict(original_region_img.reshape(-1, 3))

        # --- 1. Detect Water Layers ---
        if "water" in roles_inv:
            w_rgb = roles_inv["water"]
            w_bgr = np.array(w_rgb[::-1], dtype="uint8")
            w_cen = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - w_bgr))
            w_lab = kmeans.predict([w_cen])[0]
            w_mask = (labels == w_lab).reshape(original_region_img.shape[:2])
            w_mask_u8 = w_mask.astype("uint8") * 255
            cnts, _ = cv2.findContours(
                w_mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            for c in cnts:
                if cv2.contourArea(c) > grid_size * grid_size:
                    verts = [(v[0][0]/grid_size*8.0, v[0][1]/grid_size*8.0) for v in c]
                    enhancements["layers"].append({"layerType": "water",
                                                   "high_res_vertices": verts,
                                                   "properties": {"z-order": 0}})

        # --- 2. Detect Column Features ---
        if room_contours:
            s_rgb = roles_inv.get("stroke", (0,0,0))
            s_bgr = np.array(s_rgb[::-1], dtype="uint8")
            s_cen = min(kmeans.cluster_centers_, key=lambda c: np.linalg.norm(c - s_bgr))
            s_lab = kmeans.predict([s_cen])[0]
            s_mask = (labels == s_lab).reshape(original_region_img.shape[:2])
            s_mask_u8 = s_mask.astype("uint8") * 255
            cnts, _ = cv2.findContours(s_mask_u8, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

            min_area = (grid_size * grid_size) * 0.05
            max_area = (grid_size * grid_size) * 2.0

            for c in cnts:
                area = cv2.contourArea(c)
                if not (min_area < area < max_area):
                    continue
                M = cv2.moments(c)
                if M["m00"] == 0:
                    continue
                cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
                if any(cv2.pointPolygonTest(rc, (cx, cy), False) >= 0
                       for rc in room_contours):
                    verts = [(v[0][0]/grid_size*8.0, v[0][1]/grid_size*8.0) for v in c]
                    enhancements["features"].append({"featureType": "column",
                                                     "high_res_vertices": verts,
                                                     "properties": {"z-order": 1}})

        log.info(
            "Detected %d features and %d layers.",
            len(enhancements["features"]),
            len(enhancements["layers"]),
        )
        return enhancements


class LLaVAFeatureEnhancer:
    """Enhances feature classification using a multimodal LLM (LLaVA)."""

    def __init__(
        self,
        ollama_url: str,
        ollama_model: str,
        llava_mode: str,
        temperature: float,
        context_size: int,
    ):
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.llava_mode = llava_mode
        self.temperature = temperature
        self.context_size = context_size
        log_llm.info("LLaVA Feature Enhancer initialized in '%s' mode.", llava_mode)

    def enhance(
        self,
        enhancement_layers: Dict[str, Any],
        original_region_img: np.ndarray,
        grid_size: int,
        region_id: str,
        save_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Crops features and sends them to LLaVA for analysis."""
        if self.llava_mode == "classifier":
            return self._enhance_classifier(
                enhancement_layers, original_region_img, grid_size, region_id, save_path
            )
        elif self.llava_mode == "oracle":
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
        geom_color, llm_color = (255, 0, 0), (0, 0, 255)  # Blue, Red

        for feature in geom_features:
            px_verts = (
                np.array(feature["high_res_vertices"]) * grid_size / 8.0
            ).astype(np.int32)
            x, y, w, h = cv2.boundingRect(px_verts)
            cv2.rectangle(debug_img, (x, y), (x + w, y + h), geom_color, 2)

        for feature in llm_features:
            bbox = feature.get("bounding_box")
            if not bbox:
                continue
            x, y, w, h = bbox.get("x", 0), bbox.get("y", 0), bbox.get("width", 0), bbox.get("height", 0)
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

        filename = os.path.join(save_path, f"{region_id}_llava_oracle_reconciliation.png")
        cv2.imwrite(filename, debug_img)
        log.info("Saved LLaVA oracle debug image to %s", filename)

    def _save_classifier_debug_image(
        self,
        img: np.ndarray,
        classified_features: List[Dict[str, Any]],
        grid_size: int,
        region_id: str,
        save_path: str,
    ):
        debug_img = img.copy()
        feature_color = (0, 255, 0)  # Green

        for feature in classified_features:
            px_verts = (
                np.array(feature["high_res_vertices"]) * grid_size / 8.0
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

        filename = os.path.join(save_path, f"{region_id}_llava_classifier_results.png")
        cv2.imwrite(filename, debug_img)
        log.info("Saved LLaVA classifier debug image to %s", filename)

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
            verts = (
                np.array(feature["high_res_vertices"]) * grid_size / 8.0
            ).astype(np.int32)
            M = cv2.moments(verts)
            if M["m00"] == 0:
                continue

            # 1. Find the centroid and the grid tile it belongs to
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            gx, gy = cx // grid_size, cy // grid_size

            # 2. Calculate the 3x3 grid area for the crop
            crop_size = 3 * grid_size
            x1 = max(0, (gx - 1) * grid_size)
            y1 = max(0, (gy - 1) * grid_size)
            x2 = min(original_region_img.shape[1], (gx + 2) * grid_size)
            y2 = min(original_region_img.shape[0], (gy + 2) * grid_size)

            cropped_feature_img = original_region_img[y1:y2, x1:x2]
            if cropped_feature_img.size == 0:
                continue

            response = query_llava(
                self.ollama_url,
                self.ollama_model,
                cropped_feature_img,
                LLAVA_PROMPT_CLASSIFIER,
                temperature=self.temperature,
                context_size=self.context_size,
            )

            if response and "feature_type" in response:
                new_type = response["feature_type"]
                if isinstance(new_type, str):
                    log_llm.info(
                        "LLaVA classified feature at tile (%d, %d) as '%s'.",
                        gx,
                        gy,
                        new_type,
                    )
                    feature["featureType"] = new_type
                else:
                    log_llm.warning("LLaVA returned invalid feature_type: %s", new_type)
            else:
                log_llm.warning("LLaVA analysis failed or returned invalid format.")

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
        log_llm.info("Querying LLaVA in oracle mode...")
        response = query_llava(
            self.ollama_url,
            self.ollama_model,
            original_region_img,
            LLAVA_PROMPT_ORACLE,
            temperature=self.temperature,
            context_size=self.context_size,
        )

        if not response or "features" not in response:
            log_llm.warning("LLaVA oracle analysis failed or returned invalid format.")
            return enhancement_layers

        llm_features = response["features"]
        if not isinstance(llm_features, list):
            log_llm.warning("LLaVA oracle returned non-list for 'features'.")
            return enhancement_layers

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
            verts = (np.array(feature["high_res_vertices"]) * grid_size / 8.0)
            M = cv2.moments(verts.astype(np.int32))
            if M["m00"] != 0:
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]
                geom_centroids.append((cx, cy))
            else:
                geom_centroids.append(None)

        reconciliation_count = 0
        for llm_feature in llm_features:
            bbox = llm_feature.get("bounding_box")
            if not bbox:
                continue
            llm_cx = bbox.get("x", 0) + bbox.get("width", 0) / 2
            llm_cy = bbox.get("y", 0) + bbox.get("height", 0) / 2

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
                        old_type, new_type, min_dist
                    )
                    reconciliation_count += 1

        log_llm.info("Reconciliation complete. Updated %d features.", reconciliation_count)
        if save_path:
            self._save_oracle_debug_image(
                original_region_img, geom_features, llm_features, grid_size, region_id, save_path
            )
        return enhancement_layers
