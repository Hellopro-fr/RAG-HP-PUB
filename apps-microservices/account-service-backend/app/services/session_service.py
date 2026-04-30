"""
Login-session lifecycle for the simplified service-name flow.

Used by routers/login_simple.py:
- issue_login_session: issued after HelloPro validation, returned (raw)
  in the redirect URL.
- consume_login_session: hit by the consumer's callback in exchange for
  access+refresh tokens. One-shot, short-lived (default 60s),
  bound to the service that initiated the login.
"""

from datetime import datetime, timedelta, timezone

from app.core.security import generate_random_token, sha256_hex
from app.db.models import LoginSession


class SessionInvalid(Exception):
    pass


class SessionExpired(Exception):
    pass


async def issue_login_session(
    *,
    client_id: str,
    sub: str,
    email: str | None,
    display_name: str | None,
    next_path: str = "/",
    ttl_seconds: int = 60,
) -> str:
    raw = generate_random_token(32)
    now = datetime.now(timezone.utc)
    await LoginSession.create(
        token_hash=sha256_hex(raw),
        client_id=client_id,
        sub=sub,
        user_email=email,
        user_display_name=display_name,
        next_path=next_path or "/",
        expires_at=now + timedelta(seconds=ttl_seconds),
    )
    return raw


async def consume_login_session(
    raw_token: str, *, expected_client_id: str
) -> LoginSession:
    h = sha256_hex(raw_token)
    row = await LoginSession.filter(token_hash=h).first()
    if not row:
        raise SessionInvalid("unknown session")
    if row.client_id != expected_client_id:
        raise SessionInvalid("service mismatch")
    if row.consumed_at is not None:
        raise SessionInvalid("already consumed")
    if row.expires_at <= datetime.now(timezone.utc):
        raise SessionExpired("expired")
    row.consumed_at = datetime.now(timezone.utc)
    await row.save()
    return row
