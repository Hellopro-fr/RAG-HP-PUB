"""Tests for crawler_manager.start_crawl capacity short-circuit + Redis retry.

Spec: docs/superpowers/specs/2026-05-22-start-crawl-capacity-short-circuit-design.md
"""
import asyncio
import pytest
from unittest.mock import AsyncMock
from redis.exceptions import ConnectionError as RedisConnectionError


@pytest.mark.asyncio
async def test_with_retry_succeeds_after_one_retry():
    """Retries once on transient ConnectionError, then succeeds."""
    from app.core import crawler_manager

    call_count = {"n": 0}

    async def flaky():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RedisConnectionError("transient")
        return "ok"

    result = await crawler_manager._with_retry(flaky)
    assert result == "ok"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_with_retry_exhausts_and_raises():
    """Exhausts all attempts (1 initial + 2 retries = 3) and re-raises."""
    from app.core import crawler_manager

    call_count = {"n": 0}

    async def always_fail():
        call_count["n"] += 1
        raise RedisConnectionError("permanent")

    with pytest.raises(RedisConnectionError, match="permanent"):
        await crawler_manager._with_retry(always_fail)
    # Default: _REDIS_RETRY_ATTEMPTS = 2 → 1 initial + 2 retries = 3 total.
    assert call_count["n"] == 3


# ─── Integration tests for start_crawl reorder ─────────────────────────────────

@pytest.fixture
def manager_with_mocks(monkeypatch):
    """Construct a CrawlerManager with cache_service fully mocked.

    Returns (manager, redis_mock, cache_mocks) where cache_mocks is a dict
    of every cache_service.* method we touch in start_crawl.
    """
    import os as _os
    from collections import namedtuple
    from app.core import crawler_manager
    from app.core.crawler_manager import CrawlerManager

    # `os.uname()` is POSIX-only — stub it so tests run on Windows too.
    # start_crawl builds job_data["replica_id"] = os.uname().nodename.
    _UnameStub = namedtuple("uname_result", ["sysname", "nodename", "release", "version", "machine"])
    monkeypatch.setattr(
        _os,
        "uname",
        lambda: _UnameStub("Linux", "test-replica", "5.0", "#1", "x86_64"),
        raising=False,
    )

    # Mock every cache_service.* function start_crawl uses.
    cache_mocks = {
        "get_key": AsyncMock(),
        "set_json": AsyncMock(),
        "increment_key": AsyncMock(),
        "safe_decrement_key": AsyncMock(),
        "delete_key": AsyncMock(),
    }
    for name, mock in cache_mocks.items():
        monkeypatch.setattr(crawler_manager.cache_service, name, mock)

    # Mock the SET NX lock_key call (cache_service.redis_client.set).
    redis_mock = AsyncMock()
    redis_mock.set = AsyncMock(return_value=True)  # Lock acquired by default.
    monkeypatch.setattr(crawler_manager.cache_service, "redis_client", redis_mock)

    manager = CrawlerManager()
    manager.local_processes = {}
    return manager, redis_mock, cache_mocks


@pytest.mark.asyncio
async def test_replica_saturated_returns_503_with_zero_redis_ops(manager_with_mocks):
    """Replica at MAX_CONCURRENT_CRAWLS: 503 with Retry-After=5, NO Redis calls."""
    from fastapi import HTTPException
    from app.core import crawler_manager
    from app.core.config import settings

    manager, redis_mock, cache_mocks = manager_with_mocks

    # Saturate local_processes with MAX_CONCURRENT_CRAWLS fake live subprocesses.
    class FakeProc:
        returncode = None  # alive
    for i in range(settings.MAX_CONCURRENT_CRAWLS):
        manager.local_processes[f"existing-{i}"] = FakeProc()

    with pytest.raises(HTTPException) as exc_info:
        await manager.start_crawl(
            crawl_id="6397",
            domain="atosafr.fr",
            start_url="https://atosafr.fr/",
            callback_url="https://example.com/cb",
            failure_callback_url=None,
            params={},
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers.get("Retry-After") == str(crawler_manager.REPLICA_CAP_RETRY_AFTER_S)
    assert exc_info.value.detail["error_code"] == "REPLICA_CAPACITY_EXCEEDED"

    # No Redis op should have been invoked.
    redis_mock.set.assert_not_called()
    for name, mock in cache_mocks.items():
        assert mock.call_count == 0, f"cache_service.{name} should not have been called"


@pytest.mark.asyncio
async def test_global_saturated_returns_503_with_only_read_probe(manager_with_mocks):
    """Global READ probe shows full: 503 with Retry-After=15, only 2 get_key calls."""
    from fastapi import HTTPException
    from app.core import crawler_manager

    manager, redis_mock, cache_mocks = manager_with_mocks

    # local_processes empty (replica has room).
    # Probe returns: max=10, running=10.
    cache_mocks["get_key"].side_effect = [
        "10",  # CRAWL_MAX_GLOBAL_KEY
        "10",  # CRAWL_RUNNING_COUNT_KEY
    ]

    with pytest.raises(HTTPException) as exc_info:
        await manager.start_crawl(
            crawl_id="6397",
            domain="atosafr.fr",
            start_url="https://atosafr.fr/",
            callback_url="https://example.com/cb",
            failure_callback_url=None,
            params={},
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers.get("Retry-After") == str(crawler_manager.GLOBAL_CAP_RETRY_AFTER_S)
    assert exc_info.value.detail["error_code"] == "GLOBAL_CAPACITY_EXCEEDED"

    # Only 2 get_key probes happened. No SET NX, no set_json, no INCR, no rollback.
    assert cache_mocks["get_key"].call_count == 2
    redis_mock.set.assert_not_called()
    assert cache_mocks["set_json"].call_count == 0
    assert cache_mocks["increment_key"].call_count == 0
    assert cache_mocks["safe_decrement_key"].call_count == 0
    assert cache_mocks["delete_key"].call_count == 0


@pytest.mark.asyncio
async def test_race_overshoot_rolls_back(manager_with_mocks, monkeypatch, tmp_path):
    """Probe sees room, but INCR overshoots — race-safe rollback fires."""
    from fastapi import HTTPException
    from app.core.config import settings

    manager, redis_mock, cache_mocks = manager_with_mocks

    # Stub storage path to a tmp dir so makedirs doesn't fail.
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path))

    # local_processes empty; probe says room available, but INCR overshoots.
    cache_mocks["get_key"].side_effect = [
        "10",  # CRAWL_MAX_GLOBAL_KEY
        "9",   # CRAWL_RUNNING_COUNT_KEY (probe sees 9/10 → ok to proceed)
    ]
    cache_mocks["increment_key"].return_value = 11  # race: other replica filled the slot

    with pytest.raises(HTTPException) as exc_info:
        await manager.start_crawl(
            crawl_id="6397",
            domain="atosafr.fr",
            start_url="https://atosafr.fr/",
            callback_url="https://example.com/cb",
            failure_callback_url=None,
            params={},
        )

    assert exc_info.value.status_code == 503
    # Lock SET NX, state set_json, INCR all fired.
    redis_mock.set.assert_called_once()
    assert cache_mocks["set_json"].call_count == 1
    assert cache_mocks["increment_key"].call_count == 1
    # Race-safe rollback: decrement counter + delete lock + delete state.
    assert cache_mocks["safe_decrement_key"].call_count == 1
    assert cache_mocks["delete_key"].call_count == 2  # lock_key + job_key
