"""Async job store + manager for content-extractor batch endpoints. Job state lives
in Redis via the shared common_utils.redis.cache_service pool. The worker runs
in-process via asyncio, reusing a batch runner injected at construction (generic
over job_type). Adapted from api-detection-langue-fr/app/core/async_jobs.py."""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Callable, Awaitable

from common_utils.redis import cache_service

logger = logging.getLogger(__name__)

_JOB_KEY = "extract:job:{}"
_IDX_KEY = "extract:jobidx:{}"


class _JobsDisabled(Exception):
    """ASYNC_JOBS_ENABLED is false (permanent 503, not retryable)."""


class _JobsUnavailable(Exception):
    """Redis unreachable / first write failed (permanent 503, not retryable)."""


class _JobCapacityExceeded(Exception):
    """MAX_ACTIVE_JOBS reached (transient 503 + Retry-After)."""


class JobStore:
    """Redis CRUD over the shared cache_service pool. write() RAISES on no-client so
    the submit path can detect an unavailable Redis (do NOT swallow there)."""

    def _client(self):
        return cache_service.redis_client

    async def ping(self) -> bool:
        client = self._client()
        if not client:
            return False
        try:
            return bool(await client.ping())
        except Exception as e:
            logger.warning("[async-jobs] ping failed: %s", e)
            return False

    async def claim_index(self, cjid: str, job_id: str, ttl: int) -> bool:
        client = self._client()
        ok = await client.set(_IDX_KEY.format(cjid), job_id, nx=True, ex=ttl)
        return bool(ok)

    async def get_index(self, cjid: str) -> Optional[str]:
        client = self._client()
        try:
            return await client.get(_IDX_KEY.format(cjid))
        except Exception:
            return None

    async def delete_index(self, cjid: str) -> None:
        client = self._client()
        try:
            await client.delete(_IDX_KEY.format(cjid))
        except Exception:
            pass

    async def refresh_index_ttl(self, cjid: str, ttl: int) -> None:
        client = self._client()
        try:
            await client.expire(_IDX_KEY.format(cjid), ttl)
        except Exception:
            pass

    async def write(self, record: dict, ttl: int) -> None:
        client = self._client()
        if not client:
            raise RuntimeError("Redis client unavailable")
        await client.setex(_JOB_KEY.format(record["job_id"]), ttl, json.dumps(record))

    async def get(self, job_id: str) -> Optional[dict]:
        client = self._client()
        if not client:
            return None
        try:
            data = await client.get(_JOB_KEY.format(job_id))
            return json.loads(data) if data else None
        except Exception as e:
            logger.debug("[async-jobs] get error: %s", e)
            return None


def poll_status(record: dict, now: float, stale_threshold_s: int) -> str:
    """BO-visible status. 'stale' is derived on read for a pending/running record
    whose heartbeat froze (dead worker). Never mutates."""
    status = record.get("status", "pending")
    if status in ("pending", "running"):
        last = max(record.get("created_at", 0.0), record.get("last_activity", 0.0))
        if (now - last) > stale_threshold_s:
            return "stale"
    return status


