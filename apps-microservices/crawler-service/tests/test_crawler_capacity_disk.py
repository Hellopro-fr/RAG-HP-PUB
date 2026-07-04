# tests/test_crawler_capacity_disk.py
"""GET /capacity must expose disk state for storage/archives/stash."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    from app.router.crawler import router as CrawlerRouter
    app = FastAPI()
    app.include_router(CrawlerRouter)
    fake = AsyncMock()
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    async def fake_get_key(key):
        return {"crawl_jobs:running_count": "2", "crawl_jobs:max_global_crawls": "3"}.get(key)

    monkeypatch.setattr(cache_service, "get_key", fake_get_key, raising=False)
    return TestClient(app)


def test_capacity_includes_disk_state(client):
    from app.core.crawler_manager import crawler_manager
    fake_state = {"free_bytes": 100, "total_bytes": 1000, "used_pct": 90.0,
                  "file_count": 1, "oldest_file_age_seconds": 5}
    with patch.object(crawler_manager, "_get_archives_disk_state", return_value=fake_state):
        body = client.get("/capacity").json()
    assert body["running_jobs"] == 2
    assert body["disk"]["storage"]["used_pct"] == 90.0
    assert body["disk"]["archives"]["used_pct"] == 90.0
    assert body["disk"]["stash"]["used_pct"] == 90.0
    assert body["disk"]["high_water_pct"] == 85
