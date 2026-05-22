"""Admin/operator endpoints. Authenticated. Not user-facing."""
import logging
from collections import Counter
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verify_api_key
from common_utils.redis import cache_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


_SAMPLE_CLIENT_FIELDS = ("name", "addr", "age", "idle", "cmd", "fd")


def _count_by(clients: list, key: str) -> list:
    return Counter(c.get(key, "<unset>") for c in clients).most_common(20)


def _project_sample(client_entry: dict) -> dict:
    """Whitelist sampled client fields so future redis-py additions cannot
    silently widen the leak surface of this admin-only endpoint."""
    return {k: client_entry.get(k) for k in _SAMPLE_CLIENT_FIELDS if k in client_entry}


def _pool_stats(client) -> Dict[str, Any]:
    try:
        pool = client.connection_pool
        return {
            "max_connections": getattr(pool, "max_connections", None),
            "created_connections": getattr(pool, "_created_connections", None),
            "available": len(getattr(pool, "_available_connections", []) or []),
            "in_use": len(getattr(pool, "_in_use_connections", {}) or {}),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/redis-debug", dependencies=[Depends(verify_api_key)])
async def redis_debug():
    """
    Operator-only snapshot of this replica's Redis pool + global CLIENT LIST.
    See docs/superpowers/specs/2026-05-21-redis-connection-leak-fix-design.md.
    """
    client = cache_service.redis_client
    if client is None:
        raise HTTPException(status_code=503, detail="Redis not connected")
    try:
        info = await client.info("clients")
        all_clients = await client.client_list()
        return {
            "info_clients": info,
            "total_clients": len(all_clients),
            "client_name_counts": _count_by(all_clients, "name"),
            "client_addr_counts": _count_by(all_clients, "addr"),
            "sample_clients": [_project_sample(c) for c in all_clients[:50]],
            "pool_stats": _pool_stats(client),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"redis-debug failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"redis-debug failed: {e}")
