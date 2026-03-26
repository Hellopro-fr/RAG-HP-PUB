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

async def init_redis_pool():
    """
    Initializes the Redis connection pool.
    Connects to Redis using the URL from environment variables.
    """
    global redis_client
    if redis_client and await redis_client.ping():
        logger.info("Redis pool already initialized and connected.")
        return
        
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        logger.critical("REDIS_URL environment variable not set. Caching and state management will be unavailable.")
        redis_client = None
        return
        
    try:
        logging.info(f"Connecting to Redis at {redis_url.split('@')[-1]}...") # Avoid logging password
        redis_client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await redis_client.ping()
        logger.info("Successfully connected to Redis.")
    except redis.RedisError as e:
        logger.warning(f"Could not connect to Redis: {e}. Caching will be unavailable.")
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
    """Atomically decrements a key's value by 1."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        return await redis_client.decr(key)
    except Exception as e:
        logger.error(f"Failed to decrement key '{key}' in Redis: {e}", exc_info=True)
        return 0

# Lua script: atomically decrement only if current value > 0, else return 0.
_SAFE_DECR_SCRIPT = """
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
if current > 0 then
    return redis.call('DECR', KEYS[1])
else
    return 0
end
"""

async def safe_decrement_key(key: str) -> int:
    """Atomically decrements a key's value by 1, with a floor of 0 (never goes negative)."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        result = await redis_client.eval(_SAFE_DECR_SCRIPT, 1, key)
        return int(result)
    except Exception as e:
        logger.error(f"Failed to safe-decrement key '{key}' in Redis: {e}", exc_info=True)
        return 0


async def publish(channel: str, message: str):
    """Publishes a message to a specific Redis channel."""
    if not redis_client:
        raise ConnectionError("Redis is not connected.")
    try:
        await redis_client.publish(channel, message)
    except Exception as e:
        logger.error(f"Failed to publish message to channel '{channel}': {e}", exc_info=True)

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
