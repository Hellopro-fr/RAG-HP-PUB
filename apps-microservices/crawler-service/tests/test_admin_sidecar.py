"""Tests for GET /admin/sidecar/{crawl_id} (whitelisted diagnostic files)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_and_storage(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    from app.router.crawler import get_job_or_recover
    app = FastAPI()
    app.include_router(AdminRouter)
    job = {"crawl_id": "5", "status": "finished", "storage_path": str(tmp_path)}

    async def fake_dep(crawl_id: str):
        return job

    app.dependency_overrides[get_job_or_recover] = fake_dep
    return app, tmp_path


def test_returns_parsed_json(app_and_storage):
    app, storage = app_and_storage
    (storage / "_diez_decision.json").write_text(
        '{"mode": "skipDiez", "source": "tier2"}', encoding="utf-8")
    body = TestClient(app).get("/admin/sidecar/5",
                               params={"name": "_diez_decision.json"}).json()
    assert body["content"]["source"] == "tier2"


def test_non_json_returned_raw(app_and_storage):
    app, storage = app_and_storage
    (storage / "_exit_reason.json").write_text("not json {", encoding="utf-8")
    body = TestClient(app).get("/admin/sidecar/5",
                               params={"name": "_exit_reason.json"}).json()
    assert body["raw"] == "not json {"


def test_traversal_and_unknown_names_rejected(app_and_storage):
    app, _ = app_and_storage
    c = TestClient(app)
    assert c.get("/admin/sidecar/5", params={"name": "../../etc/passwd"}).status_code == 400
    assert c.get("/admin/sidecar/5", params={"name": "crawler.log"}).status_code == 400


def test_404_when_absent(app_and_storage):
    app, _ = app_and_storage
    resp = TestClient(app).get("/admin/sidecar/5",
                               params={"name": "_callback_payload.json"})
    assert resp.status_code == 404
