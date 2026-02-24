"""
Redis-backed event store for real-time monitoring.
Stores recent download events in Redis Streams for SSE consumption.
"""
import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, AsyncGenerator

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Max events to keep per stream (ring-buffer behaviour)
MAX_STREAM_LEN = 5000
# Stream names
STREAM_DOWNLOADS = "ids:events:downloads"
STREAM_ERRORS = "ids:events:errors"
STREAM_ALL = "ids:events:all"

# Snapshot keys
KEY_REPLICA_STATUS = "ids:replicas"          # Hash: replica_id -> JSON status
KEY_DOMAIN_STATS = "ids:domain_stats"        # Hash: domain -> JSON stats
KEY_ACTIVE_DOWNLOADS = "ids:active_downloads" # Hash: replica_id -> JSON current download


class EventStore:
    """Async Redis-based event store for real-time monitoring data."""

    def __init__(self):
        self.redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self):
        """Initialize Redis connection."""
        try:
            self._redis = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=10,
            )
            await self._redis.ping()
            logger.info("✅ EventStore connected to Redis")
        except Exception as e:
            logger.warning(f"⚠️ EventStore: Redis unavailable ({e}), events will not be stored")
            self._redis = None

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.aclose()

    @property
    def is_available(self) -> bool:
        return self._redis is not None

    # -----------------------------------------------------------------------
    # Publish events
    # -----------------------------------------------------------------------

    async def emit_download_event(self, event_data: dict):
        """Emit a download event (start, progress, complete, error)."""
        if not self.is_available:
            return
        try:
            event = {
                "timestamp": datetime.now().isoformat(),
                "type": "download",
                **{k: str(v) if not isinstance(v, str) else v for k, v in event_data.items()},
            }
            payload = {"data": json.dumps(event, ensure_ascii=False)}
            await self._redis.xadd(STREAM_DOWNLOADS, payload, maxlen=MAX_STREAM_LEN)
            await self._redis.xadd(STREAM_ALL, payload, maxlen=MAX_STREAM_LEN)
        except Exception as e:
            logger.debug(f"EventStore emit error: {e}")

    async def emit_error_event(self, event_data: dict):
        """Emit an error event."""
        if not self.is_available:
            return
        try:
            event = {
                "timestamp": datetime.now().isoformat(),
                "type": "error",
                **{k: str(v) if not isinstance(v, str) else v for k, v in event_data.items()},
            }
            payload = {"data": json.dumps(event, ensure_ascii=False)}
            await self._redis.xadd(STREAM_ERRORS, payload, maxlen=MAX_STREAM_LEN)
            await self._redis.xadd(STREAM_ALL, payload, maxlen=MAX_STREAM_LEN)
        except Exception as e:
            logger.debug(f"EventStore emit error: {e}")

    # -----------------------------------------------------------------------
    # Replica status (heartbeat)
    # -----------------------------------------------------------------------

    async def update_replica_status(self, replica_id: str, status: dict):
        """Update replica heartbeat status."""
        if not self.is_available:
            return
        try:
            status["last_seen"] = datetime.now().isoformat()
            await self._redis.hset(KEY_REPLICA_STATUS, replica_id, json.dumps(status, ensure_ascii=False))
            await self._redis.expire(KEY_REPLICA_STATUS, 300)  # 5min TTL
        except Exception as e:
            logger.debug(f"EventStore replica status error: {e}")

    async def get_all_replicas(self) -> Dict[str, dict]:
        """Get status of all replicas."""
        if not self.is_available:
            return {}
        try:
            raw = await self._redis.hgetall(KEY_REPLICA_STATUS)
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception as e:
            logger.debug(f"EventStore get replicas error: {e}")
            return {}

    # -----------------------------------------------------------------------
    # Active downloads tracking
    # -----------------------------------------------------------------------

    async def set_active_download(self, replica_id: str, download_info: Optional[dict]):
        """Set/clear the current active download for a replica."""
        if not self.is_available:
            return
        try:
            if download_info:
                await self._redis.hset(KEY_ACTIVE_DOWNLOADS, replica_id, json.dumps(download_info, ensure_ascii=False))
            else:
                await self._redis.hdel(KEY_ACTIVE_DOWNLOADS, replica_id)
        except Exception as e:
            logger.debug(f"EventStore active download error: {e}")

    async def get_active_downloads(self) -> Dict[str, dict]:
        """Get all active downloads across replicas."""
        if not self.is_available:
            return {}
        try:
            raw = await self._redis.hgetall(KEY_ACTIVE_DOWNLOADS)
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception as e:
            logger.debug(f"EventStore get active downloads error: {e}")
            return {}

    # -----------------------------------------------------------------------
    # Domain stats
    # -----------------------------------------------------------------------

    async def update_domain_stats(self, domain: str, stats: dict):
        """Update stats for a domain."""
        if not self.is_available:
            return
        try:
            stats["updated_at"] = datetime.now().isoformat()
            await self._redis.hset(KEY_DOMAIN_STATS, domain, json.dumps(stats, ensure_ascii=False))
        except Exception as e:
            logger.debug(f"EventStore domain stats error: {e}")

    async def get_all_domain_stats(self) -> Dict[str, dict]:
        """Get stats for all domains."""
        if not self.is_available:
            return {}
        try:
            raw = await self._redis.hgetall(KEY_DOMAIN_STATS)
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception as e:
            logger.debug(f"EventStore get domain stats error: {e}")
            return {}

    # -----------------------------------------------------------------------
    # SSE Stream reading
    # -----------------------------------------------------------------------

    async def read_recent_events(self, stream: str = STREAM_ALL, count: int = 100) -> List[dict]:
        """Read the N most recent events from a stream."""
        if not self.is_available:
            return []
        try:
            # xrevrange returns newest first
            entries = await self._redis.xrevrange(stream, count=count)
            events = []
            for entry_id, fields in entries:
                data = json.loads(fields.get("data", "{}"))
                data["_id"] = entry_id
                events.append(data)
            return list(reversed(events))  # chronological order
        except Exception as e:
            logger.debug(f"EventStore read error: {e}")
            return []

    async def stream_events(self, stream: str = STREAM_ALL) -> AsyncGenerator[dict, None]:
        """
        Async generator that yields new events as they arrive.
        Used for SSE streaming.
        """
        if not self.is_available:
            return
        last_id = "$"  # Only new messages
        while True:
            try:
                entries = await self._redis.xread(
                    {stream: last_id},
                    count=10,
                    block=5000,  # 5s timeout
                )
                if entries:
                    for stream_name, messages in entries:
                        for msg_id, fields in messages:
                            last_id = msg_id
                            data = json.loads(fields.get("data", "{}"))
                            data["_id"] = msg_id
                            yield data
                else:
                    # Yield heartbeat to keep SSE alive
                    yield {"type": "heartbeat", "timestamp": datetime.now().isoformat()}
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"EventStore stream error: {e}")
                await asyncio.sleep(1)


# Singleton
event_store = EventStore()
