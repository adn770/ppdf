# --- dmme_lib/services/ingestion_service.py ---
import logging
import re
import os
import json
import shutil
from .vector_store_service import VectorStoreService
from core.llm_utils import get_semantic_label
from ppdf_lib.api import process_pdf_text, process_pdf_images
from dmme_lib.constants import PROMPT_REGISTRY

log = logging.getLogger("dmme.ingest")


class IngestionService:
    def __init__(self, vector_store: VectorStoreService, ollama_url: str, model: str):
        self.vector_store = vector_store
        self.ollama_url = ollama_url
        self.model = model
        log.info("IngestionService initialized.")

    def _get_prompt(self, key: str, lang: str) -> str:
        """Safely retrieves a prompt from the registry, falling back to English."""
        return PROMPT_REGISTRY.get(key, {}).get(lang, PROMPT_REGISTRY.get(key, {}).get("en"))

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
        documents, metadatas = [], []
        for i, chunk in enumerate(chunks):
            if len(chunk) < 50:
                continue

            yield f"  -> Applying semantic label to chunk {i + 1}/{len(chunks)}..."
            label = get_semantic_label(chunk, labeler_prompt, self.ollama_url, self.model)

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

    def ingest_pdf_text(self, pdf_path: str, metadata: dict):
        """Processes and ingests a PDF file's text content, yielding progress."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        if not kb_name:
            raise ValueError("Knowledge base name is required for ingestion.")

        yield f"Analyzing PDF structure for '{kb_name}'..."
        extraction_options = {"num_cols": "auto", "rm_footers": True, "style": False}
        sections, _ = process_pdf_text(pdf_path, extraction_options, "", "", False)
        yield f"✔ Structure analysis complete. Found {len(sections)} logical sections."

        labeler_prompt = self._get_prompt("SEMANTIC_LABELER", lang)
        documents, metadatas = [], []
        chunk_id = 0
        total_paras = sum(len(s.paragraphs) for s in sections)

        yield f"Applying semantic labels to {total_paras} paragraphs..."
        for s_idx, section in enumerate(sections):
            for p_idx, para in enumerate(section.paragraphs):
                if para.is_table or len(para.get_text()) < 50:
                    continue

                label = get_semantic_label(
                    para.get_text(), labeler_prompt, self.ollama_url, self.model
                )
                if p_idx == 0:
                    msg = f"  -> Labeling section {s_idx + 1}/{len(sections)} ('{section.title or '...'}')"
                    yield msg

                documents.append(para.get_text())
                metadatas.append(
                    {
                        "source_file": metadata.get("filename", "unknown.pdf"),
                        "section": section.title or "Untitled",
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

    def process_and_extract_images(self, pdf_path: str, assets_path: str, metadata: dict):
        """Extracts images from a PDF and processes them using language-aware prompts."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        yield f"Starting image extraction for '{kb_name}'..."

        review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
        if os.path.exists(review_dir):
            shutil.rmtree(review_dir)
        os.makedirs(review_dir, exist_ok=True)

        describe_prompt = self._get_prompt("DESCRIBE_IMAGE", lang)
        classify_prompt = self._get_prompt("CLASSIFY_IMAGE", lang)

        yield from process_pdf_images(
            pdf_path, review_dir, self.ollama_url, self.model, describe_prompt, classify_prompt
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

            image_filename = json_file.replace(".json", ".png")
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
