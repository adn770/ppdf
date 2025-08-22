# --- dmap_lib/analysis/color.py ---
import logging
from collections import Counter
from typing import Tuple, Dict, Any

import cv2
import numpy as np
from sklearn.cluster import KMeans

log = logging.getLogger("dmap.analysis")


class ColorAnalyzer:
    """Encapsulates color quantization and semantic role assignment."""

    def analyze(self, img: np.ndarray, num_colors: int = 8) -> Tuple[Dict[str, Any], KMeans]:
        """
        Analyzes image colors and returns a color profile.
        """
        log.info("⚙️  Executing Stage 3: Multi-Pass Color Analysis...")
        pixels = img.reshape(-1, 3)
        kmeans = KMeans(n_clusters=num_colors, random_state=42, n_init=10).fit(pixels)
        palette_bgr = kmeans.cluster_centers_.astype("uint8")
        palette_rgb = [tuple(c[::-1]) for c in palette_bgr]

        color_profile = {"palette": palette_rgb, "roles": {}}
        roles = color_profile["roles"]
        unassigned_colors = list(palette_rgb)
        all_labels = kmeans.labels_.reshape(img.shape[:2])
        h, w, _ = img.shape

        # --- Pass 1: Anchor Color Identification (Floor) ---
        center_img = img[h // 4 : h * 3 // 4, w // 4 : w * 3 // 4, :]
        center_pixels = center_img.reshape(-1, 3)
        center_labels = kmeans.predict(center_pixels)
        center_counts = Counter(center_labels)
        floor_color = None
        for label, _ in center_counts.most_common():
            p_color = tuple(kmeans.cluster_centers_[label].astype("uint8")[::-1])
            if p_color in unassigned_colors:
                floor_color = p_color
                break
        if floor_color:
            roles[floor_color] = "floor"
            unassigned_colors.remove(floor_color)

        # --- Pass 2: Stroke Identification via Edge Sampling ---
        stroke_rgb = None
        if floor_color:
            floor_bgr = np.array(floor_color[::-1], dtype="uint8")
            floor_mask = cv2.inRange(img, floor_bgr, floor_bgr)
            contours, _ = cv2.findContours(
                floor_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            edge_pixels = []
            for contour in contours:
                for point in contour:
                    edge_pixels.append(img[point[0][1], point[0][0]])

            if edge_pixels:
                edge_labels = kmeans.predict(edge_pixels)
                valid_labels = [
                    l
                    for l in edge_labels
                    if tuple(kmeans.cluster_centers_[l].astype("uint8")[::-1])
                    in unassigned_colors
                ]
                if valid_labels:
                    stroke_label = Counter(valid_labels).most_common(1)[0][0]
                    stroke_rgb = tuple(
                        kmeans.cluster_centers_[stroke_label].astype("uint8")[::-1]
                    )
                    roles[stroke_rgb] = "stroke"
                    unassigned_colors.remove(stroke_rgb)

        # Fallback if edge sampling fails
        if not stroke_rgb and unassigned_colors:
            stroke_rgb = min(unassigned_colors, key=sum)
            roles[stroke_rgb] = "stroke"
            unassigned_colors.remove(stroke_rgb)

        # --- Pass 3: Border Color Identification (Glow & Shadow) ---
        stroke_label = kmeans.predict([np.array(stroke_rgb[::-1])])[0]
        stroke_mask = (all_labels == stroke_label).astype(np.uint8)
        dilated_mask = cv2.dilate(stroke_mask, np.ones((3, 3), np.uint8), iterations=2)
        search_mask = dilated_mask - stroke_mask
        adjacent_labels = all_labels[search_mask == 1]
        valid_adj = [
            l
            for l in adjacent_labels
            if tuple(kmeans.cluster_centers_[l].astype("uint8")[::-1]) in unassigned_colors
        ]
        if len(valid_adj) > 1:
            top_two = [item[0] for item in Counter(valid_adj).most_common(2)]
            c1 = tuple(kmeans.cluster_centers_[top_two[0]].astype("uint8")[::-1])
            c2 = tuple(kmeans.cluster_centers_[top_two[1]].astype("uint8")[::-1])
            if sum(c1) > sum(c2):
                glow_rgb, shadow_rgb = c1, c2
            else:
                glow_rgb, shadow_rgb = c2, c1
            roles[glow_rgb] = "glow"
            unassigned_colors.remove(glow_rgb)
            roles[shadow_rgb] = "shadow"
            unassigned_colors.remove(shadow_rgb)

        # --- Pass 4: Environmental Layer Identification (Water) ---
        if unassigned_colors:
            candidates = []
            rgb_to_label = {tuple(c[::-1]): i for i, c in enumerate(palette_bgr)}
            for color in unassigned_colors:
                label = rgb_to_label[color]
                mask = (all_labels == label).astype(np.uint8) * 255
                contours, _ = cv2.findContours(
                    mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                total_area = sum(cv2.contourArea(c) for c in contours)
                candidates.append((total_area, color))
            if candidates:
                best = max(candidates, key=lambda item: item[0])
                if best[0] > 500:  # Threshold for minimum area
                    water_color = best[1]
                    roles[water_color] = "water"
                    unassigned_colors.remove(water_color)
                    log.debug("Identified water color: %s", str(water_color))

        # --- Pass 5: Final Alias Classification ---
        primary_roles = list(roles.items())
        if primary_roles:
            for alias_color in unassigned_colors:
                closest = min(
                    primary_roles,
                    key=lambda i: np.linalg.norm(np.array(alias_color) - np.array(i[0])),
                )
                roles[alias_color] = f"alias_{closest[1]}"

        log.debug("--- Advanced Color Profile ---")
        for color, role in roles.items():
            log.debug("RGB: %-15s -> Role: %s", str(color), role)

        return color_profile, kmeans
