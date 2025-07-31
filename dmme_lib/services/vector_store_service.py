# --- dmme_lib/services/vector_store_service.py ---
import logging
import chromadb
from core.llm_utils import generate_embeddings_ollama

log = logging.getLogger("dmme.vector_store")


class VectorStoreService:
    def __init__(self, chroma_path: str, ollama_url: str, embedding_model: str):
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.ollama_url = ollama_url
        self.embedding_model = embedding_model
        log.info("VectorStoreService initialized. ChromaDB path: %s", chroma_path)

    def get_or_create_collection(self, collection_name: str):
        """Gets or creates a ChromaDB collection."""
        return self.client.get_or_create_collection(name=collection_name)

    def list_collections(self):
        """Lists all collections in the vector store."""
        return self.client.list_collections()

    def add_to_kb(self, kb_name: str, documents: list[str], metadatas: list[dict]):
        """Adds documents to an existing knowledge base (collection)."""
        if not documents:
            log.warning("No documents provided to add to knowledge base '%s'.", kb_name)
            return

        log.info("Adding %d documents to knowledge base '%s'.", len(documents), kb_name)
        try:
            collection = self.get_or_create_collection(kb_name)

            log.info("Generating embeddings for documents...")
            embeddings = generate_embeddings_ollama(
                documents, self.ollama_url, self.embedding_model
            )

            # Generate unique IDs to avoid collisions
            start_id = collection.count()
            ids = [f"{kb_name}_{i + start_id}" for i in range(len(documents))]

            collection.add(
                embeddings=embeddings, documents=documents, metadatas=metadatas, ids=ids
            )
            log.info("Successfully added documents to '%s'.", kb_name)
        except Exception as e:
            log.error("Failed to add documents to knowledge base '%s': %s", kb_name, e)
            raise
