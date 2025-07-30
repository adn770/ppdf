import os
import json
from PIL import Image
from io import BytesIO

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTImage

from .extractor import PDFTextExtractor, Section


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


def process_pdf_images(pdf_path: str, output_dir: str):
    """
    Processes a PDF file to extract images and their metadata.

    Args:
        pdf_path (str): The absolute path to the PDF file.
        output_dir (str): The directory where extracted images and JSON metadata
                          will be saved.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    os.makedirs(output_dir, exist_ok=True)

    image_count = 0
    for page_layout in extract_pages(pdf_path):
        for element in page_layout:
            if isinstance(element, LTImage):
                image_count += 1
                image_filename = os.path.join(output_dir, f"image_{image_count:03d}.png")
                json_filename = os.path.join(output_dir, f"image_{image_count:03d}.json")

                try:
                    image_data = element.stream.get_data()
                    img = Image.open(BytesIO(image_data))
                    img.save(image_filename)
                    print(f"Saved image: {image_filename}")
                except Exception as e:
                    print(f"Could not save image {image_filename}: {e}. Skipping.")
                    continue  # Skip to the next element if image extraction fails

                # Placeholder for LLM call and metadata
                metadata = {
                    "image_id": image_count,
                    "page_number": page_layout.pageid,
                    "bbox": [element.x0, element.y0, element.x1, element.y1],
                    "description": "LLM_DESCRIPTION_PLACEHOLDER",
                    "classification": "LLM_CLASSIFICATION_PLACEHOLDER",
                }
                with open(json_filename, "w") as f:
                    json.dump(metadata, f, indent=4)
                print(f"Saved metadata: {json_filename}")
    print(f"Extracted {image_count} images and metadata to {output_dir}")
