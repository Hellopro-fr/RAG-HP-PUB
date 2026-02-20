import aiohttp
import aiofiles
import os
import logging
import asyncio
import re
import unicodedata
from datetime import datetime
from typing import Optional, List, Dict
from image_download_service.core.image_processor import ImageProcessor
import random

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
]

# Local rate limit: delay between requests (seconds)
LOCAL_RATE_DELAY = float(os.environ.get("IMAGE_DOWNLOAD_DELAY", 0.5))

class Downloader:
    def __init__(self):
        self.image_processor = ImageProcessor()
        
        # Proxy config
        self.proxy_password = os.environ.get("APIFY_PROXY")
        self.proxy_url = os.environ.get("PROXY_URL") 
        
        if self.proxy_password and not self.proxy_url:
             self.proxy_url = f"http://auto:{self.proxy_password}@proxy.apify.com:8000"
             logger.info(f"Configured Apify Proxy (auto/port 8000)")
        elif self.proxy_url:
             logger.info(f"Configured generic Proxy: {self.proxy_url}")

    def _normalize_name(self, name: str) -> str:
        """
        Simple slugification to match PHP's normaliser_mot_expression roughly.
        """
        # Lowercase
        name = name.lower()
        
        # Remove accents
        nfkd_form = unicodedata.normalize('NFKD', name)
        name = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
        
        # Replace non-alphanumeric with -
        name = re.sub(r'[^a-z0-9]+', '-', name)
        
        # Trim dashes
        name = name.strip('-')
        
        return name

    def _get_expected_paths(self, domain: str, product_id: str, product_name: str, storage_base: str = "/app/storage", index: int = 0) -> Dict[str, str]:
        """
        Calculate expected paths for an image based on product info and index.
        Returns dict with main_path and thumb_path for each possible extension.
        """
        product_id_str = str(product_id)
        if len(product_id_str) < 3:
            product_id_str = product_id_str.zfill(3)
            
        rep1 = product_id_str[-1]
        rep2 = product_id_str[-2]
        rep3 = product_id_str[-3]
        
        normalized_name = self._normalize_name(product_name)
        
        # Check all possible extensions
        extensions = ['.jpg', '.png', '.gif', '.webp']
        paths = {}
        
        for ext in extensions:
            if index > 0:
                 filename = f"{normalized_name}-{product_id}-{index}{ext}"
            else:
                 # Check standard format for index 0 if that's what we decide, but current logic will likely pass index=1, 2, 3..
                 # If index=1, filename has -1.
                 if index == 0:
                      filename = f"{normalized_name}-{product_id}{ext}"
                 else:
                      filename = f"{normalized_name}-{product_id}-{index}{ext}"

            main_dir = os.path.join(storage_base, "images", domain, "produit-2", rep1, rep2, rep3)
            thumb_dir = os.path.join(storage_base, "images", domain, "produit-3", rep1, rep2, rep3)
            
            paths[ext] = {
                "main_path": os.path.join(main_dir, filename),
                "thumb_path": os.path.join(thumb_dir, filename),
                "filename": filename
            }
        
        return paths

    def _image_exists(self, domain: str, product_id: str, product_name: str, storage_base: str = "/app/storage", index: int = 1) -> Optional[Dict[str, str]]:
        """
        Check if image already exists for this product at specific index.
        Returns the paths if found, None otherwise.
        """
        expected_paths = self._get_expected_paths(domain, product_id, product_name, storage_base, index)
        
        for ext, paths in expected_paths.items():
            if os.path.exists(paths["main_path"]) and os.path.exists(paths["thumb_path"]):
                return paths
        
        return None

    async def download_and_process(self, url: str, domain: str, product_id: str, product_name: str, storage_base: str = "/app/storage", index: int = 0) -> Optional[Dict[str, str]]:
        """
        Downloads image bytes and delegates to ImageProcessor.
        """
        retries = 3
        timeout = aiohttp.ClientTimeout(total=30)
        
        for attempt in range(retries):
            try:
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    kwargs = {}
                    if self.proxy_url:
                        kwargs["proxy"] = self.proxy_url

                    async with session.get(url, **kwargs) as response:
                        logger.info(f"Download status for {url}: {response.status}")
                        if response.status == 200:
                            content = await response.read()
                            
                            try:
                                paths = self.image_processor.process_image(
                                    content=content,
                                    domain=domain,
                                    product_id=product_id,
                                    product_name=product_name,
                                    base_storage_dir=storage_base,
                                    index=index 
                                )
                                return paths
                            except Exception as e:
                                logger.error(f"Image processing failed for {url}: {e}")
                                return None
                            
                        else:
                            logger.warning(f"Failed to download {url}: Status {response.status}")
            except Exception as e:
                logger.warning(f"Error downloading {url} (Attempt {attempt+1}): {e}")
                await asyncio.sleep(attempt * 1)
        
        return None

    async def process_product(self, product_data: dict) -> dict:
        """
        Downloads and processes images for a product.
        Checks if individual image already exists before downloading.
        """
        domain = product_data.get("domaine", "unknown")
        product_id = product_data.get("id_produit", "unknown")
        # Try to find product name
        product_name = product_data.get("nom") or product_data.get("nom_produit") or product_data.get("name") or f"produit-{product_id}"
        
        urls = product_data.get("url_images")
        
        if not urls:
            return product_data

        if isinstance(urls, str):
            # Handle comma-separated strings (common issue)
            if "," in urls:
                 urls = [u.strip() for u in urls.split(",")]
            else:
                 urls = [urls]
        
        processed_images = []
        skipped_count = 0
        
        logger.info(f"Downloading {len(urls)} images for product {product_id} ({domain})")
        
        for i, url in enumerate(urls):
            if not url: continue
            
            # Index for file naming (starts at 1)
            img_index = i + 1
            
            # Check if *this specific image* index already exists
            existing_paths = self._image_exists(domain, product_id, product_name, index=img_index)
            if existing_paths:
                logger.info(f"⏭️  Image {img_index} already exists for product {product_id}: {existing_paths['filename']}")
                processed_images.append(existing_paths)
                skipped_count += 1
                continue

            # Local rate limiting: 2 req/s (sleep 0.5s between requests)
            if i > 0:
                await asyncio.sleep(LOCAL_RATE_DELAY)
                
            result = await self.download_and_process(url, domain, product_id, product_name, index=img_index)
            if result:
                processed_images.append(result)
        
        # Update product data with new structure
        product_data["processed_images"] = processed_images
        product_data["skipped_count"] = skipped_count
        product_data["total_images"] = len(urls)
        
        # Save to manifest for archive synchronization
        if processed_images:
            await self._save_to_manifest(domain, product_id, product_name, processed_images)
        
        return product_data

    async def _save_to_manifest(self, domain: str, product_id: str, product_name: str, processed_images: list):
        """
        Appends product metadata to the domain's manifest.json file.
        This manifest will be included in the archive for the BO to update the database.
        
        Uses fcntl.flock (LOCK_EX) for exclusive cross-replica locking 
        and atomic write (temp file + os.replace) to prevent corruption.
        """
        import json
        import fcntl
        import tempfile
        
        manifest_dir = f"/app/storage/images/{domain}"
        manifest_path = f"{manifest_dir}/manifest.json"
        lock_path = f"{manifest_path}.lock"
        
        # Create directory if needed
        os.makedirs(manifest_dir, exist_ok=True)
        
        # Build product entry
        product_entry = {
            "id_produit": product_id,
            "nom": product_name,
            "images": []
        }
        
        for img in processed_images:
            # Extract relative paths from full paths
            main_path = img.get("main_path", "")
            thumb_path = img.get("thumb_path", "")
            
            # Convert to relative paths (e.g., produit-2/1/0/0/nom-60001.jpg)
            if "/images/" in main_path:
                main_rel = main_path.split(f"/images/{domain}/")[1] if f"/images/{domain}/" in main_path else main_path
            else:
                main_rel = main_path
                
            if "/images/" in thumb_path:
                thumb_rel = thumb_path.split(f"/images/{domain}/")[1] if f"/images/{domain}/" in thumb_path else thumb_path
            else:
                thumb_rel = thumb_path
            
            product_entry["images"].append({
                "main": main_rel,
                "thumb": thumb_rel,
                "filename": img.get("filename", "")
            })
        
        # --- Exclusive lock + atomic write to prevent concurrent corruption ---
        try:
            with open(lock_path, 'w') as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                try:
                    # Read existing manifest (under lock)
                    manifest = {"products": [], "last_updated": ""}
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, 'r') as f:
                                content = f.read()
                                if content.strip():
                                    manifest = json.loads(content)
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.warning(f"Corrupted manifest detected for {domain}, starting fresh: {e}")
                            manifest = {"products": [], "last_updated": ""}
                    
                    # Update or add product entry
                    existing_idx = next((i for i, p in enumerate(manifest.get("products", [])) if p.get("id_produit") == product_id), None)
                    if existing_idx is not None:
                        manifest["products"][existing_idx] = product_entry
                    else:
                        manifest.setdefault("products", []).append(product_entry)
                    
                    manifest["last_updated"] = datetime.now().isoformat()
                    
                    # Write to temp file, then atomic rename
                    fd, tmp_path = tempfile.mkstemp(dir=manifest_dir, suffix='.tmp')
                    try:
                        with os.fdopen(fd, 'w') as tmp_f:
                            tmp_f.write(json.dumps(manifest, indent=2, ensure_ascii=False))
                        os.replace(tmp_path, manifest_path)
                    except Exception:
                        # Clean up temp file on error
                        if os.path.exists(tmp_path):
                            os.unlink(tmp_path)
                        raise
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
        except Exception as e:
            logger.error(f"Could not write manifest for {domain}: {e}")
