"""Tests for the Phase 4 Tier 5 migration of api-detection-langue-fr to the
shared async Redis pool from common_utils.cache_service.

Verifies:
  1. DomainCache._get_client() reads from cache_service.redis_client
     instead of opening its own aioredis.from_url client.
  2. main.lifespan() awaits init_redis_pool() at startup and
     close_redis_pool() at shutdown.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Reset cache_service.redis_client between tests."""
    from common_utils.redis import cache_service
    cache_service.redis_client = None
    yield
    cache_service.redis_client = None


@pytest.mark.asyncio
async def test_domain_cache_attaches_to_shared_pool(monkeypatch):
    """DomainCache._get_client() returns the module-global redis_client from
    cache_service, not a private aioredis client built from settings.REDIS_URL."""
    from common_utils.redis import cache_service
    from app.core.domain_fr import DomainCache

    mock_client = MagicMock()
    cache_service.redis_client = mock_client

    cache = DomainCache()
    client = await cache._get_client()
    assert client is mock_client


@pytest.mark.asyncio
async def test_domain_cache_returns_none_when_shared_pool_unavailable():
    """If common_utils.init_redis_pool failed (REDIS_URL unset), the cache
    must return None so callers degrade gracefully."""
    from common_utils.redis import cache_service
    from app.core.domain_fr import DomainCache

    cache_service.redis_client = None

    cache = DomainCache()
    client = await cache._get_client()
    assert client is None


@pytest.mark.asyncio
async def test_lifespan_initializes_and_closes_shared_pool():
    """main.lifespan() must run init_redis_pool() at startup and
    close_redis_pool() at shutdown."""
    mock_init = AsyncMock()
    mock_close = AsyncMock()

    with patch("main.init_redis_pool", mock_init), \
         patch("main.close_redis_pool", mock_close):
        from main import lifespan, app

        async with lifespan(app):
            mock_init.assert_awaited_once()
            mock_close.assert_not_awaited()

        mock_close.assert_awaited_once()
