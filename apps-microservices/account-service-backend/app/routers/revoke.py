from fastapi import APIRouter, HTTPException

from app.schemas import ErrorResponse, RevokeRequest
from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidSecret,
    validate_client_credentials,
)
from app.services.token_service import RefreshInvalid, revoke_chain

router = APIRouter()


def _err(status: int, code: str):
    raise HTTPException(
        status_code=status,
        detail=ErrorResponse(error=code).model_dump(exclude_none=True),
    )


@router.post("/revoke", tags=["oauth"])
async def revoke(req: RevokeRequest):
    try:
        await validate_client_credentials(req.client_id, req.client_secret)
    except (ClientNotFound, ClientInactive, InvalidSecret):
        _err(401, "invalid_client")
    try:
        await revoke_chain(raw_refresh=req.refresh_token)
    except RefreshInvalid:
        pass  # idempotent per RFC 7009
    return {"revoked": True}
