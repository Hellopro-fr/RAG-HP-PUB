"""Tests for GET /admin/recent-logs."""
import logging
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import log_buffer


@pytest.fixture(autouse=True)
def clean_buffer():
    log_buffer.clear()
    yield
    log_buffer.clear()


@pytest.fixture
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return TestClient(app)


def _fill():
    h = log_buffer.RingBufferHandler()
    h.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    for msg in ("AUTO_STASH crawl_id=1 reason=grace", "reconcile tick", "AUTO_STASH crawl_id=2 reason=timeout"):
        h.emit(logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None))


def test_returns_lines(client):
    _fill()
    body = client.get("/admin/recent-logs").json()
    assert body["count"] == 3


def test_grep_filters(client):
    _fill()
    body = client.get("/admin/recent-logs", params={"grep": "AUTO_STASH"}).json()
    assert body["count"] == 2
    assert all("AUTO_STASH" in l for l in body["lines"])


def test_invalid_regex_400(client):
    assert client.get("/admin/recent-logs", params={"grep": "("}).status_code == 400


def test_invalid_level_400(client):
    assert client.get("/admin/recent-logs", params={"level": "NOPE"}).status_code == 400


def test_auth_enforced_when_key_set(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", "sekret", raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    c = TestClient(app)
    assert c.get("/admin/recent-logs").status_code == 401
    assert c.get("/admin/recent-logs", headers={"X-API-Key": "sekret"}).status_code == 200
