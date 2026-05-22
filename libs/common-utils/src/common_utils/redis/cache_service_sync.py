"""Synchronous Redis cache service — mirror of cache_service.py for pika-based
sync consumers (5 qdrant database services, website-processor-service,
image-download-service).

Same env vars, same client_name format, same bounded pool. Use this when the
calling code cannot be made async (pika BlockingConnection, sync RabbitMQ
consumers). Greenfield code should prefer cache_service.py (async).

Minimal helpers exposed (init/close/get_client). Sync callers wrap the client
returned by ``get_client()`` for their service-specific logic (Lua scripts,
pipelines, rate-limiter sliding windows). Add domain helpers here only when a
migration demands one.

See docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md
"""

import logging
import os
import threading
from typing import Optional

import redis as sync_redis

logger = logging.getLogger(__name__)

# Mirror async constants — keep in sync with cache_service.py
DEFAULT_MAX_CONNECTIONS = 20
DEFAULT_SOCKET_TIMEOUT_S = 10
DEFAULT_SOCKET_CONNECT_TIMEOUT_S = 5
DEFAULT_HEALTH_CHECK_INTERVAL_S = 30

# Module-global client. Mirrors cache_service.redis_client (async sibling).
redis_client: Optional[sync_redis.Redis] = None

# Threading lock guards init_redis_pool_sync() against concurrent startup
# threads (e.g. uvicorn workers, pika consumer threads).
_init_lock = threading.Lock()


def _replica_name() -> str:
    """Pod identity. Matches cache_service._replica_name()."""
    return os.getenv("HOSTNAME") or "no-hostname"


def _client_name() -> str:
    """Build the Redis CLIENT SETNAME value. Matches cache_service._client_name().

    Format: ``{service}-{pod}-pid{N}``
    """
    service = (os.getenv("SERVICE_NAME") or "").strip()
    if not service:
        logger.warning(
            "SERVICE_NAME env var unset; Redis CLIENT SETNAME will use 'unset-service'. "
            "Set SERVICE_NAME in your deployment to make CLIENT LIST greppable per service."
        )
        service = "unset-service"
    return f"{service}-{_replica_name()}-pid{os.getpid()}"


def _read_positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return max(1, default)
    try:
        return max(1, int(raw))
    except ValueError:
        return max(1, default)


def _read_positive_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return max(1.0, default)
    try:
        return max(1.0, float(raw))
    except ValueError:
        return max(1.0, default)


def _ping_safe(client: "sync_redis.Redis") -> bool:
    try:
        return bool(client.ping())
    except Exception:
        return False


def init_redis_pool_sync() -> Optional[sync_redis.Redis]:
    """Synchronous twin of ``init_redis_pool()``. Idempotent.

    Returns the client (or ``None`` if REDIS_URL unset / connection failed).
    Also stores it in module-global ``redis_client`` so callers using
    ``get_client()`` can pick it up without explicit passing.

    Env vars (same as async sibling):
      - REDIS_URL (required)
      - REDIS_MAX_CONNECTIONS (default 20)
      - REDIS_SOCKET_TIMEOUT_S (default 10)
      - REDIS_SOCKET_CONNECT_TIMEOUT_S (default 5)
      - REDIS_HEALTH_CHECK_INTERVAL_S (default 30)
      - SERVICE_NAME (warns if unset)
      - HOSTNAME (set by k8s/docker; fallback 'no-hostname')
    """
    global redis_client
    with _init_lock:
        if redis_client is not None and _ping_safe(redis_client):
            logger.info("Sync Redis pool already initialized and connected.")
            return redis_client

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.critical("REDIS_URL not set. Sync caching unavailable.")
            redis_client = None
            return None

        max_conn = _read_positive_int_env("REDIS_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS)
        sock_to = _read_positive_float_env("REDIS_SOCKET_TIMEOUT_S", DEFAULT_SOCKET_TIMEOUT_S)
        sock_conn_to = _read_positive_float_env("REDIS_SOCKET_CONNECT_TIMEOUT_S", DEFAULT_SOCKET_CONNECT_TIMEOUT_S)
        health_iv = _read_positive_int_env("REDIS_HEALTH_CHECK_INTERVAL_S", DEFAULT_HEALTH_CHECK_INTERVAL_S)
        client_name = _client_name()

        try:
            logger.info(
                f"Connecting to Redis (sync) at {redis_url.split('@')[-1]} "
                f"(max_conn={max_conn}, name={client_name})"
            )
            redis_client = sync_redis.from_url(
                redis_url,
                decode_responses=True,
                max_connections=max_conn,
                socket_keepalive=True,
                socket_connect_timeout=sock_conn_to,
                socket_timeout=sock_to,
                health_check_interval=health_iv,
                client_name=client_name,
            )
            redis_client.ping()
            logger.info("Successfully connected to Redis (sync).")
            return redis_client
        except (sync_redis.RedisError, OSError) as e:
            logger.warning(f"Sync Redis init failed: {e}. Caching unavailable.")
            if redis_client is not None:
                try:
                    redis_client.close()
                except Exception:
                    pass
                redis_client = None
            return None


def close_redis_pool_sync() -> None:
    """Closes the sync Redis connection pool. Safe to call multiple times."""
    global redis_client
    with _init_lock:
        if redis_client is not None:
            try:
                redis_client.close()
            except Exception as e:
                logger.warning(f"Error closing sync Redis pool: {e}")
            redis_client = None
            logger.info("Sync Redis connection pool closed.")


def get_client() -> Optional[sync_redis.Redis]:
    """Return the module-global sync client (or ``None`` if not initialized).

    Sync callers that need raw Redis access (``register_script``, ``pipeline``,
    transactions, ``eval``, ``set``, ``get``, etc.) use this and call methods
    directly on the returned client.
    """
    return redis_client
