import base64
import hashlib
from cryptography.fernet import Fernet
import httpx
import respx

from app.core.jwt_keys import ensure_signing_key
from app.services.client_service import create_client


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()


@respx.mock
async def test_full_oauth_flow(client, monkeypatch):
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
    respx.post("https://auth.hellopro.fr/api/login").mock(
        return_value=httpx.Response(
            200, json={"email": "u@hellopro.fr", "display_name": "U"}
        )
    )

    verifier = "v" * 64
    challenge = _challenge(verifier)

    # /authorize
    r = await client.post("/authorize", json={
        "username": "u@hellopro.fr", "password": "p",
        "client_id": "svc",
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "state": "abc", "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    assert r.status_code == 200
    redirect = r.json()["redirect"]
    code = redirect.split("code=")[1].split("&")[0]

    # /token authorization_code
    r = await client.post("/token", data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": "https://svc.hellopro.eu/cb",
        "client_id": "svc", "client_secret": secret,
        "code_verifier": verifier,
    })
    assert r.status_code == 200
    pair = r.json()

    # /userinfo
    r = await client.get("/userinfo", headers={"Authorization": f"Bearer {pair['access_token']}"})
    assert r.status_code == 200
    assert r.json()["email"] == "u@hellopro.fr"

    # /token refresh_token
    r = await client.post("/token", data={
        "grant_type": "refresh_token",
        "refresh_token": pair["refresh_token"],
        "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200
    new_refresh = r.json()["refresh_token"]
    assert new_refresh != pair["refresh_token"]

    # /revoke
    r = await client.post("/revoke", json={
        "refresh_token": new_refresh,
        "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 200

    # rotate after revoke → invalid_grant
    r = await client.post("/token", data={
        "grant_type": "refresh_token",
        "refresh_token": new_refresh,
        "client_id": "svc", "client_secret": secret,
    })
    assert r.status_code == 400
