import logging
import cv2
import numpy as np
import httpx
import imagehash
from PIL import Image
from io import BytesIO
from typing import List, Dict, Tuple, Any
import anyio

logger = logging.getLogger(__name__)

class ImageProcessor:
    """
    Hybrid Engine for Image Comparison.
    Combines Perceptual Hashing (Structure) and Color Histograms (Content).
    """

    @staticmethod
    async def download_images(inputs: List[Any]) -> Tuple[Dict[str, Image.Image], List[str]]:
        """
        Concurrently downloads images using HTTPX.
        Returns a dictionary of {id: PIL.Image} and a list of failed IDs.
        """
        images = {}
        failed = []
        
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            # Create tasks for all downloads
            tasks = []
            for img_input in inputs:
                tasks.append(client.get(str(img_input.url)))
            
            # Execute all requests concurrently
            responses = await httpx.gather(*tasks, return_exceptions=True)
            
            for i, response in enumerate(responses):
                img_id = inputs[i].id
                
                if isinstance(response, Exception) or response.status_code != 200:
                    logger.warning(f"Failed to download image {img_id}: {response}")
                    failed.append(img_id)
                    continue
                
                try:
                    # Convert bytes to PIL Image
                    image_data = BytesIO(response.content)
                    pil_image = Image.open(image_data).convert('RGB')
                    images[img_id] = pil_image
                except Exception as e:
                    logger.error(f"Failed to decode image {img_id}: {e}")
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
        cv_image = np.array(pil_image)
        hsv_image = cv2.cvtColor(cv_image, cv2.COLOR_RGB2HSV)
        
        # Calculate Histograms for H, S, V channels
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