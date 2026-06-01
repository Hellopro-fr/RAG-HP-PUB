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

    # GCS download daemon paths (must match docker-compose.yml bind target for the
    # crawler-service container; daemon reads the same env var names on the host)
    DOWNLOAD_REQUESTS_PATH: str = "/app/download_requests"
    DOWNLOAD_RESULTS_PATH: str = "/app/download_results"

    # Stash flow paths (mirror download paths; bind targets must match docker-compose.yaml)
    STASH_SHARED_PATH: str = "/app/stash"
    STASH_DOWNLOAD_REQUESTS_PATH: str = "/app/gcs-stash-requests"
    STASH_DOWNLOAD_RESULTS_PATH: str = "/app/gcs-stash-downloads"

    # Stash->archive move flow (spec 2026-06-01 P3). Service writes .move-request;
    # the move-flow daemon does `gcloud storage mv stash/{id} crawls/{id}`.
    # Prefix names match the daemon's env vars (download_daemon.sh) so a single
    # .env entry configures both layers; the daemon is the actual consumer.
    MOVE_REQUESTS_PATH: str = "/app/gcs-move-requests"
    MOVE_RESULTS_PATH: str = "/app/gcs-move-results"
    MOVE_SOURCE_PREFIX: str = "stash"
    MOVE_TARGET_PREFIX: str = "crawls"
    MOVE_TIMEOUT_SECONDS: int = 120

    # Stash flow Redis lock TTLs and timeouts (seconds).
    # STASH_LOCK_TTL is bumped to 1800s (was 600s) so it exceeds nginx
    # proxy_read_timeout (600s on /crawler/ default location) and survives
    # any single nginx retry window; the heartbeat below renews TTL
    # mid-operation to handle larger crawls.
    STASH_LOCK_TTL_SECONDS: int = 1800
    UNSTASH_LOCK_TTL_SECONDS: int = 600
    UNSTASH_TIMEOUT_SECONDS: int = 300
    UNSTASH_CLEANUP_GRACE_SECONDS: int = 30

    # Archive flow Redis lock TTL (seconds). Previously hardcoded in
    # crawler_manager.archive_crawl; surfaced here for parity with stash
    # and for tunability.
    ARCHIVE_LOCK_TTL_SECONDS: int = 1800

    # Long-running lock heartbeat (used by stash + archive).
    # INTERVAL = TTL / 6 → up to 5 missed renewals before TTL expires
    # (defense against transient Redis latency).
    # MAX_DURATION = 4h hard cap; past this, heartbeat stops renewing so
    # a truly hung op cannot indefinitely hold the lock.
    LOCK_HEARTBEAT_INTERVAL_SECONDS: int = 300
    LOCK_HEARTBEAT_MAX_DURATION_SECONDS: int = 14400

    # GCS download timeout in seconds
    GCS_DOWNLOAD_TIMEOUT_SECONDS: int = 300

    # API authentication
    API_KEY: Optional[str] = None

    # Stale job detection thresholds (seconds)
    STALE_JOB_THRESHOLD_LOCAL: int = 180   # Local jobs: PID check + 3 min heartbeat gap
    STALE_JOB_THRESHOLD_REMOTE: int = 600  # Remote jobs: 10 min grace period for owning replica

    # Node-side monitor thresholds (informational; actual values passed via env to crawler subprocess)
    REDIS_LOSS_THRESHOLD_MS: int = 60_000
    PROGRESS_STALL_THRESHOLD_MS: int = 600_000

    # --- Auto-stash workflow (spec 2026-06-01) ---
    # Master gate for the auto-stash reconcile sweep (P2). Off by default.
    AUTO_STASH_ENABLED: bool = False
    # After a /results download, wait this long before stashing (happy path).
    STASH_GRACE_SECONDS: int = 3600
    # Stash a never-downloaded terminal crawl after this long (also the
    # investigation window for failed crawls).
    STASH_SAFETY_TIMEOUT_SECONDS: int = 172800
    # Disk-pressure override: at/above this used-% the sweep stashes the
    # largest terminal crawls early, regardless of grace.
    STASH_DISK_HIGH_WATER_PCT: int = 85
    # Cap on crawls stashed per sweep tick (bounds upload-daemon load).
    STASH_MAX_PER_SWEEP: int = 5

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
    }


settings = Settings()
