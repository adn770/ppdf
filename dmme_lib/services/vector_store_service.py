# --- dmme_lib/services/vector_store_service.py ---
import logging
import chromadb
from chromadb.utils import embedding_functions

log = logging.getLogger("dmme.vector_store")


class VectorStoreService:
    def __init__(self, chroma_path: str, ollama_url: str, embedding_model: str):
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.ollama_url = ollama_url
        self.embedding_model = embedding_model

        # Configure the embedding function for ChromaDB to use Ollama
        self.embedding_function = embedding_functions.OllamaEmbeddingFunction(
            url=f"{self.ollama_url}/api/embeddings",
            model_name=self.embedding_model,
        )
        log.info("VectorStoreService initialized. ChromaDB path: %s", chroma_path)

    def get_or_create_collection(self, collection_name: str, metadata: dict = None):
        """Gets or creates a ChromaDB collection with the Ollama embedding function."""
        return self.client.get_or_create_collection(
            name=collection_name, metadata=metadata, embedding_function=self.embedding_function
        )

    def list_collections(self):
        """Lists all collections in the vector store."""
        return self.client.list_collections()

    def add_to_kb(
        self,
        kb_name: str,
        documents: list[str],
        metadatas: list[dict],
        kb_metadata: dict = None,
    ):
        """Adds documents to a knowledge base, letting ChromaDB handle embeddings."""
        if not documents:
            log.warning("No documents provided to add to knowledge base '%s'.", kb_name)
            return

        log.info("Adding %d documents to knowledge base '%s'.", len(documents), kb_name)
        try:
            collection = self.get_or_create_collection(kb_name, metadata=kb_metadata)

            # Generate unique IDs to avoid collisions
            start_id = collection.count()
            ids = [f"{kb_name}_{i + start_id}" for i in range(len(documents))]

            # ChromaDB will now use the configured Ollama function to create embeddings
            collection.add(documents=documents, metadatas=metadatas, ids=ids)
            log.info("Successfully added documents to '%s'.", kb_name)
        except Exception as e:
            log.error("Failed to add documents to knowledge base '%s': %s", kb_name, e)
            raise

    def query(
        self, kb_name: str, query_text: str, n_results: int = 5, where_filter: dict = None
    ) -> tuple[list[str], list[dict]]:
        """Queries a knowledge base, returning documents and their metadata."""
        try:
            log.debug("Querying KB '%s' for: '%s'", kb_name, query_text)
            collection = self.get_or_create_collection(kb_name)
            if collection.count() == 0:
                log.warning("Query attempted on empty collection '%s'.", kb_name)
                return [], []

            results = collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where_filter,
                include=["metadatas", "documents"],
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            return docs, metas
        except Exception as e:
            log.error("Failed to query knowledge base '%s': %s", kb_name, e)
            raise

    def delete_kb(self, kb_name: str):
        """Deletes an entire knowledge base (collection)."""
        try:
            log.warning("Deleting knowledge base: '%s'", kb_name)
            self.client.delete_collection(name=kb_name)
            log.info("Knowledge base '%s' deleted successfully.", kb_name)
        except ValueError:
            log.info("Knowledge base '%s' did not exist, nothing to delete.", kb_name)
        except Exception as e:
            log.error("Failed to delete knowledge base '%s': %s", kb_name, e)
            raise
