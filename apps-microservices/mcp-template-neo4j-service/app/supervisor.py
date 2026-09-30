from __future__ import annotations

import asyncio
import collections
import dataclasses
import logging
import os
import signal
import time
from typing import Optional

from app.neo4j_env import build_process_env, check_stdio_args, parse_credentials
from app.port_pool import PortPool

logger = logging.getLogger("supervisor")

_REDACTED = "***"


@dataclasses.dataclass
class SpawnSpec:
    instance_id: str
    template_slug: str
    stdio_command: str
    stdio_args: list[str]
    env: dict[str, str]
    credentials_json: str
    credentials_hash: str
    # Last-known port the gateway wants us to reuse (see PortPool.allocate).
    runner_port: Optional[int] = None


@dataclasses.dataclass
class RunningInstance:
    instance_id: str
    template_slug: str
    port: int
    pid: int
    credentials_hash: str
    spec: SpawnSpec = dataclasses.field(repr=False)
    # Full child env, credentials included. Held in memory only.
    proc_env: dict[str, str] = dataclasses.field(repr=False, default_factory=dict)
    # Scrubbed from every stderr line before it reaches stderr_ring (the ring
    # is served to the gateway's instance detail view).
    secret: str = dataclasses.field(repr=False, default="")
    desired_state: str = "running"  # "running" | "stopped"
    status: str = "pending"         # "pending" | "running" | "failed" | "stopped"
    last_error: str = ""
    stderr_ring: collections.deque = dataclasses.field(default_factory=collections.deque)
    exit_count: int = 0
    started_at: float = 0.0
    supervisor_task: Optional[asyncio.Task] = None
    process: Optional[asyncio.subprocess.Process] = None


