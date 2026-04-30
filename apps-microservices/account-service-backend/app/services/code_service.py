from datetime import datetime, timedelta, timezone

from app.core.security import generate_random_token, sha256_hex
from app.db.models import AuthorizationCode


class CodeInvalid(Exception):
    pass


class CodeExpired(Exception):
    pass


class CodeAlreadyConsumed(Exception):
    pass


async def issue_code(
    *,
    client_id: str,
    sub: str,
    code_challenge: str,
    code_challenge_method: str,
    redirect_uri: str,
    ttl_seconds: int,
    email: str | None = None,
    display_name: str | None = None,
) -> str:
    raw = generate_random_token(32)
    now = datetime.now(timezone.utc)
    await AuthorizationCode.create(
        code_hash=sha256_hex(raw),
        client_id=client_id,
        sub=sub,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        redirect_uri=redirect_uri,
        expires_at=now + timedelta(seconds=ttl_seconds),
        user_email=email,
        user_display_name=display_name,
    )
    return raw


async def consume_code(raw: str, *, expected_redirect_uri: str) -> AuthorizationCode:
    h = sha256_hex(raw)
    record = await AuthorizationCode.filter(code_hash=h).first()
    if not record:
        raise CodeInvalid("unknown code")
    if record.consumed_at is not None:
        raise CodeAlreadyConsumed("already consumed")
    if record.redirect_uri != expected_redirect_uri:
        raise CodeInvalid("redirect_uri mismatch")
    if record.expires_at <= datetime.now(timezone.utc):
        raise CodeExpired("expired")
    record.consumed_at = datetime.now(timezone.utc)
    await record.save()
    return record
