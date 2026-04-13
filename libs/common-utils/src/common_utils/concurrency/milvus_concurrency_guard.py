import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.lua_scripts import (
    ACQUIRE_SCRIPT,
    CORRECT_COUNTERS_SCRIPT,
    RELEASE_SCRIPT,
)
from common_utils.concurrency.metrics import GuardMetrics

logger = logging.getLogger(__name__)

TOTAL_KEY = "milvus:slots:total"
WRITES_KEY = "milvus:slots:writes"
TIER2_WAITERS_KEY = "milvus:slots:tier2_waiters"
LEASE_PREFIX = "milvus:slots:lease:"


class MilvusConcurrencyGuard:
    """Async Redis-backed global concurrency guard for Milvus operations."""

    def __init__(self, redis_client, config: GuardConfig, metrics: GuardMetrics | None = None):
        self._redis = redis_client
        self._config = config
        self._metrics = metrics or GuardMetrics()
        self._fallback_semaphore = asyncio.Semaphore(config.fallback_limit)
        self._using_fallback = False
        self._acquire_sha = None
        self._release_sha = None
        self._correct_sha = None
        self._correction_task: asyncio.Task | None = None
        self._metrics.set_config_gauges(config.global_max, config.write_ceiling)

    async def _ensure_scripts(self):
        """Register Lua scripts on first use."""
        if self._redis is None:
            raise ConnectionError("Redis client is None")
        if self._acquire_sha is None:
            self._acquire_sha = self._redis.register_script(ACQUIRE_SCRIPT)
            self._release_sha = self._redis.register_script(RELEASE_SCRIPT)
            self._correct_sha = self._redis.register_script(CORRECT_COUNTERS_SCRIPT)

    async def acquire(self) -> str:
        """Acquire a slot. Returns lease_id. Raises TimeoutError on deadline."""
        tier = self._config.tier
        service = self._config.service_name
        tier_str = str(tier)
        is_tier2_waiter = False

        try:
            await self._ensure_scripts()
        except Exception as e:
            logger.warning("Redis unavailable for script registration: %s — using fallback", e)
            return await self._acquire_fallback()

        lease_id = f"{service}:{uuid.uuid4().hex[:12]}"
        lease_key = f"{LEASE_PREFIX}{lease_id}"
        lease_value = f"{service}:{tier}:{int(time.time())}"

        start = time.monotonic()
        deadline = start + self._config.acquire_timeout
        first_attempt = True

        while True:
            try:
                result = await self._acquire_sha(
                    keys=[TOTAL_KEY, WRITES_KEY, TIER2_WAITERS_KEY, lease_key],
                    args=[tier, self._config.global_max, self._config.write_ceiling, lease_value, self._config.lease_ttl],
                )

                if result == 1:
                    if is_tier2_waiter:
                        await self._redis.decr(TIER2_WAITERS_KEY)
                    duration = time.monotonic() - start
                    self._metrics.record_acquire(tier=tier_str, service=service, duration=duration)
                    if self._using_fallback:
                        self._using_fallback = False
                        self._metrics.set_fallback(service, False)
                        logger.info("Redis recovered — switching back to global guard")
                    logger.debug(
                        "Slot acquired: service=%s tier=%s lease=%s wait_ms=%.0f",
                        service, tier, lease_id, duration * 1000,
                    )
                    return lease_id

                if first_attempt and tier == 2:
                    await self._redis.incr(TIER2_WAITERS_KEY)
                    is_tier2_waiter = True
                    first_attempt = False

                if time.monotonic() >= deadline:
                    if is_tier2_waiter:
                        await self._redis.decr(TIER2_WAITERS_KEY)
                    self._metrics.record_timeout(tier=tier_str, service=service)
                    logger.warning(
                        "Acquire timeout: service=%s tier=%s waited=%.1fs",
                        service, tier, self._config.acquire_timeout,
                    )
                    raise TimeoutError(
                        f"Could not acquire Milvus slot within {self._config.acquire_timeout}s "
                        f"(service={service}, tier={tier})"
                    )

                await asyncio.sleep(self._config.retry_interval)

            except TimeoutError:
                raise
            except Exception as e:
                if is_tier2_waiter:
                    try:
                        await self._redis.decr(TIER2_WAITERS_KEY)
                    except Exception:
                        pass
                logger.warning("Redis error during acquire: %s — using fallback", e)
                return await self._acquire_fallback()

    async def _acquire_fallback(self) -> str:
        """Local semaphore fallback when Redis is unavailable."""
        if not self._using_fallback:
            self._using_fallback = True
            self._metrics.set_fallback(self._config.service_name, True)
            logger.warning(
                "Redis unavailable — falling back to local concurrency limit (%d)",
                self._config.fallback_limit,
            )
        await self._fallback_semaphore.acquire()
        return f"fallback:{uuid.uuid4().hex[:12]}"

    async def release(self, lease_id: str):
        """Release a slot by lease_id."""
        tier = self._config.tier
        service = self._config.service_name
        tier_str = str(tier)

        if lease_id.startswith("fallback:"):
            self._fallback_semaphore.release()
            logger.debug("Fallback slot released: service=%s lease=%s", service, lease_id)
            return

        lease_key = f"{LEASE_PREFIX}{lease_id}"
        try:
            await self._ensure_scripts()
            result = await self._release_sha(
                keys=[TOTAL_KEY, WRITES_KEY, lease_key],
                args=[tier],
            )
            if result == 1:
                self._metrics.record_release(tier=tier_str, service=service)
                logger.debug("Slot released: service=%s tier=%s lease=%s", service, tier, lease_id)
            else:
                logger.debug("Lease already expired: service=%s lease=%s", service, lease_id)
        except Exception as e:
            logger.warning("Redis error during release: %s — slot may leak until TTL expires", e)

    async def extend_lease(self, lease_id: str):
        """Extend TTL for long-running operations."""
        if lease_id.startswith("fallback:"):
            return
        lease_key = f"{LEASE_PREFIX}{lease_id}"
        try:
            await self._redis.expire(lease_key, self._config.lease_ttl)
        except Exception as e:
            logger.warning("Failed to extend lease %s: %s", lease_id, e)

    @asynccontextmanager
    async def slot(self):
        """Context manager: acquire, yield, release. Handles cleanup on exception."""
        lease_id = await self.acquire()
        try:
            yield lease_id
        finally:
            await self.release(lease_id)

    async def start_correction_loop(self):
        """Start background counter correction task."""
        if self._correction_task is not None:
            return
        self._correction_task = asyncio.create_task(self._correction_loop())

    async def _correction_loop(self):
        """Periodically verify counters match actual lease keys."""
        while True:
            await asyncio.sleep(self._config.correction_interval)
            try:
                await self._ensure_scripts()
                result = await self._correct_sha(
                    keys=[TOTAL_KEY, WRITES_KEY],
                    args=[LEASE_PREFIX],
                )
                corrected, actual_total, actual_writes, stored_total, stored_writes = result
                if corrected:
                    logger.warning(
                        "Counter correction: total %d->%d, writes %d->%d",
                        stored_total, actual_total, stored_writes, actual_writes,
                    )
                    self._metrics.record_lease_expiration(
                        self._config.service_name,
                        abs(stored_total - actual_total),
                    )
            except Exception as e:
                logger.debug("Counter correction skipped: %s", e)
