import hashlib
import json
import logging
import os
import redis.asyncio as redis
from typing import Optional, List, AsyncGenerator

logger = logging.getLogger("state_manager")

class DedupManager:
    """
    Manages URL deduplication using a Redis Set.
    Stores FULL URLs to allow retrieval for history file generation.
    """
    def __init__(self, redis_url: str, crawl_id: str, ttl_seconds: int = 7 * 24 * 3600):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.crawl_id = crawl_id
        self.key = f"dedup:{crawl_id}"
        self.ttl = ttl_seconds
        self._ttl_set = False

    async def _ensure_ttl(self):
        if not self._ttl_set:
            await self.redis.expire(self.key, self.ttl)
            self._ttl_set = True

    async def add_url(self, url: str) -> bool:
        """
        Adds a URL to the set. Returns True if it was new, False if already present.
        """
        is_new = await self.redis.sadd(self.key, url)
        await self._ensure_ttl()
        return is_new == 1

    async def is_known(self, url: str) -> bool:
        """
        Checks if a URL is already in the set.
        """
        return await self.redis.sismember(self.key, url)

    async def load_from_list(self, urls: List[str]):
        """
        Bulk loads a list of URLs into the deduplication set.
        """
        if not urls:
            return
        
        # Process in chunks
        chunk_size = 1000
        for i in range(0, len(urls), chunk_size):
            chunk = urls[i:i + chunk_size]
            await self.redis.sadd(self.key, *chunk)
        
        await self._ensure_ttl()
        logger.info(f"Loaded {len(urls)} URLs into deduplication set.")

    async def get_all_urls(self) -> AsyncGenerator[str, None]:
        """
        Yields all URLs from the set.
        """
        async for member in self.redis.sscan_iter(self.key):
            yield member

    async def cleanup(self):
        """
        Deletes the deduplication set from Redis.
        """
        await self.redis.delete(self.key)
        await self.redis.close()
        logger.info(f"Cleaned up deduplication set for {self.crawl_id}")


class StatsManager:
    """
    Manages update statistics and circuit breaker thresholds using Redis Hash.
    Supports resumability by saving/loading state to disk.
    """
    def __init__(self, redis_url: str, crawl_id: str, storage_path: str, ttl_seconds: int = 7 * 24 * 3600):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.crawl_id = crawl_id
        self.key = f"stats:{crawl_id}"
        self.storage_path = storage_path
        self.stats_file = os.path.join(storage_path, "update_stats.json")
        self.ttl = ttl_seconds
        self._ttl_set = False

    async def _ensure_ttl(self):
        if not self._ttl_set:
            await self.redis.expire(self.key, self.ttl)
            self._ttl_set = True

    async def increment(self, metric: str) -> int:
        """
        Increments a specific metric (errors, redirects, new_urls).
        """
        val = await self.redis.hincrby(self.key, metric, 1)
        await self._ensure_ttl()
        return val

    async def check_threshold(self, metric: str, limit: int) -> bool:
        """
        Checks if a metric has exceeded its limit.
        Returns True if threshold is EXCEEDED.
        """
        if limit is None or limit <= 0:
            return False
        
        val_str = await self.redis.hget(self.key, metric)
        val = int(val_str) if val_str else 0
        
        if val >= limit:
            logger.warning(f"THRESHOLD BREACHED: {metric} ({val}) >= limit ({limit})")
            return True
        return False

    async def save_state_to_disk(self):
        """
        Persists current stats to JSON for resumability.
        """
        try:
            data = await self.redis.hgetall(self.key)
            # Convert string values to ints
            clean_data = {k: int(v) for k, v in data.items()}
            with open(self.stats_file, 'w') as f:
                json.dump(clean_data, f)
        except Exception as e:
            logger.error(f"Failed to save stats to disk: {e}")

    async def load_state_from_disk(self):
        """
        Loads stats from JSON into Redis (if exists).
        """
        if not os.path.exists(self.stats_file):
            return

        try:
            with open(self.stats_file, 'r') as f:
                data = json.load(f)
            
            if data:
                # Redis HSET expects mapping
                await self.redis.hset(self.key, mapping=data)
                logger.info(f"Loaded existing stats: {data}")
        except Exception as e:
            logger.error(f"Failed to load stats from disk: {e}")

    async def cleanup(self):
        """
        Deletes the stats key from Redis.
        """
        await self.redis.delete(self.key)
        await self.redis.close()
        logger.info(f"Cleaned up stats for {self.crawl_id}")
