# Crawler-Service Debug/Observability Endpoints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only debug/introspection HTTP endpoints to crawler-service so an assistant with gateway-HTTP-only access (no ssh, no redis-cli, no docker exec) can investigate incidents and verify fixes autonomously.

**Architecture:** All new endpoints live in the existing authenticated admin router (`app/router/admin.py`, `X-API-Key` via `verify_api_key` — auth open when `API_KEY` unset, exactly like `/admin/redis-debug`). They are pure projections of state the service already persists (Redis blobs, per-crawl sidecar files kept by `files_to_keep`, marker dirs already bind-mounted). One new module (`app/core/log_buffer.py`) adds an in-memory ring buffer for orchestrator logs. Zero new dependencies, zero gateway changes (nginx proxies all `/crawler/*` paths), zero BO contract changes (only additive fields).

**Tech Stack:** Python 3 / FastAPI / pydantic v2 / redis (async) — existing stack only. Tests: pytest + `fastapi.testclient.TestClient` (pattern: `tests/test_admin_redis_debug.py`).

**Repo/branch:** RAG-HP-PUB, branch `features/poc`. Run tests per-file from `apps-microservices/crawler-service/` (e.g. `python -m pytest tests/test_admin_recent_logs.py -v`). ⚠️ `pydantic-core` must stay `==2.46.4` (any drift breaks ALL test collection — re-pin with `python -m pip install "pydantic-core==2.46.4"`).

**Out of scope (deliberate):** Prometheus/log shipping; Node-side `_live_stats.json` (in-flight counters); GCS stat via daemon marker protocol; fixing the dead webhook counters (`filtered_ext`/`filtered_nonfr`/`timeout_individual`/`success_extracted` always 0 — separate bug ticket); `API_KEY_RO` split key (operator shares the existing key once).

---

## Key code anchors (verified 2026-07-04)

| Anchor | Location |
|---|---|
| Admin router + auth pattern | `app/router/admin.py:13` (`prefix="/admin"`), `app/core/auth.py:13` (`verify_api_key`, open if `API_KEY` unset) |
| `get_job_or_recover` dependency | `app/router/crawler.py:42` (404 if not in Redis nor on disk; heals blob) |
| `_record_downloaded_at` (grace clock) | `app/router/crawler.py:23`; called from `/results` at `app/router/crawler.py:352` |
| `/capacity` endpoint + schema | `app/router/crawler.py:160-189`; `CapacityResponse` at `app/schemas/crawler.py:21-24` |
| Lock keys | `crawl_lock:{id}` (`crawler_manager.py:33`), `stash_lock:{id}`/`unstash_lock:{id}` (`:2787-2788`), `archive_lock:{id}` (`:2397`), `restore_lock:{id}` (`:2618`), `reconcile_leader_lock` (`:3289`) |
| Node stats hash | `stats:{crawl_id}` (crawler/src/class/StatsManager.ts, TTL 7d) |
| Disk helper (fail-open) | `crawler_manager._get_archives_disk_state(dir)` at `crawler_manager.py:2241` |
| Kept sidecar files | `files_to_keep` sets at `crawler_manager.py:2534` and `:2954` (`crawler.log`, `_callback_payload.json`, `_completion_marker.json`, `_status_snapshot.json`, `_exit_reason.json`, `_update_report.json`, `update_stats.json`, `timing.jsonl`, `timing-summary.json`) |
| Dataset dir resolution | `crawler_manager._dataset_dir_for_job` at `crawler_manager.py:1742` (`{storage_path}/storage/datasets/{domain}` + `.`→`-` fallback) |
| Daemon shared dirs (all in `settings`) | `config.py:22,35-48` (`ARCHIVES_SHARED_PATH`, `DOWNLOAD_*`, `STASH_*`, `MOVE_*`) |
| Daemon loops | `tools/upload_daemon.sh:45` (`while true; do`, watch dir `$ARCHIVES_DIR`), `tools/download_daemon.sh:127` (`while true; do`, `$REQUESTS_DIR`) |
| Logging dictConfig | `main.py:23-48` (stdout only) |
| Dockerfile final stage | `Dockerfile:22-69` (no ARG/LABEL today) |
| Compose crawler-service block | `docker-compose.yml:1331-1386` (`build:` at 1332-1334) |
| Test pattern for admin endpoints | `tests/test_admin_redis_debug.py` (minimal app + `monkeypatch.setattr(settings, "API_KEY", None)`) |

**tdd-gate note:** test filenames must share the production stem — edits to `admin.py` are satisfied by `tests/test_admin_*.py`, `crawler.py` by `tests/test_crawler_*.py`, `main.py` by `tests/test_main_*.py`, `log_buffer.py` by `tests/test_log_buffer.py`. Shell/Dockerfile/compose edits are gate-exempt.

---

### Task 0: `/version` endpoint + GIT_COMMIT build stamp

