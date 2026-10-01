"""Tests for the public GET /version endpoint (deploy identity)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client():
    from app.router.crawler import router as CrawlerRouter
    app = FastAPI()
    app.include_router(CrawlerRouter)
    return TestClient(app)


def test_version_defaults_to_unknown(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_DATE", raising=False)
    resp = _client().get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["git_commit"] == "unknown"
    assert body["build_date"] == "unknown"
    assert body["replica"]
    assert body["started_at"]


def test_version_reads_env(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "abc1234")
    monkeypatch.setenv("BUILD_DATE", "2026-07-04T00:00:00Z")
    body = _client().get("/version").json()
    assert body["git_commit"] == "abc1234"
    assert body["build_date"] == "2026-07-04T00:00:00Z"
