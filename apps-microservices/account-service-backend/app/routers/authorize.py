import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request

from app.core.settings import get_settings
from app.rate_limit import limiter
from app.schemas import (
    AuthorizeConsentResponse,
    AuthorizeRedirectResponse,
    AuthorizeRequest,
    ErrorResponse,
)
from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidRedirectUri,
    get_client_by_id,
    validate_redirect_uri,
)
from app.services.code_service import issue_code
from app.services.hellopro_client import (
    HelloProAuthError,
    HelloProUnavailable,
    validate_credentials,
)

logger = logging.getLogger("authorize")
router = APIRouter()


def _err(status: int, code: str, desc: str | None = None):
    raise HTTPException(
        status_code=status,
        detail=ErrorResponse(error=code, error_description=desc).model_dump(
            exclude_none=True
        ),
    )


@router.post(
    "/authorize",
    tags=["oauth"],
    response_model=AuthorizeRedirectResponse | AuthorizeConsentResponse,
)
@limiter.limit("10/minute")
async def authorize(request: Request, req: AuthorizeRequest):
    settings = get_settings()
    try:
        client = await get_client_by_id(req.client_id)
    except ClientNotFound:
        _err(400, "invalid_client", "unknown client_id")
    if not client.is_active:
        _err(400, "invalid_client", "client inactive")

    try:
        validate_redirect_uri(client, req.redirect_uri)
    except InvalidRedirectUri:
        _err(400, "invalid_redirect_uri")

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

    raw_code = await issue_code(
        client_id=client.client_id,
        sub=user["sub"],
        code_challenge=req.code_challenge,
        code_challenge_method=req.code_challenge_method,
        redirect_uri=req.redirect_uri,
        ttl_seconds=settings.AUTH_CODE_EXPIRE_SECONDS,
        email=user["email"],
        display_name=user["display_name"],
    )

    qs = urlencode({"code": raw_code, "state": req.state})
    redirect_url = f"{req.redirect_uri}?{qs}"
    return AuthorizeRedirectResponse(redirect=redirect_url)
