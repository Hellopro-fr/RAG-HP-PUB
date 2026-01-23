import redis
import time
import logging
import os

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        try:
            self.redis = redis.from_url(self.redis_url)
            self.redis.ping()
            logger.info(f"✅ RateLimiter connected to Redis")
        except Exception as e:
            logger.warning(f"⚠️ RateLimiter: Redis unavailable ({e}), rate limiting disabled")
            self.redis = None
        # Default limit: 100 requests per second per domain (High for testing/CDNs)
        self.default_rate = 100 
        self.window = 1 # second

    def acquire(self, domain: str) -> bool:
        """
        Simple sliding window rate limiter.
        Returns True when allowed to proceed.
        """
        if not self.redis:
            return True

        key = f"ratelimit:{domain}"
        max_retries = 60 # Prevent infinite loop (Wait up to 30s)
        
        for _ in range(max_retries):
            try:
                current = self.redis.get(key)
                if current and int(current) >= self.default_rate:
                    time.sleep(0.5)
                    continue
                
                # Increment and set expiry if new
                pipe = self.redis.pipeline()
                pipe.incr(key)
                if not current:
                    pipe.expire(key, self.window)
                pipe.execute()
                return True
            except Exception as e:
                logger.error(f"Rate limiter error: {e}")
                return True # Fail open
        
        logger.warning(f"Rate limit timeout for {domain}")
        return True # Fail open after retries


    def close(self):
        if self.redis:
            self.redis.close()
