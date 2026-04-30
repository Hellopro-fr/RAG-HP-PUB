import httpx
import respx
from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client


async def _setup(monkeypatch):
    fk = Fernet.generate_key().decode()
    monkeypatch.setenv("JWT_KEY_ENCRYPTION_KEY", fk)
    monkeypatch.setenv("HELLOPRO_AUTH_URL", "https://auth.hellopro.fr/api/login")
    monkeypatch.setenv("MYSQL_HOST", "x")
    monkeypatch.setenv("MYSQL_USER", "x")
    monkeypatch.setenv("MYSQL_PASS", "x")
    monkeypatch.setenv("MYSQL_DB", "x")
    monkeypatch.setenv("GATEWAY_ADMIN_KEY", "k")
    # Reset cached settings so monkeypatched env is picked up.
    from app.core.settings import get_settings
    get_settings.cache_clear()
    await ensure_signing_key(encryption_key=fk)
    await create_client(
        client_id="svc", name="S",
        redirect_uris=["https://svc.hellopro.eu/cb"],
        skip_consent=True,
    )


@respx.mock
async def test_authorize_happy_path_returns_redirect(client, monkeypatch):
    await _setup(monkeypatch)
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(
            200, json={"success": True, "email": "u@x", "display_name": "U"}
        )
    )
    r = await client.post("/authorize", json={
        "username": "u@x", "password": "p",
        "client_id": "svc",
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "state": "s", "code_challenge": "c",
        "code_challenge_method": "S256",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["redirect"].startswith("https://svc.hellopro.eu/cb?code=")
    assert "state=s" in body["redirect"]


async def test_authorize_unknown_client_returns_400(client, monkeypatch):
    await _setup(monkeypatch)
    r = await client.post("/authorize", json={
        "username": "u@x", "password": "p", "client_id": "nope",
        "redirect_uri": "https://x", "state": "s", "code_challenge": "c",
        "code_challenge_method": "S256",
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_client"


async def test_authorize_bad_redirect_uri_returns_400(client, monkeypatch):
    await _setup(monkeypatch)
    r = await client.post("/authorize", json={
        "username": "u@x", "password": "p", "client_id": "svc",
        "redirect_uri": "https://attacker.example/cb",
        "state": "s", "code_challenge": "c",
        "code_challenge_method": "S256",
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_redirect_uri"


@respx.mock
async def test_authorize_upstream_401_returns_401(client, monkeypatch):
    await _setup(monkeypatch)
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(401)
    )
    r = await client.post("/authorize", json={
        "username": "u@x", "password": "wrong", "client_id": "svc",
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "state": "s", "code_challenge": "c",
        "code_challenge_method": "S256",
    })
    assert r.status_code == 401
    assert r.json()["error"] == "access_denied"
