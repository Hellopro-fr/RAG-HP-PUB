from __future__ import annotations

import asyncio
import collections
import dataclasses
import logging
import os
import signal
import time
from typing import Optional

from app.port_pool import PortPool
from app.credentials import CredentialsStore

logger = logging.getLogger("supervisor")


@dataclasses.dataclass
class SpawnSpec:
    instance_id: str
    template_slug: str
    stdio_command: str
    stdio_args: list[str]
    env: dict[str, str]
    credentials_json: str
    credentials_hash: str


@dataclasses.dataclass
class RunningInstance:
    instance_id: str
    template_slug: str
    port: int
    pid: int
    credentials_path: str
    credentials_hash: str
    spec: SpawnSpec
    desired_state: str  # "running" | "stopped"
    status: str         # "pending" | "running" | "failed" | "stopped"
    last_error: str
    stderr_ring: collections.deque
    exit_count: int
    started_at: float
    supervisor_task: Optional[asyncio.Task] = None
    process: Optional[asyncio.subprocess.Process] = None


class Supervisor:
    FLAPPING_THRESHOLD = 5
    FLAPPING_WINDOW_SEC = 10.0
    BACKOFF_INITIAL = 1.0
    BACKOFF_MAX = 60.0
    HEALTHY_RESET_SEC = 60.0
    STDERR_RING_SIZE = 200

    def __init__(self, pool: PortPool, credentials: CredentialsStore):
        self._pool = pool
        self._creds = credentials
        self._instances: dict[str, RunningInstance] = {}
        self._lock = asyncio.Lock()

    def get(self, instance_id: str) -> Optional[RunningInstance]:
        return self._instances.get(instance_id)

    def list(self) -> list[RunningInstance]:
        return list(self._instances.values())

    async def spawn(self, spec: SpawnSpec, bypass_mcp_proxy: bool = False) -> RunningInstance:
        async with self._lock:
            if spec.instance_id in self._instances:
                # Spawn-on-existing = restart-with-possibly-new-spec
                await self._kill_locked(spec.instance_id, release_port=False)
            port = self._pool.allocate()
            try:
                cred_path = self._creds.write(spec.instance_id, spec.credentials_json)
            except Exception:
                self._pool.release(port)
                raise
            inst = RunningInstance(
                instance_id=spec.instance_id,
                template_slug=spec.template_slug,
                port=port, pid=0,
                credentials_path=cred_path,
                credentials_hash=spec.credentials_hash,
                spec=spec,
                desired_state="running",
                status="pending",
                last_error="",
                stderr_ring=collections.deque(maxlen=self.STDERR_RING_SIZE),
                exit_count=0,
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
        """Pop the instance, release its port, and shred credentials.

        Called by _supervise when the supervise loop terminates with status=failed
        (binary missing, flapping). Without this, the port would stay allocated and
        the credentials file would stay on disk until explicit kill().
        """
        async with self._lock:
            inst = self._instances.pop(instance_id, None)
            if not inst:
                return
            self._pool.release(inst.port)
            self._creds.shred(inst.instance_id)

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
        self._creds.shred(inst.instance_id)

    async def restart(self, instance_id: str) -> None:
        inst = self._instances.get(instance_id)
        if not inst:
            raise KeyError(instance_id)
        # Respawn with the same spec (supervisor's loop will restart after kill)
        if inst.process and inst.process.returncode is None:
            inst.process.send_signal(signal.SIGTERM)

    async def shutdown(self) -> None:
        async with self._lock:
            for iid in list(self._instances.keys()):
                await self._kill_locked(iid, release_port=True)

    async def _supervise(self, inst: RunningInstance, bypass_mcp_proxy: bool) -> None:
        backoff = self.BACKOFF_INITIAL
        while inst.desired_state == "running":
            # Build argv
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
            # Build a minimal environment: inherit PATH/HOME/LANG so the child
            # can resolve the executable (asyncio.create_subprocess_exec uses
            # execvp which consults PATH), then overlay the template's env.
            # Without PATH, execvp fails with FileNotFoundError even when the
            # binary is installed in /usr/local/bin.
            proc_env = {
                "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
                "HOME": os.environ.get("HOME", "/tmp"),
                "LANG": os.environ.get("LANG", "C.UTF-8"),
                **inst.spec.env,
            }
            try:
                proc = await asyncio.create_subprocess_exec(
                    *argv,
                    env=proc_env,
                    # cwd is the per-instance credentials directory (from
                    # CredentialsStore.write) so stdio children that hardcode
                    # filename lookups (e.g. mcp-gsc looks for
                    # service_account_credentials.json in os.getcwd()) find
                    # the file without us plumbing template-specific config.
                    cwd=inst.credentials_path,
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

            # Flapping detection. Note: uptime here is the last spawn's lifetime;
            # exit_count is cumulative across respawns. Effective rule: "latest run
            # was short AND we've crashed at least THRESHOLD times total (modulo
            # healthy-resets)". Not a true rolling time window — good enough for
            # catching wedged configurations without over-engineering.
            uptime = time.monotonic() - inst.started_at
            if uptime < self.FLAPPING_WINDOW_SEC and inst.exit_count >= self.FLAPPING_THRESHOLD:
                inst.status = "failed"
                inst.desired_state = "stopped"
                await self._release_failed(inst.instance_id)
                return

            # Healthy long-run resets backoff and exit counter
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
                inst.stderr_ring.append(line.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            return
