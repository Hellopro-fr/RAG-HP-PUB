import redis.asyncio as redis
import time
import logging
import os

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self.redis = redis.from_url(self.redis_url)
        # Default limit: 2 requests per second per domain
        self.default_rate = 2 
        self.window = 1 # second

    async def acquire(self, domain: str):
        """
        Simple sliding window or token bucket rate limiter.
        Here we use a simple expiration key strategy for req/sec.
        """
        key = f"ratelimit:{domain}"
        
        while True:
            try:
                # Get current count
                current = await self.redis.get(key)
                if current and int(current) >= self.default_rate:
                    # Limit exceeded, wait a bit
                    await asyncio.sleep(0.1)
                    continue
                
                # Increment and set expiry if new
                async with self.redis.pipeline() as pipe:
                    await pipe.incr(key)
                    if not current:
                        await pipe.expire(key, self.window)
                    await pipe.execute()
                
                return True
            except Exception as e:
                logger.error(f"Rate limiter error: {e}")
                # Fail open or closed? Let's fail open but log to avoid stalling
                return True 

    async def close(self):
        await self.redis.aclose()