class Supervisor:
    FLAPPING_THRESHOLD = 5
    FLAPPING_WINDOW_SEC = 10.0
    BACKOFF_INITIAL = 1.0
    BACKOFF_MAX = 60.0
    HEALTHY_RESET_SEC = 60.0
    STDERR_RING_SIZE = 200

    def __init__(self, pool: PortPool):
        self._pool = pool
        self._instances: dict[str, RunningInstance] = {}
        self._lock = asyncio.Lock()

    def get(self, instance_id: str) -> Optional[RunningInstance]:
        return self._instances.get(instance_id)

    def list(self) -> list[RunningInstance]:
        return list(self._instances.values())

    async def spawn(self, spec: SpawnSpec, bypass_mcp_proxy: bool = False) -> RunningInstance:
        # Parse before touching state: invalid credentials (or connection flags
        # in stdio_args) must neither consume a port nor kill a running
        # instance. Raises InvalidCredentials.
        check_stdio_args(spec.stdio_args)
        creds = parse_credentials(spec.credentials_json)
        proc_env = build_process_env(os.environ, spec.env, creds)
        async with self._lock:
            existing = self._instances.get(spec.instance_id)
            if existing is not None:
                # Spawn-on-existing = restart-with-possibly-new-spec. Keep the
                # port: the gateway stored it in mcp_servers.url, and releasing
                # then re-allocating could fail and leave no instance at all.
                port = existing.port
                await self._kill_locked(spec.instance_id, release_port=False)
            else:
                port = self._pool.allocate(preferred=spec.runner_port)
            inst = RunningInstance(
                instance_id=spec.instance_id,
                template_slug=spec.template_slug,
                port=port,
                pid=0,
                credentials_hash=spec.credentials_hash,
                spec=spec,
                proc_env=proc_env,
                secret=creds.password,
                stderr_ring=collections.deque(maxlen=self.STDERR_RING_SIZE),
                started_at=time.monotonic(),
            )
            self._instances[spec.instance_id] = inst
            inst.supervisor_task = asyncio.create_task(
                self._supervise(inst, bypass_mcp_proxy=bypass_mcp_proxy)
            )
        # Give the supervisor a moment to launch
        await asyncio.sleep(0.1)
        return inst

    async def _release_failed(self, instance_id: str) -> None:
        """Pop a failed instance (binary missing, flapping) and release its port."""
        async with self._lock:
            inst = self._instances.pop(instance_id, None)
            if inst:
                self._pool.release(inst.port)

    async def kill(self, instance_id: str) -> None:
        async with self._lock:
            await self._kill_locked(instance_id, release_port=True)

    async def _kill_locked(self, instance_id: str, release_port: bool) -> None:
        inst = self._instances.pop(instance_id, None)
        if not inst:
            return
        inst.desired_state = "stopped"
        if inst.process and inst.process.returncode is None:
            try:
                inst.process.send_signal(signal.SIGTERM)
                try:
                    await asyncio.wait_for(inst.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    inst.process.kill()
                    await inst.process.wait()
            except ProcessLookupError:
                pass
        if inst.supervisor_task and not inst.supervisor_task.done():
            inst.supervisor_task.cancel()
        if release_port:
            self._pool.release(inst.port)

    async def restart(self, instance_id: str) -> None:
        inst = self._instances.get(instance_id)
        if not inst:
            raise KeyError(instance_id)
        # The supervise loop respawns after the child exits.
        if inst.process and inst.process.returncode is None:
            inst.process.send_signal(signal.SIGTERM)

    async def shutdown(self) -> None:
        async with self._lock:
            for iid in list(self._instances.keys()):
                await self._kill_locked(iid, release_port=True)

    async def _supervise(self, inst: RunningInstance, bypass_mcp_proxy: bool) -> None:
        backoff = self.BACKOFF_INITIAL
        while inst.desired_state == "running":
            if bypass_mcp_proxy:
                argv = [inst.spec.stdio_command, *inst.spec.stdio_args]
            else:
                argv = [
                    "mcp-proxy",
                    "--port", str(inst.port),
                    "--host", "0.0.0.0",
                    "--pass-environment",
                    "--stateless",
                    "--", inst.spec.stdio_command, *inst.spec.stdio_args,
                ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    env=inst.proc_env,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.DEVNULL,
                )
            except FileNotFoundError as e:
                inst.last_error = f"spawn failed: {e}"
                inst.status = "failed"
                logger.error("instance %s: %s", inst.instance_id, inst.last_error)
                await self._release_failed(inst.instance_id)
                return

            inst.process = proc
            inst.pid = proc.pid
            inst.status = "running"
            inst.started_at = time.monotonic()
            logger.info("instance %s: started pid=%d port=%d", inst.instance_id, proc.pid, inst.port)

            drain_task = asyncio.create_task(self._drain_stderr(inst))
            try:
                exit_code = await proc.wait()
            finally:
                drain_task.cancel()

            if inst.desired_state != "running":
                inst.status = "stopped"
                return

            inst.exit_count += 1
            tail = "\n".join(list(inst.stderr_ring)[-10:])
            inst.last_error = f"exit {exit_code}; stderr tail:\n{tail}"
            logger.warning("instance %s exited: %s", inst.instance_id, inst.last_error)

            uptime = time.monotonic() - inst.started_at
            if uptime < self.FLAPPING_WINDOW_SEC and inst.exit_count >= self.FLAPPING_THRESHOLD:
                inst.status = "failed"
                inst.desired_state = "stopped"
                await self._release_failed(inst.instance_id)
                return

            if uptime > self.HEALTHY_RESET_SEC:
                backoff = self.BACKOFF_INITIAL
                inst.exit_count = 0

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.BACKOFF_MAX)

        inst.status = "stopped"

    async def _drain_stderr(self, inst: RunningInstance) -> None:
        assert inst.process and inst.process.stderr
        try:
            while True:
                line = await inst.process.stderr.readline()
                if not line:
                    return
                text = line.decode("utf-8", errors="replace").rstrip()
                if inst.secret:
                    text = text.replace(inst.secret, _REDACTED)
                inst.stderr_ring.append(text)
        except asyncio.CancelledError:
            return
