from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key


async def test_jwks_endpoint_returns_active_key(client, monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    await ensure_signing_key(encryption_key=fk)
    r = await client.get("/.well-known/jwks.json")
    assert r.status_code == 200
    data = r.json()
    assert data["keys"][0]["kty"] == "RSA"
    assert data["keys"][0]["alg"] == "RS256"