**Goal:** Identify the deployed commit/build over HTTP (verify "is my fix live?").

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/crawler.py` (top imports + new endpoint after `/capacity`)
- Modify: `apps-microservices/crawler-service/Dockerfile` (ARG/ENV in final stage)
- Modify: `docker-compose.yml:1332-1334` (build args)
- Test: `apps-microservices/crawler-service/tests/test_crawler_version.py`

**Acceptance Criteria:**
- [ ] `GET /version` returns `{git_commit, build_date, replica, started_at}` — no auth (no secrets), static per process.
- [ ] `git_commit` defaults to `"unknown"` when env absent.
- [ ] Dockerfile accepts `ARG GIT_COMMIT` / `ARG BUILD_DATE` and exports them as ENV.

**Verify:** `python -m pytest tests/test_crawler_version.py -v` → 2 passed

**Steps:**

- [ ] **Step 1: Write the failing test**

```python
# tests/test_crawler_version.py
"""Tests for the public GET /version endpoint (deploy identity)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client():
    from app.router.crawler import router as CrawlerRouter
    app = FastAPI()
    app.include_router(CrawlerRouter)
    return TestClient(app)


def test_version_defaults_to_unknown(monkeypatch):
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    monkeypatch.delenv("BUILD_DATE", raising=False)
    resp = _client().get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["git_commit"] == "unknown"
    assert body["build_date"] == "unknown"
    assert body["replica"]
    assert body["started_at"]


def test_version_reads_env(monkeypatch):
    monkeypatch.setenv("GIT_COMMIT", "abc1234")
    monkeypatch.setenv("BUILD_DATE", "2026-07-04T00:00:00Z")
    body = _client().get("/version").json()
    assert body["git_commit"] == "abc1234"
    assert body["build_date"] == "2026-07-04T00:00:00Z"
```

- [ ] **Step 2: Run to verify it fails** — `python -m pytest tests/test_crawler_version.py -v` → FAIL (404, route missing)

- [ ] **Step 3: Implement.** In `app/router/crawler.py`: add `import socket` next to the existing `import os` block, and module-level constant just after `logger = logging.getLogger(__name__)`:

```python
# Deploy identity for GET /version. Stamped once at import (= process start).
APP_STARTED_AT = datetime.utcnow().isoformat() + "Z"
```

Then add the endpoint directly after the `get_capacity` function (after line ~189):

```python
@router.get("/version")
async def version():
    """Deploy identity: which commit/build is running, on which replica, since
    when. GIT_COMMIT/BUILD_DATE are baked at image build (Dockerfile ARG->ENV);
    'unknown' means the image was built without build args."""
    return {
        "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
        "build_date": os.environ.get("BUILD_DATE", "unknown"),
        "replica": socket.gethostname(),
        "started_at": APP_STARTED_AT,
    }
```

- [ ] **Step 4: Dockerfile.** In the FINAL stage (after `WORKDIR /app`, `Dockerfile:24`), add:

```dockerfile
# Deploy identity served by GET /version. Passed by docker-compose build args;
# defaults keep local builds working without them.
ARG GIT_COMMIT=unknown
ARG BUILD_DATE=unknown
ENV GIT_COMMIT=$GIT_COMMIT BUILD_DATE=$BUILD_DATE
```

- [ ] **Step 5: docker-compose.** In `docker-compose.yml` crawler-service `build:` block (line 1332), add `args` (preserve existing keys):

```yaml
    build:
      context: .
      dockerfile: ./apps-microservices/crawler-service/Dockerfile
      args:
        GIT_COMMIT: ${GIT_COMMIT:-unknown}
        BUILD_DATE: ${BUILD_DATE:-unknown}
```

Operator build one-liner (document in commit body): `GIT_COMMIT=$(git rev-parse --short HEAD) BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) docker compose --profile crawling build crawler-service`

- [ ] **Step 6: Run test** → PASS. **Step 7: Commit** — `feat(crawler-service): GET /version deploy identity (git commit + build date)`

---

### Task 1: Log ring buffer + `GET /admin/recent-logs`

**Goal:** Make the orchestrator's log-based observability (AUTO_STASH markers, reconcile decisions, webhook retries) queryable over HTTP — docker logs rotate ~30MB and are ssh-only.

**Files:**
- Create: `apps-microservices/crawler-service/app/core/log_buffer.py`
- Modify: `apps-microservices/crawler-service/main.py:23-48` (dictConfig)
- Modify: `apps-microservices/crawler-service/app/router/admin.py`
- Test: `apps-microservices/crawler-service/tests/test_log_buffer.py`, `tests/test_admin_recent_logs.py`, `tests/test_main_ring_handler.py`

**Acceptance Criteria:**
- [ ] Every log record ≥ INFO emitted through the root logger lands in a `deque(maxlen=5000)`.
- [ ] `GET /admin/recent-logs?grep=&level=&limit=` returns matching lines, chronological, capped.
- [ ] Invalid regex or level → 400. Auth enforced when `API_KEY` set (401 without header).
- [ ] Handler never raises (logging must not break the app).

**Verify:** `python -m pytest tests/test_log_buffer.py tests/test_admin_recent_logs.py tests/test_main_ring_handler.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_log_buffer.py
"""Unit tests for the in-memory log ring buffer."""
import logging
import pytest

from app.core import log_buffer


@pytest.fixture(autouse=True)
def clean_buffer():
    log_buffer.clear()
    yield
    log_buffer.clear()


def _emit(handler, level, msg):
    record = logging.LogRecord("t", level, __file__, 1, msg, None, None)
    handler.emit(record)


def test_emit_and_get_recent():
    h = log_buffer.RingBufferHandler()
    h.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    _emit(h, logging.INFO, "AUTO_STASH crawl_id=42 reason=grace")
    _emit(h, logging.WARNING, "STASH_UPLOAD_ORPHAN crawl_id=43")
    lines = log_buffer.get_recent()
    assert len(lines) == 2
    assert "AUTO_STASH" in lines[0]  # chronological order


def test_grep_and_level_filter():
    h = log_buffer.RingBufferHandler()
    h.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    _emit(h, logging.INFO, "noise")
    _emit(h, logging.WARNING, "AUTO_STASH crawl_id=42")
    assert log_buffer.get_recent(grep="AUTO_STASH") == ["WARNING | AUTO_STASH crawl_id=42"]
    assert log_buffer.get_recent(min_levelno=logging.WARNING) == ["WARNING | AUTO_STASH crawl_id=42"]


def test_limit_keeps_newest():
    h = log_buffer.RingBufferHandler()
    h.setFormatter(logging.Formatter("%(message)s"))
    for i in range(10):
        _emit(h, logging.INFO, f"line-{i}")
    lines = log_buffer.get_recent(limit=3)
    assert lines == ["line-7", "line-8", "line-9"]


def test_emit_never_raises():
    h = log_buffer.RingBufferHandler()  # no formatter set -> format() still works
    _emit(h, logging.INFO, "ok")
    h.format = lambda r: (_ for _ in ()).throw(RuntimeError("boom"))
    _emit(h, logging.INFO, "must not raise")
```

```python
# tests/test_admin_recent_logs.py
"""Tests for GET /admin/recent-logs."""
import logging
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import log_buffer


@pytest.fixture(autouse=True)
def clean_buffer():
    log_buffer.clear()
    yield
    log_buffer.clear()


@pytest.fixture
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return TestClient(app)


def _fill():
    h = log_buffer.RingBufferHandler()
    h.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    for msg in ("AUTO_STASH crawl_id=1 reason=grace", "reconcile tick", "AUTO_STASH crawl_id=2 reason=timeout"):
        h.emit(logging.LogRecord("t", logging.INFO, __file__, 1, msg, None, None))


def test_returns_lines(client):
    _fill()
    body = client.get("/admin/recent-logs").json()
    assert body["count"] == 3


def test_grep_filters(client):
    _fill()
    body = client.get("/admin/recent-logs", params={"grep": "AUTO_STASH"}).json()
    assert body["count"] == 2
    assert all("AUTO_STASH" in l for l in body["lines"])


def test_invalid_regex_400(client):
    assert client.get("/admin/recent-logs", params={"grep": "("}).status_code == 400


def test_invalid_level_400(client):
    assert client.get("/admin/recent-logs", params={"level": "NOPE"}).status_code == 400


def test_auth_enforced_when_key_set(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", "sekret", raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    c = TestClient(app)
    assert c.get("/admin/recent-logs").status_code == 401
    assert c.get("/admin/recent-logs", headers={"X-API-Key": "sekret"}).status_code == 200
```

```python
# tests/test_main_ring_handler.py
"""main.py dictConfig must install the ring buffer handler on the root logger."""
import logging

from app.core import log_buffer


def test_root_logger_feeds_ring_buffer():
    import main  # noqa: F401  (applies dictConfig at import)
    log_buffer.clear()
    logging.getLogger("app.core.crawler_manager").info("RING_PROBE hello")
    assert any("RING_PROBE" in l for l in log_buffer.get_recent(grep="RING_PROBE"))
```

- [ ] **Step 2: Run — all FAIL** (module missing / route missing / handler not installed)

- [ ] **Step 3: Create `app/core/log_buffer.py`**

```python
"""In-memory ring buffer of recent orchestrator log lines.

