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
        ids: list[str] = None,
    ):
        """Adds documents to a knowledge base, letting ChromaDB handle embeddings."""
        if not documents:
            log.warning("No documents provided to add to knowledge base '%s'.", kb_name)
            return

        log.info("Adding %d documents to knowledge base '%s'.", len(documents), kb_name)
        try:
            collection = self.get_or_create_collection(kb_name, metadata=kb_metadata)

            # Generate unique IDs if not provided, to avoid collisions
            if not ids:
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
    ) -> tuple[list[str], list[dict], list[float]]:
        """Queries a knowledge base, returning documents, metadata, and distances."""
        try:
            log.debug("Querying KB '%s' for: '%s'", kb_name, query_text)
            collection = self.get_or_create_collection(kb_name)
            if collection.count() == 0:
                log.warning("Query attempted on empty collection '%s'.", kb_name)
                return [], [], []

            results = collection.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where_filter,
                include=["metadatas", "documents", "distances"],
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            return docs, metas, dists
        except Exception as e:
            log.error("Failed to query knowledge base '%s': %s", kb_name, e)
            raise

    def get_by_ids(self, kb_name: str, ids: list[str]) -> tuple[list[str], list[dict]]:
        """Retrieves documents and metadata for a list of specific IDs."""
        try:
            collection = self.client.get_collection(name=kb_name)
            results = collection.get(ids=ids, include=["documents", "metadatas"])
            return results.get("documents", []), results.get("metadatas", [])
        except Exception as e:
            log.error("Failed to get documents by ID from '%s': %s", kb_name, e)
            raise

    def search_collections(
        self, query_text: str, scope: str, n_results: int = 15
    ) -> list[dict]:
        """Performs a vector search across one or all knowledge bases."""
        search_targets = []
        if scope.lower() == "all":
            search_targets = [c.name for c in self.list_collections()]
        else:
            search_targets = [scope]

        all_results = []
        for kb_name in search_targets:
            docs, metas, dists = self.query(kb_name, query_text, n_results=n_results)
            for i in range(len(docs)):
                all_results.append(
                    {
                        "document": docs[i],
                        "metadata": metas[i],
                        "distance": dists[i],
                        "kb_name": kb_name,
                    }
                )

        # Sort all combined results by their distance (lower is better)
        return sorted(all_results, key=lambda x: x["distance"])[:n_results]

    def get_all_documents_and_metadata(self, kb_name: str) -> dict:
        """Retrieves all documents and their metadata from a knowledge base."""
        try:
            log.debug("Retrieving all documents and metadata from KB '%s'", kb_name)
            collection = self.client.get_collection(name=kb_name)
            if collection.count() == 0:
                return {}
            return collection.get(include=["metadatas", "documents"])
        except Exception as e:
            log.error("Failed to retrieve all from KB '%s': %s", kb_name, e)
            raise

    def get_all_from_kb(self, kb_name: str) -> list[dict]:
        """Retrieves all documents and their metadata from a knowledge base."""
        try:
            results = self.get_all_documents_and_metadata(kb_name)
            if not results:
                return []

            # Combine documents and metadatas into a single list of dicts
            combined = [
                {**meta, "document": doc}
                for doc, meta in zip(results["documents"], results["metadatas"])
            ]
            return combined
        except Exception as e:
            log.error("Failed to retrieve all documents from KB '%s': %s", kb_name, e)
            raise

    def get_kb_metadata(self, kb_name: str) -> dict:
        """Retrieves the collection-level metadata for a knowledge base."""
        try:
            collection = self.client.get_collection(name=kb_name)
            return collection.metadata or {}
        except Exception:
            # This can happen if the collection doesn't exist, which is a valid case.
            log.debug("Could not retrieve metadata for KB '%s'. It may not exist.", kb_name)
            return {}

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
