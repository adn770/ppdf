# --- dmme_lib/services/rag_service.py ---
import logging
from .vector_store_service import VectorStoreService
from core.llm_utils import query_text_llm
from dmme_lib.constants import PROMPT_GAME_MASTER, PROMPT_KICKOFF_ADVENTURE

log = logging.getLogger("dmme.rag")


class RAGService:
    def __init__(self, vector_store: VectorStoreService, ollama_url: str, model: str):
        self.vector_store = vector_store
        self.ollama_url = ollama_url
        self.model = model
        log.info("RAGService initialized.")

    def generate_kickoff_narration(self, game_config: dict, recap: str = None):
        """
        Generates the initial narration for a new game or session.
        This is a generator function that yields JSON chunks.
        """
        log.info("Generating kickoff narration for game.")
        module_kb = game_config.get("module") or game_config.get("setting")
        if not module_kb:
            raise ValueError("A module or setting knowledge base is required for kickoff.")

        # 1. Query the vector store for introductory text
        query = "adventure introduction, summary, or starting location"
        log.debug("Kickoff RAG query: '%s'", query)
        intro_docs = self.vector_store.query(module_kb, query, n_results=5)
        intro_context = "\n\n".join(intro_docs) or "No introductory text found."
        log.debug("Kickoff RAG context retrieved:\n%s", intro_context)
        yield {"type": "insight", "content": intro_context}

        # 2. Build the final prompt for the LLM
        prompt_content = f"[ADVENTURE INTRODUCTION]\n{intro_context}"
        if recap:
            prompt_content = f"[PREVIOUS SESSION RECAP]\n{recap}\n\n{prompt_content}"

        log.debug("Final kickoff prompt content:\n%s", prompt_content)

        # 3. Query the LLM and stream the response
        llm_stream = query_text_llm(
            PROMPT_KICKOFF_ADVENTURE, prompt_content, self.ollama_url, self.model, stream=True
        )
        for chunk in llm_stream:
            yield {"type": "narrative_chunk", "content": chunk}

    def generate_response(self, player_command: str, game_config: dict, history: list[dict]):
        """
        Generates a game response using the RAG pipeline.
        This is a generator function that yields JSON chunks.
        """
        log.info("Generating RAG stream for command: '%s'", player_command)

        # 1. Determine which knowledge bases to query
        kb_names = [game_config.get("rules")]
        kb_names.append(
            game_config.get("module")
            if game_config.get("mode") == "module"
            else game_config.get("setting")
        )
        kb_names_to_query = [name for name in kb_names if name]

        # 2. Query the vector stores
        retrieved_docs = []
        for name in kb_names_to_query:
            try:
                collection = self.vector_store.client.get_collection(name=name)
                results = collection.query(query_texts=[player_command], n_results=4)
                if results and results["documents"]:
                    retrieved_docs.extend(results["documents"][0])
            except Exception:
                log.warning("Could not query or find collection '%s'.", name)

        # 3. Build the context string
        context_str = "\n\n".join(retrieved_docs) or "No specific context was found."
        yield {"type": "insight", "content": context_str}

        # 4. Build the final prompt for the LLM
        history_str = "\n".join([f"{t['role'].title()}: {t['content']}" for t in history])
        user_prompt = (
            f"[CONVERSATION HISTORY]\n{history_str}\n\n"
            f"[GAME CONTEXT]\n{context_str}\n\n"
            f"[PLAYER ACTION]\n{player_command}"
        )

        # 5. Query the LLM and stream the response
        llm_stream = query_text_llm(
            PROMPT_GAME_MASTER, user_prompt, self.ollama_url, self.model, stream=True
        )
        for chunk in llm_stream:
            yield {"type": "narrative_chunk", "content": chunk}