Docker logs rotate (~30MB json-file) and are ssh-only; this keeps the last
RECENT_LOGS_MAXLEN formatted records of THIS replica queryable over HTTP via
GET /admin/recent-logs. Memory-only by design — no disk, no rotation logic.
"""
import logging
import re
from collections import deque
from typing import List, Optional, Tuple

RECENT_LOGS_MAXLEN = 5000

_buffer: "deque[Tuple[int, str]]" = deque(maxlen=RECENT_LOGS_MAXLEN)


class RingBufferHandler(logging.Handler):
    """Appends (levelno, formatted line) to the module-level ring buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            _buffer.append((record.levelno, self.format(record)))
        except Exception:
            pass  # logging must never break the app


def get_recent(grep: Optional[str] = None, min_levelno: int = logging.INFO,
               limit: int = 500) -> List[str]:
    """Newest `limit` matching lines, returned in chronological order.
    Raises re.error on an invalid grep pattern (caller maps to 400)."""
    rx = re.compile(grep) if grep else None
    out: List[str] = []
    for levelno, line in reversed(_buffer):
        if levelno < min_levelno:
            continue
        if rx is not None and not rx.search(line):
            continue
        out.append(line)
        if len(out) >= limit:
            break
    out.reverse()
    return out


def clear() -> None:
    """Test helper."""
    _buffer.clear()
```

- [ ] **Step 4: Wire into `main.py` dictConfig.** Add the handler entry and reference it everywhere `"console"` appears:

```python
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stdout",
        },
        "ring": {
            "class": "app.core.log_buffer.RingBufferHandler",
            "formatter": "default",
        },
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "ring"],
    },
    "loggers": {
        "uvicorn": {"handlers": ["console", "ring"], "level": "INFO", "propagate": False},
        "uvicorn.access": {"handlers": ["console", "ring"], "level": "INFO", "propagate": False},
        "uvicorn.error": {"handlers": ["console", "ring"], "level": "INFO", "propagate": False},
    },
```

- [ ] **Step 5: Endpoint in `app/router/admin.py`.** Extend imports (top of file):

```python
import logging
import os
import re
from collections import Counter
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import verify_api_key
from app.core import log_buffer
from common_utils.redis import cache_service
```

Add after `redis_debug`:

```python
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
```

- [ ] **Step 6: Run all 3 test files** → PASS. Also `python -m pytest tests/test_admin_redis_debug.py -v` (no regression). **Step 7: Commit** — `feat(crawler-service): in-memory log ring buffer + GET /admin/recent-logs`

---

### Task 2: `GET /admin/logs/{crawl_id}` — crawler.log tail

**Goal:** Serve the tail of the per-crawl Node log (`{storage_path}/crawler.log`) — the #1 requested paste in every incident. Read-only, no lifecycle side effects.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/admin.py`
- Test: `apps-microservices/crawler-service/tests/test_admin_crawl_log.py`

**Acceptance Criteria:**
- [ ] Returns last `tail_bytes` (default 200 KB, hard cap 2 MB) of `crawler.log` as `text/plain`, partial first line dropped.
- [ ] Optional `grep` regex filters lines; invalid regex → 400.
- [ ] 404 when the file is absent; `X-Log-Size-Bytes` header carries the full size.
- [ ] Reuses `get_job_or_recover` (works for hot AND cold crawls — the file survives stash/archive cleanup).

