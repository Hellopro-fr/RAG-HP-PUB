"""Framework-free OAuth2 + PKCE primitives (parity with libs/auth/node oauth.ts)."""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
import jwt


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@dataclass(frozen=True)
class Pkce:
    verifier: str
    challenge: str


def gen_pkce() -> Pkce:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return Pkce(verifier=verifier, challenge=challenge)


def random_state() -> str:
    return _b64url(secrets.token_bytes(16))


def build_authorize_url(*, public_url: str, client_id: str, redirect_uri: str,
                         challenge: str, state: str) -> str:
    query = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    return f"{public_url}/authorize?{query}"


def exchange_code(*, base_url: str, client_id: str, client_secret: str, code: str,
                   redirect_uri: str, verifier: str, timeout: float = 10.0) -> dict:
    resp = httpx.post(
        f"{base_url}/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        auth=(client_id, client_secret),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"[account-auth] token exchange failed: {resp.status_code}")
    return resp.json()


@dataclass(frozen=True)
class Identity:
    email: str
    name: str | None = None


def verify_and_extract(access_token: str, jwt_secret: str) -> Identity:
    # aud intentionally not verified (account-service sets aud=client_id).
    payload = jwt.decode(access_token, jwt_secret, algorithms=["HS256"],
                          options={"verify_aud": False})
    email = payload.get("sub") or payload.get("email")
    if not email:
        raise RuntimeError("[account-auth] token missing sub/email claim")
    return Identity(email=email, name=payload.get("name"))
