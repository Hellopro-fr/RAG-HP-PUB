import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Redis Configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379")
    
    # Processing Limits
    MAX_CONCURRENT_JOBS: int = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
    
    # Proxy Configuration
    # Used for downloading images from external URLs to avoid blocking
    APIFY_PROXY_PASSWORD: Optional[str] = os.getenv("APIFY_PROXY")
    APIFY_PROXY: Optional[str] = None
    if APIFY_PROXY_PASSWORD:
        APIFY_PROXY = f"http://auto:{APIFY_PROXY_PASSWORD}@proxy.apify.com:8000"

    # Data Retention
    # Time in seconds to keep job status and results in Redis (Default: 24 hours)
    JOB_RESULT_TTL: int = int(os.getenv("JOB_RESULT_TTL", "86400"))

    # --- Bounding knobs (Design 1: bounded downloads + per-job timeout + backpressure) ---
    # Per-image download timeouts (granular). READ is the inter-byte cap — flagged for
    # later p95-based tuning (a too-low value drops genuinely-slow images -> failed_images).
    IMG_DOWNLOAD_CONNECT_TIMEOUT_S: float = float(os.getenv("IMG_DOWNLOAD_CONNECT_TIMEOUT_S", "3"))
    IMG_DOWNLOAD_READ_TIMEOUT_S: float = float(os.getenv("IMG_DOWNLOAD_READ_TIMEOUT_S", "15"))
    # Per-image total wall cap (>= read timeout): one slow/dead URL fails here, never gates the job.
    IMG_DOWNLOAD_CAP_S: float = float(os.getenv("IMG_DOWNLOAD_CAP_S", "20"))
    # Per-job deadline (s): above a real ~40s job, below the BO client's 300s.
    PROCESSING_DEADLINE_S: float = float(os.getenv("PROCESSING_DEADLINE_S", "120"))
    # Async-submit backlog cap = MAX_CONCURRENT_JOBS * ASYNC_BACKLOG_FACTOR (per replica).
    ASYNC_BACKLOG_FACTOR: int = int(os.getenv("ASYNC_BACKLOG_FACTOR", "4"))

settings = Settings()