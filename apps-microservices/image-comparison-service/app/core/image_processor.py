import logging
import cv2
import numpy as np
import httpx
import imagehash
import asyncio
import base64
import gzip
import zlib
from PIL import Image, UnidentifiedImageError, ImageOps
from io import BytesIO
from typing import List, Dict, Tuple, Any, Optional
import anyio

from app.core.config import settings
from app.schemas.comparator import ImageInput, FailedImage

logger = logging.getLogger(__name__)

class ImageProcessor:
    """
    Hybrid Engine for Image Comparison.
    Combines Perceptual Hashing (Structure) and Color Histograms (Content).
    """

    # Headers mimicking the PHP `isUrlAccessible` function
    DOWNLOAD_HEADERS = {
        "Accept": "image/*",
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
    def _try_decompress(data: bytes) -> bytes:
        """
        Attempts to decompress data if it looks like GZIP or ZLIB.
        This mimics the legacy PHP gzdecode/gzinflate logic.
        """
        # Check for GZIP magic number (1f 8b)
        if data.startswith(b'\x1f\x8b'):
            try:
                return gzip.decompress(data)
            except Exception:
                pass
        
        # Check for ZLIB magic headers (common ones)
        # 78 01 (No/Low compression), 78 9C (Default), 78 DA (Best)
        if data.startswith(b'\x78'):
            try:
                return zlib.decompress(data)
            except Exception:
                pass
                
        return data

    @staticmethod
    async def load_images(inputs: List[ImageInput]) -> Tuple[Dict[str, Image.Image], List[FailedImage]]:
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

        for inp in inputs:
            if inp.content:
                # Handle Base64 Content
                try:
                    # Fix: Handle data URI scheme if present (e.g., "data:image/png;base64,...")
                    content_str = inp.content
                    if "," in content_str[:50]:
                        content_str = content_str.split(",", 1)[1]
                    
                    image_data = base64.b64decode(content_str)
                    
                    # Attempt decompression (GZIP/ZLIB)
                    image_data = ImageProcessor._try_decompress(image_data)
                    
                    pil_image = Image.open(BytesIO(image_data)).convert('RGB')
                    
                    # Apply border trimming immediately upon load
                    images[inp.id] = ImageProcessor.trim_borders(pil_image)
                except Exception as e:
                    header_hex = image_data[:10].hex() if 'image_data' in locals() else "N/A"
                    logger.error(f"Failed to decode base64 for image {inp.id}: {e} (Header: {header_hex})")
                    failed.append(FailedImage(id=inp.id, url=inp.url))
            elif inp.url:
                # Handle URL - Queue for batch download
                download_tasks.append(inp)
            else:
                failed.append(FailedImage(id=inp.id, url=None))

        # Execute downloads if any
        if download_tasks:
            # Configure Proxy if available
            # httpx.AsyncClient uses 'proxy' (singular) for a string URL
            proxy_url = None
            if settings.APIFY_PROXY:
                proxy_url = settings.APIFY_PROXY
                logger.info("Using APIFY_PROXY for image downloads.")

            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers=ImageProcessor.DOWNLOAD_HEADERS,
                verify=False,
                proxy=proxy_url
            ) as client:

                async def download_with_retry(inp):
                    """Download an image with a single retry on failure."""
                    for attempt in range(2):
                        try:
                            resp = await client.get(str(inp.url))
                            if resp.status_code == 200:
                                return resp
                            if attempt == 0:
                                await asyncio.sleep(2)
                                continue
                            logger.warning(f"HTTP {resp.status_code} for {inp.id} ({inp.url}) after retry")
                            return resp
                        except Exception as e:
                            if attempt == 0:
                                await asyncio.sleep(2)
                                continue
                            logger.warning(f"Download exception for {inp.id} ({inp.url}): {type(e).__name__} - {str(e)}")
                            return e
                    return None  # Should not reach here

                # Execute concurrently with retry
                responses = await asyncio.gather(
                    *[download_with_retry(inp) for inp in download_tasks],
                    return_exceptions=True
                )

                for i, response in enumerate(responses):
                    img_input = download_tasks[i]
                    img_id = img_input.id

                    if isinstance(response, Exception):
                        failed.append(FailedImage(id=img_id, url=img_input.url))
                        continue

                    if response is None or response.status_code != 200:
                        failed.append(FailedImage(id=img_id, url=img_input.url))
                        continue

                    try:
                        image_bytes = BytesIO(response.content)
                        # Attempt decompression for downloads too (just in case content-encoding header was missed)
                        # Though httpx usually handles this, double safety doesn't hurt if magic bytes match.
                        image_data = ImageProcessor._try_decompress(response.content)
                        
                        pil_image = Image.open(BytesIO(image_data)).convert('RGB')
                        images[img_id] = ImageProcessor.trim_borders(pil_image)
                    except Exception as e:
                        header_hex = response.content[:10].hex()
                        logger.error(f"Processing error for {img_id}: {e} (Header: {header_hex})")
                        failed.append(FailedImage(id=img_id, url=img_input.url))

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
        Calculates similarity score (0-100).
        """
        # 1. pHash Score (Structure)
        # Using 64-bit hash. Max distance is 64.
        # Adjusted formula to be more permissive for thumbnails.
        hamming_dist = feat1['phash'] - feat2['phash']
        
        # New Formula: Linear mapping from distance 0->64 to Score 100->0
        # A distance of 5 (common for thumbnails) now yields ~92%
        phash_score = max(0, (1 - hamming_dist / 64.0)) * 100
        
        # 2. Histogram Score (Content/Color)
        hist_score_raw = cv2.compareHist(feat1['hist'], feat2['hist'], cv2.HISTCMP_CORREL)
        hist_score = max(0, hist_score_raw) * 100

        # --- SMART IDENTITY LOGIC ---
        # If the structure is extremely similar (Hamming distance <= 3),
        # we treat this as a "Duplicate" or "Miniature" even if compression artifacts 
        # lower the histogram score slightly.
        # Distance 0 = Exact
        # Distance 1-3 = Very likely resized/compressed version
        if hamming_dist <= 3 and hist_score >= 85:
            # Force 100% for miniatures/duplicates to satisfy strict thresholds
            return 100.0, {"phash": phash_score, "hist": hist_score, "forced_match": True}

        # Weighted Combination
        if phash_score >= 90:
            # 80% Structure, 20% Color
            final_score = (phash_score * 0.8) + (hist_score * 0.2)
        else:
            # Standard: 60% Structure, 40% Color
            final_score = (phash_score * 0.6) + (hist_score * 0.4)
        
        # Boost: If both are high match, boost towards 100
        if phash_score > 92 and hist_score > 90:
            final_score = (final_score + 100) / 2
            
        return final_score, {"phash": phash_score, "hist": hist_score}

    @staticmethod
    def compare_batch(images: Dict[str, Image.Image], inputs: List[ImageInput]) -> List[Dict]:
        """
        Compares images and maps IDs back to URLs if available.
        """
        ids = list(images.keys())
        n = len(ids)
        if n < 2:
            return []
            
        # Create map for ID -> URL for quick lookup
        url_map = {inp.id: inp.url for inp in inputs}

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
                    "image_a_url": url_map.get(id_a),
                    "image_b_id": id_b,
                    "image_b_url": url_map.get(id_b),
                    "score": round(score, 2),
                    "method_details": details
                })
                
        return results