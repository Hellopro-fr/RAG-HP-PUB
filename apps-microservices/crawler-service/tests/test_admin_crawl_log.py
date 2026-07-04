"""Tests for GET /admin/logs/{crawl_id} (crawler.log tail)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_and_job(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    from app.router.crawler import get_job_or_recover
    app = FastAPI()
    app.include_router(AdminRouter)
    job = {"crawl_id": "77", "status": "failed", "storage_path": str(tmp_path)}

    async def fake_dep(crawl_id: str):
        return job

    app.dependency_overrides[get_job_or_recover] = fake_dep
    return app, tmp_path


def test_tail_returns_last_lines(app_and_job):
    app, storage = app_and_job
    log = storage / "crawler.log"
    log.write_text("\n".join(f"line-{i}" for i in range(100)), encoding="utf-8")
    resp = TestClient(app).get("/admin/logs/77", params={"tail_bytes": 30})
    assert resp.status_code == 200
    text = resp.text
    assert "line-99" in text
    assert "line-0\n" not in text
    assert int(resp.headers["X-Log-Size-Bytes"]) == log.stat().st_size


def test_grep_filters_lines(app_and_job):
    app, storage = app_and_job
    (storage / "crawler.log").write_text(
        "noise\n{\"event\":\"progress_stalled\"}\nnoise2\n", encoding="utf-8")
    resp = TestClient(app).get("/admin/logs/77", params={"grep": "progress_stalled"})
    assert resp.status_code == 200
    assert resp.text.strip() == '{"event":"progress_stalled"}'


def test_404_when_log_missing(app_and_job):
    app, _ = app_and_job
    assert TestClient(app).get("/admin/logs/77").status_code == 404


def test_invalid_grep_400(app_and_job):
    app, storage = app_and_job
    (storage / "crawler.log").write_text("x\n", encoding="utf-8")
    assert TestClient(app).get("/admin/logs/77", params={"grep": "("}).status_code == 400


def test_tail_single_partial_line_keeps_fragment(app_and_job):
    """A window holding only one (partial) line must return the fragment,
    not an empty tail after the drop-partial-first-line step."""
    app, storage = app_and_job
    # newline="\n": keep the file byte-exact on Windows (no CRLF translation)
    (storage / "crawler.log").write_text("A" * 100 + "\n", encoding="utf-8", newline="\n")
    resp = TestClient(app).get("/admin/logs/77", params={"tail_bytes": 30})
    assert resp.status_code == 200
    assert resp.text.strip() != ""
    assert resp.text.strip() == "A" * 29  # end of the giant line


def test_traversal_crawl_id_rejected(monkeypatch, tmp_path):
    """Fallback path (no storage_path in job) must reject a crawl_id that
    escapes CRAWLER_STORAGE_PATH."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "CRAWLER_STORAGE_PATH", str(tmp_path), raising=False)
    from fastapi import FastAPI
    from app.router.admin import router as AdminRouter
    from app.router.crawler import get_job_or_recover
    app = FastAPI()
    app.include_router(AdminRouter)

    async def fake_dep(crawl_id: str):
        return {"crawl_id": "../evil", "status": "failed"}  # no storage_path

    app.dependency_overrides[get_job_or_recover] = fake_dep
    assert TestClient(app).get("/admin/logs/whatever").status_code == 400
