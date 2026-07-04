# tests/test_crawler_results_peek.py
"""GET /results?peek=true must not stamp downloaded_at."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client_and_archive(monkeypatch, tmp_path):
    from app.router.crawler import router as CrawlerRouter, get_job_or_recover
    app = FastAPI()
    app.include_router(CrawlerRouter)
    job = {"crawl_id": "7", "status": "finished", "storage_path": str(tmp_path)}

    async def fake_dep(crawl_id: str):
        return job

    app.dependency_overrides[get_job_or_recover] = fake_dep
    archive = tmp_path / "7-results.tar.gz"
    archive.write_bytes(b"fake-tar")
    return TestClient(app), str(archive)


@pytest.mark.parametrize("peek,expected_calls", [(True, 0), (False, 1)])
def test_peek_skips_downloaded_at(client_and_archive, peek, expected_calls):
    client, archive_path = client_and_archive
    from app.core.crawler_manager import crawler_manager
    with patch.object(crawler_manager, "get_results_archive",
                      new=AsyncMock(return_value=(archive_path, False))), \
         patch("app.router.crawler._record_downloaded_at",
               new=AsyncMock()) as rec:
        resp = client.get("/results/7",
                          params={"include": "dataset", "peek": str(peek).lower()})
        assert resp.status_code == 200
        assert rec.await_count == expected_calls
