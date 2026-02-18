import logging
import cv2
import numpy as np
import httpx
import imagehash
import asyncio
import base64
from PIL import Image, UnidentifiedImageError, ImageOps
from io import BytesIO
from typing import List, Dict, Tuple, Any
import anyio

from app.core.config import settings
from app.schemas.comparator import ImageInput

logger = logging.getLogger(__name__)

class ImageProcessor:
    """
    Hybrid Engine for Image Comparison.
    Combines Perceptual Hashing (Structure) and Color Histograms (Content).
    """

    # Headers mimicking the PHP `isUrlAccessible` function
    DOWNLOAD_HEADERS = {
        "Accept": "*/*",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Priority": "u=0, i",
        "Pragma": "no-cache",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    }

    @staticmethod
    def trim_borders(pil_image: Image.Image) -> Image.Image:
        """
        Removes whitespace/borders from the image (Auto-Crop).
        Equivalent to the PHP 'removeBorders' function but faster.
        """
        try:
            # 1. Convert to RGB if not already
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            
            # 2. Invert image (assuming white background becomes black)
            # This helps getbbox find the "content" (non-black pixels)
            inverted_image = ImageOps.invert(pil_image)
            
            # 3. Get bounding box of non-zero regions
            bbox = inverted_image.getbbox()
            
            if bbox:
                # 4. Crop to the content
                return pil_image.crop(bbox)
            
            # If bbox is None (e.g. solid white image), return original
            return pil_image
        except Exception as e:
            logger.warning(f"Border trimming failed: {e}")
            return pil_image

    @staticmethod
    async def load_images(inputs: List[ImageInput]) -> Tuple[Dict[str, Image.Image], List[str]]:
        """
        Loads images from URLs (download) or Base64 content (decode).
        Returns:
            - Dictionary {id: PIL.Image}
            - List of failed IDs
        """
        images = {}
        failed = []
        
        # Separate inputs into URL-based (to download) and Content-based (to decode)
        download_tasks = []
        download_map = {} # Map index in tasks to image ID

        for inp in inputs:
            if inp.content:
                # Handle Base64 Content
                try:
                    # Fix: Handle data URI scheme if present (e.g., "data:image/png;base64,...")
                    content_str = inp.content
                    if "," in content_str[:50]:
                        content_str = content_str.split(",", 1)[1]
                    
                    image_data = base64.b64decode(content_str)
                    pil_image = Image.open(BytesIO(image_data)).convert('RGB')
                    
                    # Apply border trimming immediately upon load
                    images[inp.id] = ImageProcessor.trim_borders(pil_image)
                except Exception as e:
                    logger.error(f"Failed to decode base64 for image {inp.id}: {e}")
                    failed.append(inp.id)
            elif inp.url:
                # Handle URL - Queue for batch download
                download_tasks.append(inp)
            else:
                failed.append(inp.id)

        # Execute downloads if any
        if download_tasks:
            # Configure Proxy if available
            # httpx accepts proxies={"http://": ..., "https://": ...} or just the string
            proxies = None
            if settings.APIFY_PROXY:
                proxies = settings.APIFY_PROXY
                logger.info("Using APIFY_PROXY for image downloads.")

            async with httpx.AsyncClient(
                timeout=20.0, 
                follow_redirects=True, 
                headers=ImageProcessor.DOWNLOAD_HEADERS,
                verify=False,
                proxies=proxies
            ) as client:
                
                # Create coroutines
                reqs = [client.get(str(inp.url)) for inp in download_tasks]
                
                # Execute concurrently
                responses = await asyncio.gather(*reqs, return_exceptions=True)
                
                for i, response in enumerate(responses):
                    img_input = download_tasks[i]
                    img_id = img_input.id
                    
                    if isinstance(response, Exception):
                        logger.warning(f"Download exception for {img_id}: {response}")
                        failed.append(img_id)
                        continue
                        
                    if response.status_code != 200:
                        logger.warning(f"HTTP {response.status_code} for {img_id}")
                        failed.append(img_id)
                        continue
                    
                    try:
                        image_bytes = BytesIO(response.content)
                        pil_image = Image.open(image_bytes).convert('RGB')
                        
                        # Apply border trimming immediately upon load
                        images[img_id] = ImageProcessor.trim_borders(pil_image)
                    except Exception as e:
                        logger.error(f"Processing error for {img_id}: {e}")
                        failed.append(img_id)

        return images, failed

    @staticmethod
    def extract_features(pil_image: Image.Image) -> Dict[str, Any]:
        """
        Extracts numerical features from an image for O(1) comparison.
        1. Perceptual Hash (pHash) - Robust to structure changes.
        2. HSV Histogram - Robust to color distribution.
        """
        features = {}
        
        # 1. Compute pHash (Structure)
        features['phash'] = imagehash.phash(pil_image)

        # 2. Compute Histogram (Color)
        # Convert to numpy array for OpenCV
        cv_image = np.array(pil_image)
        
        # Convert RGB to HSV (Note: PIL is RGB, OpenCV expects RGB here because we converted PIL->NP)
        # However, cv2.cvtColor usually assumes BGR if read via cv2.imread. 
        # Since we use PIL (RGB), we use COLOR_RGB2HSV directly.
        hsv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2HSV)
        
        # Calculate Histograms for H, S, V channels
        # Ranges: H (0-180), S (0-256), V (0-256)
        hist = cv2.calcHist([hsv_image], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist)
        features['hist'] = hist.flatten()
        
        return features

    @staticmethod
    def calculate_similarity(feat1: Dict, feat2: Dict) -> Tuple[float, Dict]:
        """
        Calculates similarity score (0-100) between two feature sets.
        """
        # 1. pHash Score (Structure)
        hamming_dist = feat1['phash'] - feat2['phash']
        phash_score = max(0, (1 - hamming_dist / 30.0)) * 100
        
        # 2. Histogram Score (Content/Color)
        hist_score_raw = cv2.compareHist(feat1['hist'], feat2['hist'], cv2.HISTCMP_CORREL)
        hist_score = max(0, hist_score_raw) * 100

        # Weighted Combination
        # Increased weight for pHash as it's generally more robust for product matching
        # provided borders are handled (which we now do).
        final_score = (phash_score * 0.6) + (hist_score * 0.4)
        
        # Boost score if both are high
        if phash_score > 90 and hist_score > 90:
            final_score = (phash_score + hist_score) / 2
            
        return final_score, {"phash": phash_score, "hist": hist_score}

    @staticmethod
    def compare_batch(images: Dict[str, Image.Image]) -> List[Dict]:
        """
        Main CPU-bound function.
        Extracts features for all images and compares them.
        """
        ids = list(images.keys())
        n = len(ids)
        if n < 2:
            return []
            
        # 1. Feature Extraction (O(N))
        features_map = {}
        for img_id in ids:
            features_map[img_id] = ImageProcessor.extract_features(images[img_id])
            
        # 2. Comparison Matrix (O(N^2))
        results = []
        for i in range(n):
            for j in range(i + 1, n):
                id_a = ids[i]
                id_b = ids[j]
                
                score, details = ImageProcessor.calculate_similarity(features_map[id_a], features_map[id_b])
                
                results.append({
                    "image_a_id": id_a,
                    "image_b_id": id_b,
                    "score": round(score, 2),
                    "method_details": details
                })
                
        return results