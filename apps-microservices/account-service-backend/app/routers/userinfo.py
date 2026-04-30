from fastapi import APIRouter, Header, HTTPException

from app.core.jwt_tokens import decode_access_token
from app.schemas import UserInfoResponse

router = APIRouter()


@router.get("/userinfo", tags=["oauth"], response_model=UserInfoResponse)
async def userinfo(authorization: str | None = Header(None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})
    token = authorization[7:].strip()
    import jwt as pyjwt
    try:
        unverified = pyjwt.decode(token, options={"verify_signature": False})
        aud = unverified.get("aud")
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})
    try:
        claims = await decode_access_token(token, expected_audience=aud)
    except Exception:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})
    return UserInfoResponse(
        sub=claims["sub"],
        email=claims.get("email"),
        display_name=claims.get("display_name"),
    )
