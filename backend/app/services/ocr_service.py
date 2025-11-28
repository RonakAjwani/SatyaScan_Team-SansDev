import pytesseract
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

class OCRService:
    """
    Service to extract text from images using Tesseract OCR.
    Requires 'tesseract-ocr' to be installed on the system.
    """
    
    # Set explicit path for Windows
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

    @staticmethod
    def extract_text(image_bytes: bytes) -> str:
        try:
            image = Image.open(io.BytesIO(image_bytes))
            # Perform OCR
            # timeout to prevent hanging on large files
            text = pytesseract.image_to_string(image, timeout=10)
            return text.strip()
        except Exception as e:
            logger.error(f"OCR Failed: {e}")
            # Fallback or return empty string if OCR fails (e.g., tesseract not installed)
            return ""

    @staticmethod
    def is_available() -> bool:
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False
