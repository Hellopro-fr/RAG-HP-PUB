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


def test_compose_env_parity():
    """GUARDRAIL: every env var declared in the docker-compose crawler-service
    environment block must be either visible via /admin/config (whitelist
    prefix) or deliberately excluded with a justification. Fails the moment a
    new variable is added without deciding its visibility."""
    from pathlib import Path
    from app.router.admin import _ENV_WHITELIST_PREFIXES, _ENV_COMPOSE_EXCLUSIONS

    compose = Path(__file__).resolve().parents[3] / "docker-compose.yml"
    lines = compose.read_text(encoding="utf-8").splitlines()

    env_vars, in_service, in_env = [], False, False
    for line in lines:
        if line.rstrip() == "  crawler-service:":
            in_service = True
            continue
        if in_service and line.strip() == "environment:":
            in_env = True
            continue
        if in_env:
            stripped = line.strip()
            if stripped.startswith("- "):
                env_vars.append(stripped[2:].split("=", 1)[0])
            elif stripped.startswith("#"):
                continue
            else:
                break  # dedent = end of the environment block

    assert env_vars, f"could not parse crawler-service environment block from {compose}"

    uncovered = [v for v in env_vars
                 if not v.startswith(_ENV_WHITELIST_PREFIXES)
                 and v not in _ENV_COMPOSE_EXCLUSIONS]
    assert not uncovered, (
        f"New crawler-service compose env var(s) {uncovered} are neither "
        f"whitelisted (add a prefix to _ENV_WHITELIST_PREFIXES in "
        f"app/router/admin.py to expose them in /admin/config) nor excluded "
        f"(add to _ENV_COMPOSE_EXCLUSIONS with a justification comment).")


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
