"""Tests for app/core/redis_manager.py — RedisManager attaches to the shared
sync Redis pool from common_utils.cache_service_sync and re-registers its
Lua batch script."""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Make the service package importable as it is in container (PYTHONPATH=/app,
# module name = website_processor_service).
SERVICE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, SERVICE_ROOT + "/..")  # parent so `website_processor_service` resolves


@pytest.fixture
def mock_shared_pool():
    """Patch common_utils.cache_service_sync.init_redis_pool_sync + get_client
    so the test exercises RedisManager's wiring without a real Redis."""
    with patch("app.core.redis_manager.init_redis_pool_sync") as mock_init, \
         patch("app.core.redis_manager.get_client") as mock_get:
        client = MagicMock()
        client.register_script = MagicMock(return_value=MagicMock())
        mock_init.return_value = client
        mock_get.return_value = client
        yield {"init": mock_init, "get": mock_get, "client": client}


def test_attaches_to_shared_pool(mock_shared_pool):
    from app.core.redis_manager import RedisManager
    mgr = RedisManager()
    assert mgr.client is mock_shared_pool["client"]
    mock_shared_pool["init"].assert_called_once()


def test_registers_lua_batch_script(mock_shared_pool):
    from app.core.redis_manager import RedisManager
    mgr = RedisManager()
    mock_shared_pool["client"].register_script.assert_called_once_with(
        RedisManager.LUA_BATCH_SCRIPT
    )
    assert mgr.batch_script is not None


def test_handles_pool_unavailable():
    """If common_utils returns None (REDIS_URL unset / Redis down),
    RedisManager keeps client=None and skips script registration."""
    with patch("app.core.redis_manager.init_redis_pool_sync", return_value=None), \
         patch("app.core.redis_manager.get_client", return_value=None):
        from app.core.redis_manager import RedisManager
        mgr = RedisManager()
        assert mgr.client is None
        assert mgr.batch_script is None


def test_handles_script_registration_failure(mock_shared_pool):
    mock_shared_pool["client"].register_script.side_effect = RuntimeError("script err")
    from app.core.redis_manager import RedisManager
    mgr = RedisManager()
    assert mgr.client is None
    assert mgr.batch_script is None


def test_buffer_returns_none_when_client_unavailable():
    with patch("app.core.redis_manager.init_redis_pool_sync", return_value=None), \
         patch("app.core.redis_manager.get_client", return_value=None):
        from app.core.redis_manager import RedisManager
        mgr = RedisManager()
        result = mgr.buffer_and_check_batch("example.com", "header", '{"k":"v"}')
        assert result is None


def test_buffer_executes_lua_script(mock_shared_pool):
    from app.core.redis_manager import RedisManager
    mgr = RedisManager()
    mgr.batch_script.return_value = ["a", "b", "c"]
    result = mgr.buffer_and_check_batch("example.com", "footer", '{"k":"v"}', threshold=3, ttl_seconds=60)
    assert result == ["a", "b", "c"]
    mgr.batch_script.assert_called_once()


def test_buffer_returns_none_on_redis_error(mock_shared_pool):
    import redis
    from app.core.redis_manager import RedisManager
    mgr = RedisManager()
    mgr.batch_script.side_effect = redis.RedisError("boom")
    result = mgr.buffer_and_check_batch("example.com", "header", '{"k":"v"}')
    assert result is None
