# --- ppdf_lib/api.py ---
import os
import json
import logging
import re
import requests
from PIL import Image, UnidentifiedImageError
from io import BytesIO
from flask import current_app

from pdfminer.high_level import extract_pages
from pdfminer.layout import LTImage

from .extractor import PDFTextExtractor
from .models import Section
from core.llm_utils import query_multimodal_llm

log = logging.getLogger("ppdf.api")


def _get_classification_model():
    """Gets the classification model from the app's config service."""
    # This check is needed because ppdf.py can run standalone without a Flask app context
    if not current_app:
        return "llama3:latest"  # Fallback for standalone mode
    return current_app.config_service.get_settings()["Ollama"]["classification_model"]


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


def _chunk_text_by_paragraphs(text: str, max_size: int):
    """
    Splits text into chunks of a maximum size without breaking paragraphs.
    Yields each chunk as a string.
    """
    paragraphs = re.split(r"\n{2,}", text.strip())
    current_chunk_parts = []
    current_chunk_size = 0

    for para in paragraphs:
        para_size = len(para)
        if current_chunk_parts and current_chunk_size + para_size + 2 > max_size:
            yield "\n\n".join(current_chunk_parts)
            current_chunk_parts = [para]
            current_chunk_size = para_size
        else:
            current_chunk_parts.append(para)
            current_chunk_size += para_size + 2

    if current_chunk_parts:
        yield "\n\n".join(current_chunk_parts)


def _query_llm_api_stream(payload: dict, url: str):
    """
    Helper to query the Ollama generate endpoint and yield response chunks.
    Yields structured JSON data from the stream.
    """
    try:
        r = requests.post(f"{url}/api/generate", json=payload, stream=True)
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                try:
                    yield json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
    except requests.exceptions.RequestException as e:
        log.error("Ollama API request failed: %s", e)
        yield {"error": str(e)}


def reformat_section_with_llm(
    section: Section,
    system_prompt: str,
    ollama_url: str,
    model: str,
    chunk_size: int,
    temperature: float = 0.2,
    no_fmt_titles: bool = False,
    is_final_section: bool = False,
):
    """
    Takes a Section object, reformats its content via LLM, and streams the result.
    This is a generator function.
    """
    title = section.title or "Untitled"
    if not no_fmt_titles:
        title = title.upper()

    section_text = section.get_llm_text()
    user_content_base = f"# {title}\n\n" if not no_fmt_titles else f"{title}\n\n"

    chunks = list(_chunk_text_by_paragraphs(section_text, chunk_size))

    for i, chunk_text in enumerate(chunks):
        user_content = user_content_base + chunk_text if i == 0 else chunk_text

        stop_sequences = None
        is_final_chunk = is_final_section and i == len(chunks) - 1
        if is_final_chunk:
            stop_sequences = ["||END||"]
            lure = "The next document begins:"
            user_content += stop_sequences[0] + lure

        options = {"temperature": temperature}
        if stop_sequences:
            options["stop"] = stop_sequences

        payload = {
            "model": model,
            "system": system_prompt,
            "prompt": user_content,
            "stream": True,
            "options": options,
        }

        full_response = ""
        for j in _query_llm_api_stream(payload, ollama_url):
            if j.get("error"):
                yield f"[ERROR: {j.get('error')}]"
                break

            response_chunk = j.get("response", "")
            if response_chunk:
                full_response += response_chunk
                yield response_chunk

            if j.get("done"):
                # Handle stop sequence logic after the stream for the chunk is done
                if is_final_chunk and stop_sequences:
                    # This part is tricky with generators. The final output needs to be post-processed.
                    # A simpler approach for the library is to just yield everything and let the caller handle it.
                    # Or, we can buffer and yield. For now, let's assume caller handles stripping.
                    pass


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