class JobManager:
    def __init__(self, store: JobStore, batch_runner: Callable[..., Awaitable], settings) -> None:
        self._store = store
        self._batch_runner = batch_runner            # extractor_service.run_batch, injected
        self._s = settings
        self._job_tasks: dict[str, asyncio.Task] = {}
        self._inflight = 0                            # reserve counter (sync-guarded)

    async def get_record(self, job_id: str) -> Optional[dict]:
        return await self._store.get(job_id)

    async def submit(self, job_type: str, req) -> tuple[str, int]:
        """Returns (job_id, http_status). 202 new, 200 idempotent re-submit."""
        if not self._s.ASYNC_JOBS_ENABLED:
            raise _JobsDisabled()
        if not await self._store.ping():
            raise _JobsUnavailable()

        job_id = uuid.uuid4().hex
        cjid = req.client_job_id

        if cjid:
            claimed = await self._store.claim_index(cjid, job_id, self._s.JOB_TTL_ACTIVE_S)
            if not claimed:
                existing = await self._store.get_index(cjid)
                if existing:
                    return existing, 200
                claimed = await self._store.claim_index(cjid, job_id, self._s.JOB_TTL_ACTIVE_S)
                if not claimed:
                    existing = await self._store.get_index(cjid)
                    return (existing or job_id), 200

        from app.core.metrics import (
            ASYNC_JOB_CAPACITY_REJECTED, ASYNC_JOBS_SUBMITTED, ASYNC_JOBS_ACTIVE,
        )
        if self._inflight >= self._s.MAX_ACTIVE_JOBS:
            if cjid:
                await self._store.delete_index(cjid)
            ASYNC_JOB_CAPACITY_REJECTED.inc()
            raise _JobCapacityExceeded()
        self._inflight += 1

        now = time.time()
        record = {
            "job_id": job_id, "client_job_id": cjid, "job_type": job_type,
            "status": "pending", "total": len(req.items), "done": 0,
            "results": None, "error": None,
            "created_at": now, "started_at": None, "finished_at": None,
            "last_activity": now,
        }
        try:
            await self._store.write(record, self._s.JOB_TTL_ACTIVE_S)
        except Exception:
            self._inflight -= 1
            if cjid:
                await self._store.delete_index(cjid)
            raise _JobsUnavailable()

        task = asyncio.create_task(
            self._run_job(job_id, cjid, job_type, list(req.items),
                          req.max_concurrency, req.force_refresh)
        )
        self._job_tasks[job_id] = task
        task.add_done_callback(lambda t, jid=job_id: self._on_done(jid))
        ASYNC_JOBS_SUBMITTED.inc()
        ASYNC_JOBS_ACTIVE.set(self._inflight)
        return job_id, 202

    def _on_done(self, job_id: str) -> None:
        self._job_tasks.pop(job_id, None)
        self._inflight = max(0, self._inflight - 1)
        from app.core.metrics import ASYNC_JOBS_ACTIVE
        ASYNC_JOBS_ACTIVE.set(self._inflight)

    async def _heartbeat(self, job_id: str, progress: dict) -> None:
        try:
            while True:
                await asyncio.sleep(self._s.HEARTBEAT_INTERVAL_S)
                rec = await self._store.get(job_id)
                if not rec or rec.get("status") not in ("pending", "running"):
                    return
                rec["done"] = progress["done"]
                rec["last_activity"] = time.time()
                try:
                    await self._store.write(rec, self._s.JOB_TTL_ACTIVE_S)
                except Exception:
                    pass
        except asyncio.CancelledError:
            return

    async def _run_job(self, job_id, cjid, job_type, items, max_concurrency, force_refresh) -> None:
        from app.core.metrics import ASYNC_JOBS_TERMINAL, ASYNC_JOB_DURATION
        progress = {"done": 0}
        started = time.time()
        rec = await self._store.get(job_id) or {"job_id": job_id}
        rec.update({"status": "running", "started_at": started, "last_activity": started})
        try:
            await self._store.write(rec, self._s.JOB_TTL_ACTIVE_S)
        except Exception:
            pass

        hb = asyncio.create_task(self._heartbeat(job_id, progress))
        try:
            results = await self._batch_runner(
                job_type, items, max_concurrency, force_refresh,
                lambda done: progress.__setitem__("done", done),
            )
            hb.cancel()
            await asyncio.gather(hb, return_exceptions=True)
            rec = await self._store.get(job_id) or rec
            rec.update({
                "status": "completed", "done": len(results), "results": results,
                "finished_at": time.time(), "last_activity": time.time(),
            })
            await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
            if cjid:
                await self._store.refresh_index_ttl(cjid, self._s.JOB_RESULT_TTL_S)
            ASYNC_JOBS_TERMINAL.labels(status="completed").inc()
            ASYNC_JOB_DURATION.observe(time.time() - started)
        except asyncio.CancelledError:
            hb.cancel()
            raise                                     # shutdown() owns the record write
        except Exception as e:
            hb.cancel()
            await asyncio.gather(hb, return_exceptions=True)
            rec = await self._store.get(job_id) or rec
            rec.update({"status": "failed", "error": str(e),
                        "finished_at": time.time(), "last_activity": time.time()})
            try:
                await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
                if cjid:
                    await self._store.refresh_index_ttl(cjid, self._s.JOB_RESULT_TTL_S)
            except Exception:
                pass
            ASYNC_JOBS_TERMINAL.labels(status="failed").inc()

    async def shutdown(self) -> None:
        job_ids = list(self._job_tasks.keys())
        tasks = list(self._job_tasks.values())
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=self._s.SHUTDOWN_GRACE_S)
        for job_id in job_ids:
            rec = await self._store.get(job_id)
            if rec and rec.get("status") in ("pending", "running"):
                rec.update({"status": "failed", "error": "service_shutdown",
                            "finished_at": time.time()})
                try:
                    await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
                except Exception:
                    pass
