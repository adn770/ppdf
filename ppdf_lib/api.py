import os
from .extractor import PDFTextExtractor, Section

def process_pdf_text(pdf_path: str, options: dict) -> tuple[list[Section], list]:
    """
    Processes a PDF file to extract and reconstruct structured text.

    Args:
        pdf_path (str): The absolute path to the PDF file.
        options (dict): A dictionary of options for PDFTextExtractor.
                        Expected keys: 'num_cols', 'rm_footers', 'style'.

    Returns:
        tuple[list[Section], list]: A tuple containing a list of Section objects
                                    and a list of PageModel objects.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    extractor = PDFTextExtractor(
        pdf_path,
        num_cols=options.get('num_cols', 'auto'),
        rm_footers=options.get('rm_footers', True),
        style=options.get('style', False)
    )
    sections = extractor.extract_sections()
    return sections, extractor.page_models
