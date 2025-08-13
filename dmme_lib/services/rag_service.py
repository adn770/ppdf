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
        raw_llm_log: bool = False,
    ):
        self.vector_store = vector_store
        self.config_service = config_service
        self.assets_path = assets_path
        self.raw_llm_log = raw_llm_log
        self.context_cache = {}
        self.current_location = None
        self.last_kickoff_section = None
        log.info("RAGService initialized.")

    def _get_prompt(self, key: str, lang: str) -> str:
        """Assembles a prompt from the registry using the hybrid, English-first strategy."""
        prompt_data = PROMPT_REGISTRY.get(key, {})
        if not prompt_data:
            raise ValueError(f"Prompt key '{key}' not found in registry.")

        # For old-style, fully translated prompts (like gameplay prompts)
        if isinstance(prompt_data.get(lang), str):
            return prompt_data.get(lang, prompt_data.get("en", ""))

        # For new-style, component-based prompts
        base_prompt = prompt_data.get("base_prompt", "")
        examples = prompt_data.get("examples", {})
        lang_example = examples.get(lang, examples.get("en", ""))

        final_prompt = base_prompt
        if lang_example:
            final_prompt += f"\n\n{lang_example}"

        language_map = {"en": "English", "es": "Spanish", "ca": "Catalan"}
        if "{language_name}" in final_prompt:
            final_prompt = final_prompt.format(language_name=language_map.get(lang, "English"))

        return final_prompt

    def _format_text_for_log(self, text: str) -> str:
        """Formats a long text block into a concise, single-line summary for logging."""
        single_line_text = re.sub(r"\s+", " ", text).strip()
        if len(single_line_text) > 100:
            return f'"{single_line_text[:45]}...{single_line_text[-45:]}"'
        return f'"{single_line_text}"'

    def _log_retrieved_documents(self, context_name: str, metas: list[dict]):
        """Helper to log the essential metadata of retrieved documents for debugging."""
        log.debug("--- RAG Context: %s ---", context_name)
        if not metas:
            log.debug("  - No documents found.")
            return

        for meta in metas:
            try:
                hierarchy = json.loads(meta.get("hierarchy", "[]"))
                tags = json.loads(meta.get("tags", "[]"))
                hierarchy_str = " > ".join(hierarchy)
                log.debug(
                    "  - ID: %s | Title: '%s' | Hierarchy: %s | Tags: %s",
                    meta.get("chunk_id", "N/A"),
                    meta.get("section_title", "Unknown"),
                    hierarchy_str,
                    tags,
                )
            except (json.JSONDecodeError, TypeError):
                log.debug("  - Could not parse metadata for a document: %s", meta)
        log.debug("--- End Context: %s ---", context_name)

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
        self.last_kickoff_section = None
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

        found_docs, found_metas = [], []
        best_kickoff_chunk = None

        # --- Heuristic 1: Prioritize explicit 'kickoff' or 'hook' tags ---
        priority_labels = ["narrative:kickoff", "narrative:hook"]
        candidate_chunks = []
        for label in priority_labels:
            log.debug("Searching for kickoff content with priority label: '%s'", label)
            docs, metas, _ = self.vector_store.query(
                active_kb,
                query_text=f"Adventure start, beginning, introduction, or {label}",
                n_results=20,
            )
            for i, meta in enumerate(metas):
                if label in meta.get("tags", ""):
                    candidate_chunks.append({"doc": docs[i], "meta": meta})
        if candidate_chunks:
            best_kickoff_chunk = min(
                candidate_chunks, key=lambda x: x["meta"].get("section_number", 9999)
            )

        if best_kickoff_chunk:
            log.info("Kickoff Heuristic 1 SUCCESS: Found tagged content.")
            kickoff_meta = best_kickoff_chunk["meta"]
            self.last_kickoff_section = kickoff_meta.get("section_number")
            all_docs, all_metas = self._get_full_section(active_kb, kickoff_meta)
            s_chunks = sorted(
                zip(all_docs, all_metas), key=lambda item: item[1].get("chunk_id", 0)
            )
            start_idx = next(
                (j for j, (d, _) in enumerate(s_chunks) if d == best_kickoff_chunk["doc"]),
                -1,
            )
            if start_idx != -1:
                sequence = [s_chunks[start_idx]]
                for k in range(start_idx + 1, len(s_chunks)):
                    if "type:mechanics" in s_chunks[k][1].get("tags", ""):
                        sequence.append(s_chunks[k])
                    else:
                        break
                found_docs = [item[0] for item in sequence]
                found_metas = [item[1] for item in sequence]
            else:
                found_docs, found_metas = all_docs, all_metas
        else:
            # --- Heuristic 2: Fallback to searching the first 3 sections ---
            log.warning("Kickoff Heuristic 1 FAILED. Falling back to Heuristic 2.")
            docs, metas, _ = self.vector_store.query(
                active_kb,
                "Adventure introduction, summary, or starting location",
                n_results=1,
                where_filter={"section_number": {"$in": [0, 1, 2]}},
            )
            if docs:
                log.info("Kickoff Heuristic 2 SUCCESS: Found content in first 3 sections.")
                found_docs, found_metas = self._get_full_section(active_kb, metas[0])
            else:
                # --- Heuristic 3: Fallback to the first "location" entity ---
                log.warning("Kickoff Heuristic 2 FAILED. Falling back to Heuristic 3.")
                all_chunks = self.vector_store.get_all_from_kb(active_kb)
                first_location_chunk = None
                sorted_chunks = sorted(all_chunks, key=lambda x: x.get("chunk_id", ""))
                for chunk in sorted_chunks:
                    try:
                        entities = json.loads(chunk.get("entities", "{}"))
                        if "location" in entities.values():
                            first_location_chunk = chunk
                            break
                    except (json.JSONDecodeError, TypeError):
                        continue
                if first_location_chunk:
                    log.info("Kickoff Heuristic 3 SUCCESS: Found first location entity.")
                    found_docs, found_metas = self._get_full_section(
                        active_kb, first_location_chunk
                    )
                else:
                    # --- Heuristic 4: Final fallback to just the first section ---
                    log.warning("Kickoff Heuristic 3 FAILED. Falling back to Heuristic 4.")
                    docs, metas, _ = self.vector_store.query(
                        active_kb,
                        active_kb,  # Query with a generic term
                        n_results=50,  # Get enough to find all chunks
                        where_filter={"section_number": 0},
                    )
                    if docs:
                        log.info("Kickoff Heuristic 4 SUCCESS: Using section 0.")
                        found_docs, found_metas = docs, metas

        if not found_docs:
            found_docs = ["No introductory text was found in the knowledge base."]
            found_metas = [{"tags": '["type:prose"]'}]

        self._log_retrieved_documents("Kickoff Narration", found_metas)

        # --- Initialize Location Cache ---
        primary_location = self._find_primary_location(found_metas)
        if primary_location:
            self._build_location_cache(active_kb, primary_location)

        intro_context = "\n\n".join(found_docs)
        insight_data = [
            {
                "kb_name": active_kb,
                "section_title": meta.get("section_title", "Unknown"),
                "tags": json.loads(meta.get("tags", "[]")),
                "text": doc,
            }
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
            raw_response_log=self.raw_llm_log,
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

        # --- Define Security Filters ---
        player_safe_filter = {"is_dm_only": False}
        narrative_context_str = "No context found."
        insight_data = []

        # --- State Check: Is this the first move after kickoff? ---
        is_first_move = (
            self.last_kickoff_section is not None
            and len(history) == 2
            and history[0].get("role") == "assistant"
        )

        if is_first_move:
            log.info("First move detected. Applying sequential retrieval logic.")
            target_section = self.last_kickoff_section + 1
            # Player-safe context
            p_docs, p_metas, _ = self.vector_store.query(
                module_kb,
                "The room or area immediately following the introduction.",
                n_results=50,
                where_filter={"section_number": target_section, **player_safe_filter},
            )
            narrative_context_str = "\n\n---\n\n".join(p_docs) or "No context found."
            # Full context for DM Insight
            i_docs, i_metas, _ = self.vector_store.query(
                module_kb,
                "The room or area immediately following the introduction.",
                n_results=50,
                where_filter={"section_number": target_section},
            )
            insight_data = [
                {
                    "text": d,
                    "tags": json.loads(m.get("tags", "[]")),
                    "kb_name": module_kb,
                    "section_title": m.get("section_title", "Unknown"),
                }
                for d, m in zip(i_docs, i_metas)
            ]
            self.last_kickoff_section = None  # Consume the state
        else:
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
                    raw_response_log=self.raw_llm_log,
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
                log.debug("Expanded player command into %d search queries: %s", len(queries), queries)
            except (json.JSONDecodeError, TypeError) as e:
                log.warning("Could not parse query expansion response. Error: %s", e)

            # --- Stage 2: Execute queries and build context ---
            p_mod_docs, p_mod_metas = execute_queries(
                self.vector_store, module_kb, queries, filter=player_safe_filter
            )
            p_rules_docs, p_rules_metas = execute_queries(
                self.vector_store, rules_kb, queries, filter=player_safe_filter, n_results=3
            )

            # --- Location Cache Logic ---
            primary_location = self._find_primary_location(p_mod_metas)
            if primary_location and primary_location["name"] != self.current_location:
                # Location has changed, refresh the cache
                self._build_location_cache(module_kb, primary_location)
            elif not primary_location and self.current_location:
                # Party has left a known location into an unknown area
                log.info("Party has left '%s'. Clearing location cache.", self.current_location)
                log.debug("Cache invalidated.")
                self.current_location = None
                self.context_cache = {}

            # --- Stage 2b: Assemble Context (Cached or Live) ---
            if self.current_location and self.context_cache:
                log.debug("Using cached RAG context for location: '%s'", self.current_location)
                narrative_context_str = self.context_cache.get("player_prompt", "")
                insight_data = self.context_cache.get("insight_data", [])
                if p_rules_docs:
                    narrative_context_str += "\n\n---\n\n" + "\n\n".join(p_rules_docs)
            else:
                log.debug("No valid location cache. Performing live context defragmentation.")
                # Fallback to standard defragmentation if not in a cached location
                if p_mod_docs:
                    self._log_retrieved_documents("Player-Safe Module Context", p_mod_metas)
                    defrag_docs, _ = self._get_full_section(
                        module_kb, p_mod_metas[0], where_filter=player_safe_filter
                    )
                    narrative_context_str = "\n\n---\n\n".join(defrag_docs)
                else:
                    narrative_context_str = ""
                if p_rules_docs:
                    self._log_retrieved_documents("Player-Safe Rules Context", p_rules_metas)
                    narrative_context_str += "\n\n---\n\n" + "\n\n".join(p_rules_docs)

                # Get FULL (DM + Player) context for the insight modal
                i_mod_docs, i_mod_metas = execute_queries(self.vector_store, module_kb, queries)
                i_rules_docs, i_rules_metas = execute_queries(self.vector_store, rules_kb, queries)
                if i_mod_docs:
                    defrag_i_docs, defrag_i_metas = self._get_full_section(
                        module_kb, i_mod_metas[0]
                    )
                    insight_data.extend(
                        [
                            {
                                "text": d,
                                "tags": json.loads(m.get("tags", "[]")),
                                "kb_name": module_kb,
                                "section_title": m.get("section_title", "Unknown"),
                            }
                            for d, m in zip(defrag_i_docs, defrag_i_metas)
                        ]
                    )
                if i_rules_docs:
                    insight_data.extend(
                        [
                            {
                                "text": d,
                                "tags": json.loads(m.get("tags", "[]")),
                                "kb_name": rules_kb,
                                "section_title": m.get("section_title", "Rules Lookup"),
                            }
                            for d, m in zip(i_rules_docs, i_rules_metas)
                        ]
                    )

            narrative_context_str = narrative_context_str.strip() or "No context found."

        yield {"type": "insight", "content": json.dumps(insight_data, indent=2)}

        # --- Stage 3: Generate and Stream LLM Response ---
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
            raw_response_log=self.raw_llm_log,
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
            docs, metas, _ = self.vector_store.query(kb_name, image_query, n_results=5)
            # In-app filtering
            for i, meta in enumerate(metas):
                if '"type:image"' in meta.get("tags", ""):
                    image_doc = docs[i]
                    image_meta = meta
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
                        return  # Yield only the first match
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
                raw_response_log=self.raw_llm_log,
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
            raw_response_log=self.raw_llm_log,
        )
        summary = response_data.get("response", "").strip()
        return summary

    def _build_location_cache(self, kb_name: str, location_info: dict):
        """Builds a complete context dossier for a location and caches it."""
        location_name = location_info["name"]
        location_meta = location_info["meta"]
        log.info("New location detected: '%s'. Building context cache.", location_name)
        self.current_location = location_name
        self.context_cache = {}

        try:
            linked_ids = json.loads(location_meta.get("linked_chunks", "[]"))
            all_ids = list(set([location_meta["chunk_id"]] + linked_ids))
            log.debug("Building cache for location '%s' with chunk IDs: %s", location_name, all_ids)
            docs, metas = self.vector_store.get_by_ids(kb_name, ids=all_ids)

            player_safe_docs = [
                doc for doc, meta in zip(docs, metas) if not meta.get("is_dm_only", False)
            ]
            self.context_cache["player_prompt"] = "\n\n---\n\n".join(player_safe_docs)

            self.context_cache["insight_data"] = [
                {
                    "text": d,
                    "tags": json.loads(m.get("tags", "[]")),
                    "kb_name": kb_name,
                    "section_title": m.get("section_title", "Unknown"),
                }
                for d, m in zip(docs, metas)
            ]
            log.info(
                "Cache for '%s' built successfully with %d total chunks.",
                location_name,
                len(docs),
            )
        except (json.JSONDecodeError, TypeError, Exception) as e:
            log.error("Failed to build location cache for '%s': %s", location_name, e)
            self.current_location = None
            self.context_cache = {}


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
