import hashlib
import base64

from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client
from app.services.code_service import issue_code


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()


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
    secret = await create_client(
        client_id="svc", name="S",
        redirect_uris=["https://svc.hellopro.eu/cb"],
        skip_consent=True,
    )
    return secret


async def test_token_authorization_code_happy_path(client, monkeypatch):
    secret = await _setup(monkeypatch)
    verifier = "v" * 64
    code = await issue_code(
        client_id="svc", sub="u@x",
        code_challenge=_challenge(verifier),
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60, email="u@x", display_name="U",
    )
    r = await client.post("/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": secret,
        "code_verifier": verifier,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["access_token"]
    assert body["refresh_token"]


async def test_token_bad_secret_returns_invalid_client(client, monkeypatch):
    secret = await _setup(monkeypatch)
    verifier = "v" * 64
    code = await issue_code(
        client_id="svc", sub="u@x",
        code_challenge=_challenge(verifier),
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60,
    )
    r = await client.post("/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": "wrong",
        "code_verifier": verifier,
    })
    assert r.status_code == 401
    assert r.json()["error"] == "invalid_client"


async def test_token_bad_verifier_returns_invalid_grant(client, monkeypatch):
    secret = await _setup(monkeypatch)
    verifier = "v" * 64
    code = await issue_code(
        client_id="svc", sub="u@x",
        code_challenge=_challenge(verifier),
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60,
    )
    r = await client.post("/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": secret,
        "code_verifier": "x" * 64,
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_grant"


async def test_token_refresh_grant_rotates(client, monkeypatch):
    secret = await _setup(monkeypatch)
    verifier = "v" * 64
    code = await issue_code(
        client_id="svc", sub="u@x",
        code_challenge=_challenge(verifier),
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        ttl_seconds=60, email="u@x",
    )
    r1 = await client.post("/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": secret,
        "code_verifier": verifier,
    })
    refresh = r1.json()["refresh_token"]

    r2 = await client.post("/token", data={
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": "svc", "client_secret": secret,
    })
    assert r2.status_code == 200
    assert r2.json()["refresh_token"] != refresh
