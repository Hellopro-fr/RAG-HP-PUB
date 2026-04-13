from prometheus_client import Counter, Gauge, Histogram

# Module-level metric definitions (registered once at import time)
_SLOTS_ACTIVE = Gauge(
    "milvus_guard_slots_active",
    "Current Milvus concurrency slots in use",
    ["tier", "service"],
)
_SLOTS_MAX = Gauge(
    "milvus_guard_slots_max",
    "Configured global max concurrent Milvus operations",
)
_WRITE_CEILING = Gauge(
    "milvus_guard_write_ceiling",
    "Configured max concurrent write operations",
)
_ACQUIRE_DURATION = Histogram(
    "milvus_guard_acquire_duration_seconds",
    "Time spent waiting to acquire a Milvus concurrency slot",
    ["tier", "service"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
_ACQUIRE_TIMEOUTS = Counter(
    "milvus_guard_acquire_timeouts_total",
    "Number of acquire attempts that timed out",
    ["tier", "service"],
)
_LEASE_EXPIRATIONS = Counter(
    "milvus_guard_lease_expirations_total",
    "Number of lease expirations detected during counter correction",
    ["service"],
)
_FALLBACK_ACTIVE = Gauge(
    "milvus_guard_fallback_active",
    "1 if Redis is unavailable and local fallback is active",
    ["service"],
)


class GuardMetrics:
    """Prometheus metrics for MilvusConcurrencyGuard.

    Uses module-level singleton metrics to avoid duplicate registration
    errors when multiple instances are created (e.g., across tests).
    """

    def __init__(self):
        self.slots_active = _SLOTS_ACTIVE
        self.slots_max = _SLOTS_MAX
        self.write_ceiling = _WRITE_CEILING
        self.acquire_duration = _ACQUIRE_DURATION
        self.acquire_timeouts = _ACQUIRE_TIMEOUTS
        self.lease_expirations = _LEASE_EXPIRATIONS
        self.fallback_active = _FALLBACK_ACTIVE

    def record_acquire(self, tier: str, service: str, duration: float):
        """Record a successful slot acquisition."""
        self.slots_active.labels(tier=tier, service=service).inc()
        self.acquire_duration.labels(tier=tier, service=service).observe(duration)

    def record_release(self, tier: str, service: str):
        """Record a slot release."""
        self.slots_active.labels(tier=tier, service=service).dec()

    def record_timeout(self, tier: str, service: str):
        """Record an acquire timeout."""
        self.acquire_timeouts.labels(tier=tier, service=service).inc()

    def set_config_gauges(self, global_max: int, write_ceiling: int):
        """Set the configuration gauges (typically called once at startup)."""
        self.slots_max.set(global_max)
        self.write_ceiling.set(write_ceiling)

    def set_fallback(self, service: str, active: bool):
        """Set fallback mode indicator (1 = Redis unavailable, 0 = normal)."""
        self.fallback_active.labels(service=service).set(1 if active else 0)

    def record_lease_expiration(self, service: str, count: int = 1):
        """Record expired leases found during counter correction."""
        self.lease_expirations.labels(service=service).inc(count)
