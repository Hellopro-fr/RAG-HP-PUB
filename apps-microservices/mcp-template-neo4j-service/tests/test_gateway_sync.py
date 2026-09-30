from __future__ import annotations

import asyncio
import importlib
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# Settings is instantiated at import time in app.config, so required env vars
# must be present before app.gateway_sync is imported. Set them here so
# `import app.gateway_sync` inside the fixture below (after reload) succeeds.
os.environ.setdefault("MCP_GATEWAY_URL", "http://gateway.invalid")
os.environ.setdefault("MCP_GATEWAY_ADMIN_TOKEN", "gw-token")
os.environ.setdefault("RUNNER_ADMIN_TOKEN", "runner-token")

import app.config  # noqa: E402
import app.gateway_sync  # noqa: E402

importlib.reload(app.config)
importlib.reload(app.gateway_sync)

from app.gateway_sync import (  # noqa: E402
    reconcile_loop,
    reconcile_once,
    sync_with_gateway,
)
from app.supervisor import SpawnSpec  # noqa: E402


def _make_response(body: dict) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=body)
    return resp


def _inst(instance_id: str, credentials_hash: str) -> MagicMock:
    """A stand-in for supervisor.RunningInstance with just the fields
    reconcile_once reads (instance_id + credentials_hash)."""
    m = MagicMock()
    m.instance_id = instance_id
    m.credentials_hash = credentials_hash
    return m


def _desired(instance_id: str, credentials_hash: str) -> dict:
    return {
        "instance_id": instance_id,
        "template_slug": "ga4",
        "stdio_command": "echo",
        "stdio_args": [],
        "env": {},
        "credentials_json": "{}",
        "credentials_hash": credentials_hash,
    }


def _patch_async_client(post_mock: AsyncMock):
    """Return a context-manager patch for httpx.AsyncClient.

    The runner opens `async with httpx.AsyncClient(...) as client: ...` so we
    need a MagicMock whose __aenter__ returns an object with `post`.
    """
    client = MagicMock()
    client.post = post_mock

    client_cm = MagicMock()
    client_cm.__aenter__ = AsyncMock(return_value=client)
    client_cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=client_cm)
    return patch("app.gateway_sync.httpx.AsyncClient", factory)


@pytest.mark.asyncio
async def test_empty_desired_instances_no_spawn():
    """Empty desired set: function returns cleanly without spawning."""
    sup = MagicMock()
    sup.spawn = AsyncMock()

    post_mock = AsyncMock(return_value=_make_response({"desired_instances": []}))

    with _patch_async_client(post_mock):
        await sync_with_gateway(sup, retries=1)

    post_mock.assert_awaited_once()
    sup.spawn.assert_not_called()


@pytest.mark.asyncio
async def test_sync_retries_on_network_error(monkeypatch):
    """Fails once with ConnectError, then succeeds; spawn called for returned instance."""
    sup = MagicMock()
    sup.spawn = AsyncMock()

    # Make asyncio.sleep a no-op so backoff doesn't slow the test.
    monkeypatch.setattr("app.gateway_sync.asyncio.sleep", AsyncMock())

    desired = [
        {
            "instance_id": "it-1",
            "template_slug": "ga4",
            "stdio_command": "echo",
            "stdio_args": ["hi"],
            "env": {},
            "credentials_json": "{}",
            "credentials_hash": "abc",
        }
    ]
    ok_resp = _make_response({"desired_instances": desired})

    post_mock = AsyncMock(
        side_effect=[httpx.ConnectError("boom"), ok_resp]
    )

    with _patch_async_client(post_mock):
        await sync_with_gateway(sup, retries=3)

    assert post_mock.await_count == 2
    sup.spawn.assert_awaited_once()
    arg = sup.spawn.await_args.args[0]
    assert isinstance(arg, SpawnSpec)
    assert arg.instance_id == "it-1"


