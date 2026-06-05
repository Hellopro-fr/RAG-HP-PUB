import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Configuration de l'application"""
    
    # Server
    APP_NAME: str = "API Détection Langue Française"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # HTTP Client
    HTTP_TIMEOUT: int = 30  # secondes
    HTTP_MAX_RETRIES: int = 3
    HTTP_RETRY_DELAY: float = 1.0  # secondes
    
    # NLP Detection
    NLP_MIN_CONFIDENCE: float = 0.75  # Réduit de 0.85 pour accepter le FR avec termes techniques EN
    NLP_MIN_TEXT_LENGTH: int = 100  # Réduit de 200 pour accepter les pages minimalistes
    
    # Batch Processing
    BATCH_MAX_URLS: int = 100
    BATCH_DEFAULT_CONCURRENCY: int = 10
    BATCH_MAX_CONCURRENCY: int = 50
    
    # Browser
    CAMOUFOX_ENABLED: bool = True  # Use Camoufox (stealth Firefox). False = Playwright Chromium fallback.

    # Invalid page rejection (4XX/5XX, soft-404, redirect-to-home)
    INVALID_PAGE_DETECTION_ENABLED: bool = True
    HOMEPAGE_FALLBACK_ENABLED: bool = True
    SOFT_404_TITLE_THIN_THRESHOLD: int = 2000   # Visible-text char limit when title regex matches
    SOFT_404_H1_THIN_THRESHOLD: int = 1500      # Visible-text char limit when H1 regex matches
    INVALID_PAGE_TTL_HARD_S: int = 604800       # 7 days — http_error + redirected_to_home
    INVALID_PAGE_TTL_SOFT_S: int = 21600        # 6 hours — soft_404 (heuristic, give site time to fix)

    # Redis cache
    REDIS_URL: Optional[str] = None

    # Proxy (optionnel)
    # APIFY_PROXY env var contains the password, not the full URL
    DEFAULT_PROXY_URL: Optional[str] = None
    APIFY_PROXY: Optional[str] = None

    def model_post_init(self, __context) -> None:
        # APIFY_PROXY env var is the password — build the full proxy URL
        apify_value = self.APIFY_PROXY
        if apify_value and not apify_value.startswith('http'):
            object.__setattr__(
                self, 'APIFY_PROXY',
                f"http://auto:{apify_value}@proxy.apify.com:8000"
            )
    
    # Pemavor API (fallback pour redirections)
    PEMAVOR_API_URL: str = "https://europe-west1-pemavor-free-tools.cloudfunctions.net/HttpStatusCodeChecker"
    PEMAVOR_API_KEY: Optional[str] = None
    
    # User-Agent
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    
    # Async job API (POST /detect-batch-async + GET poll)
    ASYNC_JOBS_ENABLED: bool = True
    MAX_ACTIVE_JOBS: int = 8
    JOB_TTL_ACTIVE_S: int = 7200          # 2h — pending/running record TTL (refreshed by heartbeat)
    JOB_RESULT_TTL_S: int = 3600          # 1h — terminal record TTL (BO must poll within this)
    STALE_THRESHOLD_S: int = 120          # no heartbeat beyond this -> poll reports 'stale'
    HEARTBEAT_INTERVAL_S: int = 5         # wall-clock heartbeat tick
    ASYNC_SUBMIT_RETRY_AFTER_S: int = 15  # Retry-After on capacity 503
    ASYNC_POLL_HINT_MAX_S: int = 30       # upper bound on server poll_after_seconds hint
    SHUTDOWN_GRACE_S: int = 5             # bound on JobManager.shutdown() task drain

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
