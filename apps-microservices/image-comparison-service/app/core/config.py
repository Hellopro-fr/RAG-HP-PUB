import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Redis Configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379")
    
    # Processing Limits
    MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))
    
    # Proxy Configuration
    # Used for downloading images from external URLs to avoid blocking
    APIFY_PROXY_PASSWORD: Optional[str] = os.getenv("APIFY_PROXY")
    APIFY_PROXY: Optional[str] = None
    if APIFY_PROXY_PASSWORD:
        APIFY_PROXY = f"http://auto:{APIFY_PROXY_PASSWORD}@proxy.apify.com:8000"

settings = Settings()