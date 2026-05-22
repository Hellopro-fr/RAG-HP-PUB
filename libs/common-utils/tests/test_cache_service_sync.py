"""Tests for common_utils.redis.cache_service_sync.init_redis_pool_sync config.

Mirrors test_cache_service.py — same assertions adapted for the sync binding.
"""
import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Reset Redis env vars to known defaults so tests are hermetic."""
    for var in (
        "REDIS_URL",
        "REDIS_MAX_CONNECTIONS",
        "REDIS_SOCKET_TIMEOUT_S",
        "REDIS_SOCKET_CONNECT_TIMEOUT_S",
        "REDIS_HEALTH_CHECK_INTERVAL_S",
        "HOSTNAME",
        "SERVICE_NAME",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://:secret@10.0.0.1:6379")
    monkeypatch.setenv("HOSTNAME", "qdrant-svc-test")


@pytest.fixture
def reset_cache_service_sync():
    """Reset the module-level global so each test starts clean."""
    from common_utils.redis import cache_service_sync
    cache_service_sync.redis_client = None
    yield cache_service_sync
    cache_service_sync.redis_client = None


def test_init_uses_bounded_pool_defaults(reset_cache_service_sync):
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=mock_client) as from_url:
        reset_cache_service_sync.init_redis_pool_sync()

    assert from_url.call_count == 1
    _, kwargs = from_url.call_args
    assert kwargs["max_connections"] == 20
    assert kwargs["socket_keepalive"] is True
    assert kwargs["socket_connect_timeout"] == 5
    assert kwargs["socket_timeout"] == 10
    assert kwargs["health_check_interval"] == 30


def test_init_reads_env_overrides(reset_cache_service_sync, monkeypatch):
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "5")
    monkeypatch.setenv("REDIS_SOCKET_TIMEOUT_S", "7")
    monkeypatch.setenv("REDIS_SOCKET_CONNECT_TIMEOUT_S", "3")
    monkeypatch.setenv("REDIS_HEALTH_CHECK_INTERVAL_S", "15")
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=mock_client) as from_url:
        reset_cache_service_sync.init_redis_pool_sync()

    _, kwargs = from_url.call_args
    assert kwargs["max_connections"] == 5
    assert kwargs["socket_timeout"] == 7
    assert kwargs["socket_connect_timeout"] == 3
    assert kwargs["health_check_interval"] == 15


def test_init_clamps_zero_to_one(reset_cache_service_sync, monkeypatch):
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "0")
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=mock_client) as from_url:
        reset_cache_service_sync.init_redis_pool_sync()

    _, kwargs = from_url.call_args
    assert kwargs["max_connections"] == 1


def test_ping_safe_returns_false_on_exception(reset_cache_service_sync):
    bad_client = MagicMock()
    bad_client.ping = MagicMock(side_effect=RuntimeError("boom"))
    result = reset_cache_service_sync._ping_safe(bad_client)
    assert result is False


def test_init_skips_when_existing_client_pings_ok(reset_cache_service_sync):
    live = MagicMock()
    live.ping = MagicMock(return_value=True)
    reset_cache_service_sync.redis_client = live

    with patch("redis.from_url") as from_url:
        result = reset_cache_service_sync.init_redis_pool_sync()

    from_url.assert_not_called()
    assert result is live
    assert reset_cache_service_sync.redis_client is live


def test_init_rebuilds_when_existing_client_ping_fails(reset_cache_service_sync):
    dead = MagicMock()
    dead.ping = MagicMock(side_effect=RuntimeError("conn refused"))
    reset_cache_service_sync.redis_client = dead

    new_client = MagicMock()
    new_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=new_client) as from_url:
        result = reset_cache_service_sync.init_redis_pool_sync()

    assert from_url.call_count == 1
    assert result is new_client
    assert reset_cache_service_sync.redis_client is new_client


def test_init_returns_none_when_redis_url_missing(reset_cache_service_sync, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    with patch("redis.from_url") as from_url:
        result = reset_cache_service_sync.init_redis_pool_sync()
    from_url.assert_not_called()
    assert result is None
    assert reset_cache_service_sync.redis_client is None


def test_client_name_includes_service_hostname_pid(reset_cache_service_sync, monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "di-database-qdrant-service")
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=mock_client) as from_url:
        reset_cache_service_sync.init_redis_pool_sync()

    _, kwargs = from_url.call_args
    expected = f"di-database-qdrant-service-qdrant-svc-test-pid{os.getpid()}"
    assert kwargs["client_name"] == expected


def test_client_name_warns_when_service_unset(reset_cache_service_sync, monkeypatch, caplog):
    import logging
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with caplog.at_level(logging.WARNING, logger="common_utils.redis.cache_service_sync"):
        with patch("redis.from_url", return_value=mock_client) as from_url:
            reset_cache_service_sync.init_redis_pool_sync()

    _, kwargs = from_url.call_args
    expected = f"unset-service-qdrant-svc-test-pid{os.getpid()}"
    assert kwargs["client_name"] == expected
    assert "SERVICE_NAME env var unset" in caplog.text


def test_client_name_falls_back_to_no_hostname(reset_cache_service_sync, monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "image-download-service")
    monkeypatch.delenv("HOSTNAME", raising=False)
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=mock_client) as from_url:
        reset_cache_service_sync.init_redis_pool_sync()

    _, kwargs = from_url.call_args
    expected = f"image-download-service-no-hostname-pid{os.getpid()}"
    assert kwargs["client_name"] == expected


def test_client_name_strips_whitespace_from_service_name(reset_cache_service_sync, monkeypatch):
    """Redis CLIENT SETNAME rejects spaces — strip surrounding whitespace."""
    monkeypatch.setenv("SERVICE_NAME", "  website-processor-service  ")
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=mock_client) as from_url:
        reset_cache_service_sync.init_redis_pool_sync()

    _, kwargs = from_url.call_args
    expected = f"website-processor-service-qdrant-svc-test-pid{os.getpid()}"
    assert kwargs["client_name"] == expected


def test_client_name_empty_service_name_falls_back(reset_cache_service_sync, monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "")
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=mock_client) as from_url:
        reset_cache_service_sync.init_redis_pool_sync()

    _, kwargs = from_url.call_args
    expected = f"unset-service-qdrant-svc-test-pid{os.getpid()}"
    assert kwargs["client_name"] == expected


def test_get_client_returns_module_global(reset_cache_service_sync):
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=mock_client):
        reset_cache_service_sync.init_redis_pool_sync()

    assert reset_cache_service_sync.get_client() is mock_client


def test_get_client_returns_none_when_uninitialized(reset_cache_service_sync):
    assert reset_cache_service_sync.get_client() is None


def test_close_clears_module_global(reset_cache_service_sync):
    mock_client = MagicMock()
    mock_client.ping = MagicMock(return_value=True)

    with patch("redis.from_url", return_value=mock_client):
        reset_cache_service_sync.init_redis_pool_sync()

    assert reset_cache_service_sync.redis_client is mock_client
    reset_cache_service_sync.close_redis_pool_sync()
    assert reset_cache_service_sync.redis_client is None
    mock_client.close.assert_called_once()


def test_close_is_idempotent(reset_cache_service_sync):
    # No-op when no client; must not raise.
    reset_cache_service_sync.close_redis_pool_sync()
    assert reset_cache_service_sync.redis_client is None


def test_init_handles_connection_error(reset_cache_service_sync):
    import redis as sync_redis
    mock_client = MagicMock()
    mock_client.ping = MagicMock(side_effect=sync_redis.ConnectionError("refused"))

    with patch("redis.from_url", return_value=mock_client):
        result = reset_cache_service_sync.init_redis_pool_sync()

    assert result is None
    assert reset_cache_service_sync.redis_client is None
    mock_client.close.assert_called_once()
