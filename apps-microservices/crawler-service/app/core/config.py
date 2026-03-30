import os
from typing import Optional
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

class Settings:
    # Max concurrent crawls allowed PER service instance.
    # Can be set via environment variable.
    MAX_CONCURRENT_CRAWLS: int = int(os.getenv("MAX_CONCURRENT_CRAWLS", "10"))

    # A sensible fallback for the global max crawls if the Redis key is missing.
    # This should ideally be set to the default number of replicas.
    DEFAULT_MAX_GLOBAL_CRAWLS: int = int(os.getenv("DEFAULT_MAX_GLOBAL_CRAWLS", "3"))

    # Maximum number of OOM restarts before a crawl job is marked as failed.
    MAX_OOM_RESTARTS: int = int(os.getenv("MAX_OOM_RESTARTS", "2"))

    # Interval in seconds for the background task to reconcile the running jobs counter.
    RECONCILIATION_INTERVAL_SECONDS: int = int(os.getenv("RECONCILIATION_INTERVAL_SECONDS", "300"))

    # GCS Configuration
    GCS_BUCKET_NAME: Optional[str] = os.getenv("GCS_BUCKET_NAME")

    # Base directory for storing all crawl data (logs, datasets, etc.)
    CRAWLER_STORAGE_PATH: str = os.getenv("CRAWLER_STORAGE_PATH", "/app/storage")

    # Shared volume path where archives are placed for the upload daemon to pick up
    ARCHIVES_SHARED_PATH: str = os.getenv("ARCHIVES_SHARED_PATH", "/app/archives")

    # Shared volume paths for the download daemon (GCS retrieval)
    DOWNLOAD_REQUESTS_PATH: str = os.getenv("DOWNLOAD_REQUESTS_PATH", "/app/download_requests")
    DOWNLOAD_RESULTS_PATH: str = os.getenv("DOWNLOAD_RESULTS_PATH", "/app/download_results")
    GCS_DOWNLOAD_TIMEOUT_SECONDS: int = int(os.getenv("GCS_DOWNLOAD_TIMEOUT_SECONDS", "300"))

    # Path to the compiled Node.js crawler entry point
    CRAWLER_EXECUTABLE_PATH: str = "/app/crawler/dist/main.js"

    # Proxy configuration
    APIFY_PROXY: Optional[str] = os.getenv("APIFY_PROXY", None)


settings = Settings()