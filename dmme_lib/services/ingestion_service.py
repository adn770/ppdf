# --- dmme_lib/services/ingestion_service.py ---
import logging
import re
import os
import json
import shutil
import uuid
from PIL import Image
from io import BytesIO
from flask import current_app
from .vector_store_service import VectorStoreService
from core.llm_utils import (
    get_semantic_label,
    query_text_llm,
    get_model_details,
    query_multimodal_llm,
)
from ppdf_lib.api import process_pdf_text, reformat_section_with_llm
from ppdf_lib.models import Section
from dmme_lib.constants import PROMPT_REGISTRY
from ppdf_lib.constants import PROMPT_STRICT

log = logging.getLogger("dmme.ingest")


class IngestionService:
    def __init__(
        self,
        vector_store: VectorStoreService,
        ollama_url: str,
        dm_model: str,
        vision_model: str,
        utility_model: str,
    ):
        self.vector_store = vector_store
        self.ollama_url = ollama_url
        self.dm_model = dm_model
        self.vision_model = vision_model
        self.utility_model = utility_model
        log.info("IngestionService initialized.")

    def _get_prompt(self, key: str, lang: str) -> str:
        """Safely retrieves a prompt from the registry, falling back to English."""
        return PROMPT_REGISTRY.get(key, {}).get(lang, PROMPT_REGISTRY.get(key, {}).get("en"))

    def _format_text_for_log(self, text: str) -> str:
        """Formats a long text block into a concise, single-line summary for logging."""
        single_line_text = re.sub(r"\s+", " ", text).strip()
        if len(single_line_text) > 100:
            return f'"{single_line_text[:45]}...{single_line_text[-45:]}"'
        return f'"{single_line_text}"'

    def ingest_markdown(self, file_content: str, metadata: dict):
        """Processes and ingests a Markdown file's content, yielding progress."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        if not kb_name:
            raise ValueError("Knowledge base name is required for ingestion.")

        msg = f"✔ Starting Markdown processing for KB '{kb_name}' in '{lang}'."
        log.info(msg)
        yield msg
        chunks = [c.strip() for c in re.split(r"\n{2,}", file_content) if c.strip()]
        msg = f"Splitting file into {len(chunks)} raw chunks."
        log.info(msg)
        yield msg

        labeler_prompt = self._get_prompt("SEMANTIC_LABELER", lang)
        documents, metadatas = [], []

        valid_chunks = [c for c in chunks if len(c) >= 50]
        num_valid = len(valid_chunks)

        for i, chunk in enumerate(valid_chunks):
            msg = f"  -> Applying semantic label to chunk {i + 1}/{num_valid}..."
            log.info(msg)
            yield msg
            label = get_semantic_label(
                chunk, labeler_prompt, self.ollama_url, self.utility_model
            )
            log.debug(
                "Semantic Labeling:\n" "  - Model: %s\n" "  - Input: %s\n" "  - Label: %s",
                self.utility_model,
                self._format_text_for_log(chunk),
                label,
            )

            documents.append(chunk)
            metadatas.append(
                {
                    "source_file": metadata.get("filename", "unknown.md"),
                    "chunk_id": i,
                    "label": label,
                }
            )

        if not documents:
            msg = "✔ No valid text chunks found to ingest."
            log.info(msg)
            yield msg
            return

        msg = f"✔ Processing complete. Found {len(documents)} valid chunks."
        log.info(msg)
        yield msg
        msg = "Generating embeddings and saving to vector store..."
        log.info(msg)
        yield msg
        self.vector_store.add_to_kb(kb_name, documents, metadatas, kb_metadata=metadata)
        msg = "✔ Saved to vector store."
        log.info(msg)
        yield msg

    def _chunk_reformatted_section(self, section: Section, formatted_text: str):
        """
        Applies heuristics to chunk a reformatted section into contextually-rich documents.
        """
        # Heuristic 1: Ingest small sections as a single chunk.
        if len(formatted_text) < 1500:
            log.debug("Applying 'small section' heuristic to '%s'.", section.title)
            yield formatted_text
            return

        # Heuristic 2: Ingest sections with only a table as a single chunk.
        if len(section.paragraphs) == 1 and section.paragraphs[0].is_table:
            log.debug("Applying 'table-only section' heuristic to '%s'.", section.title)
            yield formatted_text
            return

        # Heuristic 3: Chunk based on original paragraph boundaries.
        log.debug("Applying 'paragraph boundary' chunking to '%s'.", section.title)
        para_starts = []
        search_offset = 0
        for para in section.paragraphs:
            if not para.lines or not para.lines[0].strip():
                continue

            # Use the start of the first line (first 30 chars) as a unique anchor.
            anchor = para.lines[0].strip()[:30]
            try:
                # Find this anchor in the formatted text.
                pos = formatted_text.index(anchor, search_offset)
                para_starts.append(pos)
                search_offset = pos + 1
            except ValueError:
                log.debug("Could not find anchor for a paragraph in '%s'.", section.title)

        if not para_starts:
            log.warning(
                "Could not find any paragraph boundaries in '%s'. Yielding as one chunk.",
                section.title,
            )
            yield formatted_text
            return

        for i, start_index in enumerate(para_starts):
            end_index = para_starts[i + 1] if i + 1 < len(para_starts) else len(formatted_text)
            chunk = formatted_text[start_index:end_index].strip()
            if chunk:
                yield chunk

    def ingest_pdf_text(
        self,
        pdf_path: str,
        metadata: dict,
        pages_str: str = "all",
        sections_to_include: list[str] | None = None,
    ):
        """Processes and ingests a PDF file's text content, yielding progress."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        if not kb_name:
            raise ValueError("Knowledge base name is required for ingestion.")

        msg = f"Analyzing PDF structure for '{kb_name}' (Pages: {pages_str})..."
        log.info(msg)
        yield msg
        extraction_options = {"num_cols": "auto", "rm_footers": True, "style": False}
        sections, page_models = process_pdf_text(
            pdf_path, extraction_options, "", "", apply_labeling=False, pages_str=pages_str
        )
        msg = f"✔ Structure analysis complete. Found {len(sections)} logical sections."
        log.info(msg)
        yield msg
        # --- Section Filtering based on user selection (if provided) ---
        if sections_to_include:
            sections = [s for s in sections if s.title in sections_to_include]
            msg = f"✔ Filtered to {len(sections)} user-selected sections."
            log.info(msg)
            yield msg
        # --- Section-level Classification and Filtering ---
        page_type_map = {pm.page_num: pm.page_type for pm in page_models}
        content_sections = []
        classifier_prompt = self._get_prompt("SECTION_CLASSIFIER", lang)
        valid_section_tags = {"content", "appendix"}
        valid_llm_tags = valid_section_tags.union(
            {"preface", "table_of_contents", "legal", "credits", "index"}
        )

        model_details = get_model_details(self.ollama_url, self.utility_model)
        ctx = model_details.get("context_length", 4096)  # Default to 4k if lookup fails
        target_chars = int(ctx * 0.8)
        msg = (
            f"Classifying {len(sections)} sections using '{self.utility_model}' "
            f"(context: {target_chars} chars)..."
        )
        log.info(msg)
        yield msg

        for i, section in enumerate(sections):
            if not section.paragraphs:
                continue

            context_parts = []
            current_chars = 0
            if section.title:
                title_text = f"Title: {section.title}\n\n"
                context_parts.append(title_text)
                current_chars += len(title_text)

            for para in section.paragraphs:
                para_text = para.get_text()
                if current_chars + len(para_text) > target_chars:
                    break
                context_parts.append(para_text)
                current_chars += len(para_text) + 2

            representative_text = "\n\n".join(context_parts)
            hint_tag = page_type_map.get(section.page_start, "content")

            response_data = query_text_llm(
                classifier_prompt,
                representative_text,
                self.ollama_url,
                self.utility_model,
                temperature=0.1,
            )
            final_tag = response_data.get("response", "").strip()

            if final_tag not in valid_llm_tags:
                final_tag = "content"

            log.debug(
                "Section Classification:\n"
                "  - Model: %s\n"
                "  - Title: '%s'\n"
                "  - Hint: %s -> Final Tag: %s\n"
                "  - Input: %s",
                self.utility_model,
                section.title or "Untitled",
                hint_tag,
                final_tag,
                self._format_text_for_log(representative_text),
            )

            if final_tag in valid_section_tags:
                content_sections.append(section)
            else:
                msg = f"  -> Skipping section '{section.title}' (classified as '{final_tag}')"
                log.info(msg)
                yield msg

        # --- Paragraph-level Reformatting and Semantic Labeling ---
        labeler_prompt = self._get_prompt("SEMANTIC_LABELER", lang)
        documents, metadatas = [], []
        chunk_id = 0

        for i, section in enumerate(content_sections):
            if not section.paragraphs or not any(p.lines for p in section.paragraphs):
                continue

            msg = (
                f"Reformatting section {i + 1}/{len(content_sections)} ('{section.title}')..."
            )
            log.info(msg)
            yield msg
            stream = reformat_section_with_llm(
                section=section,
                system_prompt=PROMPT_STRICT,
                ollama_url=self.ollama_url,
                model=self.utility_model,
                chunk_size=4000,
            )
            formatted_section_text = "".join(list(stream))

            msg = "  -> Chunking and labeling reformatted text..."
            log.info(msg)
            yield msg
            recovered_chunks = self._chunk_reformatted_section(section, formatted_section_text)

            for chunk in recovered_chunks:
                label = get_semantic_label(
                    chunk, labeler_prompt, self.ollama_url, self.utility_model
                )
                documents.append(chunk)
                metadatas.append(
                    {
                        "source_file": metadata.get("filename", "unknown.pdf"),
                        "section_title": section.title or "Untitled",
                        "chunk_id": chunk_id,
                        "label": label if label else "prose",
                    }
                )
                chunk_id += 1

        msg = f"✔ Processing complete. Found {len(documents)} valid chunks."
        log.info(msg)
        yield msg
        msg = "Generating embeddings and saving to vector store..."
        log.info(msg)
        yield msg
        if not documents:
            msg = "✔ No valid text chunks found to ingest."
            log.info(msg)
            yield msg
            return
        self.vector_store.add_to_kb(kb_name, documents, metadatas, kb_metadata=metadata)
        msg = "✔ Saved to vector store."
        log.info(msg)
        yield msg

    def process_and_extract_images(
        self, pdf_path: str, assets_path: str, metadata: dict, pages_str: str = "all"
    ):
        """Extracts images from a PDF and processes them using language-aware prompts."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        msg = f"Starting image extraction for '{kb_name}' (Pages: {pages_str})..."
        log.info(msg)
        yield msg

        review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
        if os.path.exists(review_dir):
            shutil.rmtree(review_dir)
        os.makedirs(review_dir, exist_ok=True)

        describe_prompt = self._get_prompt("DESCRIBE_IMAGE", lang)
        classify_prompt = self._get_prompt("CLASSIFY_IMAGE", lang)

        yield from process_pdf_images(
            pdf_path=pdf_path,
            output_dir=review_dir,
            ollama_url=self.ollama_url,
            vision_model=self.vision_model,
            utility_model=self.utility_model,
            describe_prompt=describe_prompt,
            classify_prompt=classify_prompt,
            pages_str=pages_str,
        )

    def _create_asset_manifest(self, final_dir: str):
        """Creates an assets.json manifest file with detailed asset objects."""
        manifest_data = {"assets": []}
        dir_name = os.path.basename(final_dir)
        try:
            for filename in sorted(os.listdir(final_dir)):
                if not filename.endswith(".json") or filename == "assets.json":
                    continue
                with open(os.path.join(final_dir, filename), "r") as f:
                    data = json.load(f)

                thumb_filename = data.get("thumbnail_filename")
                image_filename = data.get("image_filename")

                if not (thumb_filename and image_filename):
                    continue

                manifest_data["assets"].append(
                    {
                        "id": os.path.splitext(image_filename)[0],
                        "thumb_url": f"{dir_name}/{thumb_filename}",
                        "full_url": f"{dir_name}/{image_filename}",
                        "classification": data.get("classification", "other"),
                        "description": data.get("description", ""),
                    }
                )

            manifest_path = os.path.join(final_dir, "assets.json")
            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f, indent=4)
            log.info("Created detailed asset manifest at %s", manifest_path)
        except Exception as e:
            log.error("Failed to create asset manifest: %s", e)

    def ingest_images(self, kb_name: str, assets_path: str):
        """Finalizes image ingestion from a review directory."""
        review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
        log.info("Finalizing image ingestion for KB '%s' from dir: %s", kb_name, review_dir)
        if not os.path.isdir(review_dir):
            raise FileNotFoundError(f"Review directory not found: {review_dir}")

        documents, metadatas = [], []
        json_files = [f for f in os.listdir(review_dir) if f.endswith(".json")]
        log.debug("Found %d metadata files in review directory.", len(json_files))

        for json_file in json_files:
            with open(os.path.join(review_dir, json_file), "r") as f:
                data = json.load(f)

            if data.get("classification") == "decoration":
                log.debug("Skipping decorative image: %s", json_file)
                continue

            doc_text = (
                f"An image of type '{data['classification']}' depicting: {data['description']}"
            )
            documents.append(doc_text)

            image_filename = json_file.replace(".json", ".png")
            thumb_filename = data.get("thumbnail_filename", "")
            final_image_path = os.path.join("images", kb_name, image_filename)
            final_thumb_path = os.path.join("images", kb_name, thumb_filename)
            metadatas.append(
                {
                    "source_file": "PDF Images",
                    "label": "image_description",
                    "classification": data["classification"],
                    "image_url": final_image_path,
                    "thumbnail_url": final_thumb_path,
                }
            )
        log.info("Prepared %d images for vector store ingestion.", len(documents))

        if documents:
            self.vector_store.add_to_kb(kb_name, documents, metadatas)

        final_dir = os.path.join(assets_path, "images", kb_name)
        if os.path.exists(final_dir):
            shutil.rmtree(final_dir)
        os.rename(review_dir, final_dir)

        # Create the asset manifest after the final directory is in place
        self._create_asset_manifest(final_dir)

        log.info(
            "Image ingestion for '%s' finalized. Review dir promoted to: %s",
            kb_name,
            final_dir,
        )

    def add_custom_asset(self, kb_name: str, file_storage):
        """Processes a user-uploaded image and adds it to an existing KB."""
        assets_dir = os.path.join(current_app.config["ASSETS_PATH"], "images", kb_name)
        os.makedirs(assets_dir, exist_ok=True)

        # 1. Save files with unique names
        file_ext = os.path.splitext(file_storage.filename)[1]
        asset_id = uuid.uuid4().hex
        image_filename = f"custom_{asset_id}{file_ext}"
        thumb_filename = f"thumb_custom_{asset_id}.jpg"
        json_filename = f"custom_{asset_id}.json"
        image_path = os.path.join(assets_dir, image_filename)
        thumb_path = os.path.join(assets_dir, thumb_filename)
        json_path = os.path.join(assets_dir, json_filename)

        file_storage.save(image_path)

        # 2. Generate thumbnail
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((256, 256))
            img.save(thumb_path, "JPEG", quality=85)

        # 3. Generate metadata with LLM (Two-Stage Process)
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        kb_metadata = self.vector_store.get_kb_metadata(kb_name)
        lang = kb_metadata.get("language", "en")

        # Stage 1: Describe with vision model
        describe_prompt = self._get_prompt("DESCRIBE_IMAGE", lang)
        description = query_multimodal_llm(
            describe_prompt, image_bytes, self.ollama_url, self.vision_model
        )

        # Stage 2: Classify description with utility model
        classify_prompt = self._get_prompt("CLASSIFY_IMAGE", lang)
        classification_data = query_text_llm(
            classify_prompt, description, self.ollama_url, self.utility_model, 0.1
        )
        classification = classification_data.get("response", "").strip()

        if classification not in {"cover", "art", "map", "handout", "decoration", "other"}:
            classification = "art"

        # 4. Save metadata JSON
        metadata = {
            "description": description or "No description generated.",
            "classification": classification,
            "source": "user_upload",
            "original_filename": file_storage.filename,
            "thumbnail_filename": thumb_filename,
            "image_filename": image_filename,
        }
        with open(json_path, "w") as f:
            json.dump(metadata, f, indent=4)

        # 5. Add to vector store
        doc_text = f"An image of type '{classification}' depicting: {description}"
        doc_meta = {
            "source_file": "User Uploads",
            "label": "image_description",
            "classification": classification,
            "image_url": os.path.join("images", kb_name, image_filename),
            "thumbnail_url": os.path.join("images", kb_name, thumb_filename),
        }
        self.vector_store.add_to_kb(kb_name, [doc_text], [doc_meta])

        # 6. Update manifest
        self._create_asset_manifest(assets_dir)
        log.info("Successfully added custom asset '%s' to KB '%s'", image_filename, kb_name)
        return {
            "url": f"/assets/{doc_meta['thumbnail_url']}",
            "caption": description,
            "classification": classification,
        }

    def delete_asset(self, kb_name: str, thumb_filename: str):
        """Deletes an asset's image, thumbnail, and metadata, then updates the manifest."""
        assets_dir = os.path.join(current_app.config["ASSETS_PATH"], "images", kb_name)
        if not os.path.isdir(assets_dir):
            raise FileNotFoundError("Asset directory for KB does not exist.")

        base_name = thumb_filename.replace("thumb_", "").replace(".jpg", "")
        json_filename = f"{base_name}.json"
        json_path = os.path.join(assets_dir, json_filename)

        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Asset metadata file not found: {json_filename}")

        with open(json_path, "r") as f:
            metadata = json.load(f)

        image_filename = metadata.get("image_filename")
        if not image_filename:
            # Fallback for older assets before this key was saved
            image_exts = [".png", ".jpg", ".jpeg", ".webp"]
            for ext in image_exts:
                if os.path.exists(os.path.join(assets_dir, f"{base_name}{ext}")):
                    image_filename = f"{base_name}{ext}"
                    break
            if not image_filename:
                raise FileNotFoundError(f"Could not determine main image for {base_name}")

        thumb_path = os.path.join(assets_dir, thumb_filename)
        image_path = os.path.join(assets_dir, image_filename)

        log.info(
            "Deleting asset files for %s: %s, %s, %s",
            kb_name,
            image_filename,
            thumb_filename,
            json_filename,
        )

        # Delete the files, ignoring errors if they're already gone
        for path in [image_path, thumb_path, json_path]:
            try:
                os.remove(path)
            except FileNotFoundError:
                log.warning("File not found during deletion, continuing: %s", path)
            except Exception as e:
                log.error("Error deleting file %s: %s", path, e)
                raise

        # Regenerate the manifest
        self._create_asset_manifest(assets_dir)
