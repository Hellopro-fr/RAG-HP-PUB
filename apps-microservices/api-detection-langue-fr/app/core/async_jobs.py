"""Async job store + manager for the /detect-batch-async API.

Job state lives in Redis (records + an atomic idempotency index). The worker
runs in-process via asyncio, reusing the batch core injected at construction
(no import of app.api.routes — avoids a cycle). See spec
docs/superpowers/specs/2026-06-01-detection-langue-fr-async-job-api-design.md.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Callable, Awaitable

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None

logger = logging.getLogger(__name__)

_JOB_KEY = "detect:job:{}"
_IDX_KEY = "detect:jobidx:{}"


class _JobsDisabled(Exception):
    """ASYNC_JOBS_ENABLED is false (permanent 503, not retryable)."""


class _JobsUnavailable(Exception):
    """Redis unreachable / first write failed (permanent 503, not retryable)."""


class _JobCapacityExceeded(Exception):
    """MAX_ACTIVE_JOBS reached (transient 503 + Retry-After)."""


class JobStore:
    """Redis CRUD for job records + idempotency index. Lazy connect."""

    def __init__(self, redis_url: Optional[str], client=None) -> None:
        self._redis_url = redis_url
        self._client = client
        self._initialized = client is not None
        self._init_lock = asyncio.Lock()

    async def _get_client(self):
        async with self._init_lock:
            if not self._initialized:
                self._initialized = True
                if self._redis_url and aioredis:
                    try:
                        self._client = aioredis.from_url(self._redis_url, decode_responses=True)
                    except Exception as e:  # URL parse only; conn is lazy
                        logger.warning(f"[async-jobs] Redis client init failed: {e}")
        return self._client

    async def ping(self) -> bool:
        client = await self._get_client()
        if not client:
            return False
        try:
            return bool(await client.ping())
        except Exception as e:
            logger.warning(f"[async-jobs] Redis ping failed: {e}")
            return False

    async def claim_index(self, client_job_id: str, job_id: str, ttl: int) -> bool:
        client = await self._get_client()
        ok = await client.set(_IDX_KEY.format(client_job_id), job_id, nx=True, ex=ttl)
        return bool(ok)

    async def get_index(self, client_job_id: str) -> Optional[str]:
        client = await self._get_client()
        try:
            return await client.get(_IDX_KEY.format(client_job_id))
        except Exception:
            return None

    async def delete_index(self, client_job_id: str) -> None:
        client = await self._get_client()
        try:
            await client.delete(_IDX_KEY.format(client_job_id))
        except Exception:
            pass

    async def refresh_index_ttl(self, client_job_id: str, ttl: int) -> None:
        client = await self._get_client()
        try:
            await client.expire(_IDX_KEY.format(client_job_id), ttl)
        except Exception:
            pass

    async def write(self, record: dict, ttl: int) -> None:
        """Write a record. RAISES on failure — the submit path relies on this
        to detect an unreachable Redis (do NOT swallow here)."""
        client = await self._get_client()
        if not client:
            raise RuntimeError("Redis client unavailable")
        await client.setex(_JOB_KEY.format(record["job_id"]), ttl, json.dumps(record))

    async def get(self, job_id: str) -> Optional[dict]:
        client = await self._get_client()
        if not client:
            return None
        try:
            data = await client.get(_JOB_KEY.format(job_id))
            return json.loads(data) if data else None
        except Exception as e:
            logger.debug(f"[async-jobs] get error: {e}")
            return None


def poll_status(record: dict, now: float, stale_threshold_s: int) -> str:
    """Compute the BO-visible status. 'stale' is derived on read for a
    pending/running record whose heartbeat froze (dead worker). Never mutates."""
    status = record.get("status", "pending")
    if status in ("pending", "running"):
        last = max(record.get("created_at", 0.0), record.get("last_activity", 0.0))
        if (now - last) > stale_threshold_s:
            return "stale"
    return status