def analyze_pdf_structure(pdf_path: str, pages_str: str = "all") -> list[dict]:
    """
    Performs a read-only analysis of a PDF to get its logical section structure.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    # Use default extractor settings for analysis
    extractor = PDFTextExtractor(pdf_path)
    pages_to_process = _parse_page_selection(pages_str)
    sections = extractor.extract_sections(pages_to_process=pages_to_process)

    # Convert Section objects to a JSON-serializable list of dictionaries
    section_list = [
        {
            "title": s.title or "Untitled Section",
            "page_start": s.page_start,
            "page_end": s.page_end,
            "char_count": len(s.get_text()),
        }
        for s in sections
    ]
    return section_list


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

    # Parse all pages once to be efficient
    all_page_layouts = list(extract_pages(pdf_path))
    total_pages = len(all_page_layouts)

    # Filter pages in memory based on user selection
    pages_to_scan = [
        p for p in all_page_layouts if not pages_to_process or p.pageid in pages_to_process
    ]

    message = f"Found {len(pages_to_scan)} pages to scan for images."
    log.info(message)
    yield message

    for i, page_layout in enumerate(pages_to_scan):
        message = f"Scanning page {page_layout.pageid} ({i + 1}/{len(pages_to_scan)})..."
        log.info(message)
        yield message
        for element in find_images_recursively(page_layout):
            if element.width < 50 or element.height < 50:
                log.debug("Skipping small image on page %d.", page_layout.pageid)
                continue

            image_count += 1
            img_id = f"image_{image_count:03d}"
            image_filename = os.path.join(output_dir, f"{img_id}.png")
            thumb_filename = os.path.join(output_dir, f"thumb_{img_id}.jpg")
            json_filename = os.path.join(output_dir, f"{img_id}.json")

            image_data = None
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

                # --- Create and save thumbnail ---
                img.thumbnail((256, 256))
                img.save(thumb_filename, "JPEG", quality=85)
                yield f"  -> Created thumbnail for image {image_count}."

            except UnidentifiedImageError:
                log.warning(
                    "Could not identify image format for an image on page %d. "
                    "Attempting raw reconstruction.",
                    page_layout.pageid,
                )
                if image_data:
                    first_32_bytes = image_data[:32]
                    hexdump = " ".join(f"{byte:02x}" for byte in first_32_bytes)
                    stream_attrs = element.stream.attrs if hasattr(element, "stream") else {}
                    log.debug(
                        (
                            "Unidentified image details:\n"
                            "  - Name: %s\n"
                            "  - Dimensions: %dx%d\n"
                            "  - Stream Attrs: %s\n"
                            "  - Data Length: %d bytes\n"
                            "  - First 32 bytes: %s"
                        ),
                        element.name,
                        element.width,
                        element.height,
                        stream_attrs,
                        len(image_data),
                        hexdump,
                    )
                    # --- Fallback logic for raw image data ---
                    try:
                        width = stream_attrs.get("Width")
                        height = stream_attrs.get("Height")
                        if not (width and height):
                            log.warning("Stream Attrs missing Width/Height. Skipping.")
                            continue

                        size = (width, height)
                        data_len = len(image_data)
                        mode = None

                        # Determine mode from stream attrs first
                        bpc = stream_attrs.get("BitsPerComponent")
                        cs = stream_attrs.get("ColorSpace")

                        if bpc == 1:
                            mode = "1"
                        elif bpc == 8:
                            if cs == b"/DeviceGray":
                                mode = "L"
                            elif cs == b"/DeviceRGB" or isinstance(cs, list):
                                mode = "RGB"

                        # If mode is still unknown, fallback to data length heuristic
                        if not mode:
                            if data_len == size[0] * size[1]:
                                mode = "L"
                            elif data_len == size[0] * size[1] * 3:
                                mode = "RGB"
                            elif data_len == size[0] * size[1] * 4:
                                mode = "RGBA"

                        if mode:
                            log.debug(
                                "Attempting reconstruction with mode '%s' and true "
                                "dimensions %s",
                                mode,
                                size,
                            )
                            img = Image.frombytes(mode, size, image_data)
                            img.save(image_filename, "PNG")
                            message = (
                                "Successfully reconstructed and saved raw image "
                                f"{image_count}."
                            )
                            log.info(message)
                            yield message
                        else:
                            log.warning("Could not determine raw image mode. Skipping.")
                            continue
                    except Exception as recon_e:
                        log.error("Raw image reconstruction failed: %s", recon_e)
                        continue
                else:
                    continue
            except Exception as e:
                log.error("Could not save image %s: %s.", image_filename, e)
                continue

            with open(image_filename, "rb") as f:
                saved_image_bytes = f.read()

            description = query_multimodal_llm(
                describe_prompt, saved_image_bytes, ollama_url, model
            )

            # Intelligent Classification
            classification_model = _get_classification_model()
            page_type = extractor._classify_page_type(page_layout, [], [element], total_pages)
            if page_type in ["cover", "art"]:
                classification = page_type
                log.debug(
                    "Pre-classifying image on page %d as '%s'", page_layout.pageid, page_type
                )
            else:
                classification = query_multimodal_llm(
                    classify_prompt,
                    saved_image_bytes,
                    ollama_url,
                    classification_model,
                    temperature=0.1,
                )
                log.debug(
                    "Image Classification:\n"
                    "  - Model: %s\n"
                    "  - Prompt: %s\n"
                    "  - Classification: %s",
                    classification_model,
                    classify_prompt.replace("\n", " "),
                    classification,
                )

            valid_cats = {"cover", "art", "map", "handout", "decoration", "other"}
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
                "thumbnail_filename": os.path.basename(thumb_filename),
            }
            with open(json_filename, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
