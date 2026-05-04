"""Login routes — delegated to account-service SSO.

GET  /login   → if already authenticated, 303 to /docs; else 302 to /auth/login
                which kicks off the OAuth 2.1 + PKCE flow against account-service.
GET  /logout  → clear local session, redirect to /login.

POST /login (form-based hellopro proxy) is removed: the login form is now hosted
by account-service. Direct callers should switch to /auth/login.
"""

from __future__ import annotations

import logging
import os

import jwt
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from jwt import ExpiredSignatureError, InvalidTokenError

router = APIRouter(tags=["Authentication"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("auth")

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGO = os.environ.get("JWT_ALGO")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE")


@router.get("/login", include_in_schema=False)
async def login_page(request: Request):
    """If session valid, jump straight to /docs. Else hand off to /auth/login (PKCE start)."""
    user = request.session.get("user")
    if user and "token" in user:
        token = user["token"]
        try:
            jwt.decode(
                token, JWT_SECRET, algorithms=[JWT_ALGO],
                options={"verify_aud": False},
            )
            return RedirectResponse(url="/docs", status_code=303)
        except (ExpiredSignatureError, InvalidTokenError):
            request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=302)


@router.get("/logout", include_in_schema=False)
async def logout(request: Request):
    """Clear local session and bounce back to /login (which then re-enters SSO)."""
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
