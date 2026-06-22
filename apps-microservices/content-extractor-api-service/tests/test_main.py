import asyncio

from fastapi.testclient import TestClient


def test_app_starts_and_health_ok(monkeypatch):
    import main
    monkeypatch.setattr(main, "init_redis_pool", lambda: asyncio.sleep(0))
    monkeypatch.setattr(main, "close_redis_pool", lambda: asyncio.sleep(0))
    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert hasattr(main.app.state, "job_manager")
