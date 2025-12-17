import json
from typing import Optional, Any, List
import redis.asyncio as redis
from app.core.config import settings

class RedisCacheService:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None

    async def connect(self):
        self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def close(self):
        if self.redis_client:
            await self.redis_client.close()

    async def get_key(self, key: str) -> Optional[str]:
        if not self.redis_client: return None
        return await self.redis_client.get(key)

    async def get_json(self, key: str) -> Optional[dict]:
        if not self.redis_client: return None
        val = await self.redis_client.get(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return None
        return None

    async def set_json(self, key: str, value: Any, expire: int = None):
        if not self.redis_client: return
        val = json.dumps(value, default=str)
        await self.redis_client.set(key, val, ex=expire)

    async def increment_key(self, key: str):
        if not self.redis_client: return
        await self.redis_client.incr(key)

    async def decrement_key(self, key: str):
        if not self.redis_client: return
        await self.redis_client.decr(key)

    async def publish(self, channel: str, message: str):
        if not self.redis_client: return
        await self.redis_client.publish(channel, message)

    async def scan_keys_by_prefix(self, prefix: str) -> List[str]:
        if not self.redis_client: return []
        keys = []
        async for key in self.redis_client.scan_iter(match=f"{prefix}*"):
            keys.append(key)
        return keys

cache_service = RedisCacheService()
