import os
import shutil
import json
import unittest
from unittest.mock import patch, MagicMock
from PIL import Image
from io import BytesIO

from pdfminer.layout import LTImage

from ppdf_lib.api import process_pdf_images

class TestImageExtraction(unittest.TestCase):

    def setUp(self):
        self.test_dir = "./test_output"
        os.makedirs(self.test_dir, exist_ok=True)
        self.pdf_path = os.path.join(self.test_dir, "test_image_pdf.pdf")

        # Create a dummy PDF file for testing
        # This is a very basic placeholder. A real test would generate a PDF
        # with actual images using a library like ReportLab or PyPDF2.
        with open(self.pdf_path, "w") as f:
            f.write("%PDF-1.4\n1 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[1 0 R]>>endobj\n3 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000074 00000 n\n0000000121 00000 n\ntrailer<</Size 4/Root 3 0 R>>startxref\n168\n%%EOF")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch('ppdf_lib.api.extract_pages')
    def test_process_pdf_images(self, mock_extract_pages):
        # Create a dummy PNG image in bytes
        dummy_img = Image.new('RGB', (1, 1), color = 'blue') # Use 1x1 for minimal data
        byte_io = BytesIO()
        dummy_img.save(byte_io, format='PNG')
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

        mock_extract_pages.return_value = [mock_page_layout]

        # Mock Image.open() and its returned instance's save method
        mock_image_instance = MagicMock()
        mock_image_open = MagicMock(return_value=mock_image_instance)
        
        with patch('ppdf_lib.api.Image.open', mock_image_open):
            process_pdf_images(self.pdf_path, self.test_dir)

        # Verify Image.open was called with the correct BytesIO object
        mock_image_open.assert_called_once()
        args, kwargs = mock_image_open.call_args
        self.assertIsInstance(args[0], BytesIO)
        self.assertEqual(args[0].getvalue(), mock_image_data)

        # Verify Image.save was called with the correct filename
        image_file = os.path.join(self.test_dir, "image_001.png")
        mock_image_instance.save.assert_called_once_with(image_file)

        # Verify JSON metadata file was created
        json_file = os.path.join(self.test_dir, "image_001.json")
        self.assertTrue(os.path.exists(json_file))

        with open(json_file, 'r') as f:
            metadata = json.load(f)
            self.assertEqual(metadata['image_id'], 1)
            self.assertEqual(metadata['page_number'], 1)
            self.assertEqual(metadata['bbox'], [10, 20, 110, 120])
            self.assertEqual(metadata['description'], "LLM_DESCRIPTION_PLACEHOLDER")
            self.assertEqual(metadata['classification'], "LLM_CLASSIFICATION_PLACEHOLDER")

        

if __name__ == '__main__':
    unittest.main()
