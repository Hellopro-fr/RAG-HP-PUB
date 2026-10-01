import importlib

import pytest
from fastapi import HTTPException


@pytest.fixture
def reloaded_auth(monkeypatch):
    monkeypatch.setenv("MCP_GATEWAY_URL", "http://localhost:0")
    monkeypatch.setenv("MCP_GATEWAY_ADMIN_TOKEN", "gw")
    monkeypatch.setenv("RUNNER_ADMIN_TOKEN", "rt")
    import app.config
    import app.auth
    importlib.reload(app.config)
    importlib.reload(app.auth)
    return app.auth


@pytest.mark.asyncio
async def test_missing_header_raises_401(reloaded_auth):
    with pytest.raises(HTTPException) as ei:
        await reloaded_auth.require_admin_token(x_admin_token=None)
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_wrong_token_raises_401(reloaded_auth):
    with pytest.raises(HTTPException) as ei:
        await reloaded_auth.require_admin_token(x_admin_token="wrong")
    assert ei.value.status_code == 401


@pytest.mark.asyncio
async def test_correct_token_passes(reloaded_auth):
    await reloaded_auth.require_admin_token(x_admin_token="rt")
