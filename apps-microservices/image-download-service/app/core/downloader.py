import aiohttp
import aiofiles
import os
import logging
import asyncio
from typing import Optional, List
from urllib.parse import urlparse
from app.core.ratelimiter import RateLimiter

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

class Downloader:
    def __init__(self):
        # We'll initialize ratelimiter lazily or pass it in
        self.rate_limiter = RateLimiter()
        # Proxy config
        self.proxy_password = os.environ.get("APIFY_PROXY")
        self.proxy_url = os.environ.get("PROXY_URL") 
        
        if self.proxy_password and not self.proxy_url:
             # Construct Apify Proxy URL if password is provided but generic URL is not
             # Using "auto" session to rotate IPs per request (or per session if we kept it)
             self.proxy_url = f"http://auto:{self.proxy_password}@proxy.apify.com:8000"
             logger.info(f"Configured Apify Proxy (auto/port 8000)")
        elif self.proxy_url:
             logger.info(f"Configured generic Proxy: {self.proxy_url}")

    async def download_image(self, url: str, domain: str, product_id: str, storage_base: str = "/app/storage/images") -> Optional[str]:
        self.rate_limiter.acquire(domain)
        
        target_dir = os.path.join(storage_base, domain, product_id)
        os.makedirs(target_dir, exist_ok=True)
        
        # Extract filename
        try:
            parsed = urlparse(url)
            filename = os.path.basename(parsed.path)
            if not filename:
                filename = "image_unknown.jpg"
            # Simple sanitization
            filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._-"])
        except Exception:
            filename = "image.jpg"

        file_path = os.path.join(target_dir, filename)
        
        # Check if exists
        if os.path.exists(file_path):
            return file_path

        retries = 3
        timeout = aiohttp.ClientTimeout(total=30)
        
        for attempt in range(retries):
            try:
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    # Proxy usage only if configured
                    kwargs = {}
                    if self.proxy_url:
                        kwargs["proxy"] = self.proxy_url

                    async with session.get(url, **kwargs) as response:
                        if response.status == 200:
                            f = await aiofiles.open(file_path, mode='wb')
                            await f.write(await response.read())
                            await f.close()
                            return file_path
                        else:
                            logger.warning(f"Failed to download {url}: Status {response.status}")
            except Exception as e:
                logger.warning(f"Error downloading {url} (Attempt {attempt+1}): {e}")
                await asyncio.sleep(attempt * 1) # Exponential-ish backoff
        
        return None

    async def process_product(self, product_data: dict) -> dict:
        """
        Downloads images for a product.
        Returns the updated product data with local paths.
        """
        domain = product_data.get("domaine", "unknown")
        product_id = product_data.get("id_produit", "unknown")
        urls = product_data.get("url_images")
        
        if not urls:
            return product_data

        # Handle string vs list
        if isinstance(urls, str):
            urls = [urls]
        
        local_paths = []
        for url in urls:
            if not url: continue
            path = await self.download_image(url, domain, product_id)
            if path:
                local_paths.append(path)
        
        product_data["local_image_paths"] = local_paths
        return product_data
