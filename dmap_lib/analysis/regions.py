# --- dmap_lib/analysis/regions.py ---
import logging
from typing import List, Dict, Any, Tuple

import cv2
import numpy as np
import easyocr

log = logging.getLogger("dmap.analysis")
log_ocr = logging.getLogger("dmap.ocr")

# Initialize the OCR reader once. This can take a moment on first run.
log_ocr.info("Initializing EasyOCR reader...")
OCR_READER = easyocr.Reader(["en"], gpu=False)
log_ocr.info("EasyOCR reader initialized.")


def detect_content_regions(img: np.ndarray) -> List[Dict[str, Any]]:
    """Stage 1: Detect distinct, separate content regions in the map image."""
    log.info("Executing Stage 1: Region Detection...")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    region_contexts = []
    min_area = img.shape[0] * img.shape[1] * 0.01
    for i, contour in enumerate(contours):
        if cv2.contourArea(contour) > min_area:
            x, y, w, h = cv2.boundingRect(contour)
            region_contexts.append(
                {
                    "id": f"region_{i}",
                    "contour": contour,
                    "bounds_rect": (x, y, w, h),
                    "bounds_img": img[y : y + h, x : x + w],
                }
            )
    log.info("Found %d potential content regions.", len(region_contexts))
    return region_contexts


def parse_text_metadata(
    region_contexts: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Stage 2: Classify regions and parse text for metadata."""
    log.info("Executing Stage 2: Text & Metadata Parsing...")
    if not region_contexts:
        return {}, []

    try:
        main_dungeon_idx = max(
            range(len(region_contexts)),
            key=lambda i: cv2.contourArea(region_contexts[i]["contour"]),
        )
    except ValueError:
        return {}, []

    metadata: Dict[str, Any] = {"title": None, "notes": "", "legend": ""}
    text_blobs = []

    for i, context in enumerate(region_contexts):
        if i == main_dungeon_idx:
            context["type"] = "dungeon"
            log.debug("Region '%s' classified as 'dungeon'.", context["id"])
            continue

        context["type"] = "text"
        log.debug("Region '%s' classified as 'text', running OCR.", context["id"])
        ocr_res = OCR_READER.readtext(context["bounds_img"], detail=1, paragraph=False)
        for bbox, text, prob in ocr_res:
            h = bbox[2][1] - bbox[0][1]
            text_blobs.append({"text": text, "height": h})

    if text_blobs:
        title_idx = max(range(len(text_blobs)), key=lambda i: text_blobs[i]["height"])
        metadata["title"] = text_blobs.pop(title_idx)["text"]
        metadata["notes"] = " ".join([b["text"] for b in text_blobs])

    title_str = f"'{metadata['title']}'" if metadata["title"] else "(Not found)"
    notes_str = f"'{metadata['notes']}'" if metadata["notes"] else "(None)"
    log_ocr.info(
        "OCR metadata extraction complete. Title: %s. Notes: %s", title_str, notes_str
    )
    return metadata, region_contexts
