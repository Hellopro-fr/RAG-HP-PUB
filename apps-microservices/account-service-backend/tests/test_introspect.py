from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client
from app.services.token_service import issue_token_pair


async def _setup(monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    from app.core.settings import get_settings
    get_settings.cache_clear()
    await ensure_signing_key(encryption_key=fk)
    return fk, await create_client(client_id="svc", name="S", redirect_uris=["https://x"])


async def test_introspect_active(client, monkeypatch):
    fk, secret = await _setup(monkeypatch)
    pair = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    r = await client.post("/introspect", json={
        "token": pair["access_token"], "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["active"] is True
    assert body["sub"] == "u@x"


async def test_introspect_invalid_token(client, monkeypatch):
    _, secret = await _setup(monkeypatch)
    r = await client.post("/introspect", json={
        "token": "garbage", "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200
    assert r.json() == {"active": False}
