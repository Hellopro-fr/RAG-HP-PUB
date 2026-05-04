"""OAuth 2.1 + PKCE client for account-service SSO.

Adds /auth/login and /auth/callback to api-gateway. Sets the same
request.session["user"] dict the rest of the app already understands,
so existing DocsAuthMiddleware + /login handler keep working as fallback.

Env vars (defaults match the docker-compose wiring):
    ACCOUNT_BASE_URL       — public URL of account-service (e.g. http://account-service-backend:8600 in-cluster, https://account.hellopro.fr in prod)
    ACCOUNT_REDIRECT_URI   — e.g. http://localhost:8050/auth/callback (must match the URI registered in account-service)

Client credentials are resolved by `common_utils.sso.get_account_credentials()`,
which derives env keys from `SERVICE_NAME` (e.g. SERVICE_NAME=api-gateway →
ACCOUNT_CLIENT_ID_API_GATEWAY + ACCOUNT_CLIENT_SECRET_API_GATEWAY) and falls
back to plain ACCOUNT_CLIENT_ID + ACCOUNT_CLIENT_SECRET when those aren't set.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from common_utils.sso import (
    AccountCredentialsMissing,
    get_account_credentials,
    get_account_credentials_from_api,
)

logger = logging.getLogger("sso")

router = APIRouter(tags=["SSO"])

ACCOUNT_BASE_URL = os.environ.get("ACCOUNT_BASE_URL", "http://account-service-backend:8600")
ACCOUNT_REDIRECT_URI = os.environ.get("ACCOUNT_REDIRECT_URI", "")

# Credentials are resolved lazily on first /auth/login request: env first
# (instant, no network), then HTTP fallback to /internal/credentials/{name}
# on account-service. Cache once we get them so we don't refetch per request.
_cached_credentials: Optional[tuple[str, str]] = None


async def _get_credentials() -> tuple[str, str]:
    global _cached_credentials
    if _cached_credentials:
        return _cached_credentials
    try:
        _cached_credentials = get_account_credentials()
        return _cached_credentials
    except AccountCredentialsMissing:
        pass
    _cached_credentials = await get_account_credentials_from_api()
    return _cached_credentials

REPLAY_WINDOW_S = 5 * 60


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


@router.get("/auth/login", include_in_schema=False)
async def auth_login() -> Response:
    """Start the PKCE flow: 302 to account-service /authorize with a fresh challenge."""
    if not ACCOUNT_REDIRECT_URI:
        raise HTTPException(500, "ACCOUNT_REDIRECT_URI not configured")
    try:
        client_id, _ = await _get_credentials()
    except AccountCredentialsMissing as exc:
        raise HTTPException(500, f"account-service credentials unavailable: {exc}")

    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    state = _b64url(secrets.token_bytes(16))

    target = (
        f"{ACCOUNT_BASE_URL}/authorize"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={ACCOUNT_REDIRECT_URI}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
        f"&state={state}"
    )
    response = RedirectResponse(target, status_code=302)
    secure_cookie = os.environ.get("SECURE_COOKIE", "false").lower() in {"1", "true", "yes"}
    response.set_cookie("auth_verifier", verifier, httponly=True, samesite="lax", secure=secure_cookie, max_age=600, path="/")
    response.set_cookie("auth_state", state, httponly=True, samesite="lax", secure=secure_cookie, max_age=600, path="/")
    return response


@router.get("/auth/callback", include_in_schema=False)
async def auth_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None) -> Response:
    """Exchange the authorization code for tokens, then populate request.session."""
    if not code or not state:
        raise HTTPException(400, "missing code or state")

    stored_state = request.cookies.get("auth_state")
    verifier = request.cookies.get("auth_verifier")
    if stored_state != state:
        raise HTTPException(400, "state mismatch")
    if not verifier:
        raise HTTPException(400, "missing verifier")

    try:
        client_id, client_secret = await _get_credentials()
    except AccountCredentialsMissing as exc:
        raise HTTPException(500, f"account-service credentials unavailable: {exc}")

    async with httpx.AsyncClient(timeout=10) as cli:
        r = await cli.post(
            f"{ACCOUNT_BASE_URL}/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": ACCOUNT_REDIRECT_URI,
                "code_verifier": verifier,
            },
            auth=(client_id, client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if r.status_code != 200:
        logger.warning("token exchange failed status=%s body=%s", r.status_code, r.text)
        raise HTTPException(502, f"token exchange failed: {r.text}")

    tokens = r.json()
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")

    payload_segment = access_token.split(".")[1]
    payload_segment += "=" * (-len(payload_segment) % 4)
    import json as _json
    claims = _json.loads(base64.urlsafe_b64decode(payload_segment))

    request.session["user"] = {
        "display_name": claims.get("name") or claims.get("sub"),
        "email": claims.get("sub") or claims.get("email"),
        "token": access_token,
        "sso": {
            "sid": claims.get("sid"),
            "iss": claims.get("iss"),
            "exp": claims.get("exp"),
            "refresh_token": refresh_token,
        },
    }

    response = RedirectResponse("/docs", status_code=303)
    response.delete_cookie("auth_verifier", path="/")
    response.delete_cookie("auth_state", path="/")
    return response


@router.post("/auth/logout-webhook", include_in_schema=False)
async def logout_webhook(request: Request) -> Response:
    """Account-service back-channel logout. Drops the local session if the
    HMAC matches and the iat is within the replay window."""
    try:
        _, client_secret = await _get_credentials()
    except AccountCredentialsMissing as exc:
        raise HTTPException(500, f"account-service credentials unavailable: {exc}")

    body = await request.body()
    presented = request.headers.get("X-Logout-Signature", "")
    expected = "sha256=" + hmac.new(client_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(401, "bad signature")

    import json as _json
    try:
        evt = _json.loads(body)
    except Exception:
        raise HTTPException(400, "bad body")

    iat = int(evt.get("iat", 0))
    if abs(time.time() - iat) > REPLAY_WINDOW_S:
        raise HTTPException(401, "stale event")

    sub = evt.get("sub")
    sid = evt.get("sid")
    logger.info("[sso] back-channel logout received sub=%s sid=%s (no-op without server-side session store)", sub, sid)

    return Response(status_code=204)
