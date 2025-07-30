# --- dmme_lib/services/ingestion_service.py ---
import logging
import re
from .vector_store_service import VectorStoreService
from dmme_lib.utils.llm_utils import get_semantic_label
from ppdf_lib.api import process_pdf_text

log = logging.getLogger("dmme.ingestion")


class IngestionService:
    def __init__(self, vector_store: VectorStoreService, ollama_url: str, model: str):
        self.vector_store = vector_store
        self.ollama_url = ollama_url
        self.model = model
        log.info("IngestionService initialized.")

    def ingest_markdown(self, file_content: str, metadata: dict):
        """Processes and ingests a Markdown file's content."""
        kb_name = metadata.get("kb_name")
        if not kb_name:
            raise ValueError("Knowledge base name is required for ingestion.")

        log.info("Starting Markdown ingestion for knowledge base '%s'.", kb_name)

        chunks = [
            chunk.strip() for chunk in re.split(r"\n{2,}", file_content) if chunk.strip()
        ]

        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            if len(chunk) < 50:
                continue

            log.debug("Labeling chunk %d/%d...", i + 1, len(chunks))
            label = get_semantic_label(chunk, self.ollama_url, self.model)

            documents.append(chunk)
            metadatas.append(
                {
                    "source_file": metadata.get("filename", "unknown.md"),
                    "chunk_id": i,
                    "label": label,
                }
            )

        if not documents:
            log.warning("No suitable documents found to ingest for '%s'.", kb_name)
            return

        self.vector_store.create_kb(kb_name, documents, metadatas)
        log.info("Markdown ingestion for '%s' completed.", kb_name)

    def ingest_pdf(self, pdf_path: str, metadata: dict):
        """Processes and ingests a PDF file's content."""
        kb_name = metadata.get("kb_name")
        if not kb_name:
            raise ValueError("Knowledge base name is required for ingestion.")

        log.info("Starting PDF ingestion for knowledge base '%s'.", kb_name)

        # Use the ppdf library to extract structured and labeled text
        # We always apply labeling for knowledge base creation.
        extraction_options = {"num_cols": "auto", "rm_footers": True, "style": False}
        sections, _ = process_pdf_text(
            pdf_path, extraction_options, self.ollama_url, self.model, apply_labeling=True
        )

        documents = []
        metadatas = []
        chunk_id = 0

        for section in sections:
            for para in section.paragraphs:
                # Skip tables and very short paragraphs
                if para.is_table or len(para.get_text()) < 50:
                    continue

                documents.append(para.get_text())
                metadatas.append(
                    {
                        "source_file": metadata.get("filename", "unknown.pdf"),
                        "section": section.title or "Untitled",
                        "chunk_id": chunk_id,
                        "label": para.labels[0] if para.labels else "prose",
                    }
                )
                chunk_id += 1

        if not documents:
            log.warning("No suitable documents found to ingest for '%s'.", kb_name)
            return

        self.vector_store.create_kb(kb_name, documents, metadatas)
        log.info("PDF ingestion for '%s' completed.", kb_name)
