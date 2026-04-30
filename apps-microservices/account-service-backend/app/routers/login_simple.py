"""
Simplified service-name login flow.

Replaces the OAuth Authorization Code + PKCE round-trip from the
consumer's point of view: the consumer never holds a client_secret
and never builds a code_challenge. The only knob it owns is its own
service name (registered in OAuthClient).

Endpoints:
- POST /login              SPA submits {service, username, password, next}
                           -> 200 {redirect: "<service_redirect>?login_session=...&next=..."}
- POST /sessions/exchange  consumer callback POSTs {service, login_session}
                           -> 200 TokenResponse (one-shot)
"""

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request

from app.core.settings import get_settings
from app.rate_limit import limiter
from app.schemas import (
    ErrorResponse,
    ExchangeRequest,
    LoginRequest,
    LoginResponse,
    TokenResponse,
)
from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    get_client_by_id,
)
from app.services.hellopro_client import (
    HelloProAuthError,
    HelloProUnavailable,
    validate_credentials,
)
from app.services.session_service import (
    SessionExpired,
    SessionInvalid,
    consume_login_session,
    issue_login_session,
)
from app.services.token_service import issue_token_pair

logger = logging.getLogger("login_simple")
router = APIRouter()


def _err(status: int, code: str, desc: str | None = None):
    raise HTTPException(
        status_code=status,
        detail=ErrorResponse(error=code, error_description=desc).model_dump(
            exclude_none=True
        ),
    )


@router.post("/login", tags=["login"], response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(request: Request, req: LoginRequest):
    settings = get_settings()
    try:
        client = await get_client_by_id(req.service)
    except ClientNotFound:
        _err(400, "invalid_service", "unknown service")

    if not client.is_active:
        _err(400, "invalid_service", "service inactive")

    redirect_uris = client.redirect_uris or []
    if not redirect_uris:
        _err(500, "service_misconfigured", "no redirect_uri registered")
    redirect_base = redirect_uris[0]

    try:
        user = await validate_credentials(
            req.username,
            req.password,
            str(settings.HELLOPRO_AUTH_URL),
            timeout=settings.HELLOPRO_AUTH_TIMEOUT_SECONDS,
        )
    except HelloProAuthError:
        _err(401, "access_denied")
    except HelloProUnavailable:
        _err(503, "upstream_unavailable")

    raw_session = await issue_login_session(
        client_id=client.client_id,
        sub=user["sub"],
        email=user["email"],
        display_name=user["display_name"],
        next_path=req.next,
        ttl_seconds=settings.AUTH_CODE_EXPIRE_SECONDS,
    )

    qs = urlencode({"login_session": raw_session, "next": req.next or "/"})
    return LoginResponse(redirect=f"{redirect_base}?{qs}")


@router.post(
    "/sessions/exchange",
    tags=["login"],
    response_model=TokenResponse,
)
async def exchange(req: ExchangeRequest):
    settings = get_settings()
    try:
        client = await get_client_by_id(req.service)
    except ClientNotFound:
        _err(400, "invalid_service")
    if not client.is_active:
        _err(400, "invalid_service", "service inactive")

    try:
        sess = await consume_login_session(
            req.login_session, expected_client_id=req.service
        )
    except (SessionInvalid, SessionExpired):
        _err(400, "invalid_session")

    pair = await issue_token_pair(
        sub=sess.sub,
        client_id=req.service,
        encryption_key=settings.JWT_KEY_ENCRYPTION_KEY,
        access_ttl_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_ttl_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
        issuer=settings.JWT_ISSUER,
        email=sess.user_email,
        display_name=sess.user_display_name,
    )
    return TokenResponse(**pair)
