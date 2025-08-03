# --- ppdf_lib/api.py ---
import os
import json
import base64
import logging
import requests
from PIL import Image, UnidentifiedImageError
from io import BytesIO

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTImage

from .extractor import PDFTextExtractor
from .models import Section
from core.llm_utils import get_semantic_label

log = logging.getLogger("ppdf.api")


def _parse_page_selection(pages_str: str) -> set | None:
    """Parses a page selection string (e.g., '1,3,5-7') into a set of integers."""
    if pages_str.lower() == "all":
        return None
    pages = set()
    try:
        for p in pages_str.split(","):
            part = p.strip()
            if "-" in part:
                s, e = map(int, part.split("-"))
                pages.update(range(s, e + 1))
            else:
                pages.add(int(part))
        return pages
    except ValueError:
        log.error("Invalid page selection format: %s. Defaulting to 'all'.", pages_str)
        return None


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
    pdf_path: str,
    options: dict,
    ollama_url: str,
    model: str,
    apply_labeling=False,
    pages_str: str = "all",
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
    pages_to_process = _parse_page_selection(pages_str)
    sections = extractor.extract_sections(pages_to_process=pages_to_process)

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
    pages_str: str = "all",
):
    """
    Processes a PDF, extracts images, and yields progress messages.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    os.makedirs(output_dir, exist_ok=True)

    extractor = PDFTextExtractor(pdf_path)

    def find_images_recursively(layout_obj):
        if isinstance(layout_obj, LTImage):
            yield layout_obj
        if hasattr(layout_obj, "_objs"):
            for child in layout_obj:
                yield from find_images_recursively(child)

    image_count = 0
    pages_to_process = _parse_page_selection(pages_str)
    # pdfminer uses 0-indexed page numbers
    page_numbers = [p - 1 for p in pages_to_process] if pages_to_process else None

    pages = list(extract_pages(pdf_path, page_numbers=page_numbers))
    total_pages = len(list(extract_pages(pdf_path)))  # Get total for classification heuristic
    message = f"Found {len(pages)} pages to scan for images."
    log.info(message)
    yield message

    for i, page_layout in enumerate(pages):
        message = f"Scanning page {page_layout.pageid} ({i + 1}/{len(pages)})..."
        log.info(message)
        yield message
        for element in find_images_recursively(page_layout):
            if element.width < 50 or element.height < 50:
                log.debug("Skipping small image on page %d.", page_layout.pageid)
                continue

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
                message = f"Saved image {image_count} from page {page_layout.pageid}."
                log.info(message)
                yield message
            except UnidentifiedImageError:
                log.warning(
                    "Could not identify image format for an image on page %d. Skipping.",
                    page_layout.pageid,
                )
                continue
            except Exception as e:
                log.error("Could not save image %s: %s.", image_filename, e)
                continue

            with open(image_filename, "rb") as f:
                saved_image_bytes = f.read()

            description = _query_multimodal_llm(
                describe_prompt, saved_image_bytes, ollama_url, model
            )

            # Intelligent Classification
            page_type = extractor._classify_page_type(page_layout, [], [element], total_pages)
            if page_type in ["cover", "art"]:
                classification = page_type
                log.debug(
                    "Pre-classifying image on page %d as '%s'", page_layout.pageid, page_type
                )
            else:
                classification = _query_multimodal_llm(
                    classify_prompt, saved_image_bytes, ollama_url, model
                )

            valid_cats = {"cover", "art", "map", "decoration"}
            if classification.lower().strip() not in valid_cats:
                classification = "art"  # Default fallback

            message = f"Generated AI metadata for image {image_count}."
            log.info(message)
            yield message

            metadata = {
                "image_id": image_count,
                "page_number": page_layout.pageid,
                "bbox": [element.x0, element.y0, element.x1, element.y1],
                "description": description or "Description generation failed.",
                "classification": classification,
            }
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
