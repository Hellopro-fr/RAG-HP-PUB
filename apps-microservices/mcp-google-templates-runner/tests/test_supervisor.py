import asyncio
import time
from pathlib import Path

import pytest
import pytest_asyncio

from app.port_pool import PortPool
from app.credentials import CredentialsStore
from app.supervisor import Supervisor, SpawnSpec


@pytest_asyncio.fixture
async def supervisor(tmp_path):
    pool = PortPool(20000, 20099)
    store = CredentialsStore(base_dir=str(tmp_path))
    sup = Supervisor(pool=pool, credentials=store)
    yield sup
    await sup.shutdown()


@pytest.mark.asyncio
async def test_spawn_and_kill_simple_subprocess(supervisor):
    # Use `sleep` as a stand-in for mcp-proxy
    spec = SpawnSpec(
        instance_id="it1",
        template_slug="test",
        stdio_command="sleep",
        stdio_args=["3600"],
        env={},
        credentials_json='{"type":"service_account"}',
        credentials_hash="deadbeef",
    )
    inst = await supervisor.spawn(spec, bypass_mcp_proxy=True)
    assert inst.port in range(20000, 20100)
    assert inst.pid > 0
    await supervisor.kill("it1")
    assert supervisor.get("it1") is None


@pytest.mark.asyncio
async def test_crashing_child_is_respawned(supervisor):
    spec = SpawnSpec(
        instance_id="it2",
        template_slug="test",
        stdio_command="sh",
        stdio_args=["-c", "sleep 0.5; exit 1"],
        env={},
        credentials_json="{}",
        credentials_hash="h",
    )
    inst = await supervisor.spawn(spec, bypass_mcp_proxy=True)
    first_pid = inst.pid
    await asyncio.sleep(2.0)
    assert supervisor.get("it2").pid != first_pid


@pytest.mark.asyncio
async def test_flapping_marks_failed(supervisor):
    spec = SpawnSpec(
        instance_id="it3",
        template_slug="test",
        stdio_command="sh",
        stdio_args=["-c", "exit 1"],
        env={},
        credentials_json="{}",
        credentials_hash="h",
    )
    await supervisor.spawn(spec, bypass_mcp_proxy=True)
    # Wait long enough for 5 fast exits.
    # Backoff doubles 1s -> 2s -> 4s -> 8s, so the 5th exit lands at ~t=15s.
    # The plan proposed 3.0s which is insufficient with BACKOFF_INITIAL=1.0.
    await asyncio.sleep(16.0)
    inst = supervisor.get("it3")
    assert inst is None or inst.status == "failed"
