"""Resolve account-service OAuth2 client credentials by SERVICE_NAME.

Two strategies:

1. **Env vars** (sync, no I/O). Convention:

       SERVICE_NAME=api-gateway
           -> ACCOUNT_CLIENT_ID_API_GATEWAY
           -> ACCOUNT_CLIENT_SECRET_API_GATEWAY

   Falls back to plain ACCOUNT_CLIENT_ID / ACCOUNT_CLIENT_SECRET when
   the prefixed pair isn't set.

2. **Internal API call** (async). Fetches the credentials from
   ``GET {ACCOUNT_BASE_URL}/internal/credentials/{name}`` with an
   ``X-Admin-Token`` header. The endpoint is admin-token-gated on the
   account-service side and decrypts the secret server-side, so
   consumer services never need MySQL access or the AES key.

Used by api-gateway/app/routers/sso.py and any other Python service
that acts as an OAuth2 client of account-service.
"""

from __future__ import annotations

import os
import re
from typing import Optional, Tuple


class AccountCredentialsMissing(RuntimeError):
    """Raised when neither prefixed nor fallback env vars are set."""


_SLUG_RE = re.compile(r"[^A-Z0-9]+")


def derive_env_keys(service_name: str) -> Tuple[str, str]:
    """Map a service name to the (client_id_env, client_secret_env) pair.

    >>> derive_env_keys("api-gateway")
    ('ACCOUNT_CLIENT_ID_API_GATEWAY', 'ACCOUNT_CLIENT_SECRET_API_GATEWAY')
    """
    slug = _SLUG_RE.sub("_", service_name.upper()).strip("_")
    return f"ACCOUNT_CLIENT_ID_{slug}", f"ACCOUNT_CLIENT_SECRET_{slug}"


def get_account_credentials(service_name: Optional[str] = None) -> Tuple[str, str]:
    """Return ``(client_id, client_secret)`` for the named service.

    If `service_name` is omitted, reads `SERVICE_NAME` from the environment.
    Falls back to plain `ACCOUNT_CLIENT_ID` / `ACCOUNT_CLIENT_SECRET` when
    the prefixed pair is not defined.
    """
    name = service_name or os.environ.get("SERVICE_NAME", "").strip()

    if name:
        id_key, sec_key = derive_env_keys(name)
        cid = os.environ.get(id_key, "")
        sec = os.environ.get(sec_key, "")
        if cid and sec:
            return cid, sec

    cid = os.environ.get("ACCOUNT_CLIENT_ID", "")
    sec = os.environ.get("ACCOUNT_CLIENT_SECRET", "")
    if cid and sec:
        return cid, sec

    raise AccountCredentialsMissing(
        "Account-service OAuth2 credentials not configured. "
        "Set ACCOUNT_CLIENT_ID_<SERVICE_NAME> + ACCOUNT_CLIENT_SECRET_<SERVICE_NAME> "
        "(or plain ACCOUNT_CLIENT_ID + ACCOUNT_CLIENT_SECRET as fallback), "
        "or call get_account_credentials_from_db() for a DB lookup."
    )


async def get_account_client_from_api(
    service_name: Optional[str] = None,
    *,
    base_url: Optional[str] = None,
    admin_token: Optional[str] = None,
    timeout: float = 5.0,
) -> dict:
    """Fetch the full registered client record from account-service over HTTP.

    Calls ``GET {base_url}/internal/credentials/{service_name}`` with an
    ``X-Admin-Token`` header. Returns ``{client_id, client_secret,
    redirect_uris, name}``. The endpoint is admin-gated on the
    account-service side and decrypts the secret server-side, so this
    consumer never needs MySQL access or the AES key.

    Resolution order:
      ``service_name`` arg    or  ``SERVICE_NAME`` env
      ``base_url`` arg        or  ``ACCOUNT_BASE_URL`` env
      ``admin_token`` arg     or  ``ACCOUNT_INTERNAL_TOKEN`` env

    Lazy imports ``httpx`` — install it on the consumer (api-gateway has it).
    """
    name = service_name or os.environ.get("SERVICE_NAME", "").strip()
    if not name:
        raise AccountCredentialsMissing("service_name required (or set SERVICE_NAME env)")

    base = (base_url or os.environ.get("ACCOUNT_BASE_URL", "")).rstrip("/")
    if not base:
        raise AccountCredentialsMissing("ACCOUNT_BASE_URL not set")

    token = admin_token or os.environ.get("ACCOUNT_INTERNAL_TOKEN", "")
    if not token:
        raise AccountCredentialsMissing("ACCOUNT_INTERNAL_TOKEN not set")

    import httpx  # lazy
    from urllib.parse import quote

    url = f"{base}/internal/credentials/{quote(name, safe='')}"
    async with httpx.AsyncClient(timeout=timeout) as cli:
        r = await cli.get(url, headers={"X-Admin-Token": token})

    if r.status_code == 404:
        raise AccountCredentialsMissing(
            f"no active service named {name!r} in account-service"
        )
    if r.status_code != 200:
        raise AccountCredentialsMissing(
            f"internal credentials endpoint returned {r.status_code}: {r.text[:200]}"
        )
    body = r.json()
    if not body.get("client_id") or not body.get("client_secret"):
        raise AccountCredentialsMissing("internal credentials response missing fields")
    return body


async def get_account_credentials_from_api(
    service_name: Optional[str] = None,
    *,
    base_url: Optional[str] = None,
    admin_token: Optional[str] = None,
    timeout: float = 5.0,
) -> Tuple[str, str]:
    """Tuple-only wrapper around get_account_client_from_api(): returns
    just (client_id, client_secret) for callers that don't need redirect_uris."""
    body = await get_account_client_from_api(
        service_name, base_url=base_url, admin_token=admin_token, timeout=timeout
    )
    return body["client_id"], body["client_secret"]
