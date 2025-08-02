# --- dmme_lib/services/rag_service.py ---
import logging
import re
from .vector_store_service import VectorStoreService
from core.llm_utils import query_text_llm
from dmme_lib.constants import PROMPT_REGISTRY

log = logging.getLogger("dmme.rag")


class RAGService:
    def __init__(self, vector_store: VectorStoreService, ollama_url: str, model: str):
        self.vector_store = vector_store
        self.ollama_url = ollama_url
        self.model = model
        log.info("RAGService initialized.")

    def _get_prompt(self, key: str, lang: str) -> str:
        """Safely retrieves a prompt from the registry, falling back to English."""
        return PROMPT_REGISTRY.get(key, {}).get(lang, PROMPT_REGISTRY.get(key, {}).get("en"))

    def generate_kickoff_narration(self, game_config: dict, recap: str = None):
        """
        Generates the initial narration for a new game or session.
        This is a generator function that yields JSON chunks.
        """
        lang = game_config.get("language", "en")
        log.info("Generating kickoff narration for game in '%s'.", lang)
        module_kb = game_config.get("module") or game_config.get("setting")
        if not module_kb:
            raise ValueError("A module or setting knowledge base is required for kickoff.")

        query = "adventure introduction, summary, or starting location"
        intro_docs, _ = self.vector_store.query(module_kb, query, n_results=5)
        intro_context = "\n\n".join(intro_docs) or "No introductory text found."

        guarded_context = (
            f"[CONTEXT FROM KNOWLEDGE_BASE '{module_kb}' - {lang.upper()}]\n"
            f"{intro_context}"
        )
        log.debug("Kickoff RAG context retrieved:\n%s", guarded_context)
        yield {"type": "insight", "content": guarded_context}

        prompt_content = f"[ADVENTURE INTRODUCTION]\n{intro_context}"
        if recap:
            prompt_content = f"[PREVIOUS SESSION RECAP]\n{recap}\n\n{prompt_content}"

        kickoff_prompt = self._get_prompt("KICKOFF_ADVENTURE", lang)
        llm_stream = query_text_llm(
            kickoff_prompt, prompt_content, self.ollama_url, self.model, stream=True
        )
        for chunk in llm_stream:
            yield {"type": "narrative_chunk", "content": chunk}

    def generate_response(self, player_command: str, game_config: dict, history: list[dict]):
        """
        Generates a game response using the RAG pipeline.
        This is a generator function that yields JSON chunks.
        """
        lang = game_config.get("language", "en")
        log.info("Generating RAG stream for command: '%s' in '%s'", player_command, lang)

        kb_sources = {
            "rules": game_config.get("rules"),
            "module": (
                game_config.get("module")
                if game_config.get("mode") == "module"
                else game_config.get("setting")
            ),
        }
        kb_names_to_query = [name for name in kb_sources.values() if name]

        context_blocks = []
        for name in kb_names_to_query:
            try:
                docs, metas = self.vector_store.query(name, player_command, n_results=4)
                if docs:
                    source_lang = metas[0].get("language", "en").upper()
                    block_content = "\n\n---\n\n".join(docs)
                    context_blocks.append(
                        f"[CONTEXT FROM KNOWLEDGE_BASE '{name}' - {source_lang}]\n{block_content}"
                    )
            except Exception:
                log.warning("Could not query or find collection '%s'.", name)

        context_str = "\n\n".join(context_blocks) or "No specific context was found."
        yield {"type": "insight", "content": context_str}

        history_str = "\n".join([f"{t['role'].title()}: {t['content']}" for t in history])
        user_prompt = (
            f"[CONVERSATION HISTORY]\n{history_str}\n\n"
            f"[CONTEXT]\n{context_str}\n\n"
            f"[PLAYER ACTION]\n{player_command}"
        )

        game_master_prompt = self._get_prompt("GAME_MASTER", lang)
        llm_stream = query_text_llm(
            game_master_prompt, user_prompt, self.ollama_url, self.model, stream=True
        )

        full_narrative = ""
        for chunk in llm_stream:
            full_narrative += chunk
            yield {"type": "narrative_chunk", "content": chunk}

        if full_narrative and kb_sources["module"]:
            # Yield visual aid and ascii map in parallel-like fashion
            yield from self._find_and_yield_visual_aid(
                player_command, full_narrative, kb_sources["module"]
            )
            yield from self._find_and_yield_ascii_map(full_narrative, lang)

    def _find_and_yield_visual_aid(self, command, narrative, kb_name):
        """Queries for a relevant image and yields a visual_aid chunk if found."""
        log.debug("Searching for relevant visual aid in '%s'.", kb_name)
        image_query = f"Scene described by: {command}. {narrative}"
        try:
            docs, metas = self.vector_store.query(
                kb_name,
                image_query,
                n_results=1,
                where_filter={"label": "image_description"},
            )
            if docs and metas:
                image_doc = docs[0]
                image_meta = metas[0]
                image_path = image_meta.get("image_url")
                if image_path:
                    log.info("Found relevant visual aid: %s", image_path)
                    yield {
                        "type": "visual_aid",
                        "image_url": f"/assets/{image_path}",
                        "caption": image_doc,
                    }
        except Exception as e:
            log.error("Failed during visual aid search: %s", e)

    def _find_and_yield_ascii_map(self, narrative, lang):
        """Generates an ASCII map from a narrative and yields it."""
        log.debug("Generating ASCII map for narrative.")
        try:
            prompt = self._get_prompt("ASCII_MAP_GENERATOR", lang)
            map_response = query_text_llm(prompt, narrative, self.ollama_url, self.model)
            if map_response:
                # Clean the response to remove markdown code block delimiters
                cleaned_map = re.sub(r"```(text|ascii)?\n?|\n?```", "", map_response).strip()
                yield {"type": "ascii_map", "content": cleaned_map}
        except Exception as e:
            log.error("Failed during ASCII map generation: %s", e)

    def generate_journal_recap(self, session_log: str, lang: str) -> str:
        """
        Uses an LLM to summarize a session log into a narrative recap.
        """
        log.info("Generating journal recap in '%s'.", lang)
        prompt = self._get_prompt("SUMMARIZE_SESSION", lang)
        summary = query_text_llm(prompt, session_log, self.ollama_url, self.model)
        return summary
