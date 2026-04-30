"""Smoke tests for the demo OAuth client integration with account-service."""

import importlib

from app.routers import auth_account


def test_pkce_pair_returns_url_safe_strings():
    verifier, challenge = auth_account._pkce_pair()
    assert len(verifier) >= 43
    assert "=" not in verifier
    assert "=" not in challenge
    assert "+" not in challenge
    assert "/" not in challenge


def test_module_exposes_routes():
    paths = {r.path for r in auth_account.router.routes}
    assert "/auth/account/start" in paths
    assert "/auth/account/callback" in paths
    assert "/auth/account/logout" in paths


def test_env_defaults_present():
    importlib.reload(auth_account)
    assert auth_account.OAUTH_CLIENT_ID
    assert auth_account.OAUTH_AUTHORIZE_URL.endswith("/signin")
