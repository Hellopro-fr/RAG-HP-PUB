"""Signed rcf_session JWT (HS256, SESSION_SECRET). Parity with libs/auth/node session.ts."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

import jwt

SESSION_COOKIE = "rcf_session"


def _session_secret() -> str:
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if not secret:
        raise RuntimeError("[account-auth] Missing SESSION_SECRET")
    return secret


@dataclass(frozen=True)
class SessionClaims:
    email: str
    name: str | None = None


def create_session_token(claims: SessionClaims, ttl_seconds: int) -> str:
    now = int(time.time())
    payload = {"sub": claims.email, "name": claims.name, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, _session_secret(), algorithm="HS256")


def read_session(token: str | None) -> SessionClaims | None:
    if not token:
        return None
    secret = _session_secret()  # raise loudly on misconfig, before the try
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    email = payload.get("sub")
    if not email:
        return None
    return SessionClaims(email=email, name=payload.get("name"))
