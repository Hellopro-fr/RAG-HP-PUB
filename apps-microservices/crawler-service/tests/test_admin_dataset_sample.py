# tests/test_admin_dataset_sample.py
"""Tests for GET /admin/dataset/{crawl_id} (side-effect-free sampling)."""
import json
import os
import time
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
    job = {"crawl_id": "9", "status": "finished", "domain": "example.com",
           "storage_path": str(tmp_path)}

    async def fake_dep(crawl_id: str):
        return job

    app.dependency_overrides[get_job_or_recover] = fake_dep
    return app, tmp_path


def _mk_dataset(storage, dirname, items):
    d = storage / "storage" / "datasets" / dirname
    d.mkdir(parents=True)
    for i, (name, payload) in enumerate(items):
        p = d / name
        p.write_text(json.dumps(payload), encoding="utf-8")
        os.utime(p, (time.time() + i, time.time() + i))  # deterministic mtime order
    return d


def test_lists_newest_first_with_url_and_length(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "example.com", [
        ("a.json", {"url": "https://example.com/1", "content": "x" * 50}),
        ("b.json", {"url": "https://example.com/2", "content": "y" * 10}),
    ])
    body = TestClient(app).get("/admin/dataset/9").json()
    assert body["total_records"] == 2
    assert body["records"][0]["url"] == "https://example.com/2"  # newest first
    assert body["records"][0]["content_length"] == 10
    assert "content_preview" not in body["records"][0]  # content_chars=0 default


def test_content_preview_truncated(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "example.com", [("a.json", {"url": "u", "content": "abcdef"})])
    body = TestClient(app).get("/admin/dataset/9", params={"content_chars": 3}).json()
    assert body["records"][0]["content_preview"] == "abc"


def test_sanitized_domain_fallback_and_kind_prefix(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "error-example-com", [("e.json", {"url": "u", "errors": ["x"]})])
    body = TestClient(app).get("/admin/dataset/9", params={"kind": "error"}).json()
    assert body["total_records"] == 1


def test_404_with_cold_tier_hint_when_absent(app_and_storage):
    app, _ = app_and_storage
    resp = TestClient(app).get("/admin/dataset/9")
    assert resp.status_code == 404
    assert "side-effect-free" in resp.json()["detail"]


def test_html_index_excluded_and_pagination(app_and_storage):
    app, storage = app_and_storage
    items = [(f"f{i}.json", {"url": f"u{i}", "content": ""}) for i in range(5)]
    items.append(("html_index.json", {"u": "f"}))
    _mk_dataset(storage, "example.com", items)
    body = TestClient(app).get("/admin/dataset/9", params={"offset": 1, "limit": 2}).json()
    assert body["total_records"] == 5
    assert body["returned"] == 2
