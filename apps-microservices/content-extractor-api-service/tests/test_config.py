from app.core.config import settings


def test_existing_defaults_unchanged():
    assert settings.PORT == 8600
    assert settings.MAX_PAYLOAD_SIZE_MB == 10


def test_new_defaults():
    assert settings.UVICORN_WORKERS == 2
    assert settings.REDIS_URL.startswith("redis://")
    assert settings.RESULT_CACHE_ENABLED is True
    assert settings.RESULT_CACHE_TTL_S == 86400
    assert settings.RESULT_CACHE_VERSION == "v1"
    assert settings.SYNC_MAX_INFLIGHT == 0
    assert settings.ASYNC_JOBS_ENABLED is True
    assert settings.MAX_ACTIVE_JOBS == 8
    assert settings.DEFAULT_MAX_CONCURRENCY == 4
    assert settings.JOB_TTL_ACTIVE_S == 7200
    assert settings.JOB_RESULT_TTL_S == 3600
    assert settings.STALE_THRESHOLD_S == 120
    assert settings.HEARTBEAT_INTERVAL_S == 5
    assert settings.ASYNC_SUBMIT_RETRY_AFTER_S == 15
    assert settings.ASYNC_POLL_HINT_MAX_S == 30
    assert settings.SHUTDOWN_GRACE_S == 5
