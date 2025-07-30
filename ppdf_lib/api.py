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
from .constants import PROMPT_DESCRIBE_IMAGE, PROMPT_CLASSIFY_IMAGE

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
            timeout=90,  # Increased timeout for potentially slow vision models
        )
        response.raise_for_status()
        data = response.json()
        log.debug("LLM response received: %s", data.get("response", "").strip())
        return data.get("response", "").strip()
    except requests.exceptions.RequestException as e:
        log.error("Failed to query multimodal LLM: %s", e)
        return ""


def process_pdf_text(pdf_path: str, options: dict) -> tuple[list[Section], list]:
    """
    Processes a PDF file to extract and reconstruct structured text.

    Args:
        pdf_path (str): The absolute path to the PDF file.
        options (dict): A dictionary of options for PDFTextExtractor.
                        Expected keys: 'num_cols', 'rm_footers', 'style'.
    Returns:
        tuple[list[Section], list]: A tuple containing a list of Section objects
                                    and a list of PageModel objects.
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
    return sections, extractor.page_models


def process_pdf_images(pdf_path: str, output_dir: str, ollama_url: str, model: str):
    """
    Processes a PDF file to extract images and their metadata.

    Args:
        pdf_path (str): The absolute path to the PDF file.
        output_dir (str): The directory where extracted images and JSON metadata
                          will be saved.
        ollama_url (str): The URL of the Ollama API server.
        model (str): The name of the multimodal model to use.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    os.makedirs(output_dir, exist_ok=True)

    image_count = 0
    for page_layout in extract_pages(pdf_path):
        for element in page_layout:
            if isinstance(element, LTImage):
                image_count += 1
                img_id = f"image_{image_count:03d}"
                image_filename = os.path.join(output_dir, f"{img_id}.png")
                json_filename = os.path.join(output_dir, f"{img_id}.json")

                try:
                    image_data = element.stream.get_data()
                    img = Image.open(BytesIO(image_data))
                    # Convert to RGB if it has an alpha channel, common for PNGs
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    img.save(image_filename, "PNG")
                    log.info("Saved image: %s", image_filename)
                except Exception as e:
                    log.error("Could not save image %s: %s. Skipping.", image_filename, e)
                    continue

                # Read back the saved image bytes for the LLM call
                with open(image_filename, "rb") as f:
                    saved_image_bytes = f.read()

                # Get description from LLM
                description = _query_multimodal_llm(
                    PROMPT_DESCRIBE_IMAGE, saved_image_bytes, ollama_url, model
                )

                # Get classification from LLM
                classification = _query_multimodal_llm(
                    PROMPT_CLASSIFY_IMAGE, saved_image_bytes, ollama_url, model
                )
                valid_cats = {"art", "map", "decoration"}
                if classification not in valid_cats:
                    log.warning(
                        "LLM classification '%s' is invalid. Defaulting to 'art'.",
                        classification,
                    )
                    classification = "art"

                metadata = {
                    "image_id": image_count,
                    "page_number": page_layout.pageid,
                    "bbox": [element.x0, element.y0, element.x1, element.y1],
                    "description": description or "Description generation failed.",
                    "classification": classification,
                }
                with open(json_filename, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=4)
                log.info("Saved metadata: %s", json_filename)
    log.info("Extracted %d images and metadata to %s", image_count, output_dir)