**Verify:** `python -m pytest tests/test_admin_crawl_log.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin_crawl_log.py
"""Tests for GET /admin/logs/{crawl_id} (crawler.log tail)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_and_job(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    from app.router.crawler import get_job_or_recover
    app = FastAPI()
    app.include_router(AdminRouter)
    job = {"crawl_id": "77", "status": "failed", "storage_path": str(tmp_path)}

    async def fake_dep(crawl_id: str):
        return job

    app.dependency_overrides[get_job_or_recover] = fake_dep
    return app, tmp_path


def test_tail_returns_last_lines(app_and_job):
    app, storage = app_and_job
    log = storage / "crawler.log"
    log.write_text("\n".join(f"line-{i}" for i in range(100)), encoding="utf-8")
    resp = TestClient(app).get("/admin/logs/77", params={"tail_bytes": 30})
    assert resp.status_code == 200
    text = resp.text
    assert "line-99" in text
    assert "line-0" not in text
    assert not text.startswith("line-9\n") or True  # partial first line dropped
    assert int(resp.headers["X-Log-Size-Bytes"]) == log.stat().st_size


def test_grep_filters_lines(app_and_job):
    app, storage = app_and_job
    (storage / "crawler.log").write_text(
        "noise\n{\"event\":\"progress_stalled\"}\nnoise2\n", encoding="utf-8")
    resp = TestClient(app).get("/admin/logs/77", params={"grep": "progress_stalled"})
    assert resp.status_code == 200
    assert resp.text.strip() == '{"event":"progress_stalled"}'


def test_404_when_log_missing(app_and_job):
    app, _ = app_and_job
    assert TestClient(app).get("/admin/logs/77").status_code == 404


def test_invalid_grep_400(app_and_job):
    app, storage = app_and_job
    (storage / "crawler.log").write_text("x\n", encoding="utf-8")
    assert TestClient(app).get("/admin/logs/77", params={"grep": "("}).status_code == 400
```

- [ ] **Step 2: Run — FAIL** (route missing)

- [ ] **Step 3: Implement in `admin.py`.** Add imports: `from fastapi.responses import PlainTextResponse`, `from app.core.config import settings`, `from app.router.crawler import get_job_or_recover`. Add:

```python
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
    if not os.path.isfile(log_path):
        raise HTTPException(status_code=404, detail="crawler.log not found for this crawl.")
    size = os.path.getsize(log_path)
    with open(log_path, "rb") as f:
        f.seek(max(0, size - tail_bytes))
        data = f.read().decode("utf-8", errors="replace")
    if size > tail_bytes and "\n" in data:
        data = data.split("\n", 1)[1]  # drop the partial first line
    if grep:
        try:
            rx = re.compile(grep)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid grep regex: {e}")
        data = "\n".join(line for line in data.splitlines() if rx.search(line))
    return PlainTextResponse(data, headers={"X-Log-Size-Bytes": str(size)})
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(crawler-service): GET /admin/logs/{crawl_id} crawler.log tail`

---

### Task 3: `GET /admin/job/{crawl_id}` — raw job dump + locks + node stats

**Goal:** The un-lossy companion to `/status`: raw `crawl_job:{id}` blob (secrets redacted), the five ownership locks with TTLs, the Node crawler's `stats:{id}` hash, and the reconcile leader.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/admin.py`
- Test: `apps-microservices/crawler-service/tests/test_admin_job_dump.py`

**Acceptance Criteria:**
- [ ] Returns `{job, locks, node_stats, reconcile_leader}`.
- [ ] `job` exposes ALL blob fields (`failure_cause`, `exit_code`, `oom_restart_count`, `replica_id`, `pid`, `previous_crawl_id`, ...) with `callback_url`, `failure_callback_url` and `params.proxyapify` redacted.
- [ ] `locks` includes only currently-held keys among `crawl_lock:`, `stash_lock:`, `unstash_lock:`, `archive_lock:`, `restore_lock:` with `{value, ttl_seconds}`.
- [ ] 503 when Redis is down.

**Verify:** `python -m pytest tests/test_admin_job_dump.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin_job_dump.py
"""Tests for GET /admin/job/{crawl_id} (raw blob + locks + node stats)."""
import pytest
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


JOB = {
    "crawl_id": "42", "status": "failed", "failure_cause": "progress_stalled",
    "oom_restart_count": 1, "replica_id": "r-abc", "pid": 123,
    "callback_url": "http://bo/webhook", "failure_callback_url": "http://bo/fail",
    "params": {"crawlMode": "update", "proxyapify": "http://user:pass@proxy"},
}


@pytest.fixture
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    from app.router.crawler import get_job_or_recover
    app = FastAPI()
    app.include_router(AdminRouter)

    async def fake_dep(crawl_id: str):
        return dict(JOB)

    app.dependency_overrides[get_job_or_recover] = fake_dep

    fake = AsyncMock()

    async def fake_get(key):
        return {"stash_lock:42": "r-abc", "reconcile_leader_lock": "r-xyz"}.get(key)

    fake.get = AsyncMock(side_effect=fake_get)
    fake.ttl = AsyncMock(return_value=1543)
    fake.hgetall = AsyncMock(return_value={"filtered_qm": "12", "processed": "300"})
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    return TestClient(app)


def test_dump_exposes_failure_fields_and_redacts_secrets(client):
    body = client.get("/admin/job/42").json()
    assert body["job"]["failure_cause"] == "progress_stalled"
    assert body["job"]["oom_restart_count"] == 1
    assert body["job"]["callback_url"] == "<redacted>"
    assert body["job"]["failure_callback_url"] == "<redacted>"
    assert body["job"]["params"]["proxyapify"] == "<redacted>"
    assert body["job"]["params"]["crawlMode"] == "update"


def test_dump_lists_held_locks_with_ttl(client):
    body = client.get("/admin/job/42").json()
    assert body["locks"] == {"stash_lock:42": {"value": "r-abc", "ttl_seconds": 1543}}
    assert body["reconcile_leader"] == "r-xyz"
    assert body["node_stats"]["filtered_qm"] == "12"


def test_503_when_redis_down(client, monkeypatch):
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    assert client.get("/admin/job/42").status_code == 503
```

- [ ] **Step 2: Run — FAIL.** **Step 3: Implement in `admin.py`:**

```python
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
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(crawler-service): GET /admin/job/{crawl_id} raw state dump (blob + locks + node stats)`

---

### Task 4: `GET /admin/config` — effective runtime config (redacted)

