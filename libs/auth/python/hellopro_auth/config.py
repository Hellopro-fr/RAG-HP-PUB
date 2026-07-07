"""Auth config: resolve account-service OAuth client creds + settings from env.
Credential resolution delegates to common_utils.sso (shared convention)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from common_utils.sso import get_account_credentials


def parse_admin_emails(raw: str | None) -> frozenset[str]:
    if not raw:
        return frozenset()
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


@dataclass(frozen=True)
class AuthConfig:
    account_public_url: str
    account_base_url: str
    client_id: str
    client_secret: str
    redirect_uri: str
    jwt_secret: str
    admin_emails: frozenset[str]
    secure_cookie: bool
    session_ttl_seconds: int
    central_logout: bool


def _req(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise RuntimeError(f"[account-auth] Missing required env var: {name}")
    return v


def get_auth_config() -> AuthConfig:
    client_id, client_secret = get_account_credentials()
    ttl_raw = os.environ.get("SESSION_TTL", "28800")
    try:
        ttl = int(ttl_raw)
    except ValueError:
        ttl = 0
    if ttl <= 0:
        raise RuntimeError(
            f"[account-auth] SESSION_TTL must be a positive integer, got: {ttl_raw}"
        )
    return AuthConfig(
        account_public_url=_req("ACCOUNT_PUBLIC_URL").rstrip("/"),
        account_base_url=_req("ACCOUNT_BASE_URL").rstrip("/"),
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=_req("ACCOUNT_REDIRECT_URI"),
        jwt_secret=_req("JWT_SECRET"),
        admin_emails=parse_admin_emails(os.environ.get("ADMIN_EMAILS")),
        secure_cookie=os.environ.get("SECURE_COOKIE", "false").lower() == "true",
        session_ttl_seconds=ttl,
        central_logout=os.environ.get("SSO_CENTRAL_LOGOUT", "false").lower() == "true",
    )
