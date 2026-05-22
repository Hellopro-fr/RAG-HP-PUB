"""Integration tests for cache_service[_sync] against a REAL Redis server.

Skipped by default. To run:
    REDIS_URL=redis://localhost:16379/0 python -m pytest tests/test_cache_service_integration.py -v

Suggested setup (ephemeral Redis on port 16379, no auth):
    docker run --rm -d --name redis-cu-test -p 16379:6379 redis:7-alpine
    REDIS_URL=redis://localhost:16379/0 python -m pytest \
        tests/test_cache_service_integration.py -v
    docker stop redis-cu-test

These tests exercise the requirements from spec
docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md
section 7 ("Verification") against a real server because the unit tests
mock out redis-py's actual behavior.
"""
import asyncio
import os
import pytest
import pytest_asyncio

REDIS_URL = os.getenv("REDIS_URL", "")
INTEGRATION_ENABLED = bool(REDIS_URL) and REDIS_URL.startswith("redis://")

pytestmark = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="Set REDIS_URL=redis://host:port/db to run integration tests.",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Keep REDIS_URL; reset everything else so tests are hermetic."""
    for var in (
        "REDIS_MAX_CONNECTIONS",
        "REDIS_SOCKET_TIMEOUT_S",
        "REDIS_SOCKET_CONNECT_TIMEOUT_S",
        "REDIS_HEALTH_CHECK_INTERVAL_S",
        "HOSTNAME",
        "SERVICE_NAME",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("REDIS_URL", REDIS_URL)


@pytest_asyncio.fixture
async def reset_async(monkeypatch):
    from common_utils.redis import cache_service
    cache_service.redis_client = None
    yield cache_service
    if cache_service.redis_client is not None:
        try:
            await cache_service.redis_client.close()
        except Exception:
            pass
    cache_service.redis_client = None


@pytest.fixture
def reset_sync(monkeypatch):
    from common_utils.redis import cache_service_sync
    cache_service_sync.redis_client = None
    yield cache_service_sync
    if cache_service_sync.redis_client is not None:
        try:
            cache_service_sync.redis_client.close()
        except Exception:
            pass
    cache_service_sync.redis_client = None


# --- Async binding integration ---

@pytest.mark.asyncio
async def test_pool_caps_at_max_connections(reset_async, monkeypatch):
    """Open N+1 concurrent commands against pool of size N; the (N+1)th raises
    redis.ConnectionError immediately (no indefinite block)."""
    import redis.asyncio as r
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "3")
    monkeypatch.setenv("SERVICE_NAME", "integ-test-cap")

    await reset_async.init_redis_pool()
    client = reset_async.redis_client
    assert client is not None

    # BLPOP holds a connection for the whole timeout
    holders = [
        asyncio.create_task(client.blpop(["leaktest:no-such-key"], timeout=3))
        for _ in range(3)
    ]
    await asyncio.sleep(0.1)  # let blpops grab pool slots

    # 4th command must raise immediately (pool exhausted)
    with pytest.raises((r.ConnectionError, r.RedisError)) as exc_info:
        await asyncio.wait_for(client.get("anykey"), timeout=1.0)
    assert "Too many connections" in str(exc_info.value) or "max" in str(exc_info.value).lower()

    for t in holders:
        t.cancel()
    await asyncio.gather(*holders, return_exceptions=True)


@pytest.mark.asyncio
async def test_client_setname_appears_in_client_list(reset_async, monkeypatch):
    """A second inspector client sees the expected CLIENT LIST entry name."""
    import redis.asyncio as r
    monkeypatch.setenv("SERVICE_NAME", "integ-test-name")
    monkeypatch.setenv("HOSTNAME", "integ-pod-abc")

    await reset_async.init_redis_pool()
    # Force the pool to materialize a connection
    await reset_async.redis_client.ping()

    inspector = r.from_url(REDIS_URL, decode_responses=True)
    try:
        entries = await inspector.client_list()
        names = [e.get("name", "") for e in entries]
        expected = f"integ-test-name-integ-pod-abc-pid{os.getpid()}"
        assert expected in names, f"Expected '{expected}' in {names}"
    finally:
        await inspector.aclose()


@pytest.mark.asyncio
async def test_exception_releases_connection(reset_async, monkeypatch):
    """After triggering N redis errors mid-op, the pool's in-use count returns to 0."""
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "3")
    monkeypatch.setenv("SERVICE_NAME", "integ-test-release")

    await reset_async.init_redis_pool()
    client = reset_async.redis_client
    pool = client.connection_pool

    # Seed a string key, then trigger WRONGTYPE errors by lpush'ing onto it
    await client.set("strkey", "value")
    for _ in range(10):
        try:
            await client.lpush("strkey", "x")
        except Exception:
            pass

    # Pool fully released, no in-use leak
    in_use = len(pool._in_use_connections)
    assert in_use == 0, f"Pool leak: {in_use} conn(s) still marked in_use"


