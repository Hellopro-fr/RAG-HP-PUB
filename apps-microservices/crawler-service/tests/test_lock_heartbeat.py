"""Unit tests for _LockHeartbeat helper.

The helper renews a Redis lock TTL via Lua compare-and-set every
LOCK_HEARTBEAT_INTERVAL_SECONDS while a long-running operation holds the lock.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from app.core.crawler_manager import _LockHeartbeat


@pytest.fixture
def cm_stub():
    """Minimal CrawlerManager stub (heartbeat only needs cache_service.redis_client)."""
    return object()


@pytest.mark.asyncio
async def test_heartbeat_renews_ttl_via_lua_cas(cm_stub):
    """Happy path: at least 2 renewals over 2.5 s with interval = 1 s, Lua returns 1."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=1)
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        async with _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=10,
        ):
            await asyncio.sleep(2.5)
    assert fake_redis.eval.await_count >= 2
    args = fake_redis.eval.await_args_list[0].args
    assert "redis.call('get'" in args[0]
    assert args[1] == 1
    assert args[2] == "lk:1"
    assert args[3] == "rid:abc"
    assert args[4] == "10"


@pytest.mark.asyncio
async def test_heartbeat_stops_on_value_mismatch(cm_stub):
    """When Lua returns 0 (value mismatch, lock taken over), heartbeat stops."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(side_effect=[1, 0])
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        async with _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=10,
        ):
            await asyncio.sleep(3.5)
    assert fake_redis.eval.await_count == 2


@pytest.mark.asyncio
async def test_heartbeat_stops_at_max_duration(cm_stub):
    """When max_duration elapsed, heartbeat stops renewing."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=1)
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        async with _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=2,
        ):
            await asyncio.sleep(4.0)
    assert fake_redis.eval.await_count <= 3


@pytest.mark.asyncio
async def test_heartbeat_tolerates_transient_redis_error(cm_stub):
    """Redis exception during refresh logs WARNING + continues the loop."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(side_effect=[ConnectionError("boom"), 1, 1])
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        async with _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=10,
        ):
            await asyncio.sleep(3.5)
    assert fake_redis.eval.await_count >= 3


@pytest.mark.asyncio
async def test_heartbeat_cancels_cleanly_on_exit(cm_stub):
    """__aexit__ cancels the heartbeat task and awaits its cancellation."""
    fake_redis = AsyncMock()
    fake_redis.eval = AsyncMock(return_value=1)
    with patch("app.core.crawler_manager.cache_service") as mock_cs:
        mock_cs.redis_client = fake_redis
        hb = _LockHeartbeat(
            cm_stub, "lk:1", "rid:abc",
            ttl_seconds=10, interval_seconds=1, max_duration_seconds=10,
        )
        async with hb:
            await asyncio.sleep(0.1)
        assert hb._task.done() or hb._task.cancelled()
