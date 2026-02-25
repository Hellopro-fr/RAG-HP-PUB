"""
Shared token library for API Gateway.

Responsibilities:
- Generate opaque refresh tokens (UUID v4)
- Generate short-lived JWT access tokens (HS256)
- Verify / decode access tokens
"""

import os
import logging
from datetime import datetime, timedelta, timezone

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

logger = logging.getLogger("token_lib")

# ─── Configuration (resolved from env at import time) ─────────────────────────
JWT_SECRET: str = os.environ.get("JWT_SECRET", "changeme-jwt-secret")
JWT_ALGO: str = os.environ.get("JWT_ALGO", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
)


# ─── Refresh token helpers ─────────────────────────────────────────────────────


def generate_refresh_token(service_name: str) -> str:
    """Generate a signed JWT refresh token (no expiry) for a service."""
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": service_name,
        "type": "refresh",
        "iat": now,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    logger.debug(
        f"[token_lib] Refresh token (JWT) generated for service='{service_name}'"
    )
    return token


# ─── Access token helpers ──────────────────────────────────────────────────────


def generate_access_token(
    service_name: str,
    refresh_token_id: int,
    expire_minutes: int | None = None,
) -> str:
    """
    Generate a signed JWT access token for a service.

    Claims:
        sub  : service_name
        rtid : refresh_token DB primary key (for fast revocation check)
        iat  : issued-at timestamp
        exp  : expiry timestamp
    """
    expire = expire_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    now = datetime.now(tz=timezone.utc)

    payload = {
        "sub": service_name,
        "rtid": refresh_token_id,
        "iat": now,
        "exp": now + timedelta(minutes=expire),
    }

    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)
    logger.debug(
        f"[token_lib] Access token generated for service='{service_name}' "
        f"expire_minutes={expire}"
    )
    return token


def verify_access_token(token: str) -> dict:
    """
    Decode and verify a JWT access token.

    Returns the decoded payload dict on success.
    Raises:
        jwt.ExpiredSignatureError  — token is expired
        jwt.InvalidTokenError      — token is malformed / invalid signature
    """
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except ExpiredSignatureError:
        logger.warning("[token_lib] Access token expired.")
        raise
    except InvalidTokenError as exc:
        logger.warning(f"[token_lib] Invalid access token: {exc}")
        raise


# ─── Convenience class (optional facade) ──────────────────────────────────────


class TokenService:
    """Stateless facade that wraps the module-level helpers."""

    @staticmethod
    def new_refresh_token(service_name: str) -> str:
        return generate_refresh_token(service_name)

    @staticmethod
    def new_access_token(service_name: str, refresh_token_id: int) -> str:
        return generate_access_token(service_name, refresh_token_id)

    @staticmethod
    def decode_access_token(token: str) -> dict:
        return verify_access_token(token)