@pytest.mark.asyncio
async def test_call_with_retry_succeeds_against_real_redis(reset_async, monkeypatch):
    """Sanity: call_with_retry returns the actual SET/GET result."""
    monkeypatch.setenv("SERVICE_NAME", "integ-test-retry")
    from common_utils.redis.cache_service import call_with_retry

    await reset_async.init_redis_pool()
    client = reset_async.redis_client

    await call_with_retry(client.set, "retrytest:k", "v")
    result = await call_with_retry(client.get, "retrytest:k")
    assert result == "v"
    await client.delete("retrytest:k")


# --- Sync binding integration ---

def test_sync_pool_caps_at_max_connections(reset_sync, monkeypatch):
    """Sync parity: 4th command on pool-of-3 raises."""
    import redis as r
    import threading
    monkeypatch.setenv("REDIS_MAX_CONNECTIONS", "3")
    monkeypatch.setenv("SERVICE_NAME", "integ-test-sync-cap")

    client = reset_sync.init_redis_pool_sync()
    assert client is not None

    # Hold 3 conns via blocking BLPOPs in threads
    def holder():
        try:
            client.blpop("leaktest:no-such-sync-key", timeout=3)
        except Exception:
            pass

    threads = [threading.Thread(target=holder) for _ in range(3)]
    for t in threads:
        t.start()
    import time
    time.sleep(0.1)

    with pytest.raises((r.ConnectionError, r.RedisError)) as exc_info:
        client.get("anykey")
    assert "Too many connections" in str(exc_info.value) or "max" in str(exc_info.value).lower()

    for t in threads:
        t.join(timeout=5)


def test_sync_client_setname_appears_in_client_list(reset_sync, monkeypatch):
    """Sync parity: CLIENT LIST shows {service}-{host}-pid{N}."""
    import redis as r
    monkeypatch.setenv("SERVICE_NAME", "integ-test-sync-name")
    monkeypatch.setenv("HOSTNAME", "integ-pod-sync")

    client = reset_sync.init_redis_pool_sync()
    client.ping()  # materialize a conn

    inspector = r.from_url(REDIS_URL, decode_responses=True)
    try:
        entries = inspector.client_list()
        names = [e.get("name", "") for e in entries]
        expected = f"integ-test-sync-name-integ-pod-sync-pid{os.getpid()}"
        assert expected in names, f"Expected '{expected}' in {names}"
    finally:
        inspector.close()


def test_sync_get_client_returns_same_instance(reset_sync, monkeypatch):
    monkeypatch.setenv("SERVICE_NAME", "integ-test-sync-get")
    client = reset_sync.init_redis_pool_sync()
    assert reset_sync.get_client() is client


def test_sync_close_disconnects_all_pool_conns(reset_sync, monkeypatch):
    """After close_redis_pool_sync, no conns with this service name remain in Redis."""
    import redis as r
    import time
    monkeypatch.setenv("SERVICE_NAME", "integ-test-sync-close")
    monkeypatch.setenv("HOSTNAME", "integ-pod-close")

    client = reset_sync.init_redis_pool_sync()
    # Open a few conns by running parallel ops
    for i in range(5):
        client.set(f"closetest:{i}", str(i))
    for i in range(5):
        client.delete(f"closetest:{i}")

    expected = f"integ-test-sync-close-integ-pod-close-pid{os.getpid()}"

    reset_sync.close_redis_pool_sync()

    # Give Redis a moment to register disconnects
    time.sleep(0.2)

    inspector = r.from_url(REDIS_URL, decode_responses=True)
    try:
        entries = inspector.client_list()
        names = [e.get("name", "") for e in entries]
        remaining = [n for n in names if n == expected]
        assert remaining == [], (
            f"Expected zero conns named '{expected}' after close; found {remaining}"
        )
    finally:
        inspector.close()
