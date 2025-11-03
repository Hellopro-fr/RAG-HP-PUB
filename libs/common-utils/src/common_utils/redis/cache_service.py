import json
import logging
import os
from functools import wraps
from typing import Callable, Any, TypeVar, ParamSpec

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
    redis_url = os.getenv("REDIS_URL")
    try:
        logging.info(f"Trying to connect to Redis at {redis_url}")
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
        logger.info("Redis connection pool closed.")

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
