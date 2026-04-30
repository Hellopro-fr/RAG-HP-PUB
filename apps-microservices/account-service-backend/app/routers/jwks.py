from fastapi import APIRouter

from app.core.jwt_keys import jwks_response

router = APIRouter()


@router.get("/.well-known/jwks.json", tags=["oauth"])
async def jwks() -> dict:
    return await jwks_response()
