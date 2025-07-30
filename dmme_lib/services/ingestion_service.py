# --- dmme_lib/services/ingestion_service.py ---
import logging
import re
from .vector_store_service import VectorStoreService
from dmme_lib.utils.llm_utils import get_semantic_label

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

        # Simple chunking by splitting on double newlines
        chunks = [
            chunk.strip() for chunk in re.split(r"\n{2,}", file_content) if chunk.strip()
        ]

        documents = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            # Skip very short chunks
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
