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
    from app.core.settings import get_settings
    get_settings.cache_clear()
    await ensure_signing_key(encryption_key=fk)
    await create_client(
        client_id="svc", name="S",
        redirect_uris=["https://svc.hellopro.eu/auth/account/callback"],
        skip_consent=True,
    )


@respx.mock
async def test_login_happy_path(client, monkeypatch):
    await _setup(monkeypatch)
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(
            200, json={"success": True, "email": "u@x", "display_name": "U"}
        )
    )
    r = await client.post("/login", json={
        "service": "svc",
        "username": "u@x",
        "password": "p",
        "next": "/dashboard",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["redirect"].startswith(
        "https://svc.hellopro.eu/auth/account/callback?login_session="
    )
    assert "next=%2Fdashboard" in body["redirect"]


async def test_login_unknown_service_returns_400(client, monkeypatch):
    await _setup(monkeypatch)
    r = await client.post("/login", json={
        "service": "nope", "username": "u", "password": "p"
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_service"


@respx.mock
async def test_login_bad_creds_returns_401(client, monkeypatch):
    await _setup(monkeypatch)
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(200, json={"success": False})
    )
    r = await client.post("/login", json={
        "service": "svc", "username": "u", "password": "wrong"
    })
    assert r.status_code == 401
    assert r.json()["error"] == "access_denied"


@respx.mock
async def test_full_login_then_exchange(client, monkeypatch):
    await _setup(monkeypatch)
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(
            200, json={"success": True, "email": "u@x", "display_name": "U"}
        )
    )
    r = await client.post("/login", json={
        "service": "svc", "username": "u@x", "password": "p", "next": "/x"
    })
    assert r.status_code == 200
    redirect = r.json()["redirect"]
    session_token = redirect.split("login_session=")[1].split("&")[0]

    r2 = await client.post("/sessions/exchange", json={
        "service": "svc", "login_session": session_token
    })
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"]
    assert body["refresh_token"]


@respx.mock
async def test_exchange_unknown_session_returns_400(client, monkeypatch):
    await _setup(monkeypatch)
    r = await client.post("/sessions/exchange", json={
        "service": "svc", "login_session": "bogus"
    })
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_session"


@respx.mock
async def test_exchange_replay_returns_400(client, monkeypatch):
    await _setup(monkeypatch)
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(
            200, json={"success": True, "email": "u@x", "display_name": "U"}
        )
    )
    r = await client.post("/login", json={
        "service": "svc", "username": "u@x", "password": "p"
    })
    token = r.json()["redirect"].split("login_session=")[1].split("&")[0]
    r2 = await client.post("/sessions/exchange", json={
        "service": "svc", "login_session": token
    })
    assert r2.status_code == 200
    r3 = await client.post("/sessions/exchange", json={
        "service": "svc", "login_session": token
    })
    assert r3.status_code == 400
