import json

from scripts.seed_clients import seed_from_env
from app.db.models import OAuthClient


async def test_seed_creates_clients(monkeypatch):
    monkeypatch.setenv(
        "OAUTH_CLIENTS_SEED_JSON",
        json.dumps([{
            "client_id": "svc", "name": "S",
            "redirect_uris": ["https://svc.hellopro.eu/cb"],
            "skip_consent": True,
        }]),
    )
    await seed_from_env()
    assert await OAuthClient.filter(client_id="svc").exists()


async def test_seed_idempotent(monkeypatch):
    monkeypatch.setenv(
        "OAUTH_CLIENTS_SEED_JSON",
        json.dumps([{
            "client_id": "svc", "name": "S",
            "redirect_uris": ["https://svc.hellopro.eu/cb"],
        }]),
    )
    await seed_from_env()
    await seed_from_env()  # second call should not raise
    assert await OAuthClient.filter(client_id="svc").count() == 1
