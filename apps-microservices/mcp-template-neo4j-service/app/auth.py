import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_admin_token(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    if not x_admin_token or not secrets.compare_digest(x_admin_token, settings.runner_admin_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")
