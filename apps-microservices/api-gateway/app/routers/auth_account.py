"""
Demo OAuth2 client integration with `account-service-backend`.

Flow:
- GET  /auth/account/start    -> redirect to account-service signin page
- GET  /auth/account/callback -> exchange code for tokens, set HttpOnly cookies
- POST /auth/account/logout   -> revoke refresh token + clear cookies
"""

import base64
import hashlib
import logging
import os
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

logger = logging.getLogger("auth_account")
router = APIRouter(tags=["Account OAuth"])

OAUTH_AUTHORIZE_URL = os.environ.get(
    "OAUTH_AUTHORIZE_URL", "http://account-service-frontend:8080/signin"
)
OAUTH_TOKEN_URL = os.environ.get(
    "OAUTH_TOKEN_URL", "http://account-service-backend:8000/token"
)
OAUTH_REVOKE_URL = os.environ.get(
    "OAUTH_REVOKE_URL", "http://account-service-backend:8000/revoke"
)
OAUTH_CLIENT_ID = os.environ.get("OAUTH_ACCOUNT_CLIENT_ID", "api-gateway")
OAUTH_CLIENT_SECRET = os.environ.get("OAUTH_ACCOUNT_CLIENT_SECRET", "")
OAUTH_REDIRECT_URI = os.environ.get(
    "OAUTH_ACCOUNT_REDIRECT_URI", "http://localhost:8500/auth/account/callback"
)


def _pkce_pair() -> tuple[str, str]:
    verifier = (
        base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    )
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


@router.get("/auth/account/start")
async def auth_start(request: Request, next: str = "/"):
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(24)
    request.session["oauth_verifier"] = verifier
    request.session["oauth_state"] = state
    request.session["oauth_next"] = next

    qs = urlencode(
        {
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"{OAUTH_AUTHORIZE_URL}?{qs}", status_code=303)


@router.get("/auth/account/callback")
async def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error:
        raise HTTPException(400, f"OAuth error: {error}")
    if not code or not state:
        raise HTTPException(400, "missing code or state")

    expected_state = request.session.pop("oauth_state", None)
    verifier = request.session.pop("oauth_verifier", None)
    next_url = request.session.pop("oauth_next", "/")

    if not expected_state or state != expected_state:
        raise HTTPException(400, "invalid state (CSRF)")
    if not verifier:
        raise HTTPException(400, "missing PKCE verifier in session")

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            OAUTH_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": OAUTH_REDIRECT_URI,
                "client_id": OAUTH_CLIENT_ID,
                "client_secret": OAUTH_CLIENT_SECRET,
                "code_verifier": verifier,
            },
        )
    if r.status_code != 200:
        logger.warning("token exchange failed: %s %s", r.status_code, r.text)
        raise HTTPException(502, f"token exchange failed: {r.text}")
    tokens = r.json()

    body = (
        "<!doctype html><html><body>"
        "<h1>Login OK</h1>"
        f"<p>access_token (jwt, 15 min): <code>{tokens['access_token']}</code></p>"
        f"<p>refresh_token: <code>{tokens['refresh_token']}</code></p>"
        f"<p>expires_in: {tokens['expires_in']}s</p>"
        f'<p><a href="{next_url}">Continue</a></p>'
        "</body></html>"
    )
    response = HTMLResponse(body)
    response.set_cookie(
        "account_access_token",
        tokens["access_token"],
        max_age=tokens["expires_in"],
        httponly=True,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "account_refresh_token",
        tokens["refresh_token"],
        max_age=30 * 24 * 3600,
        httponly=True,
        samesite="lax",
        path="/auth/account",
    )
    return response


@router.post("/auth/account/logout")
async def auth_logout(request: Request):
    refresh = request.cookies.get("account_refresh_token")
    if refresh and OAUTH_CLIENT_SECRET:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                OAUTH_REVOKE_URL,
                json={
                    "refresh_token": refresh,
                    "client_id": OAUTH_CLIENT_ID,
                    "client_secret": OAUTH_CLIENT_SECRET,
                },
            )
    response = Response(content="logged out", media_type="text/plain")
    response.delete_cookie("account_access_token", path="/")
    response.delete_cookie("account_refresh_token", path="/auth/account")
    return response
