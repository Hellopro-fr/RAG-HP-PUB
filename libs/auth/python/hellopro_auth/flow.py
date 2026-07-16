"""Framework-free login orchestration (parity with libs/auth/node flow.ts)."""
from __future__ import annotations

from dataclasses import dataclass

from .config import get_auth_config
from .oauth import build_authorize_url, exchange_code, gen_pkce, random_state, verify_and_extract
from .session import SessionClaims, create_session_token


@dataclass(frozen=True)
class LoginStart:
    authorize_url: str
    verifier: str
    state: str
    secure_cookie: bool


async def start_login() -> LoginStart:
    cfg = await get_auth_config()
    pkce = gen_pkce()
    state = random_state()
    url = build_authorize_url(
        public_url=cfg.account_public_url, client_id=cfg.client_id,
        redirect_uri=cfg.redirect_uri, challenge=pkce.challenge, state=state,
    )
    return LoginStart(authorize_url=url, verifier=pkce.verifier, state=state,
                      secure_cookie=cfg.secure_cookie)


async def complete_callback(*, code: str | None, state: str | None,
                      state_cookie: str | None, verifier_cookie: str | None) -> dict:
    cfg = await get_auth_config()

    if not code or not state:
        return {"status": "error", "reason": "missing_code_or_state"}
    if not state_cookie or state_cookie != state:
        return {"status": "error", "reason": "state_mismatch"}
    if not verifier_cookie:
        return {"status": "error", "reason": "missing_verifier"}

    try:
        tokens = exchange_code(
            base_url=cfg.account_base_url, client_id=cfg.client_id, client_secret=cfg.client_secret,
            code=code, redirect_uri=cfg.redirect_uri, verifier=verifier_cookie,
        )
    except Exception:
        return {"status": "error", "reason": "exchange_failed"}

    try:
        identity = verify_and_extract(tokens["access_token"], cfg.jwt_secret)
    except Exception:
        return {"status": "error", "reason": "token_invalid"}

    if identity.email.lower() not in cfg.admin_emails:
        return {"status": "denied", "email": identity.email}

    token = create_session_token(
        SessionClaims(email=identity.email, name=identity.name), cfg.session_ttl_seconds
    )
    return {"status": "ok", "session_token": token,
            "ttl_seconds": cfg.session_ttl_seconds, "secure_cookie": cfg.secure_cookie}
