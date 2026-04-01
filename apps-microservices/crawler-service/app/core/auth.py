import logging
from typing import Optional
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> Optional[str]:
    """
    Verifies the API key if API_KEY is configured in settings.
    If API_KEY is not set (None), authentication is disabled (open access).
    If API_KEY is set, requests must include a valid X-API-Key header.
    """
    if not settings.API_KEY:
        return None  # Auth disabled

    if not api_key or api_key != settings.API_KEY:
        logger.warning(f"Unauthorized API request (invalid or missing API key).")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key."
        )
    return api_key
