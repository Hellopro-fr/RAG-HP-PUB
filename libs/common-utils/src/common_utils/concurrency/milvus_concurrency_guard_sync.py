"""Synchronous Redis-backed global concurrency guard for pika-based services."""

import logging
import threading
import time
import uuid
from contextlib import contextmanager

from common_utils.concurrency.config import GuardConfig
from common_utils.concurrency.lua_scripts import ACQUIRE_SCRIPT, RELEASE_SCRIPT
from common_utils.concurrency.metrics import GuardMetrics

logger = logging.getLogger(__name__)

TOTAL_KEY = "milvus:slots:total"
WRITES_KEY = "milvus:slots:writes"
TIER2_WAITERS_KEY = "milvus:slots:tier2_waiters"
LEASE_PREFIX = "milvus:slots:lease:"


class MilvusConcurrencyGuardSync:
    """Synchronous Redis-backed global concurrency guard for pika-based services.

    Mirror of MilvusConcurrencyGuard (async) but uses blocking I/O and
    threading.Semaphore for the local fallback — suitable for RabbitMQ
    consumer callbacks that run in pika's blocking connection thread.
    """

    def __init__(self, redis_client, config: GuardConfig, metrics: GuardMetrics | None = None):
        self._redis = redis_client
        self._config = config
        self._metrics = metrics or GuardMetrics()
        self._fallback_semaphore = threading.Semaphore(config.fallback_limit)
        self._using_fallback = False
        self._acquire_script = None
        self._release_script = None
        self._metrics.set_config_gauges(config.global_max, config.write_ceiling)

    def _ensure_scripts(self):
        """Register Lua scripts on first use (synchronous)."""
        if self._redis is None:
            raise ConnectionError("Redis client is None")
        if self._acquire_script is None:
            self._acquire_script = self._redis.register_script(ACQUIRE_SCRIPT)
            self._release_script = self._redis.register_script(RELEASE_SCRIPT)

    def acquire(self) -> str:
        """Acquire a slot. Returns lease_id. Raises TimeoutError on deadline."""
        tier = self._config.tier
        service = self._config.service_name
        tier_str = str(tier)
        is_tier2_waiter = False

        try:
            self._ensure_scripts()
        except Exception as e:
            logger.warning("Redis unavailable: %s — using fallback", e)
            return self._acquire_fallback()

        lease_id = f"{service}:{uuid.uuid4().hex[:12]}"
        lease_key = f"{LEASE_PREFIX}{lease_id}"
        lease_value = f"{service}:{tier}:{int(time.time())}"

        start = time.monotonic()
        deadline = start + self._config.acquire_timeout
        first_attempt = True

        while True:
            try:
                result = self._acquire_script(
                    keys=[TOTAL_KEY, WRITES_KEY, TIER2_WAITERS_KEY, lease_key],
                    args=[tier, self._config.global_max, self._config.write_ceiling, lease_value, self._config.lease_ttl],
                )
                if result == 1:
                    if is_tier2_waiter:
                        self._redis.decr(TIER2_WAITERS_KEY)
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
                    self._redis.incr(TIER2_WAITERS_KEY)
                    is_tier2_waiter = True
                    first_attempt = False

                if time.monotonic() >= deadline:
                    if is_tier2_waiter:
                        self._redis.decr(TIER2_WAITERS_KEY)
                    self._metrics.record_timeout(tier=tier_str, service=service)
                    raise TimeoutError(
                        f"Could not acquire Milvus slot within {self._config.acquire_timeout}s "
                        f"(service={service}, tier={tier})"
                    )
                time.sleep(self._config.retry_interval)

            except TimeoutError:
                raise
            except Exception as e:
                if is_tier2_waiter:
                    try:
                        self._redis.decr(TIER2_WAITERS_KEY)
                    except Exception:
                        pass
                logger.warning("Redis error: %s — using fallback", e)
                return self._acquire_fallback()

    def _acquire_fallback(self) -> str:
        """Local semaphore fallback when Redis is unavailable."""
        if not self._using_fallback:
            self._using_fallback = True
            self._metrics.set_fallback(self._config.service_name, True)
            logger.warning(
                "Redis unavailable — falling back to local concurrency limit (%d)",
                self._config.fallback_limit,
            )
        self._fallback_semaphore.acquire()
        return f"fallback:{uuid.uuid4().hex[:12]}"

    def release(self, lease_id: str):
        """Release a slot by lease_id."""
        tier = self._config.tier
        service = self._config.service_name
        tier_str = str(tier)

        if lease_id.startswith("fallback:"):
            self._fallback_semaphore.release()
            return

        lease_key = f"{LEASE_PREFIX}{lease_id}"
        try:
            self._ensure_scripts()
            result = self._release_script(
                keys=[TOTAL_KEY, WRITES_KEY, lease_key],
                args=[tier],
            )
            if result == 1:
                self._metrics.record_release(tier=tier_str, service=service)
        except Exception as e:
            logger.warning("Redis error during release: %s", e)

    def extend_lease(self, lease_id: str):
        """Extend TTL for long-running operations."""
        if lease_id.startswith("fallback:"):
            return
        try:
            self._redis.expire(f"{LEASE_PREFIX}{lease_id}", self._config.lease_ttl)
        except Exception as e:
            logger.warning("Failed to extend lease: %s", e)

    @contextmanager
    def slot(self):
        """Context manager: acquire, yield, release. Handles cleanup on exception."""
        lease_id = self.acquire()
        try:
            yield lease_id
        finally:
            self.release(lease_id)
