import aiohttp
import aiofiles
import os
import logging
import asyncio
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

    async def download_and_process(self, url: str, domain: str, product_id: str, product_name: str, storage_base: str = "/app/storage") -> Optional[Dict[str, str]]:
        """
        Downloads image bytes and delegates to ImageProcessor.
        """
        # Rate limiting now handled at product level via asyncio.sleep()
        
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
                            
                            # Process image (Synchronous call, but fast enough for threaded consumer or we could offload)
                            # Since we are in an async method called by a sync wrapper in consumer, we are fine.
                            # But wait, Consumer calls this in a loop via run_until_complete.
                            # Image processing is CPU bound. For now, we do it inline.
                            
                            try:
                                paths = self.image_processor.process_image(
                                    content=content,
                                    domain=domain,
                                    product_id=product_id,
                                    product_name=product_name,
                                    base_storage_dir=storage_base
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
        """
        domain = product_data.get("domaine", "unknown")
        product_id = product_data.get("id_produit", "unknown")
        # Try to find product name
        product_name = product_data.get("nom") or product_data.get("nom_produit") or product_data.get("name") or f"produit-{product_id}"
        
        urls = product_data.get("url_images")
        
        if not urls:
            return product_data

        if isinstance(urls, str):
            urls = [urls]
        
        processed_images = []
        logger.info(f"Downloading {len(urls)} images for product {product_id} ({domain})")
        
        for i, url in enumerate(urls):
            if not url: continue
            
            # Local rate limiting: 2 req/s (sleep 0.5s between requests)
            if i > 0:
                await asyncio.sleep(LOCAL_RATE_DELAY)
                
            result = await self.download_and_process(url, domain, product_id, product_name)
            if result:
                processed_images.append(result)
        
        # Update product data with new structure
        product_data["processed_images"] = processed_images
        
        # Save to manifest for archive synchronization
        if processed_images:
            await self._save_to_manifest(domain, product_id, product_name, processed_images)
        
        return product_data

    async def _save_to_manifest(self, domain: str, product_id: str, product_name: str, processed_images: list):
        """
        Appends product metadata to the domain's manifest.json file.
        This manifest will be included in the archive for the BO to update the database.
        """
        import json
        import aiofiles
        
        manifest_dir = f"/app/storage/images/{domain}"
        manifest_path = f"{manifest_dir}/manifest.json"
        
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
        
        # Load existing manifest or create new one
        manifest = {"products": [], "last_updated": ""}
        
        try:
            if os.path.exists(manifest_path):
                async with aiofiles.open(manifest_path, 'r') as f:
                    content = await f.read()
                    manifest = json.loads(content) if content else {"products": [], "last_updated": ""}
        except Exception as e:
            logger.warning(f"Could not read manifest: {e}")
        
        # Update or add product entry
        existing_idx = next((i for i, p in enumerate(manifest["products"]) if p["id_produit"] == product_id), None)
        if existing_idx is not None:
            manifest["products"][existing_idx] = product_entry
        else:
            manifest["products"].append(product_entry)
        
        manifest["last_updated"] = datetime.now().isoformat()
        
        # Write manifest
        try:
            async with aiofiles.open(manifest_path, 'w') as f:
                await f.write(json.dumps(manifest, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Could not write manifest: {e}")
