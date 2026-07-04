"""Admin/operator endpoints. Authenticated. Not user-facing."""
import logging
import os
import re
from collections import Counter
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from app.core.auth import verify_api_key
from app.core import log_buffer
from app.core.config import settings
from app.router.crawler import get_job_or_recover
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


@router.get("/recent-logs", dependencies=[Depends(verify_api_key)])
async def recent_logs(
    grep: Optional[str] = None,
    level: str = Query("INFO", description="Minimum level: DEBUG|INFO|WARNING|ERROR"),
    limit: int = Query(500, ge=1, le=2000),
):
    """Last N orchestrator log lines of THIS replica (in-memory ring buffer).
    Covers the log-based observability markers (AUTO_STASH, STASH_UPLOAD_ORPHAN,
    UNSTASH_GCS_ORPHAN, STASH_MOVE_LIMBO, reconcile decisions) without VM access.
    Per-replica: cross-check the answering replica via GET /version."""
    min_levelno = logging.getLevelName(level.upper())
    if not isinstance(min_levelno, int):
        raise HTTPException(status_code=400, detail=f"Invalid level '{level}'.")
    try:
        lines = log_buffer.get_recent(grep=grep, min_levelno=min_levelno, limit=limit)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid grep regex: {e}")
    return {"count": len(lines), "lines": lines}


MAX_TAIL_BYTES = 2_000_000  # crawler.log has no rotation; multi-day crawls reach GB scale


@router.get("/logs/{crawl_id}", dependencies=[Depends(verify_api_key)])
async def crawl_log_tail(
    tail_bytes: int = Query(200_000, ge=1, le=MAX_TAIL_BYTES),
    grep: Optional[str] = None,
    job_info: dict = Depends(get_job_or_recover),
):
    """Tail of the per-crawl Node log ({storage_path}/crawler.log). Read-only —
    unlike /results this never stamps downloaded_at nor unstashes anything.
    The file survives stash/archive cleanup (files_to_keep), so failed and
    cold crawls stay inspectable."""
    storage_path = job_info.get("storage_path") or os.path.join(
        settings.CRAWLER_STORAGE_PATH, job_info["crawl_id"])
    log_path = os.path.join(storage_path, "crawler.log")
    base = os.path.abspath(settings.CRAWLER_STORAGE_PATH)
    # Guard only the fallback branch: it joins a URL-supplied crawl_id
    # (encoded slashes can reach a path param). A Redis storage_path is trusted.
    if not job_info.get("storage_path") and not os.path.abspath(log_path).startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="Invalid crawl id.")
    if not os.path.isfile(log_path):
        raise HTTPException(status_code=404, detail="crawler.log not found for this crawl.")
    size = os.path.getsize(log_path)
    with open(log_path, "rb") as f:
        f.seek(max(0, size - tail_bytes))
        data = f.read().decode("utf-8", errors="replace")
    if size > tail_bytes and "\n" in data:
        head, rest = data.split("\n", 1)
        data = rest if rest else head  # keep the fragment rather than an empty tail
    if grep:
        try:
            rx = re.compile(grep)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid grep regex: {e}")
        data = "\n".join(line for line in data.splitlines() if rx.search(line))
    return PlainTextResponse(data, headers={"X-Log-Size-Bytes": str(size)})


_JOB_REDACT_FIELDS = ("callback_url", "failure_callback_url")
_JOB_LOCK_PATTERNS = ("crawl_lock:{id}", "stash_lock:{id}", "unstash_lock:{id}",
                      "archive_lock:{id}", "restore_lock:{id}")


@router.get("/job/{crawl_id}", dependencies=[Depends(verify_api_key)])
async def job_dump(job_info: dict = Depends(get_job_or_recover)):
    """Raw crawl_job blob (secrets redacted) + held ownership locks with TTLs +
    the Node crawler's live stats:{id} hash (7d TTL) + reconcile leader.
    The un-lossy companion to GET /status — answers failure_cause / OOM count /
    'who holds the lock behind my 409 OPERATION_IN_PROGRESS'."""
    client = cache_service.redis_client
    if client is None:
        raise HTTPException(status_code=503, detail="Redis not connected")
    blob = dict(job_info)
    for field in _JOB_REDACT_FIELDS:
        if blob.get(field):
            blob[field] = "<redacted>"
    params = blob.get("params")
    if isinstance(params, dict) and params.get("proxyapify"):
        blob["params"] = {**params, "proxyapify": "<redacted>"}
    crawl_id = blob["crawl_id"]
    locks: Dict[str, Any] = {}
    for pattern in _JOB_LOCK_PATTERNS:
        key = pattern.format(id=crawl_id)
        value = await client.get(key)
        if value is not None:
            locks[key] = {"value": value, "ttl_seconds": await client.ttl(key)}
    node_stats = await client.hgetall(f"stats:{crawl_id}") or {}
    reconcile_leader = await client.get("reconcile_leader_lock")
    return {"job": blob, "locks": locks, "node_stats": node_stats,
            "reconcile_leader": reconcile_leader}
