from app.core.security import generate_random_token, hash_secret, verify_secret
from app.db.models import OAuthClient


class ClientNotFound(Exception):
    pass


class ClientInactive(Exception):
    pass


class InvalidSecret(Exception):
    pass


class InvalidRedirectUri(Exception):
    pass


async def create_client(
    *,
    client_id: str,
    name: str,
    redirect_uris: list[str],
    post_logout_redirect_uris: list[str] | None = None,
    skip_consent: bool = True,
) -> str:
    if await OAuthClient.filter(client_id=client_id).exists():
        raise ValueError(f"client_id {client_id} already exists")
    raw = generate_random_token(32)
    await OAuthClient.create(
        client_id=client_id,
        client_secret_hash=hash_secret(raw),
        name=name,
        redirect_uris=redirect_uris,
        post_logout_redirect_uris=post_logout_redirect_uris or [],
        skip_consent=skip_consent,
        is_active=True,
    )
    return raw


async def get_client_by_id(client_id: str) -> OAuthClient:
    c = await OAuthClient.filter(client_id=client_id).first()
    if not c:
        raise ClientNotFound(client_id)
    return c


async def list_clients() -> list[OAuthClient]:
    return await OAuthClient.all()


async def delete_client(client_id: str) -> None:
    c = await get_client_by_id(client_id)
    c.is_active = False
    await c.save()


async def validate_client_credentials(client_id: str, secret: str) -> OAuthClient:
    c = await get_client_by_id(client_id)
    if not c.is_active:
        raise ClientInactive(client_id)
    if not verify_secret(secret, c.client_secret_hash):
        raise InvalidSecret(client_id)
    return c


def validate_redirect_uri(client: OAuthClient, uri: str) -> None:
    if uri not in (client.redirect_uris or []):
        raise InvalidRedirectUri(uri)
