# --- ppdf_lib/reconstructor.py ---
"""
ppdf_lib/reconstructor.py: Contains the DocumentReconstructor for Stage 3.
"""
import logging
from .models import Section, Title, BoxedNoteBlock, TableBlock, ProseBlock, Paragraph

log_reconstruct = logging.getLogger("ppdf.reconstruct")


class DocumentReconstructor:
    """
    Walks a list of PageModels to build the final list of logical Section objects.
    """

    def __init__(self, extractor):
        self.extractor = extractor

    def build_sections(self, page_models):
        """Walks PageModels to build final Section objects."""
        logging.getLogger("ppdf").info(
            "--- Stage 3: Reconstructing Document from Page Models ---"
        )
        sections, current_section, last_title, cont = [], None, None, 2

        def finalize_section(sec):
            if sec and sec.paragraphs:
                log_reconstruct.debug(
                    "Finalizing section '%s' (%d paras)",
                    sec.title,
                    len(sec.paragraphs),
                )
                sections.append(sec)

        for page in page_models:
            log_reconstruct.debug(
                "Reconstructing from Page %d (%s)",
                page.page_num,
                page.page_type,
            )
            if page.page_type != "content":
                finalize_section(current_section)
                current_section = None
                last_title = f"({page.page_type.capitalize()} Page)"
                continue
            if page.title:
                finalize_section(current_section)
                log_reconstruct.debug(
                    "Page Title found: '%s'. Creating new section.",
                    page.title.text,
                )
                current_section = Section(page.title.text, page.page_num)
                last_title, cont = page.title.text, 2

            for zone in page.zones:
                for col in zone.columns:
                    for block in col.blocks:
                        if not current_section:
                            title = (
                                f"{last_title} ({self.extractor._to_roman(cont)})"
                                if last_title
                                else "Untitled Section"
                            )
                            log_reconstruct.debug(
                                "No active section. Creating new ('%s').",
                                title,
                            )
                            if last_title:
                                cont += 1
                            current_section = Section(title, page.page_num)

                        current_section, last_title, cont = (
                            self._process_block_for_reconstruction(
                                block,
                                page,
                                sections,
                                current_section,
                                last_title,
                                cont,
                            )
                        )

        finalize_section(current_section)
        return sections

    def _process_block_for_reconstruction(
        self, block, page, sections, current_section, last_title, cont
    ):
        """Helper to process a single block during section building."""
        if isinstance(block, Title):
            # Finalize previous section and start a new one with this title
            if current_section and current_section.paragraphs:
                sections.append(current_section)
            log_reconstruct.debug(
                "Column Title found: '%s'. Creating new section.", block.text
            )
            current_section = Section(block.text, page.page_num)
            last_title, cont = block.text, 2
        elif isinstance(block, BoxedNoteBlock):
            current_section, last_title, cont = self._handle_boxed_note_block(
                block, page, sections, current_section, last_title, cont
            )
        elif isinstance(block, TableBlock):
            current_section.add_paragraph(
                Paragraph(
                    lines=self.extractor.segmenter._format_table_for_display(block),
                    page=page.page_num,
                    is_table=True,
                    llm_lines=self.extractor.segmenter._format_table_as_markdown(block),
                )
            )
        elif isinstance(block, ProseBlock):
            self._process_prose_block(
                block, current_section, page.page_num, page.body_font_size
            )
        return current_section, last_title, cont

    def _handle_boxed_note_block(
        self, block, page, sections, current_section, last_title, cont
    ):
        """Creates a dedicated section for a BoxedNoteBlock."""
        dangling_para = None
        if current_section and current_section.last_paragraph:
            dangling_para = current_section.paragraphs.pop()

        if current_section and current_section.paragraphs:
            sections.append(current_section)

        # Create a new section specifically for the boxed note
        note_sec = Section(block.title, page.page_num)

        # Process internal blocks of the BoxedNoteBlock
        for internal_block in block.internal_blocks:
            if isinstance(internal_block, TableBlock):
                note_sec.add_paragraph(
                    Paragraph(
                        lines=self.extractor.segmenter._format_table_for_display(
                            internal_block
                        ),
                        page=page.page_num,
                        is_table=True,
                        llm_lines=self.extractor.segmenter._format_table_as_markdown(
                            internal_block
                        ),
                    )
                )
            elif isinstance(internal_block, ProseBlock):
                self._process_prose_block(
                    internal_block,
                    note_sec,
                    page.page_num,
                    page.body_font_size,
                )
        sections.append(note_sec)

        # Handle paragraph that was interrupted by the note
        if dangling_para:
            title = (
                f"{last_title} ({self.extractor._to_roman(cont)})"
                if last_title
                else "Untitled Section"
            )
            if last_title:
                cont += 1
            current_section = Section(title, page.page_num)
            current_section.add_paragraph(dangling_para)
        else:
            current_section = None
        return current_section, last_title, cont

    def _process_prose_block(self, block, section, page, font_size):
        """Splits a ProseBlock into Paragraphs and adds them to a Section."""
        if not block.lines:
            return
        para_groups = self._split_prose_block_into_paragraphs(block.lines, font_size)
        for p_lines in para_groups:
            formatted_lines = [self.extractor.format_line_with_style(line) for line in p_lines]
            section.add_paragraph(Paragraph(formatted_lines, page))

    def _split_prose_block_into_paragraphs(self, lines, font_size):
        """Splits lines into paragraphs based on vertical spacing."""
        if not lines:
            return []
        paras, para, v_thresh = [], [], font_size * 1.2
        for line in lines:
            if para and (para[-1].y0 - line.y1) > v_thresh:
                paras.append(para)
                para = []
            para.append(line)
        if para:
            paras.append(para)
        return paras
