import time
import logging

from common_utils.redis.cache_service_sync import init_redis_pool_sync, get_client

logger = logging.getLogger(__name__)

class RateLimiter:
    """Sliding-window rate limiter backed by Redis.

    Uses the shared bounded pool from common_utils.cache_service_sync. The pool
    cap (REDIS_MAX_CONNECTIONS, default 20), CLIENT SETNAME identity, keepalive,
    and shutdown semantics are managed by the shared library.

    Fails open on Redis errors — downloads should not be blocked by limiter
    outages.

    See docs/superpowers/specs/2026-05-22-redis-common-utils-hardening-design.md
    """

    def __init__(self):
        # init_redis_pool_sync() is idempotent — if main.py already initialized
        # the pool, this is a no-op and just retrieves the existing client.
        client = init_redis_pool_sync()
        if client is None:
            client = get_client()
        if client is None:
            logger.warning("⚠️ RateLimiter: shared sync pool unavailable, rate limiting disabled")
        else:
            logger.info("✅ RateLimiter attached to shared sync Redis pool")
        self.redis = client
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
