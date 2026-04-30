from datetime import datetime, timedelta, timezone

from app.core.jwt_tokens import issue_access_token
from app.core.security import generate_random_token, sha256_hex
from app.db.models import RefreshToken


class RefreshInvalid(Exception):
    pass


class RefreshExpired(Exception):
    pass


class RefreshReuseDetected(Exception):
    pass


async def issue_token_pair(
    *,
    sub: str,
    client_id: str,
    encryption_key: str,
    access_ttl_seconds: int,
    refresh_ttl_days: int,
    issuer: str,
    email: str | None = None,
    display_name: str | None = None,
    rotated_from_id=None,
    user_agent: str | None = None,
    ip: str | None = None,
) -> dict:
    raw_refresh = generate_random_token(32)
    now = datetime.now(timezone.utc)
    await RefreshToken.create(
        token_hash=sha256_hex(raw_refresh),
        client_id=client_id,
        sub=sub,
        user_email=email,
        user_display_name=display_name,
        expires_at=now + timedelta(days=refresh_ttl_days),
        rotated_from_id=rotated_from_id,
        user_agent=user_agent,
        ip=ip,
    )
    access = await issue_access_token(
        sub=sub,
        client_id=client_id,
        encryption_key=encryption_key,
        ttl_seconds=access_ttl_seconds,
        issuer=issuer,
        email=email,
        display_name=display_name,
    )
    return {
        "access_token": access,
        "refresh_token": raw_refresh,
        "token_type": "Bearer",
        "expires_in": access_ttl_seconds,
    }


async def _lookup(raw_refresh: str) -> RefreshToken:
    h = sha256_hex(raw_refresh)
    row = await RefreshToken.filter(token_hash=h).first()
    if not row:
        raise RefreshInvalid("unknown refresh")
    return row


async def rotate_refresh(
    *,
    raw_refresh: str,
    client_id: str,
    encryption_key: str,
    access_ttl_seconds: int,
    refresh_ttl_days: int,
    issuer: str,
) -> dict:
    row = await _lookup(raw_refresh)
    if row.client_id != client_id:
        raise RefreshInvalid("client mismatch")
    if row.revoked_at is not None:
        # Reuse path: detect rotation child and revoke chain.
        children = await RefreshToken.filter(
            rotated_from_id=row.id
        ).exists()
        if children:
            await RefreshToken.filter(
                client_id=row.client_id, sub=row.sub
            ).update(revoked_at=datetime.now(timezone.utc))
            raise RefreshReuseDetected("reuse detected — chain revoked")
        raise RefreshInvalid("refresh revoked")
    if row.expires_at <= datetime.now(timezone.utc):
        raise RefreshExpired("expired")

    # Mark old as revoked + issue new with rotated_from_id pointing to old.
    row.revoked_at = datetime.now(timezone.utc)
    await row.save()
    return await issue_token_pair(
        sub=row.sub,
        client_id=row.client_id,
        encryption_key=encryption_key,
        access_ttl_seconds=access_ttl_seconds,
        refresh_ttl_days=refresh_ttl_days,
        issuer=issuer,
        email=row.user_email,
        display_name=row.user_display_name,
        rotated_from_id=row.id,
    )


async def revoke_chain(*, raw_refresh: str) -> None:
    row = await _lookup(raw_refresh)
    await RefreshToken.filter(client_id=row.client_id, sub=row.sub).update(
        revoked_at=datetime.now(timezone.utc)
    )
