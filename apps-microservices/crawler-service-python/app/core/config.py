import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Crawler configuration
    CRAWLER_STORAGE_PATH: str = os.getenv("CRAWLER_STORAGE_PATH", "/app/storage")
    CRAWLER_EXECUTABLE_PATH: str = "/app/src/main.py"
    
    # Concurrency limits
    MAX_CONCURRENT_CRAWLS: int = int(os.getenv("MAX_CONCURRENT_CRAWLS", "1"))
    DEFAULT_MAX_GLOBAL_CRAWLS: int = int(os.getenv("DEFAULT_MAX_GLOBAL_CRAWLS", "10"))
    
    # Redis configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379")
    
    # Proxy configuration
    APIFY_PROXY: Optional[str] = os.getenv("APIFY_PROXY", None)

    # Maintenance configuration
    RECONCILIATION_INTERVAL_SECONDS: int = int(os.getenv("RECONCILIATION_INTERVAL_SECONDS", "300"))
    
    # GCS Configuration
    GCS_BUCKET_NAME: str = os.getenv("GCS_BUCKET_NAME")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
