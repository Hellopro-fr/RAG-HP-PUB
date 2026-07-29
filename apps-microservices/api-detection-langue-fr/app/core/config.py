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
    NLP_SOFT_MIN_CONFIDENCE: float = 0.5  # Plancher du rattrapage soft-FR (cas 8b) : sous ce seuil, l'argmax `fr` ne vaut pas rattrapage
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

    # Stub-page hop : suit une fois la cible d'une page « stub » (meta-refresh
    # ou lien unique même hôte, texte visible < NLP_MIN_TEXT_LENGTH) au lieu
    # de la rejeter en fetch_empty_content. Un seul saut, jamais récursif.
    STUB_PAGE_HOP_ENABLED: bool = True

    # Redis (shared pool via common_utils.redis.cache_service — initialised in
    # main.py's lifespan; bridged to the process env there because cache_service
    # reads os.environ, not this Settings object). Pool tuning is env-only:
    # REDIS_MAX_CONNECTIONS, REDIS_SOCKET_TIMEOUT_S, REDIS_SOCKET_CONNECT_TIMEOUT_S,
    # REDIS_HEALTH_CHECK_INTERVAL_S, SERVICE_NAME (client name).
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
    # Jobs exécutés SIMULTANÉMENT (file FIFO absorbe le reste jusqu'à
    # MAX_ACTIVE_JOBS). 1 = sérialisé : chaque job dispose du pool navigateurs
    # entier au lieu de le partager avec 7 autres (tempêtes de timeouts).
    JOB_WORKER_CONCURRENCY: int = 1
    JOB_TTL_ACTIVE_S: int = 7200          # 2h — pending/running record TTL (refreshed by heartbeat)
    JOB_RESULT_TTL_S: int = 3600          # 1h — terminal record TTL (BO must poll within this)
    STALE_THRESHOLD_S: int = 120          # no heartbeat beyond this -> poll reports 'stale'
    HEARTBEAT_INTERVAL_S: int = 5         # wall-clock heartbeat tick
    ASYNC_SUBMIT_RETRY_AFTER_S: int = 15  # Retry-After on capacity 503
    ASYNC_POLL_HINT_MAX_S: int = 30       # upper bound on server poll_after_seconds hint
    SHUTDOWN_GRACE_S: int = 5             # bound on JobManager.shutdown() task drain

    # Browser-op hardening (scraper teardown/launch/op timeouts)
    TEARDOWN_TIMEOUT_S: int = 10       # bound + abandon on browser/context/page close & playwright.stop
    BROWSER_OP_TIMEOUT_S: int = 30     # context default timeout (new_page/content/route/add_cookies)
    BROWSER_LAUNCH_TIMEOUT_S: int = 45 # wrap Camoufox + Chromium launch
    JOB_MAX_S: int = 1500  # worker abandons a job exceeding this (< DETECTION_ASYNC_MAX_WAIT_S=1800 caller budget)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
