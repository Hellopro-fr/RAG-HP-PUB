import asyncio

import pytest
import pytest_asyncio

from app.neo4j_env import InvalidCredentials
from app.port_pool import PortPool
from app.supervisor import SpawnSpec, Supervisor

CREDS = '{"uri":"bolt://neo4j:7687","username":"reader","password":"s3cret","database":"graph"}'


def _spec(instance_id, args, creds=CREDS, env=None):
    return SpawnSpec(
        instance_id=instance_id,
        template_slug="neo4j",
        stdio_command="sh",
        stdio_args=["-c", args],
        env=env if env is not None else {"NEO4J_READ_ONLY": "true"},
        credentials_json=creds,
        credentials_hash="h",
    )


@pytest_asyncio.fixture
async def supervisor():
    pool = PortPool(21000, 21009)
    sup = Supervisor(pool=pool)
    yield sup
    await sup.shutdown()


@pytest.mark.asyncio
async def test_child_receives_neo4j_env(supervisor):
    inst = await supervisor.spawn(
        _spec("n1", 'echo "$NEO4J_URI $NEO4J_USERNAME $NEO4J_DATABASE $NEO4J_READ_ONLY" >&2; sleep 3600'),
        bypass_mcp_proxy=True,
    )
    await asyncio.sleep(0.5)
    assert inst.port in range(21000, 21010)
    assert "bolt://neo4j:7687 reader graph true" in list(inst.stderr_ring)


@pytest.mark.asyncio
async def test_stderr_redacts_password(supervisor):
    inst = await supervisor.spawn(
        _spec("n2", 'echo "password is $NEO4J_PASSWORD" >&2; sleep 3600'),
        bypass_mcp_proxy=True,
    )
    await asyncio.sleep(0.5)
    lines = list(inst.stderr_ring)
    assert "password is ***" in lines
    assert not any("s3cret" in line for line in lines)


@pytest.mark.asyncio
async def test_runner_secrets_not_inherited(supervisor, monkeypatch):
    monkeypatch.setenv("RUNNER_ADMIN_TOKEN", "runner-secret")
    inst = await supervisor.spawn(
        _spec("n3", 'echo "token=[$RUNNER_ADMIN_TOKEN]" >&2; sleep 3600'),
        bypass_mcp_proxy=True,
    )
    await asyncio.sleep(0.5)
    assert "token=[]" in list(inst.stderr_ring)


@pytest.mark.asyncio
async def test_invalid_credentials_consume_no_port(supervisor):
    with pytest.raises(InvalidCredentials):
        await supervisor.spawn(_spec("bad", "sleep 1", creds="{}"), bypass_mcp_proxy=True)
    assert supervisor.get("bad") is None
    assert supervisor._pool.used() == []


@pytest.mark.asyncio
async def test_stdio_args_rejected_before_port(supervisor):
    spec = _spec("argv", "sleep 1")
    spec.stdio_args = ["--db-url", "bolt://evil:7687"]
    with pytest.raises(InvalidCredentials):
        await supervisor.spawn(spec, bypass_mcp_proxy=True)
    assert supervisor.get("argv") is None
    assert supervisor._pool.used() == []


@pytest.mark.asyncio
async def test_kill_releases_port(supervisor):
    await supervisor.spawn(_spec("n4", "sleep 3600"), bypass_mcp_proxy=True)
    await supervisor.kill("n4")
    assert supervisor.get("n4") is None
    assert supervisor._pool.used() == []


@pytest.mark.asyncio
async def test_crashing_child_is_respawned(supervisor):
    inst = await supervisor.spawn(_spec("n5", "sleep 0.5; exit 1"), bypass_mcp_proxy=True)
    first_pid = inst.pid
    await asyncio.sleep(2.0)
    assert supervisor.get("n5").pid != first_pid


@pytest.mark.asyncio
async def test_mcp_proxy_argv(supervisor, monkeypatch):
    seen = {}

    async def fake_exec(*argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs["env"]
        raise FileNotFoundError("mcp-proxy")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    await supervisor.spawn(_spec("n6", "unused"))
    await asyncio.sleep(0.2)
    port = seen["argv"][2]
    assert list(seen["argv"]) == [
        "mcp-proxy", "--port", port, "--host", "0.0.0.0",
        "--pass-environment", "--stateless", "--", "sh", "-c", "unused",
    ]
    assert seen["env"]["NEO4J_PASSWORD"] == "s3cret"
    # The failed spawn released its port.
    assert supervisor._pool.used() == []


@pytest.mark.asyncio
async def test_respawn_same_id_keeps_port(supervisor):
    first = await supervisor.spawn(_spec("r1", "sleep 3600"), bypass_mcp_proxy=True)
    port = first.port
    spec = _spec("r1", "sleep 3600")
    spec.credentials_hash = "h2"
    second = await supervisor.spawn(spec, bypass_mcp_proxy=True)
    assert second is not first
    assert second.port == port
    assert supervisor._pool.used() == [port]
    await supervisor.kill("r1")
    assert supervisor._pool.used() == []
