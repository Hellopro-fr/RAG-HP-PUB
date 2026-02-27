import redis
import os
import logging
import hashlib
import json

logger = logging.getLogger(__name__)

class RedisManager:
    """
    Manages atomic batch operations for website pages using a Lua script.
    Guarantees that only one consumer processes a full batch even under high concurrency.
    """
    
    # Lua script to atomicaly Push, Check Length, and optionally Pop
    LUA_BATCH_SCRIPT = """
    local key = KEYS[1]
    local content = ARGV[1]
    local threshold = tonumber(ARGV[2])
    local ttl = tonumber(ARGV[3])
    
    -- Push the new page content to the list
    redis.call('RPUSH', key, content)
    
    -- Reset expiration on every push to keep the batch alive while active
    redis.call('EXPIRE', key, ttl)
    
    -- Check length
    local len = redis.call('LLEN', key)
    
    if len >= threshold then
        -- Return the batch elements
        local batch = redis.call('LRANGE', key, 0, threshold - 1)
        -- Trim the list (remove processed elements)
        redis.call('LTRIM', key, threshold, -1)
        return batch
    else
        return nil
    end
    """

    def __init__(self):
        self.redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        self.client = None
        self.batch_script = None
        
        try:
            self.client = redis.from_url(self.redis_url, decode_responses=True)
            self.batch_script = self.client.register_script(self.LUA_BATCH_SCRIPT)
            logger.info(f"✅ Redis Manager connected to {self.redis_url}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")

    def buffer_and_check_batch(self, domain: str, page_type: str, payload: str, threshold: int = 3, ttl_seconds: int = 86400):
        """
        Buffers a page payload and checks if the batch is ready.
        
        Args:
            domain (str): The domain name (e.g., 'google.com').
            page_type (str): 'header' or 'footer'.
            payload (str): The serialized JSON message content.
            threshold (int): Number of pages required to trigger processing.
            ttl_seconds (int): Expiration for the buffer key (default 24h).
            
        Returns:
            list[str] | None: Returns list of 3 JSON strings if batch is full, else None.
        """
        if not self.client:
            logger.warning("Redis client not available. Skipping buffering.")
            return None

        # Create a safe key
        # We hash the domain to ensure key safety and consistency
        domain_hash = hashlib.md5(domain.encode()).hexdigest()
        key = f"pending:{page_type}:{domain}:{domain_hash}"
        
        try:
            # Execute atomic Lua script
            result = self.batch_script(keys=[key], args=[payload, threshold, ttl_seconds])
            
            if result:
                logger.info(f"⚡ Batch ready for {domain} ({page_type})! Processing {len(result)} pages.")
                return result
            else:
                logger.info(f"⏳ Page buffered for {domain} ({page_type}). Waiting for more...")
                return None
                
        except redis.RedisError as e:
            logger.error(f"Redis error during batch operation: {e}")
            return None