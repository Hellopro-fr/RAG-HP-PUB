from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client
from app.services.token_service import issue_token_pair


async def test_userinfo_returns_claims(client, monkeypatch):
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
    await create_client(client_id="svc", name="S", redirect_uris=["https://x"])
    pair = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
        email="u@x", display_name="U",
    )
    r = await client.get(
        "/userinfo",
        headers={"Authorization": f"Bearer {pair['access_token']}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["sub"] == "u@x"
    assert body["email"] == "u@x"
    assert body["display_name"] == "U"


async def test_userinfo_missing_bearer_returns_401(client):
    r = await client.get("/userinfo")
    assert r.status_code == 401
