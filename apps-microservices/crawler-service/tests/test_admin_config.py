# tests/test_admin_config.py
"""Tests for GET /admin/config (effective runtime config, redacted)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return TestClient(app)


def test_settings_present_and_secrets_masked(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "APIFY_PROXY", "http://user:pass@proxy", raising=False)
    body = client.get("/admin/config").json()
    assert body["settings"]["AUTO_STASH_ENABLED"] in (True, False)
    assert body["settings"]["STASH_GRACE_SECONDS"] == settings.STASH_GRACE_SECONDS
    assert body["settings"]["APIFY_PROXY"] == "<set>"
    assert body["settings"]["API_KEY"] is None  # None stays None = auth disabled signal


def test_api_key_masked_when_set(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", "sekret", raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    body = TestClient(app).get("/admin/config", headers={"X-API-Key": "sekret"}).json()
    assert body["settings"]["API_KEY"] == "<set>"
    assert "sekret" not in str(body)


def test_env_whitelist_only(client, monkeypatch):
    monkeypatch.setenv("DIEZ_TIER2_ENABLED", "true")
    monkeypatch.setenv("QUEUE_PURGE_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://:secret@host:6379")
    monkeypatch.setenv("APIFY_PROXY", "http://user:pass@proxy")
    body = client.get("/admin/config").json()
    assert body["env"]["DIEZ_TIER2_ENABLED"] == "true"
    assert body["env"]["QUEUE_PURGE_ENABLED"] == "true"
    assert "REDIS_URL" not in body["env"]
    assert "APIFY_PROXY" not in body["env"]
