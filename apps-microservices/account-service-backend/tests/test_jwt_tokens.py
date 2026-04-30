import time

import jwt as pyjwt
import pytest
from cryptography.fernet import Fernet

from app.core.jwt_keys import decrypt_private_pem, ensure_signing_key
from app.core.jwt_tokens import decode_access_token, issue_access_token


def _fk() -> str:
    return Fernet.generate_key().decode()


async def test_issue_access_token_has_required_claims():
    fk = _fk()
    key = await ensure_signing_key(encryption_key=fk)
    token = await issue_access_token(
        sub="u@x",
        client_id="svc",
        encryption_key=fk,
        ttl_seconds=900,
        issuer="https://account.hellopro.eu",
        email="u@x",
        display_name="U",
    )
    claims = pyjwt.decode(
        token, key.public_pem, algorithms=["RS256"], audience="svc",
        options={"verify_aud": True}
    )
    assert claims["sub"] == "u@x"
    assert claims["aud"] == "svc"
    assert claims["iss"] == "https://account.hellopro.eu"
    assert claims["email"] == "u@x"
    assert claims["display_name"] == "U"
    assert claims["exp"] > int(time.time())
    assert "jti" in claims
    headers = pyjwt.get_unverified_header(token)
    assert headers["alg"] == "RS256"
    assert headers["kid"] == key.kid


async def test_decode_access_token_round_trip():
    fk = _fk()
    await ensure_signing_key(encryption_key=fk)
    token = await issue_access_token(
        sub="u@x", client_id="svc", encryption_key=fk,
        ttl_seconds=10, issuer="iss",
    )
    claims = await decode_access_token(token, expected_audience="svc")
    assert claims["sub"] == "u@x"


async def test_decode_rejects_alg_none():
    fk = _fk()
    await ensure_signing_key(encryption_key=fk)
    bad = pyjwt.encode({"sub": "x", "aud": "svc"}, key="", algorithm="none")
    with pytest.raises(Exception):
        await decode_access_token(bad, expected_audience="svc")


async def test_decode_rejects_expired():
    fk = _fk()
    await ensure_signing_key(encryption_key=fk)
    token = await issue_access_token(
        sub="u@x", client_id="svc", encryption_key=fk,
        ttl_seconds=-10, issuer="iss",
    )
    with pytest.raises(pyjwt.ExpiredSignatureError):
        await decode_access_token(token, expected_audience="svc")
