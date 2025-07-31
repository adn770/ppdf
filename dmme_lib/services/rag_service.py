# --- dmme_lib/services/rag_service.py ---
import logging
from .vector_store_service import VectorStoreService
from core.llm_utils import query_text_llm
from dmme_lib.constants import PROMPT_GAME_MASTER

log = logging.getLogger("dmme.rag")


class RAGService:
    def __init__(self, vector_store: VectorStoreService, ollama_url: str, model: str):
        self.vector_store = vector_store
        self.ollama_url = ollama_url
        self.model = model
        log.info("RAGService initialized.")

    def generate_response(
        self, player_command: str, game_config: dict, history: list[dict]
    ) -> dict:
        """
        Generates a game response using the RAG pipeline.
        """
        log.info("Generating RAG response for command: '%s'", player_command)

        # 1. Determine which knowledge bases to query
        kb_names_to_query = [game_config.get("rules")]
        if game_config.get("mode") == "module":
            kb_names_to_query.append(game_config.get("module"))
        else:  # freestyle mode
            kb_names_to_query.append(game_config.get("setting"))

        kb_names_to_query = [name for name in kb_names_to_query if name]
        log.debug("Querying KBs: %s", kb_names_to_query)

        # 2. Query the vector stores
        retrieved_docs = []
        for kb_name in kb_names_to_query:
            try:
                collection = self.vector_store.client.get_collection(name=kb_name)
                results = collection.query(query_texts=[player_command], n_results=4)
                if results and results["documents"]:
                    retrieved_docs.extend(results["documents"][0])
            except Exception as e:
                log.warning("Could not query collection '%s': %s", kb_name, e)

        # 3. Build the context string
        context_str = "\n\n".join(retrieved_docs)
        if not context_str:
            log.warning("No context retrieved from vector stores.")
            context_str = "No specific context was found for this action."

        # 4. Build the final prompt for the LLM
        history_str = "\n".join(
            [f"{turn['role'].title()}: {turn['content']}" for turn in history]
        )

        user_prompt = (
            f"[CONVERSATION HISTORY]\n{history_str}\n\n"
            f"[GAME CONTEXT]\n{context_str}\n\n"
            f"[PLAYER ACTION]\n{player_command}"
        )

        # 5. Query the LLM
        llm_response = query_text_llm(
            PROMPT_GAME_MASTER, user_prompt, self.ollama_url, self.model
        )

        # 6. Format and return the final response object
        response_data = {
            "type": "narrative",
            "content": llm_response,
            "dm_insight": context_str,  # For debugging on the frontend
        }
        return response_data
