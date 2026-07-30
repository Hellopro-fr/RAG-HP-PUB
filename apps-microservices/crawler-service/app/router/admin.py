"""Admin/operator endpoints. Authenticated. Not user-facing."""
import json
import logging
import os
import re
import time
from collections import Counter
from datetime import datetime
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
        # Server-side idle reaper — the ONLY mechanism recycling half-open
        # connections left by SIGKILLed crawler processes. timeout=0 means
        # orphans accumulate forever (the historical maxclients incident).
        # CONFIG GET may be disabled on managed Redis — degrade gracefully.
        try:
            server_config = await client.config_get("timeout")
            server_config.update(await client.config_get("tcp-keepalive"))
        except Exception as e:
            server_config = {"error": f"CONFIG GET unavailable: {e}"}
        return {
            "info_clients": info,
            "total_clients": len(all_clients),
            "server_idle_reaper": server_config,
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


_SECRET_SETTINGS = ("API_KEY", "APIFY_PROXY")
# Prefixes of env vars exposed by GET /admin/config (diagnostic surface).
# Deliberately narrow: "REDIS_LOSS"/"REDIS_MAX"/... (never "REDIS_") so
# REDIS_URL credentials can never leak.
# GUARDRAIL: every variable in the docker-compose crawler-service environment
# block MUST match a prefix here OR be listed in _ENV_COMPOSE_EXCLUSIONS —
# enforced by tests/test_admin_config.py::test_compose_env_parity, which fails
# the moment someone adds a new env var without deciding its visibility.
_ENV_WHITELIST_PREFIXES = (
    "DIEZ_", "QM_", "TIMING_", "DETECTION_", "NAVIGATION_", "RECOVER_",
    "PROGRESS_", "REDIS_LOSS", "REDIS_MAX", "REDIS_SOCKET", "REDIS_HEALTH",
    "NODE_OPTIONS", "MAX_CONCURRENT", "DEFAULT_MAX_GLOBAL", "AUTO_STASH",
    "STASH_", "QUEUE_", "CONTENT_EXTRACTOR", "DATASET_",
)
# Compose env vars deliberately NOT exposed by /admin/config. Add here ONLY
# with a justification comment; anything diagnostic belongs in the whitelist.
_ENV_COMPOSE_EXCLUSIONS = frozenset({
    "REDIS_URL",     # carries the Redis password
    "API_KEY",       # admin auth secret (mapped from API_KEY_ADMIN_CRAWLER_SERVICE)
    "SERVICE_NAME",  # static identity, no diagnostic value
})


@router.get("/config", dependencies=[Depends(verify_api_key)])
async def effective_config():
    """Effective runtime configuration: pydantic Settings (secrets masked to
    '<set>'; None means genuinely unset) + the whitelisted env vars the Node
    crawler subprocess inherits. Answers 'is AUTO_STASH_ENABLED / DIEZ_TIER2 /
    QM_TIER2 actually ON on this deployment?' without VM access."""
    cfg = settings.model_dump()
    for key in _SECRET_SETTINGS:
        if cfg.get(key):
            cfg[key] = "<set>"
    env = {k: v for k, v in sorted(os.environ.items())
           if k.startswith(_ENV_WHITELIST_PREFIXES)}
    return {"settings": cfg, "env": env}


_DATASET_PREFIXES = {"main": "", "error": "error-", "nfr": "nfr-", "update": "update-"}
_DATASET_MAX_PARSE_BYTES = 20_000_000  # skip parsing pathological items; metadata still listed


def _dataset_dir(job_info: dict, kind: str) -> Optional[str]:
    """Mirror crawler_manager._dataset_dir_for_job (crawler_manager.py:1742),
    generalized to the error-/nfr-/update- dataset variants. Same
    {domain} -> {domain with . -> -} sanitized fallback."""
    storage_path = job_info.get("storage_path")
    domain = job_info.get("domain")
    if not storage_path or not domain:
        return None
    base = os.path.join(storage_path, "storage", "datasets")
    prefix = _DATASET_PREFIXES[kind]
    for candidate in (domain, domain.replace(".", "-")):
        path = os.path.join(base, prefix + candidate)
        if os.path.isdir(path):
            return path
    return None


@router.get("/dataset/{crawl_id}", dependencies=[Depends(verify_api_key)])
async def dataset_sample(
    kind: str = Query("main", pattern="^(main|error|nfr|update)$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    content_chars: int = Query(0, ge=0, le=5000),
    job_info: dict = Depends(get_job_or_recover),
):
    """List/sample a crawl's dataset records WITHOUT downloading the /results
    tar and WITHOUT lifecycle side effects (no downloaded_at stamp, no
    unstash). Newest records first."""
    dataset_dir = _dataset_dir(job_info, kind)
    if dataset_dir is None:
        raise HTTPException(
            status_code=404,
            detail="Dataset not on local disk (crawl may be stashed/archived — "
                   "this endpoint is deliberately side-effect-free; use /unstash "
                   "or /results to restore cold data).")
    if kind == "update":
        # The update dir holds JSONL event files (deleted/redirected/new_urls):
        # one record per LINE, not one .json file per record like the other kinds
        # (previously this branch always reported 0 records). Newest file first.
        jsonl_entries = []
        with os.scandir(dataset_dir) as it:
            for entry in it:
                if not entry.name.endswith(".jsonl"):
                    continue
                try:
                    st = entry.stat()
                except OSError:
                    continue
                jsonl_entries.append((entry.name, st.st_mtime, st.st_size))
        jsonl_entries.sort(key=lambda e: (e[1], e[0]), reverse=True)
        lines = []
        for name, _mtime, size in jsonl_entries:
            if size > _DATASET_MAX_PARSE_BYTES:
                lines.append({"file": name, "parse_error": f"file too large to parse ({size} bytes)"})
                continue
            try:
                with open(os.path.join(dataset_dir, name), "r", encoding="utf-8",
                          errors="replace") as f:
                    for i, raw in enumerate(f):
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            # provenance keys applied LAST so a record field named
                            # 'file'/'line' can never clobber them
                            rec = {**json.loads(raw), "file": name, "line": i + 1}
                        except Exception as e:
                            rec = {"file": name, "line": i + 1, "parse_error": str(e)}
                        lines.append(rec)
            except OSError as e:
                lines.append({"file": name, "parse_error": str(e)})
        page = lines[offset:offset + limit]
        return {"kind": kind, "total_records": len(lines), "offset": offset,
                "returned": len(page), "records": page}
    entries = []
    with os.scandir(dataset_dir) as it:
        for entry in it:
            if (not entry.name.endswith(".json") or entry.name == "html_index.json"
                    or entry.name.startswith("__")):  # __metadata__/__collapsed_urls sidecars, not rows
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            entries.append((entry.name, st.st_mtime, st.st_size))
    entries.sort(key=lambda e: (e[1], e[0]), reverse=True)  # newest first, name-stable on mtime ties
    records = []
    for name, mtime, size in entries[offset:offset + limit]:
        record = {"file": name, "size_bytes": size,
                  "mtime": datetime.utcfromtimestamp(mtime).isoformat(), "url": None}
        if size > _DATASET_MAX_PARSE_BYTES:
            record["parse_error"] = f"file too large to parse ({size} bytes)"
            records.append(record)
            continue
        try:
            with open(os.path.join(dataset_dir, name), "r", encoding="utf-8",
                      errors="replace") as f:
                item = json.load(f)
            record["url"] = item.get("url")
            content = item.get("content") or ""
            record["content_length"] = len(content)
            if content_chars:
                record["content_preview"] = content[:content_chars]
        except Exception as e:  # unparseable item file is itself a finding
            record["parse_error"] = str(e)
        records.append(record)
    return {"kind": kind, "total_records": len(entries), "offset": offset,
            "returned": len(records), "records": records}


# Exact filenames served for investigations. Since the 2026-07-04 cleanup
# change, stash/archive cleanup removes only the storage/ subtree, so ALL root
# sidecars survive on disk; this whitelist is the serving allowlist, not a
# retention list. crawler.log has its own /admin/logs endpoint; timing.jsonl
# excluded (unbounded size).
_SIDECAR_WHITELIST = frozenset({
    "_callback_payload.json", "_completion_marker.json", "_status_snapshot.json",
    "_exit_reason.json", "_update_report.json", "update_stats.json",
    "timing-summary.json", "_queue_stats.json",
    "_diez_decision.json", "_diez_audit.json",
    "_questionmark_decision.json", "_questionmark_observations.json",
    "_questionmark_audit.json",
    "_canonical_dedup_audit.json",
})


@router.get("/sidecar/{crawl_id}", dependencies=[Depends(verify_api_key)])
async def sidecar_file(
    name: str = Query(..., description="One of the known per-crawl sidecar filenames."),
    job_info: dict = Depends(get_job_or_recover),
):
    """One per-crawl diagnostic sidecar, parsed as JSON when possible.
    `name` is matched against a fixed whitelist — it is a lookup key, never a
    filesystem path (no traversal surface)."""
    if name not in _SIDECAR_WHITELIST:
        raise HTTPException(
            status_code=400,
            detail=f"name must be one of: {', '.join(sorted(_SIDECAR_WHITELIST))}")
    storage_path = job_info.get("storage_path") or os.path.join(
        settings.CRAWLER_STORAGE_PATH, job_info["crawl_id"])
    path = os.path.join(storage_path, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"{name} not present for this crawl.")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    try:
        return {"name": name, "content": json.loads(text)}
    except json.JSONDecodeError:
        return {"name": name, "raw": text[:100_000]}


_ERROR_MARKER_SUFFIXES = (".error", ".move-error")
_DAEMON_STATE_MAX_FILES = 200
_DAEMON_STATE_MAX_SCAN = 2000  # hard stat() bound; a backlog beyond this is itself the finding


def _daemon_dirs() -> Dict[str, str]:
    """Shared flow dirs (already bind-mounted, config.py:22-53). Read at call
    time so tests can monkeypatch settings paths."""
    return {
        "archives": settings.ARCHIVES_SHARED_PATH,
        "archives_dead_letter": os.path.join(settings.ARCHIVES_SHARED_PATH, "dead_letter"),
        "stash": settings.STASH_SHARED_PATH,
        "stash_dead_letter": os.path.join(settings.STASH_SHARED_PATH, "dead_letter"),
        "download_requests": settings.DOWNLOAD_REQUESTS_PATH,
        "download_results": settings.DOWNLOAD_RESULTS_PATH,
        "stash_download_requests": settings.STASH_DOWNLOAD_REQUESTS_PATH,
        "stash_download_results": settings.STASH_DOWNLOAD_RESULTS_PATH,
        "move_requests": settings.MOVE_REQUESTS_PATH,
        "move_results": settings.MOVE_RESULTS_PATH,
    }


def _describe_dir(path: str) -> Dict[str, Any]:
    if not os.path.isdir(path):
        return {"exists": False}
    now = time.time()
    files, error_markers = [], {}
    try:
        names = os.listdir(path)
    except OSError as e:
        return {"exists": True, "error": str(e)}
    # Stat the heartbeat directly: listdir order is unspecified, so it could
    # fall past the scan bound — exactly when a backlog makes it matter most.
    heartbeat_age = None
    hb_path = os.path.join(path, ".daemon-heartbeat")
    try:
        heartbeat_age = int(now - os.stat(hb_path).st_mtime)
    except OSError:
        pass
    truncated = len(names) > _DAEMON_STATE_MAX_SCAN
    names = names[:_DAEMON_STATE_MAX_SCAN]
    for name in names:
        if name == ".daemon-heartbeat":
            continue
        full = os.path.join(path, name)
        if not os.path.isfile(full):
            continue
        try:
            st = os.stat(full)
        except OSError:
            continue
        files.append({"name": name, "size_bytes": st.st_size,
                      "age_seconds": int(now - st.st_mtime)})
        if name.endswith(_ERROR_MARKER_SUFFIXES):
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    error_markers[name] = f.read(2000)
            except OSError:
                pass
    files.sort(key=lambda f: f["age_seconds"])
    return {"exists": True, "file_count": len(files),
            "scan_truncated": truncated,
            "heartbeat_age_seconds": heartbeat_age,
            "files": files[:_DAEMON_STATE_MAX_FILES],
            "error_markers": error_markers}


@router.get("/daemon-state", dependencies=[Depends(verify_api_key)])
async def daemon_state():
    """Liveness/backlog view of the GCS daemons' shared marker directories.
    Heartbeat age (each daemon loop touches .daemon-heartbeat in its watch
    dir) + pending markers + dead-letter contents + *.error texts —
    distinguishes 'daemon dead' vs 'GCS slow' vs 'dead-lettered' in one call."""
    return {name: _describe_dir(path) for name, path in _daemon_dirs().items()}


_STORAGE_DIRS_MAX_LIMIT = 500
# Full recursive sizing of the page stops once this much wall time is spent;
# the gateway caps requests at 180s — stay far under.
_STORAGE_DIRS_SIZING_BUDGET_S = 60.0


def _dir_size_bytes(path: str) -> int:
    """Recursive byte size of a tree (regular files only, symlinks not
    followed). Per-file stat errors are ignored — a vanishing file mid-walk
    must not kill a visibility endpoint."""
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path, followlinks=False):
        for fname in filenames:
            try:
                total += os.stat(os.path.join(dirpath, fname),
                                 follow_symlinks=False).st_size
            except OSError:
                continue
    return total


@router.get("/storage-dirs", dependencies=[Depends(verify_api_key)])
async def storage_dirs(
    offset: int = Query(0),
    limit: int = Query(100),
    sizes: bool = Query(False),
):
    """Per-crawl directory inventory of CRAWLER_STORAGE_PATH (the 384G volume).
    Lists immediate subdirs (name = crawl_id by convention) with cheap stats,
    optional recursive sizes (time-budgeted), and each dir's crawl_job Redis
    status — the leftover hunt: a dir whose Redis blob says stashed/archived
    but which still holds a storage/ subtree is disk the cleanup missed.
    Read-only, fail-open: missing root or dead Redis degrade, never 500."""
    # Clamp instead of 422: operators probing with a huge limit should get a
    # capped page, not a validation error.
    offset = max(0, offset)
    limit = max(1, min(limit, _STORAGE_DIRS_MAX_LIMIT))
    started = time.monotonic()
    root = settings.CRAWLER_STORAGE_PATH

    def _response(total, dirs, budget_hit, error=None):
        body = {"root": root, "total_dirs": total, "offset": offset,
                "limit": limit, "returned": len(dirs), "sizes": sizes,
                "sizing_budget_hit": budget_hit,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "dirs": dirs}
        if error is not None:
            body["error"] = error
        return body

    names = []
    try:
        with os.scandir(root) as it:
            for entry in it:
                if entry.is_dir(follow_symlinks=False):
                    names.append(entry.name)
    except OSError as e:
        return _response(0, [], False, error=str(e))
    names.sort()  # stable pagination

    now = time.time()
    budget_hit = False
    dirs = []
    for name in names[offset:offset + limit]:
        path = os.path.join(root, name)
        try:
            mtime_age = int(now - os.stat(path).st_mtime)
        except OSError:
            mtime_age = None
        try:
            with os.scandir(path) as it:
                top_entry_count = sum(1 for _ in it)
        except OSError:
            top_entry_count = None
        info = {
            "name": name,
            "mtime_age_seconds": mtime_age,
            # The heavy Crawlee tree; its presence on a stashed/archived crawl
            # is the leftover signature.
            "has_storage_subtree": os.path.isdir(os.path.join(path, "storage")),
            "top_entry_count": top_entry_count,
        }
        if sizes:
            if budget_hit or time.monotonic() - started >= _STORAGE_DIRS_SIZING_BUDGET_S:
                budget_hit = True
                info["size_bytes"] = None
            else:
                info["size_bytes"] = _dir_size_bytes(path)
        dirs.append(info)

    # Redis join, fail-open: this endpoint exists precisely for incident
    # visibility — it must keep answering when Redis does not.
    try:
        for d in dirs:
            blob = await cache_service.get_json(f"crawl_job:{d['name']}")
            if blob:
                d["redis"] = {"present": True, "status": blob.get("status"),
                              "stashed_at": blob.get("stashed_at")}
            else:
                d["redis"] = {"present": False, "status": None, "stashed_at": None}
    except Exception as e:
        for d in dirs:
            d["redis"] = {"error": str(e)}

    return _response(len(names), dirs, budget_hit)
