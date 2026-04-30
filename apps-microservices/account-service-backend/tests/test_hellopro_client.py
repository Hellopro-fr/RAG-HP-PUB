import httpx
import pytest
import respx

from app.services.hellopro_client import (
    HelloProAuthError,
    HelloProUnavailable,
    validate_credentials,
)

URL = "https://auth.hellopro.fr/api/login"


@respx.mock
async def test_validate_credentials_ok():
    respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "token": "upstream-token",
                "email": "u@hellopro.fr",
                "display_name": "U",
            },
        )
    )
    info = await validate_credentials("u@hellopro.fr", "p", URL, timeout=2.0)
    assert info["email"] == "u@hellopro.fr"
    assert info["display_name"] == "U"


@respx.mock
async def test_validate_credentials_401_raises_auth_error():
    respx.post(URL).mock(return_value=httpx.Response(401))
    with pytest.raises(HelloProAuthError):
        await validate_credentials("u", "p", URL, timeout=2.0)


@respx.mock
async def test_validate_credentials_5xx_retried_then_unavailable():
    route = respx.post(URL).mock(
        side_effect=[httpx.Response(500), httpx.Response(503)]
    )
    with pytest.raises(HelloProUnavailable):
        await validate_credentials("u", "p", URL, timeout=2.0)
    assert route.call_count == 2


@respx.mock
async def test_validate_credentials_timeout_unavailable():
    respx.post(URL).mock(side_effect=httpx.ConnectTimeout("nope"))
    with pytest.raises(HelloProUnavailable):
        await validate_credentials("u", "p", URL, timeout=0.1)