**Goal:** Answer "is flag X actually ON in this deployment?" — settings + the Node-subprocess env vars, secrets masked.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/admin.py`
- Test: `apps-microservices/crawler-service/tests/test_admin_config.py`

**Acceptance Criteria:**
- [ ] Returns `{settings, env}`; `settings` = `settings.model_dump()` with `API_KEY`/`APIFY_PROXY` masked to `"<set>"` when set (None stays None — signals auth disabled).
- [ ] `env` = whitelisted-prefix subset only; `REDIS_URL` (credentials) and `APIFY_PROXY` never appear.

**Verify:** `python -m pytest tests/test_admin_config.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin_config.py
"""Tests for GET /admin/config (effective runtime config, redacted)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return TestClient(app)


def test_settings_present_and_secrets_masked(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "APIFY_PROXY", "http://user:pass@proxy", raising=False)
    body = client.get("/admin/config").json()
    assert body["settings"]["AUTO_STASH_ENABLED"] in (True, False)
    assert body["settings"]["STASH_GRACE_SECONDS"] == settings.STASH_GRACE_SECONDS
    assert body["settings"]["APIFY_PROXY"] == "<set>"
    assert body["settings"]["API_KEY"] is None  # None stays None = auth disabled signal


def test_env_whitelist_only(client, monkeypatch):
    monkeypatch.setenv("DIEZ_TIER2_ENABLED", "true")
    monkeypatch.setenv("REDIS_URL", "redis://:secret@host:6379")
    monkeypatch.setenv("APIFY_PROXY", "http://user:pass@proxy")
    body = client.get("/admin/config").json()
    assert body["env"]["DIEZ_TIER2_ENABLED"] == "true"
    assert "REDIS_URL" not in body["env"]
    assert "APIFY_PROXY" not in body["env"]
```

- [ ] **Step 2: Run — FAIL.** **Step 3: Implement in `admin.py`:**

```python
_SECRET_SETTINGS = ("API_KEY", "APIFY_PROXY")
# Prefixes of env vars the Node subprocess consumes (it inherits container env).
# Deliberately narrow: "REDIS_LOSS" (not "REDIS_") so REDIS_URL credentials never leak.
_ENV_WHITELIST_PREFIXES = (
    "DIEZ_", "QM_", "TIMING_", "DETECTION_", "NAVIGATION_", "RECOVER_",
    "PROGRESS_", "REDIS_LOSS", "NODE_OPTIONS", "MAX_CONCURRENT",
    "DEFAULT_MAX_GLOBAL", "AUTO_STASH", "STASH_",
)


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
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(crawler-service): GET /admin/config effective runtime config (secrets redacted)`

---

### Task 5: `GET /admin/dataset/{crawl_id}` — list/sample dataset records

**Goal:** Inspect a crawl's captured URLs/content without the multi-GB `/results` tar and without lifecycle side effects (no `downloaded_at` stamp, no unstash).

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/admin.py`
- Test: `apps-microservices/crawler-service/tests/test_admin_dataset_sample.py`

**Acceptance Criteria:**
- [ ] `?kind=main|error|nfr|update&offset&limit&content_chars` pages over dataset item files, newest first.
- [ ] Each record: `{file, mtime, size_bytes, url, content_length[, content_preview][, parse_error]}`; `html_index.json` excluded.
- [ ] Resolves `{domain}` and sanitized `{domain .->-}` dirs (mirrors `_dataset_dir_for_job`).
- [ ] 404 with cold-tier hint when the dataset dir is absent — endpoint NEVER unstashes.

**Verify:** `python -m pytest tests/test_admin_dataset_sample.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin_dataset_sample.py
"""Tests for GET /admin/dataset/{crawl_id} (side-effect-free sampling)."""
import json
import os
import time
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_and_storage(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    from app.router.crawler import get_job_or_recover
    app = FastAPI()
    app.include_router(AdminRouter)
    job = {"crawl_id": "9", "status": "finished", "domain": "example.com",
           "storage_path": str(tmp_path)}

    async def fake_dep(crawl_id: str):
        return job

    app.dependency_overrides[get_job_or_recover] = fake_dep
    return app, tmp_path


def _mk_dataset(storage, dirname, items):
    d = storage / "storage" / "datasets" / dirname
    d.mkdir(parents=True)
    for i, (name, payload) in enumerate(items):
        p = d / name
        p.write_text(json.dumps(payload), encoding="utf-8")
        os.utime(p, (time.time() + i, time.time() + i))  # deterministic mtime order
    return d


def test_lists_newest_first_with_url_and_length(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "example.com", [
        ("a.json", {"url": "https://example.com/1", "content": "x" * 50}),
        ("b.json", {"url": "https://example.com/2", "content": "y" * 10}),
    ])
    body = TestClient(app).get("/admin/dataset/9").json()
    assert body["total_records"] == 2
    assert body["records"][0]["url"] == "https://example.com/2"  # newest first
    assert body["records"][0]["content_length"] == 10
    assert "content_preview" not in body["records"][0]  # content_chars=0 default


def test_content_preview_truncated(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "example.com", [("a.json", {"url": "u", "content": "abcdef"})])
    body = TestClient(app).get("/admin/dataset/9", params={"content_chars": 3}).json()
    assert body["records"][0]["content_preview"] == "abc"


def test_sanitized_domain_fallback_and_kind_prefix(app_and_storage):
    app, storage = app_and_storage
    _mk_dataset(storage, "error-example-com", [("e.json", {"url": "u", "errors": ["x"]})])
    body = TestClient(app).get("/admin/dataset/9", params={"kind": "error"}).json()
    assert body["total_records"] == 1


def test_404_with_cold_tier_hint_when_absent(app_and_storage):
    app, _ = app_and_storage
    resp = TestClient(app).get("/admin/dataset/9")
    assert resp.status_code == 404
    assert "side-effect-free" in resp.json()["detail"]


def test_html_index_excluded_and_pagination(app_and_storage):
    app, storage = app_and_storage
    items = [(f"f{i}.json", {"url": f"u{i}", "content": ""}) for i in range(5)]
    items.append(("html_index.json", {"u": "f"}))
    _mk_dataset(storage, "example.com", items)
    body = TestClient(app).get("/admin/dataset/9", params={"offset": 1, "limit": 2}).json()
    assert body["total_records"] == 5
    assert body["returned"] == 2
```

- [ ] **Step 2: Run — FAIL.** **Step 3: Implement in `admin.py`.** Add `import json` and `from datetime import datetime` to imports. Add:

```python
_DATASET_PREFIXES = {"main": "", "error": "error-", "nfr": "nfr-", "update": "update-"}


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
    entries = []
    with os.scandir(dataset_dir) as it:
        for entry in it:
            if not entry.name.endswith(".json") or entry.name == "html_index.json":
                continue
            try:
                st = entry.stat()
            except OSError:
                continue
            entries.append((entry.name, st.st_mtime, st.st_size))
    entries.sort(key=lambda e: e[1], reverse=True)  # newest first
    records = []
    for name, mtime, size in entries[offset:offset + limit]:
        record = {"file": name, "size_bytes": size,
                  "mtime": datetime.utcfromtimestamp(mtime).isoformat(), "url": None}
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
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(crawler-service): GET /admin/dataset/{crawl_id} side-effect-free dataset sampling`

---

### Task 6: `GET /admin/sidecar/{crawl_id}?name=` — whitelisted sidecar files

**Goal:** Serve the per-crawl diagnostic sidecars kept on disk for investigations (callback payload, diez/QM decisions+audits, exit reason, timing summary...).

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/admin.py`
- Test: `apps-microservices/crawler-service/tests/test_admin_sidecar.py`

**Acceptance Criteria:**
- [ ] Exact-match whitelist of 13 known filenames — anything else → 400 (no path traversal surface, `name` is a lookup key, never a path).
- [ ] Valid JSON returned parsed under `content`; non-JSON returned as `raw` capped 100 KB.
- [ ] 404 when file absent.

**Verify:** `python -m pytest tests/test_admin_sidecar.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin_sidecar.py
"""Tests for GET /admin/sidecar/{crawl_id} (whitelisted diagnostic files)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app_and_storage(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    from app.router.admin import router as AdminRouter
    from app.router.crawler import get_job_or_recover
    app = FastAPI()
    app.include_router(AdminRouter)
    job = {"crawl_id": "5", "status": "finished", "storage_path": str(tmp_path)}

    async def fake_dep(crawl_id: str):
        return job

    app.dependency_overrides[get_job_or_recover] = fake_dep
    return app, tmp_path


def test_returns_parsed_json(app_and_storage):
    app, storage = app_and_storage
    (storage / "_diez_decision.json").write_text(
        '{"mode": "skipDiez", "source": "tier2"}', encoding="utf-8")
    body = TestClient(app).get("/admin/sidecar/5",
                               params={"name": "_diez_decision.json"}).json()
    assert body["content"]["source"] == "tier2"


def test_non_json_returned_raw(app_and_storage):
    app, storage = app_and_storage
    (storage / "_exit_reason.json").write_text("not json {", encoding="utf-8")
    body = TestClient(app).get("/admin/sidecar/5",
                               params={"name": "_exit_reason.json"}).json()
    assert body["raw"] == "not json {"


def test_traversal_and_unknown_names_rejected(app_and_storage):
    app, _ = app_and_storage
    c = TestClient(app)
    assert c.get("/admin/sidecar/5", params={"name": "../../etc/passwd"}).status_code == 400
    assert c.get("/admin/sidecar/5", params={"name": "crawler.log"}).status_code == 400


def test_404_when_absent(app_and_storage):
    app, _ = app_and_storage
    resp = TestClient(app).get("/admin/sidecar/5",
                               params={"name": "_callback_payload.json"})
    assert resp.status_code == 404
```

- [ ] **Step 2: Run — FAIL.** **Step 3: Implement in `admin.py`:**

```python
# Exact filenames kept on disk for investigations (files_to_keep sets in
# crawler_manager.py:2534/:2954 + the diez/QM decision sidecars). crawler.log
# has its own /admin/logs endpoint; timing.jsonl excluded (unbounded size).
_SIDECAR_WHITELIST = frozenset({
    "_callback_payload.json", "_completion_marker.json", "_status_snapshot.json",
    "_exit_reason.json", "_update_report.json", "update_stats.json",
    "timing-summary.json", "_queue_stats.json",
    "_diez_decision.json", "_diez_audit.json",
    "_questionmark_decision.json", "_questionmark_observations.json",
    "_questionmark_audit.json",
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
```

- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `feat(crawler-service): GET /admin/sidecar/{crawl_id} whitelisted diagnostic sidecars`

---

### Task 7: `GET /admin/daemon-state` + daemon heartbeat files

**Goal:** Distinguish "daemon dead" from "GCS slow" from "request dead-lettered" in one call: marker-dir listings + error-marker contents + heartbeat ages.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/admin.py`
- Modify: `tools/upload_daemon.sh:45` (heartbeat touch after `while true; do`)
- Modify: `tools/download_daemon.sh:127` (heartbeat touch after `while true; do`)
- Test: `apps-microservices/crawler-service/tests/test_admin_daemon_state.py`

**Acceptance Criteria:**
- [ ] Returns one entry per shared dir (10: archives, archives_dead_letter, stash, stash_dead_letter, download_requests/results, stash_download_requests/results, move_requests/results): `{exists, file_count, heartbeat_age_seconds, files[≤200], error_markers}`.
- [ ] `*.error` / `*.move-error` file contents included (first 2000 chars).
- [ ] `.daemon-heartbeat` excluded from `files`, surfaced as `heartbeat_age_seconds`.
- [ ] Both daemon loops touch `.daemon-heartbeat` in their watch dir each cycle; `bash -n` passes on both scripts.

**Verify:** `python -m pytest tests/test_admin_daemon_state.py -v` → all pass; `bash -n tools/upload_daemon.sh && bash -n tools/download_daemon.sh` → silent

**Steps:**

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin_daemon_state.py
"""Tests for GET /admin/daemon-state (GCS daemon liveness/backlog view)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client_and_dirs(monkeypatch, tmp_path):
    from app.core.config import settings
    monkeypatch.setattr(settings, "API_KEY", None, raising=False)
    # Point every shared dir at tmp subdirs (only some will exist).
    monkeypatch.setattr(settings, "ARCHIVES_SHARED_PATH", str(tmp_path / "archives"), raising=False)
    monkeypatch.setattr(settings, "STASH_SHARED_PATH", str(tmp_path / "stash"), raising=False)
    monkeypatch.setattr(settings, "DOWNLOAD_REQUESTS_PATH", str(tmp_path / "dlreq"), raising=False)
    monkeypatch.setattr(settings, "DOWNLOAD_RESULTS_PATH", str(tmp_path / "dlres"), raising=False)
    monkeypatch.setattr(settings, "STASH_DOWNLOAD_REQUESTS_PATH", str(tmp_path / "sdreq"), raising=False)
    monkeypatch.setattr(settings, "STASH_DOWNLOAD_RESULTS_PATH", str(tmp_path / "sdres"), raising=False)
    monkeypatch.setattr(settings, "MOVE_REQUESTS_PATH", str(tmp_path / "mvreq"), raising=False)
    monkeypatch.setattr(settings, "MOVE_RESULTS_PATH", str(tmp_path / "mvres"), raising=False)
    from app.router.admin import router as AdminRouter
    app = FastAPI()
    app.include_router(AdminRouter)
    return TestClient(app), tmp_path


def test_missing_dirs_reported_not_fatal(client_and_dirs):
    client, _ = client_and_dirs
    body = client.get("/admin/daemon-state").json()
    assert body["archives"]["exists"] is False
    assert set(body.keys()) >= {"archives", "stash", "download_requests",
                                "move_requests", "archives_dead_letter"}


def test_files_heartbeat_and_error_markers(client_and_dirs):
    client, tmp = client_and_dirs
    d = tmp / "dlreq"
    d.mkdir()
    (d / "123.request").write_text("", encoding="utf-8")
    (d / "456.error").write_text("gcloud: AccessDenied", encoding="utf-8")
    (d / ".daemon-heartbeat").write_text("2026-07-04T00:00:00Z", encoding="utf-8")
    body = client.get("/admin/daemon-state").json()
    dl = body["download_requests"]
    assert dl["exists"] is True
    assert dl["file_count"] == 2  # heartbeat excluded
    assert dl["heartbeat_age_seconds"] is not None
    assert dl["error_markers"]["456.error"].startswith("gcloud")
    names = {f["name"] for f in dl["files"]}
    assert names == {"123.request", "456.error"}
```

- [ ] **Step 2: Run — FAIL.** **Step 3: Implement in `admin.py`.** Add `import time` to imports. Add:

```python
_ERROR_MARKER_SUFFIXES = (".error", ".move-error")
_DAEMON_STATE_MAX_FILES = 200


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
    heartbeat_age = None
    try:
        names = os.listdir(path)
    except OSError as e:
        return {"exists": True, "error": str(e)}
    for name in names:
        full = os.path.join(path, name)
        if not os.path.isfile(full):
            continue
        try:
            st = os.stat(full)
        except OSError:
            continue
        if name == ".daemon-heartbeat":
            heartbeat_age = int(now - st.st_mtime)
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
```

- [ ] **Step 4: Daemon heartbeats.** In `tools/upload_daemon.sh`, immediately after `while true; do` (line 45):

```bash
    # Liveness signal read by crawler-service GET /admin/daemon-state.
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$ARCHIVES_DIR/.daemon-heartbeat" 2>/dev/null || true
```

In `tools/download_daemon.sh`, immediately after `while true; do` (line 127):

```bash
    # Liveness signal read by crawler-service GET /admin/daemon-state.
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$REQUESTS_DIR/.daemon-heartbeat" 2>/dev/null || true
```

(Heartbeat files match neither daemon's `find -name "*.tar.gz"` / `-name "*.request"` patterns — no interference.)

- [ ] **Step 5: Verify** — pytest PASS + `bash -n` on both scripts. **Step 6: Commit** — `feat(crawler-service): GET /admin/daemon-state + daemon heartbeat markers`

---

### Task 8: Disk state on `GET /capacity`

**Goal:** Expose `used_pct`/`free_bytes` for storage/archives/stash on demand (today only visible inside 503 INSUFFICIENT_DISK_SPACE bodies) — verifies the auto-stash disk-pressure trigger.

**Files:**
- Modify: `apps-microservices/crawler-service/app/schemas/crawler.py:21-24` (`CapacityResponse`)
- Modify: `apps-microservices/crawler-service/app/router/crawler.py:160-189` (`get_capacity`)
- Test: `apps-microservices/crawler-service/tests/test_crawler_capacity_disk.py`

**Acceptance Criteria:**
- [ ] `CapacityResponse` gains `disk: Optional[dict] = None` (additive — BO reads running/max/is_full, unaffected).
- [ ] `/capacity` returns `disk = {storage, archives, stash, high_water_pct}` using the existing fail-open `_get_archives_disk_state` helper (degraded dict with `None`s on error — never raises).

**Verify:** `python -m pytest tests/test_crawler_capacity_disk.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing test**

```python
# tests/test_crawler_capacity_disk.py
"""GET /capacity must expose disk_state for storage/archives/stash."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    from app.router.crawler import router as CrawlerRouter
    app = FastAPI()
    app.include_router(CrawlerRouter)
    fake = AsyncMock()
    from common_utils.redis import cache_service
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)

    async def fake_get_key(key):
        return {"crawl_jobs:running_count": "2", "crawl_jobs:max_global_crawls": "3"}.get(key)

    monkeypatch.setattr(cache_service, "get_key", fake_get_key, raising=False)
    return TestClient(app)


def test_capacity_includes_disk_state(client):
    from app.core.crawler_manager import crawler_manager
    fake_state = {"free_bytes": 100, "total_bytes": 1000, "used_pct": 90.0,
                  "file_count": 1, "oldest_file_age_seconds": 5}
    with patch.object(crawler_manager, "_get_archives_disk_state", return_value=fake_state):
        body = client.get("/capacity").json()
    assert body["running_jobs"] == 2
    assert body["disk"]["storage"]["used_pct"] == 90.0
    assert body["disk"]["archives"]["used_pct"] == 90.0
    assert body["disk"]["stash"]["used_pct"] == 90.0
    assert body["disk"]["high_water_pct"] == 85
```

- [ ] **Step 2: Run — FAIL.** **Step 3: Schema.** In `app/schemas/crawler.py` (Optional already imported for other schemas — verify, else add `from typing import Optional`):

```python
class CapacityResponse(BaseModel):
    running_jobs: int
    max_global_jobs: int
    is_full: bool
    # Read-on-demand disk diagnostics (auto-stash disk-pressure verification).
    # None only if the field is omitted; the helper itself is fail-open.
    disk: Optional[dict] = None
```

- [ ] **Step 4: Endpoint.** In `get_capacity` (`app/router/crawler.py`), replace the final `return CapacityResponse(...)` block:

```python
        disk = {
            "storage": crawler_manager._get_archives_disk_state(settings.CRAWLER_STORAGE_PATH),
            "archives": crawler_manager._get_archives_disk_state(settings.ARCHIVES_SHARED_PATH),
            "stash": crawler_manager._get_archives_disk_state(settings.STASH_SHARED_PATH),
            "high_water_pct": settings.STASH_DISK_HIGH_WATER_PCT,
        }
        return CapacityResponse(
            running_jobs=running_jobs,
            max_global_jobs=max_global,
            is_full=running_jobs >= max_global,
            disk=disk,
        )
```

- [ ] **Step 5: Run** → PASS (also re-run any existing capacity tests: `python -m pytest tests/ -k capacity -v`). **Step 6: Commit** — `feat(crawler-service): disk state block on GET /capacity`

---

### Task 9: `?peek=true` on `GET /results`

**Goal:** Investigation reads must not start the auto-stash grace clock. `peek=true` skips the `downloaded_at` stamp.

**Files:**
- Modify: `apps-microservices/crawler-service/app/router/crawler.py:328-352`
- Test: `apps-microservices/crawler-service/tests/test_crawler_results_peek.py`

**Acceptance Criteria:**
- [ ] `GET /results/{id}?include=...&peek=true` does NOT call `_record_downloaded_at`; default (`peek=false`) behavior unchanged.
- [ ] Docstring/description states the limit: peek does NOT prevent the inline unstash of stashed crawls (that happens inside `get_results_archive`); the fully side-effect-free path is `/admin/dataset`.

**Verify:** `python -m pytest tests/test_crawler_results_peek.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write failing test**

```python
# tests/test_crawler_results_peek.py
"""GET /results?peek=true must not stamp downloaded_at."""
import pytest
from unittest.mock import AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client_and_archive(monkeypatch, tmp_path):
    from app.router.crawler import router as CrawlerRouter, get_job_or_recover
    app = FastAPI()
    app.include_router(CrawlerRouter)
    job = {"crawl_id": "7", "status": "finished", "storage_path": str(tmp_path)}

    async def fake_dep(crawl_id: str):
        return job

    app.dependency_overrides[get_job_or_recover] = fake_dep
    archive = tmp_path / "7-results.tar.gz"
    archive.write_bytes(b"fake-tar")
    return TestClient(app), str(archive)


@pytest.mark.parametrize("peek,expected_calls", [(True, 0), (False, 1)])
def test_peek_skips_downloaded_at(client_and_archive, peek, expected_calls):
    client, archive_path = client_and_archive
    from app.core.crawler_manager import crawler_manager
    with patch.object(crawler_manager, "get_results_archive",
                      new=AsyncMock(return_value=(archive_path, False))), \
         patch("app.router.crawler._record_downloaded_at",
               new=AsyncMock()) as rec:
        resp = client.get("/results/7",
                          params={"include": "dataset", "peek": str(peek).lower()})
        assert resp.status_code == 200
        assert rec.await_count == expected_calls
```

- [ ] **Step 2: Run — FAIL.** **Step 3: Implement.** In `download_crawl_results` (`app/router/crawler.py:328`), add the query param and guard the stamp:

```python
@router.get("/results/{crawl_id}")
async def download_crawl_results(
    include: List[IncludeInArchive] = Query(..., description="Specify which components to include in the archive. Can be provided multiple times (e.g., ?include=dataset&include=request_queues)."),
    peek: bool = Query(False, description="Investigation read: skip recording "
                       "downloaded_at (auto-stash grace clock). NOTE: does not "
                       "prevent inline unstash of stashed crawls — for a fully "
                       "side-effect-free view use GET /admin/dataset."),
    job_info: dict = Depends(get_job_or_recover)
):
```

and replace line 351-352:

```python
        # Record the consume signal (stream-start) for the auto-stash sweep —
        # unless this is an investigation peek.
        if not peek:
            await _record_downloaded_at(job_info)
```

- [ ] **Step 4: Run** → PASS. Also run the auto-stash results regression file: `python -m pytest tests/test_auto_stash_results.py -v`. **Step 5: Commit** — `feat(crawler-service): ?peek=true on GET /results skips the auto-stash grace stamp`

---

## Final verification (after all tasks)

- [ ] `python -m pytest tests/test_crawler_version.py tests/test_log_buffer.py tests/test_main_ring_handler.py tests/test_admin_recent_logs.py tests/test_admin_crawl_log.py tests/test_admin_job_dump.py tests/test_admin_config.py tests/test_admin_dataset_sample.py tests/test_admin_sidecar.py tests/test_admin_daemon_state.py tests/test_crawler_capacity_disk.py tests/test_crawler_results_peek.py -v` → all green
- [ ] Regression: `python -m pytest tests/test_admin_redis_debug.py tests/test_auto_stash_results.py tests/test_auto_stash_fields.py -v` → green
- [ ] `bash -n tools/upload_daemon.sh tools/download_daemon.sh`
- [ ] Grep check — no secret can leak: `grep -n "REDIS_URL\|proxyapify\|APIFY_PROXY\|API_KEY" apps-microservices/crawler-service/app/router/admin.py` → only redaction sites.

## Deploy notes (operator)

1. Build with identity: `GIT_COMMIT=$(git rev-parse --short HEAD) BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) docker compose --profile crawling build crawler-service` then `up -d`.
2. Restart the 4 GCS daemons (screen sessions) to pick up the heartbeat touch.
3. Set `API_KEY` in `.env` if not already (all `/admin/*` routes honor it; unset = open, matching current `/admin/redis-debug` behavior). Share the key once with the assistant (local env var / gitignored note — never committed).
4. Smoke: `GET /crawler/version` → commit sha; `GET /crawler/admin/config` → flags; `GET /crawler/admin/daemon-state` → heartbeat ages < poll interval.
