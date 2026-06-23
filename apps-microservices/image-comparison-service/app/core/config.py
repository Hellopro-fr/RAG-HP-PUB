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
    # TTL for NON-terminal status keys ('processing'). Derived to stay > PROCESSING_DEADLINE_S:
    # a live job refreshes its status TTL on every write (inter-write gaps <= the deadline), so a
    # real in-flight job never expires mid-flight, while an orphaned 'processing' (worker restarted
    # or killed mid-job — nothing flips it terminal) self-heals in ~minutes instead of lingering the
    # full JOB_RESULT_TTL (24h). On expiry: /status & /results -> 404 -> BO poll treats it as
    # terminal -> keep-all (no false dedup). Grace tunable via STALE_STATUS_GRACE_S.
    PROCESSING_STATUS_TTL_S: int = int(PROCESSING_DEADLINE_S) + int(os.getenv("STALE_STATUS_GRACE_S", "60"))
    # Async-submit backlog cap = MAX_CONCURRENT_JOBS * ASYNC_BACKLOG_FACTOR (per replica).
    ASYNC_BACKLOG_FACTOR: int = int(os.getenv("ASYNC_BACKLOG_FACTOR", "4"))

    # --- Per-URL feature cache (Design C) ---
    # Cache-aside store of the extracted feature {phash, hist} keyed by image URL, on the
    # shared Redis. A hit skips download+decode+extract. Eviction is safe (miss -> recompute);
    # TTL is the SOLE staleness guardrail against a URL whose bytes change in place.
    FEATURE_CACHE_ENABLED: bool = os.getenv("FEATURE_CACHE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    # 7 days. Bounds the wrongful-exclusion window; expires before a weeks-later algo re-run.
    FEATURE_CACHE_TTL_S: int = int(os.getenv("FEATURE_CACHE_TTL_S", "604800"))
    # Algorithm version tag in the cache key. Bump when trim_borders / extract_features change
    # so old (incompatible) cached features are ignored rather than mixed in.
    FEATURE_CACHE_VERSION: str = os.getenv("FEATURE_CACHE_VERSION", "v1")

settings = Settings()