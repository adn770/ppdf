# --- dmme_lib/services/rag_service.py ---
import logging
import re
import json
import os
from flask import current_app
from collections import defaultdict

from .vector_store_service import VectorStoreService
from .config_service import ConfigService
from core.llm_utils import query_text_llm
from dmme_lib.constants import PROMPT_REGISTRY

log = logging.getLogger("dmme.rag")


class RAGService:
    def __init__(
        self,
        vector_store: VectorStoreService,
        config_service: ConfigService,
        assets_path: str,
    ):
        self.vector_store = vector_store
        self.config_service = config_service
        self.assets_path = assets_path
        self.context_cache = {}
        self.current_location = None
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

    def _get_full_section(
        self, kb_name: str, chunk_meta: dict, where_filter: dict | None = None
    ) -> tuple[list[str], list[dict]]:
        """Retrieves all chunks belonging to the same section as the given chunk."""
        section_title = chunk_meta.get("section_title")
        if not section_title:
            log.warning("Cannot defragment chunk; missing 'section_title' metadata.")
            return [], []

        log.debug("Defragmenting RAG context for section: '%s'", section_title)
        base_where = {"section_title": section_title}
        final_where = {"$and": [base_where, where_filter]} if where_filter else base_where

        docs, metas, _ = self.vector_store.query(
            kb_name,
            query_text=section_title,
            n_results=100,
            where_filter=final_where,
        )
        return docs, metas

    def generate_kickoff_narration(self, game_config: dict, recap: str = None):
        """
        Generates the initial narration for a new game or session.
        This is a generator function that yields JSON chunks.
        """
        # Reset cache for the new game session
        self.context_cache = {}
        self.current_location = None
        log.info("Context cache cleared for new game session.")

        # --- Get Session-Specific Configuration ---
        global_settings = self.config_service.get_settings()
        lang = game_config.get("language") or global_settings["Appearance"]["language"]
        dm_config = self.config_service.get_model_config("dm")
        if game_config.get("llm_model"):
            dm_config["model"] = game_config["llm_model"]
            log.info("Overriding DM model for session to: %s", dm_config["model"])

        log.info("Generating kickoff narration for game in '%s'.", lang)
        module_kb = game_config.get("module")
        setting_kb = game_config.get("setting")
        active_kb = module_kb or setting_kb

        if not active_kb:
            raise ValueError("A module or setting knowledge base is required for kickoff.")

        # --- Yield Cover Mosaic for Module Mode ---
        if game_config.get("mode") == "module" and module_kb:
            yield from self._find_and_yield_cover_mosaic(module_kb)

        priority_labels = ["narrative:kickoff", "narrative:hook"]
        found_docs, found_metas = [], []

        for label in priority_labels:
            log.debug("Searching for kickoff content with priority label: '%s'", label)
            docs, metas, _ = self.vector_store.query(
                active_kb,
                query_text=f"Text for starting an adventure, like a {label.replace('_', ' ')}",
                n_results=1,
                where_filter={"tags": {"$contains": label}},
            )
            if docs:
                log.info("Found high-priority kickoff content with label '%s'.", label)
                # Get all chunks from the same section to ensure we have the full sequence
                all_docs, all_metas = self._get_full_section(active_kb, metas[0])
                # Combine and sort chunks by their original ingestion order
                s_chunks = sorted(
                    zip(all_docs, all_metas), key=lambda i: i[1].get("chunk_id", 0)
                )
                # Find the starting point of our kickoff sequence
                start_idx = next((i for i, (d, _) in enumerate(s_chunks) if d == docs[0]), -1)
                if start_idx != -1:
                    sequence = [s_chunks[start_idx]]
                    for i in range(start_idx + 1, len(s_chunks)):
                        chunk_tags = json.loads(s_chunks[i][1].get("tags", "[]"))
                        if "type:mechanics" in chunk_tags:
                            sequence.append(s_chunks[i])
                        else:
                            break
                    found_docs = [item[0] for item in sequence]
                    found_metas = [item[1] for item in sequence]
                    log.info("Built kickoff sequence with %d chunks.", len(found_docs))
                else:
                    found_docs, found_metas = self._get_full_section(active_kb, metas[0])
                break

        # Fallback: General search if no priority content was found
        if not found_docs:
            log.debug("No high-priority content found. Falling back to general search.")
            docs, metas, _ = self.vector_store.query(
                active_kb, "adventure introduction, summary, or starting location", n_results=1
            )
            if docs:
                found_docs, found_metas = self._get_full_section(active_kb, metas[0])

        if not found_docs:
            found_docs = ["No introductory text was found in the knowledge base."]
            found_metas = [{"tags": '["type:prose"]'}]

        intro_context = "\n\n".join(found_docs)
        insight_data = [
            {"tags": json.loads(meta.get("tags", "[]")), "text": doc}
            for doc, meta in zip(found_docs, found_metas)
        ]
        log.debug("Final kickoff RAG context retrieved:\n%s", intro_context)
        yield {"type": "insight", "content": json.dumps(insight_data, indent=2)}

        prompt_content = f"[ADVENTURE INTRODUCTION]\n{intro_context}"
        if recap:
            prompt_content = f"[PREVIOUS SESSION RECAP]\n{recap}\n\n{prompt_content}"

        kickoff_prompt = self._get_prompt("KICKOFF_ADVENTURE", lang)
        llm_stream = query_text_llm(
            kickoff_prompt,
            prompt_content,
            dm_config["url"],
            dm_config["model"],
            stream=True,
            temperature=dm_config["temperature"],
            context_window=dm_config["context_window"],
        )
        for chunk_data in llm_stream:
            yield {"type": "narrative_chunk", "content": chunk_data.get("response", "")}

    def _find_primary_location(self, metas: list[dict]):
        """Finds the first named location entity in a list of metadata."""
        for meta in metas:
            entities_str = meta.get("entities", "{}")
            try:
                entities = json.loads(entities_str)
                for name, type in entities.items():
                    if type == "location":
                        log.debug("Found primary location entity: '%s'", name)
                        return {"name": name, "meta": meta}
            except (json.JSONDecodeError, TypeError):
                continue
        return None

    def generate_response(self, player_command: str, game_config: dict, history: list[dict]):
        """
        Generates a game response using a multi-query, cached RAG pipeline.
        This is a generator function that yields JSON chunks.
        """
        # --- Get Session-Specific Configuration ---
        global_settings = self.config_service.get_settings()
        lang = game_config.get("language") or global_settings["Appearance"]["language"]
        dm_config = self.config_service.get_model_config("dm")
        if game_config.get("llm_model"):
            dm_config["model"] = game_config["llm_model"]
            log.info("Overriding DM model for session to: %s", dm_config["model"])

        log.info("Generating RAG stream for command: '%s' in '%s'", player_command, lang)

        module_kb = (
            game_config.get("module")
            if game_config.get("mode") == "module"
            else game_config.get("setting")
        )
        rules_kb = game_config.get("rules")
        history_str = "\n".join([f"{t['role'].title()}: {t['content']}" for t in history])

        # --- Stage 1: Expand player command into multiple search queries ---
        expander_prompt = self._get_prompt("QUERY_EXPANDER", lang)
        expander_user_content = expander_prompt.format(
            history=history_str, command=player_command
        )
        queries = [player_command]
        try:
            util_config = self.config_service.get_model_config("classify")
            response_data = query_text_llm(
                "",
                expander_user_content,
                util_config["url"],
                util_config["model"],
                stream=False,
                temperature=util_config["temperature"],
                context_window=util_config["context_window"],
            )
            response_str = response_data.get("response", "[]")
            json_match = re.search(r"\[.*\]", response_str, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                expanded_queries = json.loads(json_str)
            else:
                expanded_queries = []

            if isinstance(expanded_queries, list):
                queries.extend(expanded_queries)
            log.info("Expanded into %d search queries: %s", len(queries), queries)
        except (json.JSONDecodeError, TypeError) as e:
            log.warning("Could not parse query expansion response. Error: %s", e)

        # --- Stage 2: Execute all queries and check for cacheable location ---
        narrative_filter = {"is_dm_only": False}

        # We query for insight first to identify a primary location
        insight_module_docs, insight_module_metas = execute_queries(
            self.vector_store, module_kb, queries, n_results=3
        )
        primary_location = self._find_primary_location(insight_module_metas)

        # --- Stage 3: Build Context (Cache or Live) ---
        if primary_location and primary_location["name"] == self.current_location:
            log.info(
                "CACHE HIT: Using cached context for location: '%s'", self.current_location
            )
            cache_entry = self.context_cache[self.current_location]
            narrative_context_str = cache_entry["narrative_context"]
            insight_data = cache_entry["insight_data"]
        else:
            log.info("CACHE MISS: Building live context.")
            if primary_location:
                log.info(
                    "New location detected: '%s'. Building cache.", primary_location["name"]
                )
                self.current_location = primary_location["name"]

                # Build player-safe context for the new location
                narrative_docs, _ = self._get_full_section(
                    module_kb, primary_location["meta"], where_filter=narrative_filter
                )
                narrative_context_str = "\n\n---\n\n".join(narrative_docs)

                # Build full insight context for the new location
                full_docs, full_metas = self._get_full_section(
                    module_kb, primary_location["meta"]
                )
                insight_data = [
                    {"text": d, "tags": json.loads(m.get("tags", "[]"))}
                    for d, m in zip(full_docs, full_metas)
                ]
                # Store both in cache
                self.context_cache[self.current_location] = {
                    "narrative_context": narrative_context_str,
                    "insight_data": insight_data,
                }
            else:
                # No primary location, use multi-query results directly and clear cache
                self.current_location = None
                log.info("No primary location. Using merged query results.")
                narrative_module_docs, _ = execute_queries(
                    self.vector_store, module_kb, queries, filter=narrative_filter
                )
                rules_docs, _ = execute_queries(
                    self.vector_store, rules_kb, queries, n_results=3
                )

                context_blocks = []
                if narrative_module_docs:
                    context_blocks.append("\n\n---\n\n".join(narrative_module_docs))
                if rules_docs:
                    context_blocks.append("\n\n---\n\n".join(rules_docs))
                narrative_context_str = "\n\n".join(context_blocks) or "No context found."

                insight_rules_docs, _ = execute_queries(
                    self.vector_store, rules_kb, queries, n_results=3
                )
                insight_data = [
                    {"text": d, "tags": json.loads(m.get("tags", "[]"))}
                    for d, m in zip(insight_module_docs, insight_module_metas)
                ]
                insight_data.extend(
                    [{"text": doc, "tags": ["type:mechanics"]} for doc in insight_rules_docs]
                )

        yield {"type": "insight", "content": json.dumps(insight_data, indent=2)}

        # --- Stage 4: Generate and Stream LLM Response ---
        user_prompt = (
            f"[CONVERSATION HISTORY]\n{history_str}\n\n"
            f"[CONTEXT]\n{narrative_context_str}\n\n"
            f"[PLAYER ACTION]\n{player_command}"
        )
        game_master_prompt = self._get_prompt("GAME_MASTER", lang)
        llm_stream = query_text_llm(
            game_master_prompt,
            user_prompt,
            dm_config["url"],
            dm_config["model"],
            stream=True,
            temperature=dm_config["temperature"],
            context_window=dm_config["context_window"],
        )
        full_narrative = ""
        for chunk_data in llm_stream:
            chunk_content = chunk_data.get("response", "")
            full_narrative += chunk_content
            yield {"type": "narrative_chunk", "content": chunk_content}

        show_visuals = game_config.get("show_visual_aids", False)
        show_ascii = game_config.get("show_ascii_scene", False)
        if full_narrative and module_kb:
            if show_visuals:
                yield from self._find_and_yield_visual_aid(
                    player_command, full_narrative, module_kb
                )
            if show_ascii:
                yield from self._find_and_yield_ascii_map(full_narrative, lang)

    def _find_and_yield_cover_mosaic(self, kb_name: str):
        """Finds up to 4 cover images from the manifest and yields them as a mosaic."""
        log.debug("Searching for asset manifest in '%s' for mosaic.", kb_name)
        try:
            manifest_path = os.path.join(self.assets_path, "images", kb_name, "assets.json")

            if os.path.exists(manifest_path):
                with open(manifest_path, "r") as f:
                    manifest = json.load(f)

                all_assets = manifest.get("assets", [])
                cover_assets = [a for a in all_assets if a.get("classification") == "cover"]

                if len(cover_assets) > 1:
                    last_image = cover_assets.pop()
                    cover_assets.insert(0, last_image)

                cover_assets_data = []
                for asset in cover_assets[:4]:
                    thumb = asset.get("thumb_url")
                    full = asset.get("full_url")
                    if thumb and full:
                        cover_assets_data.append(
                            {
                                "thumb_url": f"/assets/images/{thumb}",
                                "full_url": f"/assets/images/{full}",
                            }
                        )

                if cover_assets_data:
                    log.info("Found %d cover images for mosaic.", len(cover_assets_data))
                    yield {"type": "cover_mosaic", "assets": cover_assets_data}
        except Exception as e:
            log.error("Failed during cover mosaic manifest processing: %s", e)

    def _find_and_yield_visual_aid(self, command, narrative, kb_name):
        """Queries for a relevant image and yields a visual_aid chunk if found."""
        log.debug("Searching for relevant visual aid in '%s'.", kb_name)
        image_query = f"Scene described by: {command}. {narrative}"
        try:
            docs, metas, _ = self.vector_store.query(
                kb_name,
                image_query,
                n_results=1,
                where_filter={"tags": {"$contains": "type:image"}},
            )
            if docs and metas:
                image_doc = docs[0]
                image_meta = metas[0]
                full_url = image_meta.get("image_url")
                thumb_url = image_meta.get("thumbnail_url")
                if full_url and thumb_url:
                    log.info("Found relevant visual aid: %s", full_url)
                    yield {
                        "type": "visual_aid",
                        "full_url": f"/assets/{full_url}",
                        "thumb_url": f"/assets/{thumb_url}",
                        "caption": image_doc,
                    }
        except Exception as e:
            log.error("Failed during visual aid search: %s", e)

    def _find_and_yield_ascii_map(self, narrative, lang: str):
        """Generates an ASCII map from a narrative and yields it."""
        log.debug("Generating ASCII map for narrative.")
        try:
            prompt = self._get_prompt("ASCII_MAP_GENERATOR", "en")
            util_config = self.config_service.get_model_config("classify")
            response_data = query_text_llm(
                prompt,
                narrative,
                util_config["url"],
                util_config["model"],
                temperature=util_config["temperature"],
                context_window=util_config["context_window"],
            )
            map_response = response_data.get("response", "").strip()
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
        dm_config = self.config_service.get_model_config("dm")
        response_data = query_text_llm(
            prompt,
            session_log,
            dm_config["url"],
            dm_config["model"],
            temperature=dm_config["temperature"],
            context_window=dm_config["context_window"],
        )
        summary = response_data.get("response", "").strip()
        return summary


def execute_queries(vector_store, kb_name, queries, filter=None, n_results=2):
    """
    Helper to run queries against a KB, respecting its indexing strategy.
    Returns unique results.
    """
    if not kb_name:
        return [], []
    unique_docs = {}
    try:
        kb_meta = vector_store.get_kb_metadata(kb_name)
        strategy = kb_meta.get("indexing_strategy", "standard")
        log.debug("Executing queries on '%s' with strategy: '%s'", kb_name, strategy)

        if strategy == "deep":
            summary_kb_name = f"{kb_name}_summaries"
            summary_docs, summary_metas, _ = vector_store.query(
                summary_kb_name, " ".join(queries), n_results=n_results
            )
            parent_ids = [m.get("parent_id") for m in summary_metas if m.get("parent_id")]
            if not parent_ids:
                return [], []

            docs, metas = vector_store.get_by_ids(kb_name, ids=parent_ids)
        else:  # Standard strategy
            docs, metas = [], []
            for query in queries:
                q_docs, q_metas, _ = vector_store.query(
                    kb_name, query, n_results=n_results, where_filter=filter
                )
                docs.extend(q_docs)
                metas.extend(q_metas)

        for doc, meta in zip(docs, metas):
            if doc not in unique_docs:
                unique_docs[doc] = meta

    except Exception as e:
        log.warning("Could not query KB '%s' for queries. Error: %s", kb_name, e)

    doc_list = list(unique_docs.keys())
    meta_list = list(unique_docs.values())
    return doc_list, meta_list
