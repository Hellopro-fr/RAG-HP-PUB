from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.db.models import RefreshToken
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


async def test_revoke_marks_chain_revoked(client, monkeypatch):
    fk, secret = await _setup(monkeypatch)
    pair = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    r = await client.post("/revoke", json={
        "refresh_token": pair["refresh_token"],
        "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200
    rows = await RefreshToken.filter(client_id="svc", sub="u@x").all()
    assert all(row.revoked_at is not None for row in rows)


async def test_revoke_unknown_token_returns_200(client, monkeypatch):
    _, secret = await _setup(monkeypatch)
    r = await client.post("/revoke", json={
        "refresh_token": "bogus", "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200  # RFC 7009: revoke is idempotent
