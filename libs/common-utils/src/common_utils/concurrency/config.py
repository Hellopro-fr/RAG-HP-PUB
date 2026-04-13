import os
from dataclasses import dataclass, field


@dataclass
class GuardConfig:
    """Configuration for MilvusConcurrencyGuard."""

    global_max: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_GLOBAL_MAX_CONCURRENT", "50"))
    )
    write_ceiling: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_WRITE_CEILING", "30"))
    )
    tier: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_TIER", "3"))
    )
    service_name: str = field(
        default_factory=lambda: os.getenv("MILVUS_CONCURRENCY_SERVICE_NAME", "unknown")
    )
    lease_ttl: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_LEASE_TTL", "60"))
    )
    acquire_timeout: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_ACQUIRE_TIMEOUT", "30"))
    )
    retry_interval: float = field(
        default_factory=lambda: float(os.getenv("MILVUS_CONCURRENCY_RETRY_INTERVAL", "0.5"))
    )
    fallback_limit: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_FALLBACK_LIMIT", "5"))
    )
    correction_interval: int = field(
        default_factory=lambda: int(os.getenv("MILVUS_CONCURRENCY_CORRECTION_INTERVAL", "30"))
    )
