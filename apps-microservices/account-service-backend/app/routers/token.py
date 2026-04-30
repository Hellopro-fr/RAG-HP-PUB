from fastapi import APIRouter, Form, HTTPException, Request

from app.core.security import verify_pkce
from app.core.settings import get_settings
from app.rate_limit import limiter
from app.schemas import ErrorResponse, TokenResponse
from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidSecret,
    validate_client_credentials,
)
from app.services.code_service import (
    CodeAlreadyConsumed,
    CodeExpired,
    CodeInvalid,
    consume_code,
)
from app.services.token_service import (
    RefreshExpired,
    RefreshInvalid,
    RefreshReuseDetected,
    issue_token_pair,
    rotate_refresh,
)

router = APIRouter()


def _err(status: int, code: str, desc: str | None = None):
    raise HTTPException(
        status_code=status,
        detail=ErrorResponse(error=code, error_description=desc).model_dump(
            exclude_none=True
        ),
    )


async def _authn_client(client_id: str, client_secret: str):
    try:
        return await validate_client_credentials(client_id, client_secret)
    except (ClientNotFound, ClientInactive):
        _err(401, "invalid_client", "unknown or inactive client")
    except InvalidSecret:
        _err(401, "invalid_client", "bad secret")


@router.post("/token", tags=["oauth"], response_model=TokenResponse)
@limiter.limit("60/minute")
async def token(
    request: Request,
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    code: str | None = Form(None),
    redirect_uri: str | None = Form(None),
    code_verifier: str | None = Form(None),
    refresh_token: str | None = Form(None),
):
    settings = get_settings()
    await _authn_client(client_id, client_secret)

    if grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier:
            _err(400, "invalid_request", "missing code/redirect_uri/code_verifier")
        try:
            record = await consume_code(code, expected_redirect_uri=redirect_uri)
        except (CodeInvalid, CodeAlreadyConsumed, CodeExpired):
            _err(400, "invalid_grant")
        if not verify_pkce(code_verifier, record.code_challenge, record.code_challenge_method):
            _err(400, "invalid_grant", "PKCE verifier mismatch")
        if record.client_id != client_id:
            _err(400, "invalid_grant", "client mismatch")
        pair = await issue_token_pair(
            sub=record.sub,
            client_id=client_id,
            encryption_key=settings.JWT_KEY_ENCRYPTION_KEY,
            access_ttl_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_ttl_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
            issuer=settings.JWT_ISSUER,
            email=record.user_email,
            display_name=record.user_display_name,
        )
        return TokenResponse(**pair)

    if grant_type == "refresh_token":
        if not refresh_token:
            _err(400, "invalid_request", "missing refresh_token")
        try:
            pair = await rotate_refresh(
                raw_refresh=refresh_token,
                client_id=client_id,
                encryption_key=settings.JWT_KEY_ENCRYPTION_KEY,
                access_ttl_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                refresh_ttl_days=settings.REFRESH_TOKEN_EXPIRE_DAYS,
                issuer=settings.JWT_ISSUER,
            )
        except (RefreshInvalid, RefreshExpired, RefreshReuseDetected):
            _err(400, "invalid_grant")
        return TokenResponse(**pair)

    _err(400, "unsupported_grant_type")
