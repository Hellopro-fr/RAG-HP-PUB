import secrets
import time

import jwt as pyjwt

from app.core.jwt_keys import decrypt_private_pem, get_active_signing_key
from app.db.models import SigningKey


async def issue_access_token(
    *,
    sub: str,
    client_id: str,
    encryption_key: str,
    ttl_seconds: int,
    issuer: str,
    email: str | None = None,
    display_name: str | None = None,
) -> str:
    key = await get_active_signing_key()
    now = int(time.time())
    claims: dict = {
        "iss": issuer,
        "sub": sub,
        "aud": client_id,
        "iat": now,
        "exp": now + ttl_seconds,
        "jti": secrets.token_urlsafe(16),
    }
    if email is not None:
        claims["email"] = email
    if display_name is not None:
        claims["display_name"] = display_name
    private_pem = decrypt_private_pem(key.private_pem_encrypted, encryption_key)
    return pyjwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": key.kid})


async def _public_pem_for(kid: str) -> str:
    key = await SigningKey.get(kid=kid)
    return key.public_pem


async def decode_access_token(token: str, *, expected_audience: str) -> dict:
    headers = pyjwt.get_unverified_header(token)
    if headers.get("alg") != "RS256":
        raise pyjwt.InvalidAlgorithmError(f"unexpected alg {headers.get('alg')}")
    public_pem = await _public_pem_for(headers["kid"])
    return pyjwt.decode(
        token,
        public_pem,
        algorithms=["RS256"],
        audience=expected_audience,
        options={"require": ["exp", "iat", "sub", "aud"]},
    )
