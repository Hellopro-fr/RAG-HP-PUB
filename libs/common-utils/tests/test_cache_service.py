"""Tests for common_utils.redis.cache_service.init_redis_pool config."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
    monkeypatch.setenv("HOSTNAME", "crawler-service-test")


@pytest.fixture
def reset_cache_service():
    """Reset the module-level global so each test starts clean."""
    from common_utils.redis import cache_service
    cache_service.redis_client = None
    yield cache_service
    cache_service.redis_client = None


@pytest.mark.asyncio
async def test_init_uses_bounded_pool_defaults(reset_cache_service):
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    assert from_url.call_count == 1
    _, kwargs = from_url.call_args
    assert kwargs["max_connections"] == 20
    assert kwargs["socket_keepalive"] is True
    assert kwargs["socket_connect_timeout"] == 5
    assert kwargs["socket_timeout"] == 10
    assert kwargs["health_check_interval"] == 30
    assert kwargs["client_name"] == "crawler-py-crawler-service-test"


@pytest.mark.asyncio
async def test_init_reads_env_overrides(reset_cache_service, monkeypatch):
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "5")
    monkeypatch.setenv("REDIS_SOCKET_TIMEOUT_S", "7")
    monkeypatch.setenv("REDIS_SOCKET_CONNECT_TIMEOUT_S", "3")
    monkeypatch.setenv("REDIS_HEALTH_CHECK_INTERVAL_S", "15")
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["max_connections"] == 5
    assert kwargs["socket_timeout"] == 7
    assert kwargs["socket_connect_timeout"] == 3
    assert kwargs["health_check_interval"] == 15


@pytest.mark.asyncio
async def test_init_clamps_zero_to_one(reset_cache_service, monkeypatch):
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "0")
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["max_connections"] == 1


@pytest.mark.asyncio
async def test_ping_safe_returns_false_on_exception(reset_cache_service):
    bad_client = AsyncMock()
    bad_client.ping = AsyncMock(side_effect=RuntimeError("boom"))
    result = await reset_cache_service._ping_safe(bad_client)
    assert result is False


@pytest.mark.asyncio
async def test_init_skips_when_existing_client_pings_ok(reset_cache_service):
    live = AsyncMock()
    live.ping = AsyncMock(return_value=True)
    reset_cache_service.redis_client = live

    with patch("redis.asyncio.from_url") as from_url:
        await reset_cache_service.init_redis_pool()

    from_url.assert_not_called()
    assert reset_cache_service.redis_client is live


@pytest.mark.asyncio
async def test_init_rebuilds_when_existing_client_ping_fails(reset_cache_service):
    dead = AsyncMock()
    dead.ping = AsyncMock(side_effect=RuntimeError("conn refused"))
    reset_cache_service.redis_client = dead

    new_client = AsyncMock()
    new_client.ping = AsyncMock(return_value=True)
    new_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=new_client) as from_url:
        await reset_cache_service.init_redis_pool()

    assert from_url.call_count == 1
    assert reset_cache_service.redis_client is new_client


@pytest.mark.asyncio
async def test_init_returns_when_redis_url_missing(reset_cache_service, monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    with patch("redis.asyncio.from_url") as from_url:
        await reset_cache_service.init_redis_pool()
    from_url.assert_not_called()
    assert reset_cache_service.redis_client is None


@pytest.mark.asyncio
async def test_init_falls_back_to_pid_when_hostname_unset(reset_cache_service, monkeypatch):
    monkeypatch.delenv("HOSTNAME", raising=False)
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["client_name"].startswith("crawler-py-pid-")


@pytest.mark.asyncio
async def test_client_name_uses_service_name_env_when_set(reset_cache_service, monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "api-gateway")
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    # HOSTNAME is set to "crawler-service-test" by the autouse fixture.
    assert kwargs["client_name"] == "api-gateway-crawler-service-test"


@pytest.mark.asyncio
async def test_client_name_falls_back_to_crawler_py_when_unset(reset_cache_service, monkeypatch):
    # SERVICE_NAME is deleted by the autouse fixture; belt-and-suspenders explicit:
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["client_name"] == "crawler-py-crawler-service-test"


@pytest.mark.asyncio
async def test_client_name_falls_back_when_service_name_empty(reset_cache_service, monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "")
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["client_name"] == "crawler-py-crawler-service-test"


@pytest.mark.asyncio
async def test_client_name_falls_back_when_service_name_whitespace(reset_cache_service, monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "   ")
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["client_name"] == "crawler-py-crawler-service-test"


@pytest.mark.asyncio
async def test_client_name_strips_surrounding_whitespace_from_service_name(reset_cache_service, monkeypatch):
    # Trailing/leading whitespace must not embed into the Redis CLIENT SETNAME value
    # (Redis rejects spaces in client names — would fail at runtime).
    monkeypatch.setenv("SERVICE_NAME", "  api-gateway  ")
    mock_client = AsyncMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.register_script = MagicMock(return_value=MagicMock())

    with patch("redis.asyncio.from_url", return_value=mock_client) as from_url:
        await reset_cache_service.init_redis_pool()

    _, kwargs = from_url.call_args
    assert kwargs["client_name"] == "api-gateway-crawler-service-test"
