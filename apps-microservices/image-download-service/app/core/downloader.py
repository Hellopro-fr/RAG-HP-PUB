import aiohttp
import os
import logging
import asyncio
from typing import Optional, List, Dict
from app.core.image_processor import ImageProcessor
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
        for i, url in enumerate(urls):
            if not url: continue
            
            # Local rate limiting: 2 req/s (sleep 0.5s between requests)
            if i > 0:
                await asyncio.sleep(0.5)
                
            result = await self.download_and_process(url, domain, product_id, product_name)
            if result:
                processed_images.append(result)
        
        # Update product data with new structure
        # We might want to store list of {main, thumb}
        product_data["processed_images"] = processed_images
        
        return product_data
