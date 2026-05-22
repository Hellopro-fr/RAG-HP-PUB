"""Tests for main.py — verifies lifespan wires the shared async Redis pool
from common_utils and exposes it on app.state for downstream consumers
(stats.prewarm_cache, router/stats global-cache helpers)."""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SERVICE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVICE_ROOT)

# Stub heavy native deps so the test doesn't need pymilvus/pyvips etc.
for _heavy in (
    "pymilvus", "uvloop",
    "app.core.api_rest_milvus",
    "common_utils.concurrency.milvus_concurrency_guard",
    "app.router.stats",
):
    sys.modules.setdefault(_heavy, MagicMock())


@pytest.mark.asyncio
async def test_lifespan_initializes_shared_redis_pool():
    """main.lifespan() must call init_redis_pool() then expose the shared
    client on app.state.redis_client so router/stats.py picks it up."""
    mock_client = AsyncMock()
    mock_init = AsyncMock()
    mock_close = AsyncMock()

    # Provide a real coroutine for prewarm_cache so asyncio.create_task accepts it
    async def _prewarm_stub(*a, **kw):
        return None
    sys.modules["app.router.stats"].prewarm_cache = _prewarm_stub

    with patch("main.init_redis_pool", mock_init), \
         patch("main.close_redis_pool", mock_close), \
         patch("main.cache_service") as mock_cs, \
         patch("main.MilvusConcurrencyGuard") as mock_guard_cls, \
         patch("main.start_metrics_server_in_thread"), \
         patch("main.get_milvus_connection"):
        mock_cs.redis_client = mock_client
        guard = MagicMock()
        guard.start_correction_loop = AsyncMock()
        mock_guard_cls.return_value = guard

        from main import lifespan, app

        async with lifespan(app):
            mock_init.assert_awaited_once()
            assert app.state.redis_client is mock_client
            # Guard should receive the shared client
            mock_guard_cls.assert_called_once()
            args = mock_guard_cls.call_args.args
            assert args[0] is mock_client

        mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_handles_shared_pool_unavailable():
    """If common_utils returns None (REDIS_URL unset), lifespan must still
    yield (service can run REST-only) and app.state.redis_client is None."""
    with patch("main.init_redis_pool", new_callable=AsyncMock), \
         patch("main.close_redis_pool", new_callable=AsyncMock), \
         patch("main.cache_service") as mock_cs, \
         patch("main.MilvusConcurrencyGuard") as mock_guard_cls, \
         patch("main.start_metrics_server_in_thread"), \
         patch("main.get_milvus_connection"):
        mock_cs.redis_client = None
        guard = MagicMock()
        guard.start_correction_loop = AsyncMock()
        mock_guard_cls.return_value = guard

        from main import lifespan, app

        async with lifespan(app):
            assert app.state.redis_client is None
