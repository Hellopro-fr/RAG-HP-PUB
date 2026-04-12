from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Max concurrent crawls allowed PER service instance.
    MAX_CONCURRENT_CRAWLS: int = 10

    # A sensible fallback for the global max crawls if the Redis key is missing.
    DEFAULT_MAX_GLOBAL_CRAWLS: int = 3

    # Interval in seconds for the background task to reconcile the running jobs counter.
    RECONCILIATION_INTERVAL_SECONDS: int = 300

    # GCS Configuration
    GCS_BUCKET_NAME: Optional[str] = None

    # Base directory for storing all crawl data (logs, datasets, etc.)
    CRAWLER_STORAGE_PATH: str = "/app/storage"

    # Shared volume path where archives are placed for the upload daemon to pick up
    ARCHIVES_SHARED_PATH: str = "/app/archives"

    # Path to the compiled Node.js crawler entry point
    CRAWLER_EXECUTABLE_PATH: str = "/app/crawler/dist/main.js"

    # Proxy configuration
    APIFY_PROXY: Optional[str] = None

    # OOM restart configuration
    MAX_OOM_RESTARTS: int = 2

    # GCS download daemon paths
    DOWNLOAD_REQUESTS_PATH: str = "/app/gcs-requests"
    DOWNLOAD_RESULTS_PATH: str = "/app/gcs-downloads"

    # GCS download timeout in seconds
    GCS_DOWNLOAD_TIMEOUT_SECONDS: int = 300

    # API authentication
    API_KEY: Optional[str] = None

    # Stale job detection thresholds (seconds)
    STALE_JOB_THRESHOLD_LOCAL: int = 180   # Local jobs: PID check + 3 min heartbeat gap
    STALE_JOB_THRESHOLD_REMOTE: int = 600  # Remote jobs: 10 min grace period for owning replica

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()