@pytest.mark.asyncio
async def test_sync_gives_up_after_max_retries(monkeypatch, caplog):
    """All attempts raise: function returns without raising and never spawns."""
    sup = MagicMock()
    sup.spawn = AsyncMock()

    monkeypatch.setattr("app.gateway_sync.asyncio.sleep", AsyncMock())

    post_mock = AsyncMock(side_effect=httpx.ConnectError("down"))

    with _patch_async_client(post_mock):
        with caplog.at_level("ERROR", logger="runner.sync"):
            await sync_with_gateway(sup, retries=2)

    assert post_mock.await_count == 2
    sup.spawn.assert_not_called()
    assert any("giving up" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_spawn_failure_is_logged_not_raised(monkeypatch):
    """An instance whose spawn raises must not abort the sync."""
    sup = MagicMock()
    sup.spawn = AsyncMock(side_effect=RuntimeError("spawn kaboom"))

    monkeypatch.setattr("app.gateway_sync.asyncio.sleep", AsyncMock())

    desired = [
        {
            "instance_id": "it-bad",
            "template_slug": "ga4",
            "stdio_command": "echo",
            "stdio_args": [],
            "env": {},
            "credentials_json": "{}",
            "credentials_hash": "h",
        }
    ]
    post_mock = AsyncMock(return_value=_make_response({"desired_instances": desired}))

    with _patch_async_client(post_mock):
        # Must not raise.
        await sync_with_gateway(sup, retries=1)

    sup.spawn.assert_awaited_once()


# --- reconcile_once: idempotent convergence ------------------------------


@pytest.mark.asyncio
async def test_reconcile_spawns_missing_instance():
    sup = MagicMock()
    sup.spawn = AsyncMock()
    sup.kill = AsyncMock()
    sup.list = MagicMock(return_value=[])

    post_mock = AsyncMock(
        return_value=_make_response({"desired_instances": [_desired("it-1", "abc")]})
    )

    with _patch_async_client(post_mock):
        ok = await reconcile_once(sup)

    assert ok is True
    sup.spawn.assert_awaited_once()
    assert sup.spawn.await_args.args[0].instance_id == "it-1"
    sup.kill.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_leaves_unchanged_instance_untouched():
    """A running instance whose hash matches the gateway must NOT be respawned
    — otherwise the periodic loop would restart healthy instances every cycle."""
    sup = MagicMock()
    sup.spawn = AsyncMock()
    sup.kill = AsyncMock()
    sup.list = MagicMock(return_value=[_inst("it-1", "abc")])

    post_mock = AsyncMock(
        return_value=_make_response({"desired_instances": [_desired("it-1", "abc")]})
    )

    with _patch_async_client(post_mock):
        ok = await reconcile_once(sup)

    assert ok is True
    sup.spawn.assert_not_called()
    sup.kill.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_respawns_on_hash_change():
    sup = MagicMock()
    sup.spawn = AsyncMock()
    sup.kill = AsyncMock()
    sup.list = MagicMock(return_value=[_inst("it-1", "OLD")])

    post_mock = AsyncMock(
        return_value=_make_response({"desired_instances": [_desired("it-1", "NEW")]})
    )

    with _patch_async_client(post_mock):
        ok = await reconcile_once(sup)

    assert ok is True
    sup.spawn.assert_awaited_once()
    sup.kill.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_kills_extras_not_in_desired():
    sup = MagicMock()
    sup.spawn = AsyncMock()
    sup.kill = AsyncMock()
    sup.list = MagicMock(return_value=[_inst("zombie", "x")])

    post_mock = AsyncMock(return_value=_make_response({"desired_instances": []}))

    with _patch_async_client(post_mock):
        ok = await reconcile_once(sup)

    assert ok is True
    sup.kill.assert_awaited_once_with("zombie")
    sup.spawn.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_returns_false_on_network_error():
    """Gateway unreachable: reconcile_once reports failure (so the loop retries
    fast) and never mutates local state."""
    sup = MagicMock()
    sup.spawn = AsyncMock()
    sup.kill = AsyncMock()
    sup.list = MagicMock(return_value=[])

    post_mock = AsyncMock(side_effect=httpx.ConnectError("down"))

    with _patch_async_client(post_mock):
        ok = await reconcile_once(sup)

    assert ok is False
    sup.spawn.assert_not_called()
    sup.kill.assert_not_called()


# --- reconcile_loop: boot self-heal + interval selection -----------------


@pytest.mark.asyncio
async def test_reconcile_loop_retries_fast_then_settles(monkeypatch):
    """First tick is immediate. A failed reconcile sleeps the short retry
    interval; a successful one sleeps the long interval. This is what stops a
    boot-time gateway-DNS race from permanently orphaning instances."""
    results = iter([False, True])

    async def fake_once(_sup):
        return next(results)

    monkeypatch.setattr("app.gateway_sync.reconcile_once", fake_once)

    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)
        if len(sleeps) >= 2:
            raise asyncio.CancelledError

    monkeypatch.setattr("app.gateway_sync.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await reconcile_loop(MagicMock(), ok_interval=300, fail_interval=15)

    # fail → 15s retry, then success → 300s settle.
    assert sleeps == [15, 300]
