# --- dmap_lib/analysis/features.py ---
import logging
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
from sklearn.cluster import KMeans

from dmap_lib.llm import query_llava
from dmap_lib.prompts import LLAVA_PROMPT_CLASSIFIER

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

    def __init__(self, ollama_url: str, ollama_model: str):
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        log_llm.info("LLaVA Feature Enhancer initialized.")

    def enhance(
        self,
        enhancement_layers: Dict[str, Any],
        original_region_img: np.ndarray,
        grid_size: int,
    ) -> Dict[str, Any]:
        """Crops features, sends them to LLaVA for analysis, and logs the result."""
        features = enhancement_layers.get("features", [])
        if not features:
            return enhancement_layers

        # 1. Process only the first feature for now to verify the API call
        feature = features[0]
        verts = (
            np.array(feature["high_res_vertices"]) * grid_size / 8.0
        ).astype(np.int32)
        x, y, w, h = cv2.boundingRect(verts)

        padding = int(grid_size * 0.2)
        x1, y1 = max(0, x - padding), max(0, y - padding)
        x2, y2 = min(original_region_img.shape[1], x + w + padding), min(
            original_region_img.shape[0], y + h + padding
        )

        cropped_feature_img = original_region_img[y1:y2, x1:x2]

        if cropped_feature_img.size == 0:
            log_llm.warning("Cropped feature image is empty. Skipping.")
            return enhancement_layers

        # 2. Call the LLaVA API
        log_llm.info("Sending feature to LLaVA for classification...")
        llava_response = query_llava(
            prompt=LLAVA_PROMPT_CLASSIFIER,
            image=cropped_feature_img,
            ollama_url=self.ollama_url,
            model=self.ollama_model,
        )

        # 3. Log the raw response for debugging
        log_llm.debug("LLaVA raw response:\n%s", llava_response)

        return enhancement_layers
