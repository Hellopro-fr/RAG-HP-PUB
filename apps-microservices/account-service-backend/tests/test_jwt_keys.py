from cryptography.fernet import Fernet

from app.core.jwt_keys import (
    decrypt_private_pem,
    encrypt_private_pem,
    ensure_signing_key,
    get_active_signing_key,
    jwks_response,
)
from app.db.models import SigningKey


def _fernet_key() -> str:
    return Fernet.generate_key().decode()


async def test_ensure_signing_key_creates_first_key():
    key = await ensure_signing_key(encryption_key=_fernet_key())
    assert key.kid
    assert key.is_active is True
    assert "BEGIN PUBLIC KEY" in key.public_pem


async def test_ensure_signing_key_reuses_active():
    fk = _fernet_key()
    a = await ensure_signing_key(encryption_key=fk)
    b = await ensure_signing_key(encryption_key=fk)
    assert a.kid == b.kid


async def test_encrypt_decrypt_roundtrip():
    fk = _fernet_key()
    enc = encrypt_private_pem("private-pem-bytes", fk)
    assert enc != "private-pem-bytes"
    assert decrypt_private_pem(enc, fk) == "private-pem-bytes"


async def test_get_active_signing_key_returns_only_active():
    fk = _fernet_key()
    await ensure_signing_key(encryption_key=fk)
    await SigningKey.all().update(is_active=False)
    new = await ensure_signing_key(encryption_key=fk)
    active = await get_active_signing_key()
    assert active.kid == new.kid


async def test_jwks_response_shape():
    fk = _fernet_key()
    await ensure_signing_key(encryption_key=fk)
    jwks = await jwks_response()
    assert "keys" in jwks
    assert jwks["keys"][0]["kty"] == "RSA"
    assert jwks["keys"][0]["alg"] == "RS256"
    assert jwks["keys"][0]["use"] == "sig"
    assert "kid" in jwks["keys"][0]
    assert "n" in jwks["keys"][0]
    assert "e" in jwks["keys"][0]
