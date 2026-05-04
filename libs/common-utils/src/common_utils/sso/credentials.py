"""Resolve account-service OAuth2 client credentials by SERVICE_NAME.

Convention: each service container sets `SERVICE_NAME` (e.g. `api-gateway`).
The helper looks up two env vars derived from that name:

    SERVICE_NAME=api-gateway
        -> ACCOUNT_CLIENT_ID_API_GATEWAY
        -> ACCOUNT_CLIENT_SECRET_API_GATEWAY

If the prefixed vars are not set, falls back to plain `ACCOUNT_CLIENT_ID`
and `ACCOUNT_CLIENT_SECRET` so single-service deployments keep working
without any rename.

Used by api-gateway/app/routers/sso.py and any other Python service that
acts as an OAuth2 client of account-service.
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
        "(or plain ACCOUNT_CLIENT_ID + ACCOUNT_CLIENT_SECRET as fallback)."
    )
