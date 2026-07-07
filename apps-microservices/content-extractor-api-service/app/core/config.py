from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Content Extractor API"
    APP_VERSION: str = "1.0.0"
    PORT: int = 8600
    LOG_LEVEL: str = "info"
    MAX_PAYLOAD_SIZE_MB: int = 10

    # --- Axis 1: workers (GIL -> processes give CPU parallelism, not threads) ---
    UVICORN_WORKERS: int = 2

    # --- Redis (job store + result cache). cache_service.init_redis_pool() reads
    # REDIS_URL from the environment itself; this mirrors it for documentation. ---
    REDIS_URL: str = "redis://redis:6379"

    # --- Result cache ---
    RESULT_CACHE_ENABLED: bool = True
    RESULT_CACHE_TTL_S: int = 86400          # 24h (HTML drifts; crawler re-crawls)
    RESULT_CACHE_VERSION: str = "v1"         # bump on extractor/boilerpy3 algo change

    # --- Sync admission (0 = disabled, always admit) ---
    SYNC_MAX_INFLIGHT: int = 0

    # --- Async job API ---
    ASYNC_JOBS_ENABLED: bool = True
    MAX_ACTIVE_JOBS: int = 8                 # per-worker in-flight async jobs
    DEFAULT_MAX_CONCURRENCY: int = 4         # per-job item concurrency (NEW; CPU-bound)
    JOB_TTL_ACTIVE_S: int = 7200
    JOB_RESULT_TTL_S: int = 3600
    STALE_THRESHOLD_S: int = 120
    HEARTBEAT_INTERVAL_S: int = 5
    ASYNC_SUBMIT_RETRY_AFTER_S: int = 15
    ASYNC_POLL_HINT_MAX_S: int = 30
    SHUTDOWN_GRACE_S: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
