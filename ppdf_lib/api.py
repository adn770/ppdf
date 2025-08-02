# --- ppdf_lib/api.py ---
import os
import json
import base64
import logging
import requests
from PIL import Image
from io import BytesIO

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTImage

from .extractor import PDFTextExtractor, Section
from core.llm_utils import get_semantic_label

log = logging.getLogger("ppdf.api")


def _query_multimodal_llm(prompt: str, image_bytes: bytes, ollama_url: str, model: str) -> str:
    """Sends a prompt and a single image to an Ollama multimodal model."""
    if not image_bytes:
        log.error("No image bytes provided for multimodal query.")
        return ""

    encoded_image = base64.b64encode(image_bytes).decode("utf-8")

    try:
        log.debug("Querying multimodal LLM '%s'...", model)
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "images": [encoded_image],
                "stream": False,
            },
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        log.debug("LLM response received: %s", data.get("response", "").strip())
        return data.get("response", "").strip()
    except requests.exceptions.RequestException as e:
        log.error("Failed to query multimodal LLM: %s", e)
        return ""


def process_pdf_text(
    pdf_path: str, options: dict, ollama_url: str, model: str, apply_labeling=False
) -> tuple[list[Section], list]:
    """
    Processes a PDF file to extract and reconstruct structured text.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    extractor = PDFTextExtractor(
        pdf_path,
        num_cols=options.get("num_cols", "auto"),
        rm_footers=options.get("rm_footers", True),
        style=options.get("style", False),
    )
    sections = extractor.extract_sections()

    # Note: Semantic labeling is now handled by the dmme IngestionService,
    # which has access to the internationalized prompts.
    # This function is now only responsible for raw structural extraction.

    return sections, extractor.page_models


def process_pdf_images(
    pdf_path: str,
    output_dir: str,
    ollama_url: str,
    model: str,
    describe_prompt: str,
    classify_prompt: str,
):
    """
    Processes a PDF, extracts images, and yields progress messages.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    os.makedirs(output_dir, exist_ok=True)

    def find_images_recursively(layout_obj):
        if isinstance(layout_obj, LTImage):
            yield layout_obj
        if hasattr(layout_obj, "_objs"):
            for child in layout_obj:
                yield from find_images_recursively(child)

    image_count = 0
    pages = list(extract_pages(pdf_path))
    yield f"Found {len(pages)} pages to scan for images."

    for i, page_layout in enumerate(pages):
        yield f"Scanning page {i + 1}/{len(pages)}..."
        for element in find_images_recursively(page_layout):
            image_count += 1
            img_id = f"image_{image_count:03d}"
            image_filename = os.path.join(output_dir, f"{img_id}.png")
            json_filename = os.path.join(output_dir, f"{img_id}.json")

            try:
                image_data = element.stream.get_data()
                if not image_data:
                    log.warning("Image %s has no data stream, skipping.", img_id)
                    continue
                img = Image.open(BytesIO(image_data))
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(image_filename, "PNG")
                yield f"Saved image {image_count} from page {page_layout.pageid}."
            except Exception as e:
                log.error("Could not save image %s: %s.", image_filename, e)
                continue

            with open(image_filename, "rb") as f:
                saved_image_bytes = f.read()

            description = _query_multimodal_llm(
                describe_prompt, saved_image_bytes, ollama_url, model
            )
            classification = _query_multimodal_llm(
                classify_prompt, saved_image_bytes, ollama_url, model
            )
            valid_cats = {"art", "map", "decoration"}
            if classification.lower().strip() not in valid_cats:
                classification = "art"
            yield f"Generated AI metadata for image {image_count}."

            metadata = {
                "image_id": image_count,
                "page_number": page_layout.pageid,
                "bbox": [element.x0, element.y0, element.x1, element.y1],
                "description": description or "Description generation failed.",
                "classification": classification,
            }
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
