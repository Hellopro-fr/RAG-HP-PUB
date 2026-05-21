"""Tests for /admin/redis-debug endpoint."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_admin_router(monkeypatch):
    """Build a minimal FastAPI app with only the admin router mounted."""
    # Disable API key auth so TestClient calls succeed without a header.
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return app


def test_returns_503_when_redis_client_none(app_with_admin_router, monkeypatch):
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    client = TestClient(app_with_admin_router)
    resp = client.get("/admin/redis-debug")
    assert resp.status_code == 503


def test_returns_full_snapshot_when_redis_alive(app_with_admin_router, monkeypatch):
    fake = AsyncMock()
    fake.info = AsyncMock(return_value={"connected_clients": "42"})
    fake.client_list = AsyncMock(return_value=[
        {"name": "crawler-py-r1", "addr": "10.0.0.1:1"},
        {"name": "crawler-py-r1", "addr": "10.0.0.1:2"},
        {"name": "crawler-node-abc", "addr": "10.0.0.2:1"},
    ])
    pool = MagicMock()
    pool.max_connections = 20
    pool._created_connections = 3
    pool._available_connections = [object(), object()]
    pool._in_use_connections = {object(): None}
    fake.connection_pool = pool

    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    client = TestClient(app_with_admin_router)
    resp = client.get("/admin/redis-debug")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_clients"] == 3
    assert body["info_clients"]["connected_clients"] == "42"
    name_counts = dict(body["client_name_counts"])
    assert name_counts["crawler-py-r1"] == 2
    assert name_counts["crawler-node-abc"] == 1
    assert body["pool_stats"]["max_connections"] == 20
    assert body["pool_stats"]["in_use"] == 1


def test_pool_stats_failure_does_not_500(app_with_admin_router, monkeypatch):
    # Use a custom class — mutating `type(AsyncMock())` would pollute every
    # other AsyncMock instance in this process. A bespoke class with a raising
    # property is hermetic.
    class FakeRedisRaisingPool:
        def __init__(self):
            self.info = AsyncMock(return_value={"connected_clients": "1"})
            self.client_list = AsyncMock(return_value=[])

        @property
        def connection_pool(self):
            raise AttributeError("nope")

    fake = FakeRedisRaisingPool()

    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    client = TestClient(app_with_admin_router)
    resp = client.get("/admin/redis-debug")
    assert resp.status_code == 200
    assert "error" in resp.json()["pool_stats"]
