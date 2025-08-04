# --- dmme_lib/services/ingestion_service.py ---
import logging
import re
import os
import json
import shutil
from flask import current_app
from .vector_store_service import VectorStoreService
from core.llm_utils import get_semantic_label, query_text_llm, get_model_details
from ppdf_lib.api import process_pdf_text, process_pdf_images
from dmme_lib.constants import PROMPT_REGISTRY

log = logging.getLogger("dmme.ingest")


class IngestionService:
    def __init__(self, vector_store: VectorStoreService, ollama_url: str, model: str):
        self.vector_store = vector_store
        self.ollama_url = ollama_url
        self.model = model
        log.info("IngestionService initialized.")

    def _get_classification_model(self):
        """Gets the classification model from the app's config service."""
        return current_app.config_service.get_settings()["Ollama"]["classification_model"]

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

        yield f"✔ Starting Markdown processing for KB '{kb_name}' in '{lang}'."
        chunks = [c.strip() for c in re.split(r"\n{2,}", file_content) if c.strip()]
        yield f"Splitting file into {len(chunks)} raw chunks."

        labeler_prompt = self._get_prompt("SEMANTIC_LABELER", lang)
        classification_model = self._get_classification_model()
        documents, metadatas = [], []
        for i, chunk in enumerate(chunks):
            if len(chunk) < 50:
                continue

            yield f"  -> Applying semantic label to chunk {i + 1}/{len(chunks)}..."
            label = get_semantic_label(
                chunk, labeler_prompt, self.ollama_url, classification_model
            )
            log.debug(
                "Semantic Labeling:\n" "  - Model: %s\n" "  - Input: %s\n" "  - Label: %s",
                classification_model,
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
            yield "✔ No valid text chunks found to ingest."
            return

        yield f"✔ Semantic labeling complete. Found {len(documents)} valid chunks."
        yield "Generating embeddings and saving to vector store..."
        self.vector_store.add_to_kb(kb_name, documents, metadatas, kb_metadata=metadata)
        yield "✔ Saved to vector store."

    def ingest_pdf_text(self, pdf_path: str, metadata: dict, pages_str: str = "all"):
        """Processes and ingests a PDF file's text content, yielding progress."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        if not kb_name:
            raise ValueError("Knowledge base name is required for ingestion.")

        yield f"Analyzing PDF structure for '{kb_name}' (Pages: {pages_str})..."
        extraction_options = {"num_cols": "auto", "rm_footers": True, "style": False}
        sections, page_models = process_pdf_text(
            pdf_path, extraction_options, "", "", apply_labeling=False, pages_str=pages_str
        )
        yield f"✔ Structure analysis complete. Found {len(sections)} logical sections."

        # --- Section-level Classification and Filtering ---
        page_type_map = {pm.page_num: pm.page_type for pm in page_models}
        content_sections = []
        classifier_prompt = self._get_prompt("SECTION_CLASSIFIER", lang)
        classification_model = self._get_classification_model()
        valid_section_tags = {"content", "appendix"}
        valid_llm_tags = valid_section_tags.union(
            {"preface", "table_of_contents", "legal", "credits", "index"}
        )

        model_details = get_model_details(self.ollama_url, classification_model)
        ctx = model_details.get("context_length", 4096)  # Default to 4k if lookup fails
        target_chars = int(ctx * 0.8)
        yield (
            f"Classifying {len(sections)} sections using '{classification_model}' "
            f"(context: {target_chars} chars)..."
        )

        for i, section in enumerate(sections):
            if not section.paragraphs:
                continue

            # Build a rich context for classification
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
                current_chars += len(para_text) + 2  # Account for newlines

            representative_text = "\n\n".join(context_parts)
            hint_tag = page_type_map.get(section.page_start, "content")

            final_tag = query_text_llm(
                classifier_prompt,
                representative_text,
                self.ollama_url,
                classification_model,
                temperature=0.1,
            ).strip()

            if final_tag not in valid_llm_tags:
                final_tag = "content"  # Default to content on ambiguous response

            log.debug(
                "Section Classification:\n"
                "  - Model: %s\n"
                "  - Title: '%s'\n"
                "  - Hint: %s -> Final Tag: %s\n"
                "  - Prompt: %s\n"
                "  - Input: %s",
                classification_model,
                section.title or "Untitled",
                hint_tag,
                final_tag,
                classifier_prompt.replace("\n", " "),
                self._format_text_for_log(representative_text),
            )

            if final_tag in valid_section_tags:
                content_sections.append(section)
            else:
                yield f"  -> Skipping section '{section.title}' (classified as '{final_tag}')"

        # --- Paragraph-level Semantic Labeling on Filtered Sections ---
        labeler_prompt = self._get_prompt("SEMANTIC_LABELER", lang)
        documents, metadatas = [], []
        chunk_id = 0
        total_paras = sum(len(s.paragraphs) for s in content_sections)

        yield f"Applying semantic labels to {total_paras} paragraphs..."
        para_count = 0
        for section in content_sections:
            for para in section.paragraphs:
                para_count += 1
                para_text = para.get_text()
                if para.is_table or len(para_text) < 50:
                    continue

                label = get_semantic_label(
                    para_text, labeler_prompt, self.ollama_url, classification_model
                )

                log.debug(
                    "Semantic Labeling:\n" "  - Model: %s\n" "  - Input: %s\n" "  - Label: %s",
                    classification_model,
                    self._format_text_for_log(para_text),
                    label,
                )

                if (para_count) % 25 == 0 or para_count == 1:
                    yield f"  -> Labeling paragraph {para_count}/{total_paras}..."

                documents.append(para_text)
                metadatas.append(
                    {
                        "source_file": metadata.get("filename", "unknown.pdf"),
                        "section_title": section.title or "Untitled",
                        "chunk_id": chunk_id,
                        "label": label if label else "prose",
                    }
                )
                chunk_id += 1
        yield f"✔ Semantic labeling complete. Found {len(documents)} valid chunks."

        yield "Generating embeddings and saving to vector store..."
        if not documents:
            yield "✔ No valid text chunks found to ingest."
            return
        self.vector_store.add_to_kb(kb_name, documents, metadatas, kb_metadata=metadata)
        yield "✔ Saved to vector store."

    def process_and_extract_images(
        self, pdf_path: str, assets_path: str, metadata: dict, pages_str: str = "all"
    ):
        """Extracts images from a PDF and processes them using language-aware prompts."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        yield f"Starting image extraction for '{kb_name}' (Pages: {pages_str})..."

        review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
        if os.path.exists(review_dir):
            shutil.rmtree(review_dir)
        os.makedirs(review_dir, exist_ok=True)

        describe_prompt = self._get_prompt("DESCRIBE_IMAGE", lang)
        classify_prompt = self._get_prompt("CLASSIFY_IMAGE", lang)

        yield from process_pdf_images(
            pdf_path,
            review_dir,
            self.ollama_url,
            self.model,
            describe_prompt,
            classify_prompt,
            pages_str=pages_str,
        )

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

            image_filename = json_file.replace(".png", ".json")
            final_image_path = os.path.join("images", kb_name, image_filename)
            metadatas.append(
                {
                    "source_file": "PDF Images",
                    "label": "image_description",
                    "classification": data["classification"],
                    "image_url": final_image_path,
                }
            )
        log.info("Prepared %d images for vector store ingestion.", len(documents))

        if documents:
            self.vector_store.add_to_kb(kb_name, documents, metadatas)

        final_dir = os.path.join(assets_path, "images", kb_name)
        if os.path.exists(final_dir):
            shutil.rmtree(final_dir)
        os.rename(review_dir, final_dir)
        log.info(
            "Image ingestion for '%s' finalized. Review dir promoted to: %s",
            kb_name,
            final_dir,
        )
