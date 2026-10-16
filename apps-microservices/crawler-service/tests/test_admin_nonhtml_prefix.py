# tests/test_admin_nonhtml_prefix.py
"""R23 (2): kind=pdf on GET /admin/dataset/{crawl_id} and the NONHTML_ env
prefix on GET /admin/config."""
import json

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
    for name, payload in items:
        (d / name).write_text(json.dumps(payload), encoding="utf-8")
    return d


def test_pdf_prefix_matches_crawler_dataset_name():
    # crawler/src/httpStatusPolicy.ts pdfDatasetName: `pdf-${crawleeStorageName}`
    from app.router.admin import _DATASET_PREFIXES
    assert _DATASET_PREFIXES["pdf"] == "pdf-"


def test_kind_pdf_reads_sanitized_pdf_dataset(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "pdf-example-com", [
        ("a.json", {"url": "https://example.com/image/x1", "source": "",
                    "status": 200, "content_type": "image/jpeg"}),
        ("b.json", {"url": "https://example.com/image/x2", "source": "",
                    "status": 200, "content_type": "image/jpeg"}),
    ])
    resp = TestClient(app).get("/admin/dataset/9", params={"kind": "pdf"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "pdf"
    assert body["total_records"] == 2
    assert {r["url"] for r in body["records"]} == {
        "https://example.com/image/x1", "https://example.com/image/x2"}
    assert set(body) == {"kind", "total_records", "offset", "returned", "records"}


def test_kind_pdf_exports_content_type_or_none(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "pdf-example-com", [
        ("a.json", {"url": "https://example.com/g", "content_type": "image/jpeg"}),
        ("b.json", {"url": "https://example.com/s", "source": "", "status": 200}),
    ])
    body = TestClient(app).get("/admin/dataset/9", params={"kind": "pdf"}).json()
    by_url = {r["url"]: r for r in body["records"]}
    assert by_url["https://example.com/g"]["content_type"] == "image/jpeg"
    assert by_url["https://example.com/s"]["content_type"] is None


def test_kind_pdf_reads_unsanitized_dir_too(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "pdf-example.com", [("a.json", {"url": "https://example.com/d/1"})])
    body = TestClient(app).get("/admin/dataset/9", params={"kind": "pdf"}).json()
    assert body["total_records"] == 1


def test_kind_main_never_reads_pdf_dir(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "pdf-example-com", [("a.json", {"url": "https://example.com/d/1"})])
    resp = TestClient(app).get("/admin/dataset/9")  # kind=main
    assert resp.status_code == 404  # only pdf-example-com exists: main finds nothing


def test_kind_pdf_absent_is_404(app_and_storage):
    app, _ = app_and_storage
    resp = TestClient(app).get("/admin/dataset/9", params={"kind": "pdf"})
    assert resp.status_code == 404


def test_unknown_kind_still_rejected(app_and_storage):
    app, _ = app_and_storage
    assert TestClient(app).get("/admin/dataset/9", params={"kind": "bogus"}).status_code == 422


@pytest.fixture
def config_client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return TestClient(app)


def test_nonhtml_env_exposed_in_config(config_client, monkeypatch):
    monkeypatch.setenv("NONHTML_PREFIX_MODE", "shadow")
    monkeypatch.setenv("NONHTML_PREFIX_MIN", "5")
    monkeypatch.setenv("NONHTML_PREFIX_PROBES", "3")
    monkeypatch.setenv("NONHTML_ISOLATED_MAX", "7")
    env = config_client.get("/admin/config").json()["env"]
    assert env["NONHTML_PREFIX_MODE"] == "shadow"
    assert env["NONHTML_PREFIX_MIN"] == "5"
    assert env["NONHTML_PREFIX_PROBES"] == "3"
    assert env["NONHTML_ISOLATED_MAX"] == "7"


def test_non_whitelisted_lookalike_not_exposed(config_client, monkeypatch):
    monkeypatch.setenv("XNONHTML_PREFIX_MODE", "shadow")
    env = config_client.get("/admin/config").json()["env"]
    assert "XNONHTML_PREFIX_MODE" not in env
