# --- dmme_lib/services/rag_service.py ---
import logging
import re
import json
from flask import current_app
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

    def _format_text_for_log(self, text: str) -> str:
        """Formats a long text block into a concise, single-line summary for logging."""
        single_line_text = re.sub(r"\s+", " ", text).strip()
        if len(single_line_text) > 100:
            return f'"{single_line_text[:45]}...{single_line_text[-45:]}"'
        return f'"{single_line_text}"'

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
        intro_docs, intro_metas = self.vector_store.query(module_kb, query, n_results=5)
        intro_context = "\n\n".join(intro_docs) or "No introductory text found."

        insight_data = [
            {"label": meta.get("label", "prose"), "text": doc}
            for doc, meta in zip(intro_docs, intro_metas)
        ]
        guarded_context = f"[CONTEXT FROM KNOWLEDGE_BASE '{module_kb}']\n{intro_context}"
        log.debug("Kickoff RAG context retrieved:\n%s", guarded_context)
        yield {"type": "insight", "content": json.dumps(insight_data, indent=2)}

        prompt_content = f"[ADVENTURE INTRODUCTION]\n{intro_context}"
        if recap:
            prompt_content = f"[PREVIOUS SESSION RECAP]\n{recap}\n\n{prompt_content}"

        kickoff_prompt = self._get_prompt("KICKOFF_ADVENTURE", lang)
        session_model = game_config.get("llm_model", self.model)
        llm_stream = query_text_llm(
            kickoff_prompt, prompt_content, self.ollama_url, session_model, stream=True
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

        module_kb = (
            game_config.get("module")
            if game_config.get("mode") == "module"
            else game_config.get("setting")
        )
        rules_kb = game_config.get("rules")

        # Define priority for sorting descriptive chunks first
        label_priority = [
            "location_description",
            "read_aloud_text",
            "lore",
            "prose",
            "item_description",
            "dialogue",
            "mechanics",
            "stat_block",
        ]
        priority_map = {label: i for i, label in enumerate(label_priority)}

        # 1. Get and sort Module/Setting chunks
        sorted_module_chunks = []
        if module_kb:
            try:
                docs, metas = self.vector_store.query(module_kb, player_command, n_results=4)
                module_chunks = [
                    {"text": doc, "label": meta.get("label", "prose")}
                    for doc, meta in zip(docs, metas)
                ]
                sorted_module_chunks = sorted(
                    module_chunks, key=lambda x: priority_map.get(x["label"], 99)
                )
                if sorted_module_chunks:
                    log_msg = [
                        f"Retrieved & sorted {len(sorted_module_chunks)} chunks from '{module_kb}':"
                    ]
                    for c in sorted_module_chunks:
                        log_msg.append(
                            f"  - Label: {c['label']:<20} | "
                            f"Text: {self._format_text_for_log(c['text'])}"
                        )
                    log.debug("\n".join(log_msg))
            except Exception:
                log.warning("Could not query or find module/setting KB '%s'.", module_kb)

        # 2. Get Rules chunks
        rules_chunks = []
        if rules_kb:
            try:
                docs, metas = self.vector_store.query(rules_kb, player_command, n_results=2)
                rules_chunks = [
                    {"text": doc, "label": meta.get("label", "mechanics")}
                    for doc, meta in zip(docs, metas)
                ]
                if rules_chunks:
                    log_msg = [f"Retrieved {len(rules_chunks)} chunks from '{rules_kb}':"]
                    for c in rules_chunks:
                        log_msg.append(
                            f"  - Label: {c['label']:<20} | "
                            f"Text: {self._format_text_for_log(c['text'])}"
                        )
                    log.debug("\n".join(log_msg))
            except Exception:
                log.warning("Could not query or find rules KB '%s'.", rules_kb)

        # 3. Build final context string and insight data
        context_blocks = []
        insight_data = []

        if sorted_module_chunks:
            context_blocks.append(
                f"[CONTEXT FROM '{module_kb.upper()}']\n"
                + "\n\n---\n\n".join(c["text"] for c in sorted_module_chunks)
            )
            insight_data.extend(sorted_module_chunks)
        if rules_chunks:
            context_blocks.append(
                f"[CONTEXT FROM '{rules_kb.upper()}']\n"
                + "\n\n---\n\n".join(c["text"] for c in rules_chunks)
            )
            insight_data.extend(rules_chunks)

        context_str = "\n\n".join(context_blocks) or "No specific context was found."
        yield {"type": "insight", "content": json.dumps(insight_data, indent=2)}

        history_str = "\n".join([f"{t['role'].title()}: {t['content']}" for t in history])
        user_prompt = (
            f"[CONVERSATION HISTORY]\n{history_str}\n\n"
            f"[CONTEXT]\n{context_str}\n\n"
            f"[PLAYER ACTION]\n{player_command}"
        )

        game_master_prompt = self._get_prompt("GAME_MASTER", lang)
        session_model = game_config.get("llm_model", self.model)
        llm_stream = query_text_llm(
            game_master_prompt, user_prompt, self.ollama_url, session_model, stream=True
        )

        full_narrative = ""
        for chunk in llm_stream:
            full_narrative += chunk
            yield {"type": "narrative_chunk", "content": chunk}

        show_visuals = game_config.get("show_visual_aids", False)
        show_ascii = game_config.get("show_ascii_scene", False)

        if full_narrative and module_kb:
            if show_visuals:
                yield from self._find_and_yield_visual_aid(
                    player_command, full_narrative, module_kb
                )
            if show_ascii:
                yield from self._find_and_yield_ascii_map(full_narrative, game_config)

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

    def _find_and_yield_ascii_map(self, narrative, game_config):
        """Generates an ASCII map from a narrative and yields it."""
        log.debug("Generating ASCII map for narrative.")
        try:
            lang = game_config.get("language", "en")
            classification_model = current_app.config_service.get_settings()["Ollama"][
                "classification_model"
            ]
            prompt = self._get_prompt("ASCII_MAP_GENERATOR", lang)
            map_response = query_text_llm(
                prompt, narrative, self.ollama_url, classification_model
            )
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
