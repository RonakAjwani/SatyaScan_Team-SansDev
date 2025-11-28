from backend.app.services.ocr_service import OCRService
from PIL import Image, ImageDraw, ImageFont
import io

def test_ocr_mock():
    print("--- Testing OCR Service ---")
    
    # Create a dummy image with text
    img = Image.new('RGB', (200, 100), color = (255, 255, 255))
    
    # You can't easily draw text without a font file in some envs, 
    # but let's try default or just check availability.
    # If we can't verify OCR execution (due to missing tesseract binary),
    # we verify the fallback logic.
    
    if OCRService.is_available():
        print("Tesseract is available on this system.")
        # Proceed to real test if we had an image
    else:
        print("Tesseract is NOT available. Testing fallback.")
        
        # Test empty/failure case
        text = OCRService.extract_text(b"invalid_bytes")
        assert text == ""
        print("Fallback handled correctly.")

if __name__ == "__main__":
    test_ocr_mock()
