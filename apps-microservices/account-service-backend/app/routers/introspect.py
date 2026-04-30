from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core.jwt_tokens import decode_access_token
from app.schemas import ErrorResponse, IntrospectRequest
from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidSecret,
    validate_client_credentials,
)

router = APIRouter()


@router.post("/introspect", tags=["oauth"])
async def introspect(req: IntrospectRequest):
    try:
        await validate_client_credentials(req.client_id, req.client_secret)
    except (ClientNotFound, ClientInactive, InvalidSecret):
        raise HTTPException(
            status_code=401,
            detail=ErrorResponse(error="invalid_client").model_dump(),
        )
    try:
        claims = await decode_access_token(req.token, expected_audience=req.client_id)
    except Exception:
        return JSONResponse({"active": False})
    body = {"active": True}
    for k in ("sub", "aud", "exp", "iat"):
        if claims.get(k) is not None:
            body[k] = claims[k]
    return JSONResponse(body)
