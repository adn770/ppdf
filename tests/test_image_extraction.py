import os
import shutil
import json
from unittest.mock import MagicMock
from PIL import Image
from io import BytesIO
import pytest

from pdfminer.layout import LTImage

from ppdf_lib.api import process_pdf_images


@pytest.fixture
def setup_test_environment():
    test_dir = "./test_output"
    os.makedirs(test_dir, exist_ok=True)
    pdf_path = os.path.join(test_dir, "test_image_pdf.pdf")

    # Create a dummy PDF file for testing
    with open(pdf_path, "w") as f:
        f.write(
            "%PDF-1.4\n1 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[1 0 R]>>endobj\n3 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000074 00000 n\n0000000121 00000 n\ntrailer<</Size 4/Root 3 0 R>>startxref\n168\n%%EOF"
        )

    yield test_dir, pdf_path

    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)


def test_process_pdf_images(setup_test_environment, mocker):
    test_dir, pdf_path = setup_test_environment

    # Create a dummy PNG image in bytes
    dummy_img = Image.new("RGB", (1, 1), color="blue")  # Use 1x1 for minimal data
    byte_io = BytesIO()
    dummy_img.save(byte_io, format="PNG")
    mock_image_data = byte_io.getvalue()

    # Mock LTImage object
    mock_lt_image = MagicMock(spec=LTImage)
    mock_lt_image.__class__ = LTImage
    mock_lt_image.x0 = 10
    mock_lt_image.y0 = 20
    mock_lt_image.x1 = 110
    mock_lt_image.y1 = 120
    mock_lt_image.width = 100
    mock_lt_image.height = 100
    mock_lt_image.stream = MagicMock()
    mock_lt_image.stream.get_data.return_value = mock_image_data

    # Mock page_layout object
    mock_page_layout = MagicMock()
    mock_page_layout.pageid = 1
    mock_page_layout.__iter__.return_value = [mock_lt_image]

    mock_extract_pages = mocker.patch("ppdf_lib.api.extract_pages")
    mock_extract_pages.return_value = [mock_page_layout]

    # Mock Image.open() and its returned instance's save method
    mock_image_instance = MagicMock()

    def mock_save(filename, format):
        with open(filename, "wb") as f:
            f.write(mock_image_data)

    mock_image_instance.save.side_effect = mock_save
    # NOTE: We patch Image.open in the module where it's *used* (ppdf_lib.api)
    mock_image_open = mocker.patch("ppdf_lib.api.Image.open", return_value=mock_image_instance)

    mock_query_llm = mocker.patch("ppdf_lib.api._query_multimodal_llm")
    mock_query_llm.side_effect = [
        "LLM_DESCRIPTION_PLACEHOLDER",
        "art",  # Ensure a valid classification is returned
    ]

    # Consume the generator to execute the function
    list(process_pdf_images(pdf_path, test_dir, "http://mock-url", "mock-model"))

    # Verify Image.open was called with the correct BytesIO object
    mock_image_open.assert_called_once()
    args, kwargs = mock_image_open.call_args
    assert isinstance(args[0], BytesIO)
    assert args[0].getvalue() == mock_image_data

    # Verify Image.save was called with the correct filename
    image_file = os.path.join(test_dir, "image_001.png")
    mock_image_instance.save.assert_called_once_with(image_file, "PNG")

    # Verify JSON metadata file was created
    json_file = os.path.join(test_dir, "image_001.json")
    assert os.path.exists(json_file)

    with open(json_file, "r") as f:
        metadata = json.load(f)
        assert metadata["image_id"] == 1
        assert metadata["page_number"] == 1
        assert metadata["bbox"] == [10, 20, 110, 120]
        assert metadata["description"] == "LLM_DESCRIPTION_PLACEHOLDER"
        assert metadata["classification"] == "art"
