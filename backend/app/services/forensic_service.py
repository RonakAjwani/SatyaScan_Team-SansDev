import cv2
import numpy as np
from PIL import Image, ExifTags
import io
import os
import logging

logger = logging.getLogger(__name__)

class ForensicService:
    """
    Service for image forensics: ELA (Error Level Analysis) and Metadata extraction.
    """
    
    @staticmethod
    def perform_ela(image_bytes: bytes, quality: int = 90) -> dict:
        """
        Performs Error Level Analysis (ELA) to detect manipulation.
        Returns a score (0-100) indicating potential manipulation and a path to the ELA image.
        """
        try:
            # 1. Load original image
            nparr = np.frombuffer(image_bytes, np.uint8)
            original = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if original is None:
                return {"ela_score": 0, "ela_path": None, "error": "Could not decode image"}

            # 2. Re-save at known quality to a buffer
            _, buffer = cv2.imencode('.jpg', original, [cv2.IMWRITE_JPEG_QUALITY, quality])
            resaved = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
            
            # 3. Calculate absolute difference
            diff = cv2.absdiff(original, resaved)
            
            # 4. Enhance the difference (scale up)
            scale = 20
            ela_image = cv2.scaleAdd(diff, scale, np.zeros_like(diff))
            
            # 5. Calculate a simple "manipulation score" based on max intensity
            # High intensity in specific regions (not uniform) suggests manipulation
            gray_ela = cv2.cvtColor(ela_image, cv2.COLOR_BGR2GRAY)
            max_val = np.max(gray_ela)
            mean_val = np.mean(gray_ela)
            
            # Heuristic: If max difference is very high compared to mean, it might be spliced
            ela_score = min(100, (max_val - mean_val) * 0.5)
            
            # 6. Save ELA image for inspection (optional, can be returned to UI)
            # For now, we just return the score
            
            return {
                "ela_score": round(ela_score, 2),
                "max_diff": int(max_val),
                "mean_diff": round(mean_val, 2)
            }
            
        except Exception as e:
            logger.error(f"ELA Failed: {e}")
            return {"ela_score": 0, "error": str(e)}

    @staticmethod
    def analyze_frequency_spectrum(image_bytes: bytes) -> dict:
        """
        Analyzes the frequency spectrum (FFT) to detect GAN artifacts.
        GANs often leave checkerboard artifacts in the high-frequency domain.
        """
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
            
            if img is None:
                return {"gan_score": 0, "error": "Could not decode image"}

            # 1. Compute 2D FFT
            f = np.fft.fft2(img)
            fshift = np.fft.fftshift(f)
            magnitude_spectrum = 20 * np.log(np.abs(fshift) + 1e-8)

            # 2. Analyze High Frequency Components
            # GANs often have anomalous peaks in the high frequency regions (corners of the shifted spectrum)
            rows, cols = img.shape
            crow, ccol = rows // 2, cols // 2
            
            # Mask low frequencies (center)
            mask_size = int(min(rows, cols) * 0.1)
            mask = np.ones((rows, cols), np.uint8)
            mask[crow-mask_size:crow+mask_size, ccol-mask_size:ccol+mask_size] = 0
            
            high_freq_spectrum = magnitude_spectrum * mask
            
            # 3. Calculate "Artifact Score"
            # High variance or specific peaks in high freq might indicate GAN
            # This is a simplified heuristic. Real fingerprinting needs a classifier.
            mean_high_freq = np.mean(high_freq_spectrum)
            std_high_freq = np.std(high_freq_spectrum)
            
            # Normalize score (0-100)
            # Higher std deviation in high freq often means unnatural periodic patterns (checkerboard)
            # TUNED: Reduced sensitivity. Previously (std/mean)*500 was too aggressive for compressed JPEGs.
            # New formula: (std/mean) * 150. A ratio of 0.2 (common in JPEGs) -> 30 (Safe). 
            # A ratio of 0.5 (strong artifacts) -> 75 (Suspicious).
            ratio = (std_high_freq / mean_high_freq) if mean_high_freq > 0 else 0
            gan_score = min(100, ratio * 150)
            
            return {
                "gan_score": round(gan_score, 2),
                "spectral_mean": round(mean_high_freq, 2),
                "spectral_std": round(std_high_freq, 2)
            }
            
        except Exception as e:
            logger.error(f"GAN Analysis Failed: {e}")
            return {"gan_score": 0, "error": str(e)}

    @staticmethod
    def extract_metadata(image_bytes: bytes) -> dict:
        """
        Extracts EXIF/IPTC metadata and looks for AI signatures.
        """
        try:
            image = Image.open(io.BytesIO(image_bytes))
            exif_data = {}
            
            if image.getexif():
                for tag_id, value in image.getexif().items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    exif_data[str(tag)] = str(value)
            
            # Check for AI/Editing signatures
            ai_keywords = [
                "Midjourney", "Stable Diffusion", "DALL-E", "Adobe Firefly", "AI Generated",
                "Bing Image Creator", "Leonardo.ai", "RunwayML", "Pika Labs", "DeepFloyd",
                "Imagene", "Synthesia", "Artbreeder", "Nightcafe", "Crayon", "Wombo Dream",
                "Nano Banana", "Flux", "Ideogram", "Freepik", "Gemini", "Imagen", "ChatGPT",
                "DeepFaceLab", "DeepFaceLive", "Deepfakes", "FaceSwap", "Face2Face", "dfaker",
                "Deepswap", "MyVoiceYourFace", "Generated Photos"
            ]
            editing_keywords = [
                "Photoshop", "GIMP", "Canva", "Edited", "Lightroom", "Snapseed",
                "PicsArt", "FaceApp", "Remini", "VSCO", "After Effects", "Premiere Pro",
                "Adobe Express", "Affinity Photo", "Apple Photos", "Google Photos",
                "Lensa", "Photoroom", "Photopea", "Pixlr", "Fotor", "BeFunky"
            ]
            
            detected_software = exif_data.get("Software", "")
            
            is_ai = any(k.lower() in str(exif_data).lower() for k in ai_keywords)
            is_edited = any(k.lower() in str(exif_data).lower() for k in editing_keywords)
            
            return {
                "software": detected_software,
                "is_ai_generated": is_ai,
                "is_edited": is_edited,
                "raw_exif": str(exif_data)[:500] # Truncate for safety
            }
            
        except Exception as e:
            logger.error(f"Metadata Extraction Failed: {e}")
            return {"error": str(e)}

forensic_service = ForensicService()
