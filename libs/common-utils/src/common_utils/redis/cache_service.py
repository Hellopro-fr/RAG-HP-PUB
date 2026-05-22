import asyncio
import json
import logging
import os
from functools import wraps
from typing import Callable, Any, TypeVar, ParamSpec, Optional, Dict, List

import redis.asyncio as redis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Type variables for generic function wrapping
P = ParamSpec("P")
R = TypeVar("R")

# Global Redis client instance
redis_client: redis.Redis | None = None

# Guards init_redis_pool() against concurrent startup coroutines racing past the
# already-initialized check before redis_client is assigned. Lazy-init in
# Python 3.10+ binds to the running event loop on first acquire, so module-level
# construction is safe.
_init_lock: asyncio.Lock = asyncio.Lock()

DEFAULT_MAX_CONNECTIONS = 20
DEFAULT_SOCKET_TIMEOUT_S = 10
DEFAULT_SOCKET_CONNECT_TIMEOUT_S = 5
DEFAULT_HEALTH_CHECK_INTERVAL_S = 30

DEFAULT_RETRY_ATTEMPTS = 2
DEFAULT_RETRY_BACKOFF_BASE_S = 0.5


def _replica_name() -> str:
    """Pod identity. HOSTNAME is set by k8s/docker; falls back to the literal
    'no-hostname' so the appended PID always disambiguates replicas
    (multi-worker uvicorn/gunicorn, container restarts, ad-hoc shells).

    See docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md
    """
    return os.getenv("HOSTNAME") or "no-hostname"


def _client_name() -> str:
    """Build the Redis CLIENT SETNAME value used by init_redis_pool.

    Format: ``{service}-{pod}-pid{N}``
    Example: ``api-rest-milvus-api-rest-milvus-7d4b9-pid12345``

    ``service`` is read from the SERVICE_NAME env var. If unset, empty, or
    whitespace, a WARNING is logged and the literal ``unset-service`` is used —
    the connection is still attributable in ``CLIENT LIST`` and the warning
    surfaces misconfiguration in logs without breaking startup.

    ``pod`` is the HOSTNAME env var, or ``no-hostname`` fallback.
    ``pid`` is always appended (multi-worker servers are otherwise indistinguishable).

    See docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md
    """
    service = (os.getenv("SERVICE_NAME") or "").strip()
    if not service:
        logger.warning(
            "SERVICE_NAME env var unset; Redis CLIENT SETNAME will use 'unset-service'. "
            "Set SERVICE_NAME in your deployment to make CLIENT LIST greppable per service."
        )
        service = "unset-service"
    return f"{service}-{_replica_name()}-pid{os.getpid()}"


async def _ping_safe(client: "redis.Redis") -> bool:
    try:
        return await client.ping()
    except Exception:
        return False


def _read_positive_int_env(name: str, default: int) -> int:
    """Reads env var as int, falls back to default on empty/missing/invalid. Clamped to >=1."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return max(1, default)
    try:
        return max(1, int(raw))
    except ValueError:
        return max(1, default)


def _read_positive_float_env(name: str, default: float) -> float:
    """Reads env var as float, falls back to default on empty/missing/invalid. Clamped to >=1.0."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return max(1.0, default)
    try:
        return max(1.0, float(raw))
    except ValueError:
        return max(1.0, default)


async def init_redis_pool():
    """
    Initializes the Redis connection pool with a bounded client + proactive
    health check. Idempotent — concurrent callers are serialized by an asyncio
    lock so the first one wins and subsequent calls reuse the existing client.

    Specs:
      - docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md
      - docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md
    """
    global redis_client
    async with _init_lock:
        if redis_client and await _ping_safe(redis_client):
            logger.info("Redis pool already initialized and connected.")
            return

        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            logger.critical("REDIS_URL environment variable not set. Caching and state management will be unavailable.")
            redis_client = None
            return

        max_conn = _read_positive_int_env("REDIS_MAX_CONNECTIONS", DEFAULT_MAX_CONNECTIONS)
        sock_to = _read_positive_float_env("REDIS_SOCKET_TIMEOUT_S", DEFAULT_SOCKET_TIMEOUT_S)
        sock_conn_to = _read_positive_float_env("REDIS_SOCKET_CONNECT_TIMEOUT_S", DEFAULT_SOCKET_CONNECT_TIMEOUT_S)
        health_iv = _read_positive_int_env("REDIS_HEALTH_CHECK_INTERVAL_S", DEFAULT_HEALTH_CHECK_INTERVAL_S)
        client_name = _client_name()

        try:
            logger.info(
                f"Connecting to Redis at {redis_url.split('@')[-1]} "
                f"(max_conn={max_conn}, name={client_name})"
            )
            redis_client = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=max_conn,
                socket_keepalive=True,
                socket_connect_timeout=sock_conn_to,
                socket_timeout=sock_to,
                health_check_interval=health_iv,
                client_name=client_name,
            )
            await redis_client.ping()
            # Register Lua scripts for EVALSHA-based execution (avoids sending raw Lua on every call)
            global _safe_decr_script, _delete_if_terminal_script
            _safe_decr_script = redis_client.register_script(_SAFE_DECR_LUA)
            _delete_if_terminal_script = redis_client.register_script(_DELETE_IF_TERMINAL_LUA)
            logger.info("Successfully connected to Redis.")
        except (redis.RedisError, OSError, asyncio.TimeoutError) as e:
            logger.warning(f"Could not connect to Redis: {e}. Caching will be unavailable.")
            # Best-effort close on half-built client; ignore secondary failures.
            if redis_client is not None:
                try:
                    await redis_client.close()
                except Exception:
                    pass
            redis_client = None

