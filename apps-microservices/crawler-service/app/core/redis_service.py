import json
import logging
from typing import Optional, Any, List, Dict

import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisService:
    """
    A reusable singleton service for interacting with Redis.
    Handles connection management and JSON serialization/deserialization.
    """
    def __init__(self):
        self._client: Optional[Redis] = None

    async def connect(self):
        """Establishes the connection pool to Redis."""
        if self._client:
            return
        try:
            redis_url = settings.REDIS_URL
            # If a password is provided, inject it into the URL for authentication.
            if settings.REDIS_PASSWORD:
                redis_url = redis_url.replace("://", f"://:{settings.REDIS_PASSWORD}@")

            self._client = redis.from_url(redis_url, decode_responses=True)
            await self._client.ping()
            logger.info("Successfully connected to Redis.")
        except Exception as e:
            logger.critical(f"Failed to connect to Redis: {e}", exc_info=True)
            self._client = None

    async def disconnect(self):
        """Closes the Redis connection pool."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed.")

    async def set_data(self, key: str, data: Dict[str, Any], ttl: Optional[int] = None):
        """Sets data for a key, serializing it to JSON."""
        if not self._client:
            raise ConnectionError("Redis is not connected.")
        try:
            value = json.dumps(data, default=str) # Use default=str for datetime objects
            await self._client.set(key, value, ex=ttl)
        except Exception as e:
            logger.error(f"Failed to set data for key '{key}' in Redis: {e}", exc_info=True)

    async def get_data(self, key: str) -> Optional[Dict[str, Any]]:
        """Gets data for a key, deserializing it from JSON."""
        if not self._client:
            raise ConnectionError("Redis is not connected.")
        try:
            value = await self._client.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.error(f"Failed to get data for key '{key}' from Redis: {e}", exc_info=True)
        return None

    async def delete_data(self, key: str) -> bool:
        """Deletes a key from Redis."""
        if not self._client:
            raise ConnectionError("Redis is not connected.")
        try:
            result = await self._client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Failed to delete key '{key}' from Redis: {e}", exc_info=True)
            return False

    async def get_all_keys_by_prefix(self, prefix: str) -> List[str]:
        """Gets all keys matching a given prefix."""
        if not self._client:
            raise ConnectionError("Redis is not connected.")
        try:
            return [key async for key in self._client.scan_iter(f"{prefix}*")]
        except Exception as e:
            logger.error(f"Failed to scan keys with prefix '{prefix}' from Redis: {e}", exc_info=True)
            return []

# Create a single instance to be used throughout the application
redis_service = RedisService()