# --- dmme_lib/services/ingestion_service.py ---
import logging
import re
import os
import json
import shutil
import uuid
from PIL import Image
from io import BytesIO
from flask import current_app
from collections import defaultdict
from .vector_store_service import VectorStoreService
from .config_service import ConfigService
from core.llm_utils import (
    get_semantic_tags,
    query_text_llm,
    get_model_details,
    query_multimodal_llm,
)
from ppdf_lib.api import process_pdf_text, process_pdf_images, reformat_section_with_llm
from ppdf_lib.models import Section
from dmme_lib.constants import PROMPT_REGISTRY
from ppdf_lib.constants import PROMPT_STRICT

log = logging.getLogger("dmme.ingest")


class IngestionService:
    def __init__(
        self,
        vector_store: VectorStoreService,
        config_service: ConfigService,
        utility_model: str,
    ):
        self.vector_store = vector_store
        self.config_service = config_service
        self.utility_model = utility_model
        log.info("IngestionService initialized.")

    def _get_prompt(self, key: str, lang: str) -> str:
        """Safely retrieves a prompt from the registry, falling back to English."""
        return PROMPT_REGISTRY.get(key, {}).get(lang, PROMPT_REGISTRY.get(key, {}).get("en"))

    def _format_text_for_log(self, text: str) -> str:
        """Formats a long text block into a concise, single-line summary for logging."""
        single_line_text = re.sub(r"\s+", " ", text).strip()
        if len(single_line_text) > 100:
            return f'"{single_line_text[:45]}...{single_line_text[-45:]}"'
        return f'"{single_line_text}"'

    def _extract_key_terms_from_chunk(self, chunk: str, tags: list[str]) -> list[str]:
        """
        Extracts key terms from a chunk.
        For stat blocks, it extracts the title. For others, it extracts bolded text.
        """
        if "type:stat_block" in tags:
            first_line = chunk.split("\n", 1)[0]
            # Remove markdown bolding and any leading/trailing whitespace
            cleaned_name = re.sub(r"[\*#]", "", first_line).strip()
            if cleaned_name:
                return [cleaned_name]
            return []
        else:
            # Find all non-overlapping matches of text between double asterisks
            return re.findall(r"\*\*(.*?)\*\*", chunk)

    def _parse_stat_block(self, chunk: str, lang: str) -> dict:
        """Uses an LLM to parse a stat block string into a structured dictionary."""
        log.debug("Parsing stat block with LLM...")
        prompt = self._get_prompt("STAT_BLOCK_PARSER", lang)
        try:
            util_config = self.config_service.get_model_config("classify")
            response_data = query_text_llm(
                prompt,
                chunk,
                util_config["url"],
                util_config["model"],
                temperature=0.0,
            )
            response_str = response_data.get("response", "").strip()
            return json.loads(response_str)
        except (json.JSONDecodeError, TypeError) as e:
            log.warning("Could not parse stat block JSON from LLM: %s", e)
            return {}

    def _parse_spell(self, chunk: str, lang: str) -> dict:
        """Uses an LLM to parse a spell description into a structured dictionary."""
        log.debug("Parsing spell with LLM...")
        prompt = self._get_prompt("SPELL_PARSER", lang)
        try:
            util_config = self.config_service.get_model_config("classify")
            response_data = query_text_llm(
                prompt,
                chunk,
                util_config["url"],
                util_config["model"],
                temperature=0.0,
            )
            response_str = response_data.get("response", "").strip()
            json_match = re.search(r"\{.*\}", response_str, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            log.warning("No JSON object found in spell parser response: %s", response_str)
            return {}
        except (json.JSONDecodeError, TypeError) as e:
            log.warning("Could not parse spell JSON from LLM: %s", e)
            return {}

    def ingest_markdown(self, file_content: str, metadata: dict):
        """Processes and ingests a Markdown file's content, yielding progress."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        kb_type = metadata.get("kb_type", "module")
        if not kb_name:
            raise ValueError("Knowledge base name is required for ingestion.")

        msg = f"✔ Starting Markdown processing for KB '{kb_name}' in '{lang}'."
        log.info(msg)
        yield msg

        # Split content into sections based on Markdown headers
        sections = re.split(r"\n(?=#+ )", file_content)
        msg = f"Splitting file into {len(sections)} logical sections based on headers."
        log.info(msg)
        yield msg

        prompt_key = (
            "SEMANTIC_LABELER_RULES" if kb_type == "rules" else "SEMANTIC_LABELER_ADVENTURE"
        )
        labeler_prompt_template = self._get_prompt(prompt_key, lang)
        log.debug("Using semantic labeler prompt key: '%s'", prompt_key)
        labeler_prompt = labeler_prompt_template.format(kickoff_cue="No hint provided.")
        util_config = self.config_service.get_model_config("classify")

        processed_chunks = []
        chunk_id_counter = 0

        for section_text in sections:
            if not section_text.strip():
                continue

            lines = section_text.strip().split("\n")
            title = lines[0].lstrip("# ").strip()
            content = "\n".join(lines[1:])

            chunks = [
                c.strip() for c in re.split(r"\n{2,}", content) if c.strip() and len(c) >= 50
            ]

            for chunk in chunks:
                msg = f"  -> Labeling chunk from section '{title}'..."
                log.info(msg)
                yield msg
                tags = get_semantic_tags(
                    chunk, labeler_prompt, util_config["url"], util_config["model"]
                )
                # Apply secrecy rule for stat blocks
                if "type:stat_block" in tags:
                    tags.append("access:dm_only")
                    log.debug("Applying semantic rule: Added access:dm_only to stat_block.")

                final_tags = sorted(list(set(tags)))
                key_terms = self._extract_key_terms_from_chunk(chunk, final_tags)
                is_dm_only = "access:dm_only" in final_tags

                processed_chunks.append(
                    {
                        "text": chunk,
                        "metadata": {
                            "source_file": metadata.get("filename", "unknown.md"),
                            "section_title": title,
                            "chunk_id": chunk_id_counter,
                            "tags": final_tags,
                            "is_dm_only": is_dm_only,
                            "key_terms": json.dumps(key_terms),
                        },
                    }
                )
                chunk_id_counter += 1

        if not processed_chunks:
            msg = "✔ No valid text chunks found to ingest."
            log.info(msg)
            yield msg
            return

        # Post-processing for entity linking
        msg = f"✔ Found {len(processed_chunks)} valid chunks. Starting entity linking..."
        log.info(msg)
        yield msg
        final_metadatas = self._link_entities_in_document(processed_chunks, lang)
        documents = [chunk["text"] for chunk in processed_chunks]

        for meta in final_metadatas:
            meta["entities"] = json.dumps(meta.get("entities", {}))
            meta["linked_chunks"] = json.dumps(meta.get("linked_chunks", []))
            meta["structured_stats"] = json.dumps(meta.get("structured_stats", {}))
            meta["structured_spell_data"] = json.dumps(meta.get("structured_spell_data", {}))
            meta["tags"] = json.dumps(meta.get("tags", []))

        msg = "Generating embeddings and saving to vector store..."
        log.info(msg)
        yield msg
        self.vector_store.add_to_kb(kb_name, documents, final_metadatas, kb_metadata=metadata)
        msg = "✔ Saved to vector store."
        log.info(msg)
        yield msg

    def _link_entities_in_document(self, processed_chunks: list[dict], lang: str):
        """Post-processes chunks to extract and link named entities."""
        entity_extractor_prompt = self._get_prompt("ENTITY_EXTRACTOR", lang)
        util_config = self.config_service.get_model_config("classify")
        entity_map = defaultdict(list)

        # Stage 1: Extract entities and structured stats from all chunks
        log.info("  -> Starting entity extraction for %d chunks...", len(processed_chunks))
        for i, chunk_data in enumerate(processed_chunks):
            metadata = chunk_data["metadata"]

            # Deep parse stat blocks if applicable
            if "type:stat_block" in metadata.get("tags", []):
                stats = self._parse_stat_block(chunk_data["text"], lang)
                metadata["structured_stats"] = stats

            # Deep parse spells if applicable
            if "type:spell" in metadata.get("tags", []):
                spell_data = self._parse_spell(chunk_data["text"], lang)
                metadata["structured_spell_data"] = spell_data

            key_terms = json.loads(metadata.get("key_terms", "[]"))
            if not key_terms:
                continue

            log.debug("Extracting entities from terms: %s", key_terms)
            try:
                response_data = query_text_llm(
                    entity_extractor_prompt,
                    json.dumps(key_terms),
                    util_config["url"],
                    util_config["model"],
                    temperature=0.0,
                )
                response_str = response_data.get("response", "").strip()
                entities = json.loads(response_str)
                metadata["entities"] = entities
                for entity_name in entities.keys():
                    entity_map[entity_name].append(metadata["chunk_id"])
            except (json.JSONDecodeError, TypeError) as e:
                log.warning("Could not parse entity JSON from LLM: %s", e)
            except Exception as e:
                log.error("Unexpected error during entity extraction: %s", e)

        # Stage 2: Create links based on the entity map
        log.info("  -> Building relational links between chunks...")
        for chunk_data in processed_chunks:
            metadata = chunk_data["metadata"]
            linked_chunk_ids = set()
            if "entities" in metadata:
                for entity_name in metadata["entities"].keys():
                    for chunk_id in entity_map[entity_name]:
                        if chunk_id != metadata["chunk_id"]:
                            linked_chunk_ids.add(chunk_id)
            metadata["linked_chunks"] = sorted(list(linked_chunk_ids))

        return [chunk["metadata"] for chunk in processed_chunks]

    def ingest_pdf_text(
        self,
        pdf_path: str,
        metadata: dict,
        pages_str: str = "all",
        sections_to_include: list[str] | None = None,
        kickoff_cue: str = "",
    ):
        """Processes and ingests a PDF file's text content, yielding progress."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        if not kb_name:
            raise ValueError("Knowledge base name is required for ingestion.")

        msg = f"Analyzing PDF structure for '{kb_name}' (Pages: {pages_str})..."
        log.info(msg)
        yield msg
        extraction_options = {"num_cols": "auto", "rm_footers": True, "style": True}
        sections, page_models = process_pdf_text(
            pdf_path, extraction_options, "", "", apply_labeling=False, pages_str=pages_str
        )
        msg = f"✔ Structure analysis complete. Found {len(sections)} logical sections."
        log.info(msg)
        yield msg
        # --- Section Filtering based on user selection (if provided) ---
        if sections_to_include:
            sections = [s for s in sections if s.title in sections_to_include]
            msg = f"✔ Filtered to {len(sections)} user-selected sections."
            log.info(msg)
            yield msg
        # --- Section-level Classification and Filtering ---
        page_type_map = {pm.page_num: pm.page_type for pm in page_models}
        content_sections = []
        classifier_prompt = self._get_prompt("SECTION_CLASSIFIER", lang)
        valid_section_tags = {"content", "appendix"}
        valid_llm_tags = valid_section_tags.union(
            {"preface", "table_of_contents", "legal", "credits", "index"}
        )
        util_config = self.config_service.get_model_config("classify")
        model_details = get_model_details(util_config["url"], util_config["model"])
        ctx = model_details.get("context_length", 4096)
        target_chars = int(ctx * 0.8)
        msg = f"Classifying {len(sections)} sections using '{util_config['model']}'..."
        log.info(msg)
        yield msg

        for i, section in enumerate(sections):
            if not section.paragraphs:
                continue
            context_parts, current_chars = [], 0
            if section.title:
                title_text = f"Title: {section.title}\n\n"
                context_parts.append(title_text)
                current_chars += len(title_text)

            for para in section.paragraphs:
                para_text = para.get_text()
                if current_chars + len(para_text) > target_chars:
                    break
                context_parts.append(para_text)
                current_chars += len(para_text) + 2

            representative_text = "\n\n".join(context_parts)
            response_data = query_text_llm(
                classifier_prompt,
                representative_text,
                util_config["url"],
                util_config["model"],
                temperature=0.1,
            )
            final_tag = response_data.get("response", "").strip()

            if final_tag not in valid_llm_tags:
                final_tag = "content"

            log.debug(
                (
                    "Section Classification:\n"
                    "  - Model: %s\n"
                    "  - Title: '%s'\n"
                    "  - Final Tag: %s\n"
                    "  - Input: %s"
                ),
                self.utility_model,
                section.title or "Untitled",
                final_tag,
                self._format_text_for_log(representative_text),
            )

            if final_tag in valid_section_tags:
                content_sections.append(section)
            else:
                msg = f"  -> Skipping section '{section.title}' (classified as '{final_tag}')"
                log.info(msg)
                yield msg

        # --- Paragraph-level Reformatting and Semantic Labeling ---
        kb_type = metadata.get("kb_type", "module")
        prompt_key = (
            "SEMANTIC_LABELER_RULES" if kb_type == "rules" else "SEMANTIC_LABELER_ADVENTURE"
        )
        labeler_prompt_template = self._get_prompt(prompt_key, lang)
        log.debug("Using semantic labeler prompt key: '%s'", prompt_key)
        processed_chunks, chunk_id = [], 0
        fmt_config = self.config_service.get_model_config("format")
        final_labeler_prompt = labeler_prompt_template.format(
            kickoff_cue=kickoff_cue or "No hint provided."
        )

        for i, section in enumerate(content_sections):
            if not section.paragraphs:
                continue
            msg = f"Processing section {i + 1}/{len(content_sections)} ('{section.title}')..."
            log.info(msg)
            yield msg

            for para in section.paragraphs:
                # Create a temporary section with just this paragraph for reformatting
                temp_section = Section()
                temp_section.add_paragraph(para)
                stream = reformat_section_with_llm(
                    section=temp_section,
                    system_prompt=PROMPT_STRICT,
                    ollama_url=fmt_config["url"],
                    model=fmt_config["model"],
                    chunk_size=4000,
                )
                chunk = "".join(list(stream))
                if not chunk.strip():
                    continue

                # Get initial tags from the LLM or structural rules
                tags = []
                if para.is_table:
                    tags.append("access:dm_only")
                    log.debug("Applying structural rule: Added access:dm_only to table.")
                else:
                    tags = get_semantic_tags(
                        chunk, final_labeler_prompt, util_config["url"], util_config["model"]
                    )

                # Apply additional hard-coded semantic rules
                if "type:stat_block" in tags:
                    tags.append("access:dm_only")
                    log.debug("Applying semantic rule: Added access:dm_only to stat_block.")
                if "narrative:kickoff" in tags and section.page_start > 10:
                    tags.remove("narrative:kickoff")
                    tags.append("type:read_aloud")

                final_tags = sorted(list(set(tags)))
                key_terms = self._extract_key_terms_from_chunk(chunk, final_tags)
                is_dm_only = "access:dm_only" in final_tags

                processed_chunks.append(
                    {
                        "text": chunk,
                        "metadata": {
                            "source_file": metadata.get("filename", "unknown.pdf"),
                            "section_title": section.title or "Untitled",
                            "page_start": section.page_start,
                            "chunk_id": chunk_id,
                            "tags": final_tags,
                            "is_dm_only": is_dm_only,
                            "key_terms": json.dumps(key_terms),
                        },
                    }
                )
                chunk_id += 1

        # --- Post-processing: Entity Extraction and Linking ---
        msg = "Post-processing: Extracting entities and creating links..."
        log.info(msg)
        yield msg
        final_metadatas = self._link_entities_in_document(processed_chunks, lang)
        documents = [chunk["text"] for chunk in processed_chunks]

        # Convert complex fields to JSON strings for storage
        for meta in final_metadatas:
            meta["entities"] = json.dumps(meta.get("entities", {}))
            meta["linked_chunks"] = json.dumps(meta.get("linked_chunks", []))
            meta["structured_stats"] = json.dumps(meta.get("structured_stats", {}))
            meta["structured_spell_data"] = json.dumps(meta.get("structured_spell_data", {}))
            meta["tags"] = json.dumps(meta.get("tags", []))

        msg = f"✔ Processing complete. Found {len(documents)} valid chunks."
        log.info(msg)
        yield msg
        msg = "Generating embeddings and saving to vector store..."
        log.info(msg)
        yield msg
        if not documents:
            msg = "✔ No valid text chunks found to ingest."
            log.info(msg)
            yield msg
            return
        self.vector_store.add_to_kb(kb_name, documents, final_metadatas, kb_metadata=metadata)
        msg = "✔ Saved to vector store."
        log.info(msg)
        yield msg

    def process_and_extract_images(
        self, pdf_path: str, assets_path: str, metadata: dict, pages_str: str = "all"
    ):
        """Extracts images from a PDF and processes them using language-aware prompts."""
        kb_name = metadata.get("kb_name")
        lang = metadata.get("language", "en")
        msg = f"Starting image extraction for '{kb_name}' (Pages: {pages_str})..."
        log.info(msg)
        yield msg

        review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
        if os.path.exists(review_dir):
            shutil.rmtree(review_dir)
        os.makedirs(review_dir, exist_ok=True)

        describe_prompt = self._get_prompt("DESCRIBE_IMAGE", lang)
        classify_prompt = self._get_prompt("CLASSIFY_IMAGE", lang)
        vision_config = self.config_service.get_model_config("vision")
        util_config = self.config_service.get_model_config("classify")
        yield from process_pdf_images(
            pdf_path=pdf_path,
            output_dir=review_dir,
            ollama_url=vision_config["url"],
            vision_model=vision_config["model"],
            utility_model=util_config["model"],
            describe_prompt=describe_prompt,
            classify_prompt=classify_prompt,
            pages_str=pages_str,
        )

    def _create_asset_manifest(self, final_dir: str):
        """Creates an assets.json manifest file with detailed asset objects."""
        manifest_data = {"assets": []}
        dir_name = os.path.basename(final_dir)
        try:
            for filename in sorted(os.listdir(final_dir)):
                if not filename.endswith(".json") or filename == "assets.json":
                    continue
                with open(os.path.join(final_dir, filename), "r") as f:
                    data = json.load(f)

                thumb_filename = data.get("thumbnail_filename")
                image_filename = data.get("image_filename")

                if not (thumb_filename and image_filename):
                    continue

                manifest_data["assets"].append(
                    {
                        "id": os.path.splitext(image_filename)[0],
                        "thumb_url": f"{dir_name}/{thumb_filename}",
                        "full_url": f"{dir_name}/{image_filename}",
                        "classification": data.get("classification", "other"),
                        "description": data.get("description", ""),
                    }
                )

            manifest_path = os.path.join(final_dir, "assets.json")
            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f, indent=4)
            log.info("Created detailed asset manifest at %s", manifest_path)
        except Exception as e:
            log.error("Failed to create asset manifest: %s", e)

    def ingest_images(self, kb_name: str, assets_path: str):
        """Finalizes image ingestion from a review directory."""
        review_dir = os.path.join(assets_path, "images", f"{kb_name}_reviewing")
        log.info("Finalizing image ingestion for KB '%s' from dir: %s", kb_name, review_dir)
        if not os.path.isdir(review_dir):
            raise FileNotFoundError(f"Review directory not found: {review_dir}")

        documents, metadatas = [], []
        json_files = [f for f in os.listdir(review_dir) if f.endswith(".json")]
        log.debug("Found %d metadata files in review directory.", len(json_files))

        for json_file in json_files:
            with open(os.path.join(review_dir, json_file), "r") as f:
                data = json.load(f)

            if data.get("classification") == "decoration":
                log.debug("Skipping decorative image: %s", json_file)
                continue

            doc_text = (
                f"An image of type '{data['classification']}' depicting: {data['description']}"
            )
            documents.append(doc_text)

            image_filename = json_file.replace(".json", ".png")
            thumb_filename = data.get("thumbnail_filename", "")
            final_image_path = os.path.join("images", kb_name, image_filename)
            final_thumb_path = os.path.join("images", kb_name, thumb_filename)
            metadatas.append(
                {
                    "source_file": "PDF Images",
                    "tags": json.dumps(["type:image"]),
                    "is_dm_only": False,
                    "classification": data["classification"],
                    "image_url": final_image_path,
                    "thumbnail_url": final_thumb_path,
                }
            )
        log.info("Prepared %d images for vector store ingestion.", len(documents))

        if documents:
            self.vector_store.add_to_kb(kb_name, documents, metadatas)

        final_dir = os.path.join(assets_path, "images", kb_name)
        if os.path.exists(final_dir):
            shutil.rmtree(final_dir)
        os.rename(review_dir, final_dir)

        # Create the asset manifest after the final directory is in place
        self._create_asset_manifest(final_dir)

        log.info(
            "Image ingestion for '%s' finalized. Review dir promoted to: %s",
            kb_name,
            final_dir,
        )

    def add_custom_asset(self, kb_name: str, file_storage):
        """Processes a user-uploaded image and adds it to an existing KB."""
        assets_dir = os.path.join(current_app.config["ASSETS_PATH"], "images", kb_name)
        os.makedirs(assets_dir, exist_ok=True)

        # 1. Save files with unique names
        file_ext = os.path.splitext(file_storage.filename)[1]
        asset_id = uuid.uuid4().hex
        image_filename = f"custom_{asset_id}{file_ext}"
        thumb_filename = f"thumb_custom_{asset_id}.jpg"
        json_filename = f"custom_{asset_id}.json"
        image_path = os.path.join(assets_dir, image_filename)
        thumb_path = os.path.join(assets_dir, thumb_filename)
        json_path = os.path.join(assets_dir, json_filename)

        file_storage.save(image_path)

        # 2. Generate thumbnail
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((256, 256))
            img.save(thumb_path, "JPEG", quality=85)

        # 3. Generate metadata with LLM (Two-Stage Process)
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        kb_metadata = self.vector_store.get_kb_metadata(kb_name)
        lang = kb_metadata.get("language", "en")
        vision_config = self.config_service.get_model_config("vision")
        util_config = self.config_service.get_model_config("classify")

        # Stage 1: Describe with vision model
        describe_prompt = self._get_prompt("DESCRIBE_IMAGE", lang)
        description = query_multimodal_llm(
            describe_prompt, image_bytes, vision_config["url"], vision_config["model"]
        )

        # Stage 2: Classify description with utility model
        classify_prompt = self._get_prompt("CLASSIFY_IMAGE", lang)
        classification_data = query_text_llm(
            classify_prompt, description, util_config["url"], util_config["model"], 0.1
        )
        classification = classification_data.get("response", "").strip()

        if classification not in {"cover", "art", "map", "handout", "decoration", "other"}:
            classification = "art"

        # 4. Save metadata JSON
        metadata = {
            "description": description or "No description generated.",
            "classification": classification,
            "source": "user_upload",
            "original_filename": file_storage.filename,
            "thumbnail_filename": thumb_filename,
            "image_filename": image_filename,
        }
        with open(json_path, "w") as f:
            json.dump(metadata, f, indent=4)

        # 5. Add to vector store
        doc_text = f"An image of type '{classification}' depicting: {description}"
        doc_meta = {
            "source_file": "User Uploads",
            "tags": json.dumps(["type:image"]),
            "is_dm_only": False,
            "classification": classification,
            "image_url": os.path.join("images", kb_name, image_filename),
            "thumbnail_url": os.path.join("images", kb_name, thumb_filename),
        }
        self.vector_store.add_to_kb(kb_name, [doc_text], [doc_meta])

        # 6. Update manifest
        self._create_asset_manifest(assets_dir)
        log.info("Successfully added custom asset '%s' to KB '%s'", image_filename, kb_name)
        return {
            "url": f"/assets/{doc_meta['thumbnail_url']}",
            "caption": description,
            "classification": classification,
        }

    def delete_asset(self, kb_name: str, thumb_filename: str):
        """Deletes an asset's image, thumbnail, and metadata, then updates the manifest."""
        assets_dir = os.path.join(current_app.config["ASSETS_PATH"], "images", kb_name)
        if not os.path.isdir(assets_dir):
            raise FileNotFoundError("Asset directory for KB does not exist.")

        base_name = thumb_filename.replace("thumb_", "").replace(".jpg", "")
        json_filename = f"{base_name}.json"
        json_path = os.path.join(assets_dir, json_filename)

        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Asset metadata file not found: {json_filename}")

        with open(json_path, "r") as f:
            metadata = json.load(f)

        image_filename = metadata.get("image_filename")
        if not image_filename:
            # Fallback for older assets before this key was saved
            image_exts = [".png", ".jpg", ".jpeg", ".webp"]
            for ext in image_exts:
                if os.path.exists(os.path.join(assets_dir, f"{base_name}{ext}")):
                    image_filename = f"{base_name}{ext}"
                    break
            if not image_filename:
                raise FileNotFoundError(f"Could not determine main image for {base_name}")

        thumb_path = os.path.join(assets_dir, thumb_filename)
        image_path = os.path.join(assets_dir, image_filename)
        log.info("Deleting asset files for %s: %s", kb_name, image_filename)

        # Delete the files, ignoring errors if they're already gone
        for path in [image_path, thumb_path, json_path]:
            try:
                os.remove(path)
            except FileNotFoundError:
                log.warning("File not found during deletion, continuing: %s", path)
            except Exception as e:
                log.error("Error deleting file %s: %s", path, e)
                raise

        # Regenerate the manifest
        self._create_asset_manifest(assets_dir)