async def close_redis_pool():
    """
    Closes the Redis connection pool.
    """
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
        logger.info("Redis connection pool closed.")

# --- General Purpose Functions ---

async def set_json(key: str, data: Dict[str, Any], ttl: Optional[int] = None):
    """Sets a dictionary for a key, serializing it to JSON."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        value = json.dumps(data, default=str)
        await redis_client.set(key, value, ex=ttl)
    except Exception as e:
        logger.error(f"Failed to set JSON for key '{key}' in Redis: {e}", exc_info=True)

async def set_json_nx(key: str, data: Dict[str, Any]) -> bool:
    """Atomically sets a key only if it does not already exist (SET NX).
    Returns True if the key was set, False if it already existed."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        value = json.dumps(data, default=str)
        result = await redis_client.set(key, value, nx=True)
        return result is True
    except Exception as e:
        logger.error(f"Failed to SET NX for key '{key}' in Redis: {e}", exc_info=True)
        return False

async def get_json(key: str) -> Optional[Dict[str, Any]]:
    """Gets a dictionary for a key, deserializing it from JSON."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        value = await redis_client.get(key)
        if value:
            return json.loads(value)
    except Exception as e:
        logger.error(f"Failed to get JSON for key '{key}' from Redis: {e}", exc_info=True)
    return None

async def set_key(key: str, value: Any, ttl: Optional[int] = None):
    """Sets a raw value for a key."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        await redis_client.set(key, value, ex=ttl)
    except Exception as e:
        logger.error(f"Failed to set key '{key}' in Redis: {e}", exc_info=True)

async def get_key(key: str) -> Optional[str]:
    """Gets the raw string value of a key."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        return await redis_client.get(key)
    except Exception as e:
        logger.error(f"Failed to get key '{key}' from Redis: {e}", exc_info=True)
    return None

async def delete_key(key: str) -> bool:
    """Deletes a key from Redis."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        result = await redis_client.delete(key)
        return result > 0
    except Exception as e:
        logger.error(f"Failed to delete key '{key}' from Redis: {e}", exc_info=True)
        return False

async def scan_keys_by_prefix(prefix: str) -> List[str]:
    """Gets all keys matching a given prefix using SCAN."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        return [key async for key in redis_client.scan_iter(f"{prefix}*")]
    except Exception as e:
        logger.error(f"Failed to scan keys with prefix '{prefix}' from Redis: {e}", exc_info=True)
        return []

async def increment_key(key: str) -> int:
    """Atomically increments a key's value by 1."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        return await redis_client.incr(key)
    except Exception as e:
        logger.error(f"Failed to increment key '{key}' in Redis: {e}", exc_info=True)
        return 0

async def decrement_key(key: str) -> int:
    """Atomically decrements a key's value by 1.

    WARNING: This function can drive the counter below zero. For counters that
    must never go negative (e.g. running-job counts), use safe_decrement_key() instead.
    """
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        return await redis_client.decr(key)
    except Exception as e:
        logger.error(f"Failed to decrement key '{key}' in Redis: {e}", exc_info=True)
        return 0

# Lua script: atomically decrement only if current value > 0, else return 0.
_SAFE_DECR_LUA = """
local current = tonumber(redis.call('GET', KEYS[1])) or 0
if current > 0 then
    return redis.call('DECR', KEYS[1])
else
    return 0
end
"""

# Lua script: atomically delete a key only if its JSON "status" field is terminal.
# Returns 1 if the key was deleted, 0 if the key didn't exist or had a non-terminal status.
_DELETE_IF_TERMINAL_LUA = """
local val = redis.call('GET', KEYS[1])
if not val then return 0 end
local status = cjson.decode(val)["status"]
if status == "failed" or status == "finished" then
    redis.call('DEL', KEYS[1])
    return 1
end
return 0
"""

# Registered script handles — set by init_redis_pool().
_safe_decr_script = None
_delete_if_terminal_script = None

async def safe_decrement_key(key: str) -> int:
    """Atomically decrements a key's value by 1, with a floor of 0 (never goes negative).

    Returns the new value after decrement, or 0 if the key was already at 0.
    On Redis error, returns 0 and logs — callers cannot distinguish floor from failure
    without inspecting logs.
    """
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        if _safe_decr_script is not None:
            result = await _safe_decr_script(keys=[key])
        else:
            result = await redis_client.eval(_SAFE_DECR_LUA, 1, key)
        return int(result)
    except Exception as e:
        logger.error(f"Failed to safe-decrement key '{key}' in Redis: {e}", exc_info=True)
        return 0


