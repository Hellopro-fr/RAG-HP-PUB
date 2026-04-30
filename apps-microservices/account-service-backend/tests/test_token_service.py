import pytest
from cryptography.fernet import Fernet

from app.core.jwt_keys import ensure_signing_key
from app.db.models import RefreshToken
from app.services.token_service import (
    RefreshExpired,
    RefreshInvalid,
    RefreshReuseDetected,
    issue_token_pair,
    revoke_chain,
    rotate_refresh,
)


def _fk() -> str:
    return Fernet.generate_key().decode()


async def _setup():
    fk = _fk()
    await ensure_signing_key(encryption_key=fk)
    return fk


async def test_issue_token_pair_returns_access_and_refresh():
    fk = await _setup()
    pair = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30,
        issuer="iss", email="u@x", display_name="U",
    )
    assert pair["token_type"] == "Bearer"
    assert pair["expires_in"] == 900
    assert pair["access_token"]
    assert pair["refresh_token"]
    assert await RefreshToken.filter(client_id="svc", sub="u@x").exists()


async def test_rotate_refresh_marks_old_revoked_and_issues_new():
    fk = await _setup()
    p1 = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    p2 = await rotate_refresh(
        raw_refresh=p1["refresh_token"], client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    assert p2["refresh_token"] != p1["refresh_token"]
    rows = await RefreshToken.filter(client_id="svc", sub="u@x").all()
    assert any(r.revoked_at is not None for r in rows)
    assert any(r.revoked_at is None for r in rows)


async def test_rotate_refresh_unknown_raises():
    fk = await _setup()
    with pytest.raises(RefreshInvalid):
        await rotate_refresh(
            raw_refresh="bogus", client_id="svc", encryption_key=fk,
            access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
        )


async def test_rotate_refresh_reuse_revokes_chain():
    fk = await _setup()
    p1 = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    await rotate_refresh(
        raw_refresh=p1["refresh_token"], client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    with pytest.raises(RefreshReuseDetected):
        await rotate_refresh(
            raw_refresh=p1["refresh_token"], client_id="svc", encryption_key=fk,
            access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
        )
    rows = await RefreshToken.filter(client_id="svc", sub="u@x").all()
    assert all(r.revoked_at is not None for r in rows)


async def test_revoke_chain_marks_all_revoked():
    fk = await _setup()
    p = await issue_token_pair(
        sub="u@x", client_id="svc", encryption_key=fk,
        access_ttl_seconds=900, refresh_ttl_days=30, issuer="iss",
    )
    await revoke_chain(raw_refresh=p["refresh_token"])
    rows = await RefreshToken.filter(client_id="svc", sub="u@x").all()
    assert all(r.revoked_at is not None for r in rows)
