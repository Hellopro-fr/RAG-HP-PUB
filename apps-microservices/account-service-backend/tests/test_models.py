from datetime import datetime, timedelta, timezone

from app.db.models import (
    AuthorizationCode,
    OAuthClient,
    RefreshToken,
    SigningKey,
)


async def test_oauth_client_roundtrip():
    c = await OAuthClient.create(
        client_id="svc",
        client_secret_hash="h",
        name="Service",
        redirect_uris=["https://svc.hellopro.eu/cb"],
    )
    fetched = await OAuthClient.get(client_id="svc")
    assert fetched.id == c.id
    assert fetched.skip_consent is True
    assert fetched.is_active is True


async def test_auth_code_roundtrip():
    await AuthorizationCode.create(
        code_hash="abc",
        client_id="svc",
        sub="user@x",
        code_challenge="ch",
        code_challenge_method="S256",
        redirect_uri="https://svc.hellopro.eu/cb",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=60),
    )
    assert await AuthorizationCode.filter(code_hash="abc").exists()


async def test_refresh_token_roundtrip():
    await RefreshToken.create(
        token_hash="th",
        client_id="svc",
        sub="user@x",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert await RefreshToken.filter(token_hash="th").exists()


async def test_signing_key_roundtrip():
    await SigningKey.create(kid="k1", private_pem_encrypted="x", public_pem="y")
    assert await SigningKey.filter(kid="k1").exists()
