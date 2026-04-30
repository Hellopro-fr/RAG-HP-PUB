"""Smoke tests for the account-service consumer integration."""

import importlib

from app.routers import auth_account


def test_module_exposes_routes():
    paths = {r.path for r in auth_account.router.routes}
    assert "/auth/account/start" in paths
    assert "/auth/account/callback" in paths
    assert "/auth/account/logout" in paths


def test_env_defaults_present():
    importlib.reload(auth_account)
    assert auth_account.ACCOUNT_SERVICE_NAME
    assert auth_account.ACCOUNT_SIGNIN_URL.endswith("/signin")
    assert auth_account.ACCOUNT_LOGIN_URL.endswith("/login")
    assert auth_account.ACCOUNT_EXCHANGE_URL.endswith("/sessions/exchange")
