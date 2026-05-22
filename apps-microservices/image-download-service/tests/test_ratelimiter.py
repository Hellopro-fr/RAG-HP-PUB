"""Tests for app/core/ratelimiter.py — RateLimiter attaches to the shared
sync Redis pool from common_utils.cache_service_sync."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

SERVICE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVICE_ROOT + "/..")


@pytest.fixture
def mock_shared_pool():
    """Patch common_utils.cache_service_sync init + get so RateLimiter
    wiring is exercised without a real Redis."""
    with patch("app.core.ratelimiter.init_redis_pool_sync") as mock_init, \
         patch("app.core.ratelimiter.get_client") as mock_get:
        client = MagicMock()
        mock_init.return_value = client
        mock_get.return_value = client
        yield {"init": mock_init, "get": mock_get, "client": client}


def test_attaches_to_shared_pool(mock_shared_pool):
    from app.core.ratelimiter import RateLimiter
    limiter = RateLimiter()
    assert limiter.redis is mock_shared_pool["client"]
    mock_shared_pool["init"].assert_called_once()


def test_acquire_fails_open_when_pool_unavailable():
    """When common_utils returns None (REDIS_URL unset), RateLimiter
    fails open (returns True) so downloads are not blocked."""
    with patch("app.core.ratelimiter.init_redis_pool_sync", return_value=None), \
         patch("app.core.ratelimiter.get_client", return_value=None):
        from app.core.ratelimiter import RateLimiter
        limiter = RateLimiter()
        assert limiter.redis is None
        assert limiter.acquire("example.com") is True


def test_acquire_allows_under_rate_limit(mock_shared_pool):
    from app.core.ratelimiter import RateLimiter
    limiter = RateLimiter()
    # Current count below threshold (None means key not set yet)
    mock_shared_pool["client"].get.return_value = None
    pipe = MagicMock()
    mock_shared_pool["client"].pipeline.return_value = pipe

    assert limiter.acquire("example.com") is True
    pipe.incr.assert_called_once()
    pipe.expire.assert_called_once()
    pipe.execute.assert_called_once()


def test_acquire_fails_open_on_redis_exception(mock_shared_pool):
    from app.core.ratelimiter import RateLimiter
    limiter = RateLimiter()
    mock_shared_pool["client"].get.side_effect = RuntimeError("boom")
    assert limiter.acquire("example.com") is True


def test_close_is_noop_when_pool_unavailable():
    """close() must not error when the limiter never acquired a client."""
    with patch("app.core.ratelimiter.init_redis_pool_sync", return_value=None), \
         patch("app.core.ratelimiter.get_client", return_value=None):
        from app.core.ratelimiter import RateLimiter
        limiter = RateLimiter()
        # Should not raise
        limiter.close()
