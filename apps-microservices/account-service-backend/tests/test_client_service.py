import pytest

from app.services.client_service import (
    ClientInactive,
    ClientNotFound,
    InvalidRedirectUri,
    InvalidSecret,
    create_client,
    delete_client,
    get_client_by_id,
    list_clients,
    validate_client_credentials,
    validate_redirect_uri,
)


async def test_create_client_returns_secret_once():
    raw = await create_client(
        client_id="svc",
        name="Service",
        redirect_uris=["https://svc.hellopro.eu/cb"],
        post_logout_redirect_uris=["https://svc.hellopro.eu/"],
        skip_consent=True,
    )
    assert raw and len(raw) >= 32


async def test_create_client_duplicate_raises():
    await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    with pytest.raises(ValueError):
        await create_client(client_id="svc", name="B", redirect_uris=["https://x"])


async def test_get_client_by_id_returns_row():
    await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    c = await get_client_by_id("svc")
    assert c.name == "A"


async def test_get_client_unknown_raises():
    with pytest.raises(ClientNotFound):
        await get_client_by_id("nope")


async def test_list_clients_returns_all():
    await create_client(client_id="a", name="A", redirect_uris=["https://x"])
    await create_client(client_id="b", name="B", redirect_uris=["https://y"])
    assert {c.client_id for c in await list_clients()} == {"a", "b"}


async def test_delete_client_marks_inactive():
    await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    await delete_client("svc")
    c = await get_client_by_id("svc")
    assert c.is_active is False


async def test_validate_redirect_uri_exact_match():
    await create_client(
        client_id="svc", name="A",
        redirect_uris=["https://svc.hellopro.eu/cb"],
    )
    c = await get_client_by_id("svc")
    validate_redirect_uri(c, "https://svc.hellopro.eu/cb")  # ok
    with pytest.raises(InvalidRedirectUri):
        validate_redirect_uri(c, "https://svc.hellopro.eu/cb/")
    with pytest.raises(InvalidRedirectUri):
        validate_redirect_uri(c, "https://attacker.example/cb")


async def test_validate_credentials_ok_and_wrong_secret():
    raw = await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    c = await validate_client_credentials("svc", raw)
    assert c.client_id == "svc"
    with pytest.raises(InvalidSecret):
        await validate_client_credentials("svc", "wrong")


async def test_validate_credentials_inactive():
    raw = await create_client(client_id="svc", name="A", redirect_uris=["https://x"])
    await delete_client("svc")
    with pytest.raises(ClientInactive):
        await validate_client_credentials("svc", raw)