async def delete_if_terminal(key: str) -> bool:
    """Atomically deletes a key only if its JSON 'status' is 'failed' or 'finished'.

    Uses a Lua script to avoid the race condition of GET-then-DELETE across replicas.
    Returns True if the key was deleted, False if it didn't exist or had a non-terminal status.
    """
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        if _delete_if_terminal_script is not None:
            result = await _delete_if_terminal_script(keys=[key])
        else:
            result = await redis_client.eval(_DELETE_IF_TERMINAL_LUA, 1, key)
        return int(result) == 1
    except Exception as e:
        logger.error(f"Failed to delete-if-terminal for key '{key}' in Redis: {e}", exc_info=True)
        return False


async def publish(channel: str, message: str):
    """Publishes a message to a specific Redis channel."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        await redis_client.publish(channel, message)
    except Exception as e:
        logger.error(f"Failed to publish message to channel '{channel}': {e}", exc_info=True)

# --- Retry Helper ---

async def call_with_retry(
    fn: Callable[..., Any],
    *args: Any,
    attempts: int = DEFAULT_RETRY_ATTEMPTS,
    backoff_base_s: float = DEFAULT_RETRY_BACKOFF_BASE_S,
    **kwargs: Any,
) -> Any:
    """Run a redis-py async call with bounded retry on transient connection errors.

    Retries on ``redis.ConnectionError``, ``redis.TimeoutError``, ``OSError``,
    and ``asyncio.TimeoutError``. Other exceptions (RedisError data errors,
    Lua failures, etc.) propagate immediately.

    Backoff between attempts: ``backoff_base_s * 2 ** attempt``.
    The final attempt's exception is re-raised — callers see the real error,
    not a silent None.

    Usage:
        result = await call_with_retry(redis_client.get, "mykey")
        await call_with_retry(redis_client.set, "k", "v", attempts=3)

    This wrapper is opt-in. Existing helpers (set_json, get_json, ...) keep
    their swallow-on-error semantics for backwards compat. Use this when the
    caller needs the failure surfaced.

    See docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md
    """
    last_exc: Exception | None = None
    for attempt in range(attempts + 1):
        try:
            return await fn(*args, **kwargs)
        except (redis.ConnectionError, redis.TimeoutError, OSError, asyncio.TimeoutError) as e:
            last_exc = e
            if attempt < attempts:
                wait_s = backoff_base_s * (2 ** attempt)
                logger.warning(
                    f"Redis transient error on attempt {attempt + 1}/{attempts + 1}: {e}. "
                    f"Retrying in {wait_s:.2f}s."
                )
                await asyncio.sleep(wait_s)
                continue
            raise
    assert last_exc is not None  # unreachable; loop either returns or raises
    raise last_exc


# --- Caching Decorator (Existing Functionality) ---

def _generate_cache_key(func: Callable, *args: P.args, **kwargs: P.kwargs) -> str:
    """
    Generates a unique cache key for a function call based on its name and arguments.
    """
    func_name = func.__name__
    # Simple serialization of args and kwargs for key generation
    # This might need more sophisticated handling for complex objects
    args_str = json.dumps(args, sort_keys=True, default=str)
    kwargs_str = json.dumps(kwargs, sort_keys=True, default=str)
    return f"cache:{func_name}:{args_str}:{kwargs_str}"

async def cache_or_execute(
    func: Callable[P, R],
    *args: P.args,
    expire_seconds: int = 300,
    **kwargs: P.kwargs
) -> R:
    """
    A generic caching wrapper that attempts to retrieve data from Redis first.
    If a cache hit occurs, it returns the cached data.
    If a cache miss occurs, it executes the original function, caches its result,
    and then returns the result.
    Handles Redis unavailability gracefully.
    """
    if not redis_client:
        logger.debug("Redis client not available. Executing function without caching.")
        return await func(*args, **kwargs)

    cache_key = _generate_cache_key(func, *args, **kwargs)

    try:
        cached_result = await redis_client.get(cache_key)
        if cached_result:
            logger.info(f"CACHE HIT for key: {cache_key}")
            return json.loads(cached_result)
    except redis.RedisError as e:
        logger.error(f"Error accessing Redis for key {cache_key}: {e}. Executing function without caching.")
        return await func(*args, **kwargs)

    # Cache miss or Redis error during get
    logger.info(f"CACHE MISS for key: {cache_key}. Executing function.")
    result = await func(*args, **kwargs)

    try:
        # Cache the result with an expiration time
        await redis_client.setex(cache_key, expire_seconds, json.dumps(result))
        logger.info(f"Cached result for key: {cache_key} with expiration {expire_seconds}s.")
    except redis.RedisError as e:
        logger.error(f"Error caching result for key {cache_key}: {e}. Result not cached.")

    return result
