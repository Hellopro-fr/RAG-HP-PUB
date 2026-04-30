"""
Demo client integration with `account-service` (simplified service-name flow).

Flow:
- GET  /auth/account/start    -> redirect to account-service signin with
                                 ?service=<name>&next=<path>
- GET  /auth/account/callback -> exchange login_session for tokens via
                                 POST /sessions/exchange (no client_secret),
                                 set HttpOnly cookies, redirect to `next`.
- POST /auth/account/logout   -> revoke refresh token + clear cookies.

The consumer service holds NO client_secret and generates NO PKCE pair.
The only configuration it needs is its registered service name (and the
URLs of the account-service endpoints).
"""

import logging
import os
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

logger = logging.getLogger("auth_account")
router = APIRouter(tags=["Account OAuth"])

ACCOUNT_SIGNIN_URL = os.environ.get(
    "ACCOUNT_SIGNIN_URL",
    os.environ.get(
        "OAUTH_AUTHORIZE_URL", "http://account-service-frontend:8080/signin"
    ),
)
ACCOUNT_LOGIN_URL = os.environ.get(
    "ACCOUNT_LOGIN_URL", "http://account-service-backend:8000/login"
)
ACCOUNT_EXCHANGE_URL = os.environ.get(
    "ACCOUNT_EXCHANGE_URL",
    "http://account-service-backend:8000/sessions/exchange",
)
ACCOUNT_REVOKE_URL = os.environ.get(
    "ACCOUNT_REVOKE_URL", "http://account-service-backend:8000/revoke"
)
ACCOUNT_SERVICE_NAME = os.environ.get(
    "ACCOUNT_SERVICE_NAME",
    os.environ.get("OAUTH_ACCOUNT_CLIENT_ID", "api-gateway"),
)
# Optional: for legacy /revoke (still requires client_secret on the
# account-service side). Leave blank to skip server-side revocation.
ACCOUNT_CLIENT_SECRET = os.environ.get("OAUTH_ACCOUNT_CLIENT_SECRET", "")


@router.get("/auth/account/start")
async def auth_start(request: Request, next: str = "/"):
    qs = urlencode({"service": ACCOUNT_SERVICE_NAME, "next": next})
    return RedirectResponse(f"{ACCOUNT_SIGNIN_URL}?{qs}", status_code=303)


@router.get("/auth/account/callback")
async def auth_callback(
    request: Request,
    login_session: str | None = None,
    next: str = "/",
    error: str | None = None,
):
    if error:
        raise HTTPException(400, f"login error: {error}")
    if not login_session:
        raise HTTPException(400, "missing login_session")

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            ACCOUNT_EXCHANGE_URL,
            json={
                "service": ACCOUNT_SERVICE_NAME,
                "login_session": login_session,
            },
        )
    if r.status_code != 200:
        logger.warning("exchange failed: %s %s", r.status_code, r.text)
        raise HTTPException(502, f"exchange failed: {r.text}")
    tokens = r.json()

    body = (
        "<!doctype html><html><body>"
        "<h1>Login OK</h1>"
        f"<p>access_token (jwt, {tokens['expires_in']}s):"
        f" <code>{tokens['access_token']}</code></p>"
        f"<p>refresh_token: <code>{tokens['refresh_token']}</code></p>"
        f'<p><a href="{next}">Continue</a></p>'
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
    if refresh and ACCOUNT_CLIENT_SECRET:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                ACCOUNT_REVOKE_URL,
                json={
                    "refresh_token": refresh,
                    "client_id": ACCOUNT_SERVICE_NAME,
                    "client_secret": ACCOUNT_CLIENT_SECRET,
                },
            )
    response = Response(content="logged out", media_type="text/plain")
    response.delete_cookie("account_access_token", path="/")
    response.delete_cookie("account_refresh_token", path="/auth/account")
    return response
