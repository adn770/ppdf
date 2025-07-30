# --- dmme_lib/services/vector_store_service.py ---
import logging
import chromadb
from dmme_lib.utils.llm_utils import generate_embeddings_ollama

log = logging.getLogger("dmme.vector_store")


class VectorStoreService:
    def __init__(self, chroma_path: str, ollama_url: str, embedding_model: str):
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.ollama_url = ollama_url
        self.embedding_model = embedding_model
        log.info("VectorStoreService initialized. ChromaDB path: %s", chroma_path)

    def create_kb(self, kb_name: str, documents: list[str], metadatas: list[dict]):
        """Creates a new knowledge base (collection) and populates it."""
        if not documents:
            log.warning("No documents provided to create knowledge base '%s'.", kb_name)
            return

        log.info("Creating knowledge base '%s' with %d documents.", kb_name, len(documents))
        try:
            collection = self.client.create_collection(name=kb_name)

            log.info("Generating embeddings for documents...")
            embeddings = generate_embeddings_ollama(
                documents, self.ollama_url, self.embedding_model
            )

            ids = [f"{kb_name}_{i}" for i in range(len(documents))]

            collection.add(
                embeddings=embeddings, documents=documents, metadatas=metadatas, ids=ids
            )
            log.info("Successfully created and populated '%s'.", kb_name)
        except Exception as e:
            log.error("Failed to create knowledge base '%s': %s", kb_name, e)
            # Cleanup if collection was created but population failed
            try:
                self.client.delete_collection(name=kb_name)
            except Exception:
                pass
            raise
