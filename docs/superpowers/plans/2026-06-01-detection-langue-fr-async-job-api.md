# api-detection-langue-fr Async Job API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `api-detection-langue-fr` an async job API (`POST /detect-batch-async` → `202 job_id`; `GET /detect-batch-async/{id}` → poll) so BO's hot-path scripts stop hitting the 180s `detect-batch` timeout.

**Architecture:** Approach A — Redis-backed job store + in-process asyncio worker reusing an extracted `_run_batch_core` (sync `/detect-batch` behavior unchanged). Shared prod admission pool (crawler-service is immune via `html_content` bypass). Restart = fail-fast: heartbeat goes stale, BO re-enqueues absent URLs via `domaine_fr_retry`. Hot-path BO migration only.

**Tech Stack:** Python 3.10 / FastAPI / `redis.asyncio` / Prometheus (service); PHP / cURL via `call_api_hellopro` (BO).

**Spec:** `docs/superpowers/specs/2026-06-01-detection-langue-fr-async-job-api-design.md` (committed `c5782698`).

**Repos / branches:**
- Service tasks (1–5): `RAG-HP-PUB` on `features/poc`. Run from `c:/Users/randr/Documents/Workspaces/RAG-HP-PUB`.
- BO tasks (6–8): `Hellopro` on `main`. Run from `C:/Users/randr/Documents/Workspaces/Hellopro`.

**Deploy gate (operational, from spec §8):** RAG-HP-PUB ships FIRST (additive, sync untouched), then Hellopro. Tasks 6–8 are `blockedBy` Task 5 so the service contract is final before BO codes against it.

**Conventions:**
- Commit per task, Conventional Commits, **bilingual EN+FR** (ask language at first commit; reuse for the rest of the session).
- Windows cp1252: write `.git/COMMIT_EDITMSG` via the Write tool (UTF-8), then `git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG`.
- Service tests run locally with mocks (no Redis/browser). Each test file is self-contained — do NOT run the whole suite (pre-existing broken tests; see spec blockers). Run only the new file.

---

## File Structure

**Service (RAG-HP-PUB / `apps-microservices/api-detection-langue-fr`):**
- `app/models/schemas.py` — MODIFY: add `BatchOpts`, `BatchCounts` (dataclasses), `AsyncBatchSubmitRequest`, `AsyncBatchSubmitResponse`, `AsyncBatchStatusResponse`.
- `app/core/config.py` — MODIFY: add 8 async settings.
- `app/core/metrics.py` — MODIFY: add 4 async metrics.
- `app/api/routes.py` — MODIFY: extract `_run_batch_core`; thin `/detect-batch` wrapper; add the two async endpoints.
- `app/core/async_jobs.py` — CREATE: `JobStore`, `JobManager`, exceptions, `poll_status`.
- `main.py` — MODIFY: add `lifespan` building `JobManager` into `app.state`.
- `tests/test_batch_core_refactor.py`, `tests/test_async_jobstore.py`, `tests/test_async_jobmanager.py`, `tests/test_async_endpoints.py` — CREATE.

**BO (Hellopro / `BO`):**
- `admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php` — MODIFY: add async constants, `_detection_absent_urls()`, `detectBatchUrlsAsync()`.
- `script/chatgpt/variante_categorie/script_identifier_site_fr_v2.php` — MODIFY: migrate to async.
- `script/chatgpt/variante_categorie/script_retry_identifier_site_fr.php` — MODIFY: migrate to async.
- `admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_smoke_detection_async_rindra_BO.php` — CREATE: smoke + pure-function asserts.

---

## Task 1: Async types, config, metrics

**Goal:** Add the dataclasses, request/response schemas, settings, and Prometheus metrics the rest of the plan depends on. No behavior change.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/models/schemas.py`
- Modify: `apps-microservices/api-detection-langue-fr/app/core/config.py`
- Modify: `apps-microservices/api-detection-langue-fr/app/core/metrics.py`
- Test: `apps-microservices/api-detection-langue-fr/tests/test_async_schemas.py`

**Acceptance Criteria:**
- [ ] `BatchOpts`, `BatchCounts` importable from `app.models.schemas`.
- [ ] `AsyncBatchSubmitRequest` rejects > 100 items and defaults `mode=DetectionMode.COMPLETE`.
- [ ] The 8 settings exist with documented defaults; 4 new metrics registered without name collision.

**Verify:** `cd "c:/Users/randr/Documents/Workspaces/RAG-HP-PUB" && python -m pytest apps-microservices/api-detection-langue-fr/tests/test_async_schemas.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Add dataclasses + async schemas to `app/models/schemas.py`**

At the top, extend imports:
```python
from dataclasses import dataclass
```
Append at end of file:
```python
# ============================================================================
# Async batch job models
# ============================================================================

@dataclass
class BatchOpts:
    """Per-call batch options, decoupled from the request model so the batch
    core can be driven by both the sync route and the async worker."""
    proxy_url: Optional[str] = None
    use_nlp_detection: bool = True
    force_refresh: bool = False
    max_concurrency: int = 10
    homepage_fallback: bool = True


@dataclass
class BatchCounts:
    """Authoritative tallies returned by the batch core (success/failed/error)."""
    success_count: int
    failed_count: int
    error_count: int


class AsyncBatchSubmitRequest(BaseModel):
    """Submit body for POST /detect-batch-async. Mirrors BatchDetectionRequest
    plus an optional client idempotency key. Items must contain no duplicate URLs."""
    items: list[BatchItem] = Field(..., max_length=100)
    mode: DetectionMode = Field(default=DetectionMode.COMPLETE)
    proxy_url: Optional[str] = Field(default=None)
    use_nlp_detection: bool = Field(default=True)
    force_refresh: bool = Field(default=False)
    max_concurrency: int = Field(default=10, ge=1, le=50)
    homepage_fallback: bool = Field(default=True)
    client_job_id: Optional[str] = Field(
        default=None,
        description="Caller idempotency key. A re-submit with the same key returns the existing job."
    )


class AsyncBatchSubmitResponse(BaseModel):
    job_id: str
    status: str
    total: int
    poll_after_seconds: int


class AsyncBatchStatusResponse(BaseModel):
    job_id: str
    status: str                                   # pending|running|completed|failed|stale
    total: int
    done: int
    success_count: int
    failed_count: int
    error_count: int
    results: Optional[list[DetectionResponse]] = None
    processing_time_ms: Optional[float] = None
    error: Optional[str] = None
    poll_after_seconds: int
```

- [ ] **Step 2: Add settings to `app/core/config.py`**

Insert before `class Config:` inside `Settings`:
```python
    # Async job API (POST /detect-batch-async + GET poll)
    ASYNC_JOBS_ENABLED: bool = True
    MAX_ACTIVE_JOBS: int = 8
    JOB_TTL_ACTIVE_S: int = 7200          # 2h — pending/running record TTL (refreshed by heartbeat)
    JOB_RESULT_TTL_S: int = 3600          # 1h — terminal record TTL (BO must poll within this)
    STALE_THRESHOLD_S: int = 120          # no heartbeat beyond this → poll reports 'stale'
    HEARTBEAT_INTERVAL_S: int = 5         # wall-clock heartbeat tick
    ASYNC_SUBMIT_RETRY_AFTER_S: int = 15  # Retry-After on capacity 503
    ASYNC_POLL_HINT_MAX_S: int = 30       # upper bound on server poll_after_seconds hint
    SHUTDOWN_GRACE_S: int = 5             # bound on JobManager.shutdown() task drain
```

- [ ] **Step 3: Add metrics to `app/core/metrics.py`**

Append:
```python
# Async job API metrics.
ASYNC_JOBS_SUBMITTED = Counter(
    "detect_async_jobs_submitted_total",
    "Async batch jobs accepted (202)",
)
ASYNC_JOBS_ACTIVE = Gauge(
    "detect_async_jobs_active",
    "Currently reserved/in-flight async jobs",
)
ASYNC_JOBS_TERMINAL = Counter(
    "detect_async_jobs_terminal_total",
    "Async jobs reaching a terminal status",
    labelnames=("status",),
)
ASYNC_JOB_DURATION = Histogram(
    "detect_async_job_duration_seconds",
    "Async job wall-clock from running to terminal",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
)
ASYNC_JOB_CAPACITY_REJECTED = Counter(
    "detect_async_job_capacity_rejected_total",
    "Submits rejected because MAX_ACTIVE_JOBS was reached",
)
```
(Async per-item fetches reuse the existing `ADMISSION_REJECTED` counter with `endpoint="/api/v1/detect-batch-async"` — no new metric for that.)

- [ ] **Step 4: Write the test `tests/test_async_schemas.py`**

```python
import pytest
from pydantic import ValidationError

from app.models.schemas import (
    BatchItem, BatchOpts, BatchCounts, DetectionMode,
    AsyncBatchSubmitRequest, AsyncBatchStatusResponse,
)
from app.core.config import settings
from app.core import metrics


def test_batchopts_defaults():
    o = BatchOpts()
    assert o.max_concurrency == 10 and o.use_nlp_detection is True
    assert BatchCounts(1, 2, 3).success_count == 1


def test_submit_request_defaults_and_limit():
    req = AsyncBatchSubmitRequest(items=[BatchItem(url="https://a.fr")])
    assert req.mode == DetectionMode.COMPLETE
    assert req.client_job_id is None
    with pytest.raises(ValidationError):
        AsyncBatchSubmitRequest(items=[BatchItem(url=f"https://a{i}.fr") for i in range(101)])


def test_status_response_optional_results():
    r = AsyncBatchStatusResponse(
        job_id="x", status="running", total=2, done=1,
        success_count=0, failed_count=0, error_count=0, poll_after_seconds=5,
    )
    assert r.results is None


def test_settings_present():
    assert settings.MAX_ACTIVE_JOBS == 8
    assert settings.JOB_RESULT_TTL_S < settings.JOB_TTL_ACTIVE_S
    assert settings.HEARTBEAT_INTERVAL_S < settings.STALE_THRESHOLD_S


def test_metrics_registered():
    for name in (
        "ASYNC_JOBS_SUBMITTED", "ASYNC_JOBS_ACTIVE", "ASYNC_JOBS_TERMINAL",
        "ASYNC_JOB_DURATION", "ASYNC_JOB_CAPACITY_REJECTED",
    ):
        assert hasattr(metrics, name)
```

- [ ] **Step 5: Run + commit**

Run: `cd "c:/Users/randr/Documents/Workspaces/RAG-HP-PUB" && python -m pytest apps-microservices/api-detection-langue-fr/tests/test_async_schemas.py -v`
Expected: 5 passed.
Commit: `feat(detection): async job types, config, metrics`.

---

## Task 2: Extract `_run_batch_core` (refactor, no behavior change)

**Goal:** Move the `/detect-batch` 2-pass orchestration into a reusable `_run_batch_core(items, mode, opts, progress_cb=None)` returning `(results, BatchCounts)`; make `/detect-batch` a thin wrapper. Behavior of the sync endpoint is unchanged.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py:358-640` (the batch handler)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_batch_core_refactor.py`

**Acceptance Criteria:**
- [ ] `_run_batch_core` is importable from `app.api.routes` and returns `(list[DetectionResponse], BatchCounts)`.
- [ ] `/detect-batch` still returns a `BatchDetectionResponse` with identical `results` order + counts as before.
- [ ] `progress_cb(done:int)` fires once per item completion only when provided (no-op when `None`).
- [ ] Pass-2 retry of `fetch_failed/challenge_page/admission_rejected` preserved.

**Verify:** `cd "c:/Users/randr/Documents/Workspaces/RAG-HP-PUB" && python -m pytest apps-microservices/api-detection-langue-fr/tests/test_batch_core_refactor.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the characterization test FIRST `tests/test_batch_core_refactor.py`**

This stubs `_detect_single_url` so the test exercises the *orchestration* (ordering, counts, pass-2 retry) without NLP/browser.
```python
import pytest
from app.api import routes
from app.models.schemas import BatchItem, BatchOpts, BatchCounts, DetectionMode, DetectionResponse


@pytest.mark.asyncio
async def test_core_orders_and_counts(monkeypatch):
    async def fake_detect(url, **kwargs):
        ok = url.endswith(".fr")
        return DetectionResponse(ok=ok, url=url, method="url_tld" if ok else "nlp_negative")
    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url="https://a.fr"), BatchItem(url="https://b.com"), BatchItem(url="https://c.fr")]
    results, counts = await routes._run_batch_core(items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=3))

    assert [r.url for r in results] == ["https://a.fr", "https://b.com", "https://c.fr"]  # order preserved
    assert counts.success_count == 2 and counts.failed_count == 1 and counts.error_count == 0


@pytest.mark.asyncio
async def test_core_pass2_retries_fetch_failed(monkeypatch):
    calls = {"https://flaky.fr": 0}
    async def fake_detect(url, **kwargs):
        if url == "https://flaky.fr":
            calls[url] += 1
            if calls[url] == 1:
                return DetectionResponse(ok=False, url=url, method="fetch_failed")
            return DetectionResponse(ok=True, url=url, method="url_tld")  # recovers on retry
        return DetectionResponse(ok=True, url=url, method="url_tld")
    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)

    items = [BatchItem(url="https://flaky.fr")]
    results, counts = await routes._run_batch_core(items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=1))
    assert results[0].ok is True and calls["https://flaky.fr"] == 2  # pass-2 retried


@pytest.mark.asyncio
async def test_core_progress_cb(monkeypatch):
    async def fake_detect(url, **kwargs):
        return DetectionResponse(ok=True, url=url, method="url_tld")
    monkeypatch.setattr(routes, "_detect_single_url", fake_detect)
    seen = []
    items = [BatchItem(url=f"https://a{i}.fr") for i in range(3)]
    await routes._run_batch_core(items, DetectionMode.COMPLETE, BatchOpts(max_concurrency=3),
                                 progress_cb=lambda done: seen.append(done))
    assert sorted(seen) == [1, 2, 3]
```

- [ ] **Step 2: Run the test — expect failure (`_run_batch_core` not defined)**

Run: `python -m pytest apps-microservices/api-detection-langue-fr/tests/test_batch_core_refactor.py -v`
Expected: FAIL — `AttributeError: module 'app.api.routes' has no attribute '_run_batch_core'`.

- [ ] **Step 3: Add `BatchOpts`/`BatchCounts` to the routes import**

In `app/api/routes.py`, add to the `from app.models.schemas import (...)` block:
```python
    BatchOpts,
    BatchCounts,
```
And add to the top imports:
```python
from typing import Optional, Callable
```
(extend the existing `from typing import Optional`).

- [ ] **Step 4: Define `_run_batch_core` by moving the handler body**

Replace the current `async def detect_french_batch(...)` body (lines ~358–640). Create the core function and a thin wrapper.

Insert this function ABOVE the route (e.g. after `_detect_single_url`):
```python
async def _run_batch_core(
    items: list[BatchItem],
    mode: DetectionMode,
    opts: BatchOpts,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> tuple[list[DetectionResponse], BatchCounts]:
    """Shared 2-pass batch orchestration. Used by the sync /detect-batch route
    (progress_cb=None) and the async worker (throttled progress_cb)."""
    items_to_process = items
    total_items = len(items_to_process)
    start_time = time.time()

    logger.info(f"[BATCH] Debut traitement: {total_items} URLs, concurrence={opts.max_concurrency}, mode={mode}")

    semaphore = asyncio.Semaphore(opts.max_concurrency)
    processed_count = 0
    count_lock = asyncio.Lock()

    async def _increment_count() -> int:
        nonlocal processed_count
        async with count_lock:
            processed_count += 1
            if progress_cb is not None:
                progress_cb(processed_count)
            return processed_count

    # ... MOVE the existing closures and both mode branches here VERBATIM, with
    # these mechanical substitutions (the only changes):
    #   request.mode            -> mode
    #   request.proxy_url       -> opts.proxy_url
    #   request.use_nlp_detection -> opts.use_nlp_detection
    #   request.force_refresh   -> opts.force_refresh
    #   request.homepage_fallback -> opts.homepage_fallback
    #   request.max_concurrency -> opts.max_concurrency
    # The two `return BatchDetectionResponse(...)` statements become:
    #   return results, BatchCounts(success_count=success_count,
    #                               failed_count=failed_count,
    #                               error_count=error_count)
    # (drop processing_time_ms here — the wrapper computes it.)
```

Concretely: the moved blocks are `_process_item_core` (was ~400–444), `process_single` (~446–460), the `first_match` block (~465–563), and the `complete`/`simple` block (~569–640). They reference only the substituted names above plus the locals defined here (`semaphore`, `_increment_count`, `total_items`, `start_time`, `_with_group`). Replace the FIRST-branch return (first_match, was ~556–563):
```python
        return results, BatchCounts(
            success_count=success_count, failed_count=failed_count, error_count=error_count
        )
```
and the SECOND-branch return (complete/simple, was ~633–640):
```python
    return results, BatchCounts(
        success_count=success_count, failed_count=failed_count, error_count=error_count
    )
```

- [ ] **Step 5: Rewrite `/detect-batch` as a thin wrapper**

Replace the `detect_french_batch` body (keep the decorator + docstring):
```python
@router.post("/detect-batch", response_model=BatchDetectionResponse)
async def detect_french_batch(request: BatchDetectionRequest) -> BatchDetectionResponse:
    """(keep the existing docstring verbatim)"""
    start_time = time.time()
    opts = BatchOpts(
        proxy_url=request.proxy_url,
        use_nlp_detection=request.use_nlp_detection,
        force_refresh=request.force_refresh,
        max_concurrency=request.max_concurrency,
        homepage_fallback=request.homepage_fallback,
    )
    results, counts = await _run_batch_core(request.items, request.mode, opts)
    processing_time_ms = (time.time() - start_time) * 1000
    return BatchDetectionResponse(
        total=len(results),
        success_count=counts.success_count,
        failed_count=counts.failed_count,
        error_count=counts.error_count,
        results=list(results),
        processing_time_ms=round(processing_time_ms, 2),
    )
```

- [ ] **Step 6: Run the test — expect pass**

Run: `python -m pytest apps-microservices/api-detection-langue-fr/tests/test_batch_core_refactor.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

`refactor(detection): extract _run_batch_core from /detect-batch (no behavior change)`. Commit this in isolation — the async-wiring commits (Task 4/5) must not touch the core body again. The `progress_cb` plumbing lands HERE.

---

## Task 3: `JobStore` (Redis-backed job records)

**Goal:** A Redis CRUD layer for job records + the atomic idempotency index. Mirrors `DomainCache` lazy-connect, but the submit-path write is **checked** (raises on failure) and a `ping()` probe exists.

**Files:**
- Create: `apps-microservices/api-detection-langue-fr/app/core/async_jobs.py`
- Test: `apps-microservices/api-detection-langue-fr/tests/test_async_jobstore.py`

**Acceptance Criteria:**
- [ ] `claim_index` uses `SET key val NX EX ttl` (atomic) — returns `True` only on first claim.
- [ ] `write` raises on Redis failure (submit path detects it); `get` returns `None` on failure (read path degrades).
- [ ] `ping()` returns `False` when Redis is unreachable.

**Verify:** `cd "c:/Users/randr/Documents/Workspaces/RAG-HP-PUB" && python -m pytest apps-microservices/api-detection-langue-fr/tests/test_async_jobstore.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Create `app/core/async_jobs.py` (JobStore + exceptions + poll_status)**

```python
"""Async job store + manager for the /detect-batch-async API.

Job state lives in Redis (records + an atomic idempotency index). The worker
runs in-process via asyncio, reusing the batch core injected at construction
(no import of app.api.routes — avoids a cycle). See spec
docs/superpowers/specs/2026-06-01-detection-langue-fr-async-job-api-design.md.
"""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Callable, Awaitable

try:
    import redis.asyncio as aioredis
except ImportError:  # pragma: no cover
    aioredis = None

logger = logging.getLogger(__name__)

_JOB_KEY = "detect:job:{}"
_IDX_KEY = "detect:jobidx:{}"


class _JobsDisabled(Exception):
    """ASYNC_JOBS_ENABLED is false (permanent 503, not retryable)."""


class _JobsUnavailable(Exception):
    """Redis unreachable / first write failed (permanent 503, not retryable)."""


class _JobCapacityExceeded(Exception):
    """MAX_ACTIVE_JOBS reached (transient 503 + Retry-After)."""


class JobStore:
    """Redis CRUD for job records + idempotency index. Lazy connect."""

    def __init__(self, redis_url: Optional[str], client=None) -> None:
        self._redis_url = redis_url
        self._client = client
        self._initialized = client is not None
        self._init_lock = asyncio.Lock()

    async def _get_client(self):
        async with self._init_lock:
            if not self._initialized:
                self._initialized = True
                if self._redis_url and aioredis:
                    try:
                        self._client = aioredis.from_url(self._redis_url, decode_responses=True)
                    except Exception as e:  # URL parse only; conn is lazy
                        logger.warning(f"[async-jobs] Redis client init failed: {e}")
        return self._client

    async def ping(self) -> bool:
        client = await self._get_client()
        if not client:
            return False
        try:
            return bool(await client.ping())
        except Exception as e:
            logger.warning(f"[async-jobs] Redis ping failed: {e}")
            return False

    async def claim_index(self, client_job_id: str, job_id: str, ttl: int) -> bool:
        client = await self._get_client()
        ok = await client.set(_IDX_KEY.format(client_job_id), job_id, nx=True, ex=ttl)
        return bool(ok)

    async def get_index(self, client_job_id: str) -> Optional[str]:
        client = await self._get_client()
        try:
            return await client.get(_IDX_KEY.format(client_job_id))
        except Exception:
            return None

    async def delete_index(self, client_job_id: str) -> None:
        client = await self._get_client()
        try:
            await client.delete(_IDX_KEY.format(client_job_id))
        except Exception:
            pass

    async def refresh_index_ttl(self, client_job_id: str, ttl: int) -> None:
        client = await self._get_client()
        try:
            await client.expire(_IDX_KEY.format(client_job_id), ttl)
        except Exception:
            pass

    async def write(self, record: dict, ttl: int) -> None:
        """Write a record. RAISES on failure — the submit path relies on this
        to detect an unreachable Redis (do NOT swallow here)."""
        client = await self._get_client()
        if not client:
            raise RuntimeError("Redis client unavailable")
        await client.setex(_JOB_KEY.format(record["job_id"]), ttl, json.dumps(record))

    async def get(self, job_id: str) -> Optional[dict]:
        client = await self._get_client()
        if not client:
            return None
        try:
            data = await client.get(_JOB_KEY.format(job_id))
            return json.loads(data) if data else None
        except Exception as e:
            logger.debug(f"[async-jobs] get error: {e}")
            return None


def poll_status(record: dict, now: float, stale_threshold_s: int) -> str:
    """Compute the BO-visible status. 'stale' is derived on read for a
    pending/running record whose heartbeat froze (dead worker). Never mutates."""
    status = record.get("status", "pending")
    if status in ("pending", "running"):
        last = max(record.get("created_at", 0.0), record.get("last_activity", 0.0))
        if (now - last) > stale_threshold_s:
            return "stale"
    return status
```

- [ ] **Step 2: Write `tests/test_async_jobstore.py` with a dependency-free fake Redis**

```python
import pytest
from app.core.async_jobs import JobStore, poll_status


class FakeRedis:
    def __init__(self, fail=False):
        self.fail = fail
        self.kv = {}

    async def ping(self):
        if self.fail:
            raise ConnectionError("down")
        return True

    async def set(self, key, val, nx=False, ex=None):
        if self.fail:
            raise ConnectionError("down")
        if nx and key in self.kv:
            return None
        self.kv[key] = val
        return True

    async def get(self, key):
        if self.fail:
            raise ConnectionError("down")
        return self.kv.get(key)

    async def setex(self, key, ttl, val):
        if self.fail:
            raise ConnectionError("down")
        self.kv[key] = val

    async def delete(self, key):
        self.kv.pop(key, None)

    async def expire(self, key, ttl):
        return True


@pytest.mark.asyncio
async def test_claim_index_atomic():
    store = JobStore(redis_url=None, client=FakeRedis())
    assert await store.claim_index("c1", "job-A", 100) is True
    assert await store.claim_index("c1", "job-B", 100) is False   # already claimed
    assert await store.get_index("c1") == "job-A"


@pytest.mark.asyncio
async def test_write_raises_on_failure():
    store = JobStore(redis_url=None, client=FakeRedis(fail=True))
    with pytest.raises(Exception):
        await store.write({"job_id": "x"}, 100)


@pytest.mark.asyncio
async def test_get_degrades_to_none():
    store = JobStore(redis_url=None, client=FakeRedis(fail=True))
    assert await store.get("x") is None


@pytest.mark.asyncio
async def test_ping():
    assert await JobStore(None, client=FakeRedis()).ping() is True
    assert await JobStore(None, client=FakeRedis(fail=True)).ping() is False


def test_poll_status_stale():
    rec = {"status": "running", "created_at": 0.0, "last_activity": 0.0}
    assert poll_status(rec, now=1000.0, stale_threshold_s=120) == "stale"
    assert poll_status({**rec, "last_activity": 990.0}, now=1000.0, stale_threshold_s=120) == "running"
    assert poll_status({"status": "completed"}, now=1e9, stale_threshold_s=120) == "completed"
```

- [ ] **Step 3: Run + commit**

Run: `python -m pytest apps-microservices/api-detection-langue-fr/tests/test_async_jobstore.py -v` → 5 passed.
Commit: `feat(detection): JobStore Redis layer + poll_status for async jobs`.

---

## Task 4: `JobManager` (worker, idempotency, capacity, shutdown)

**Goal:** The asyncio worker: race-free `submit`, heartbeat ticker, terminal writes with authoritative counts, single-writer shutdown. Batch runner is injected (no routes import).

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/async_jobs.py` (append `JobManager`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_async_jobmanager.py`

**Acceptance Criteria:**
- [ ] Concurrent submits with the same `client_job_id` → one spawned task, both get the same `job_id`.
- [ ] `_inflight` never exceeds `MAX_ACTIVE_JOBS` (reserve is synchronous, pre-await).
- [ ] Completed record carries counts from the runner return (authoritative), not the heartbeat snapshot.
- [ ] `shutdown()` cancels tasks, awaits them, then marks only non-terminal records `failed(service_shutdown)`.

**Verify:** `cd "c:/Users/randr/Documents/Workspaces/RAG-HP-PUB" && python -m pytest apps-microservices/api-detection-langue-fr/tests/test_async_jobmanager.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Append `JobManager` to `app/core/async_jobs.py`**

```python
from app.models.schemas import BatchItem, BatchOpts, DetectionMode  # noqa: E402


class JobManager:
    def __init__(self, store: JobStore, batch_runner: Callable[..., Awaitable], settings) -> None:
        self._store = store
        self._batch_runner = batch_runner          # _run_batch_core, injected
        self._s = settings
        self._job_tasks: dict[str, asyncio.Task] = {}
        self._inflight = 0                          # reserve counter (sync-guarded)

    async def get_record(self, job_id: str) -> Optional[dict]:
        return await self._store.get(job_id)

    async def submit(self, req) -> tuple[str, int]:
        """Returns (job_id, http_status). http_status is 202 (new) or 200 (existing)."""
        if not self._s.ASYNC_JOBS_ENABLED:
            raise _JobsDisabled()
        if not await self._store.ping():
            raise _JobsUnavailable()

        job_id = uuid.uuid4().hex
        cjid = req.client_job_id

        # Idempotency claim FIRST (atomic SET NX). Existing → return it, no spawn.
        if cjid:
            claimed = await self._store.claim_index(cjid, job_id, self._s.JOB_TTL_ACTIVE_S)
            if not claimed:
                existing = await self._store.get_index(cjid)
                if existing:
                    return existing, 200
                claimed = await self._store.claim_index(cjid, job_id, self._s.JOB_TTL_ACTIVE_S)
                if not claimed:
                    existing = await self._store.get_index(cjid)
                    return (existing or job_id), 200

        # Capacity reserve — synchronous, NO await between check and increment.
        from app.core.metrics import (
            ASYNC_JOB_CAPACITY_REJECTED, ASYNC_JOBS_SUBMITTED, ASYNC_JOBS_ACTIVE,
        )
        if self._inflight >= self._s.MAX_ACTIVE_JOBS:
            if cjid:
                await self._store.delete_index(cjid)
            ASYNC_JOB_CAPACITY_REJECTED.inc()
            raise _JobCapacityExceeded()
        self._inflight += 1

        now = time.time()
        record = {
            "job_id": job_id, "client_job_id": cjid, "status": "pending",
            "total": len(req.items), "done": 0,
            "success_count": 0, "failed_count": 0, "error_count": 0,
            "results": None, "error": None,
            "created_at": now, "started_at": None, "finished_at": None,
            "last_activity": now,
        }
        try:
            await self._store.write(record, self._s.JOB_TTL_ACTIVE_S)
        except Exception:
            self._inflight -= 1
            if cjid:
                await self._store.delete_index(cjid)
            raise _JobsUnavailable()

        opts = BatchOpts(
            proxy_url=req.proxy_url, use_nlp_detection=req.use_nlp_detection,
            force_refresh=req.force_refresh, max_concurrency=req.max_concurrency,
            homepage_fallback=req.homepage_fallback,
        )
        task = asyncio.create_task(
            self._run_job(job_id, cjid, list(req.items), req.mode, opts)
        )
        self._job_tasks[job_id] = task
        task.add_done_callback(lambda t, jid=job_id: self._on_done(jid))
        ASYNC_JOBS_SUBMITTED.inc()
        ASYNC_JOBS_ACTIVE.set(self._inflight)
        return job_id, 202

    def _on_done(self, job_id: str) -> None:
        self._job_tasks.pop(job_id, None)
        self._inflight = max(0, self._inflight - 1)
        from app.core.metrics import ASYNC_JOBS_ACTIVE
        ASYNC_JOBS_ACTIVE.set(self._inflight)

    async def _heartbeat(self, job_id: str, progress: dict) -> None:
        try:
            while True:
                await asyncio.sleep(self._s.HEARTBEAT_INTERVAL_S)
                rec = await self._store.get(job_id)
                if not rec or rec.get("status") not in ("pending", "running"):
                    return
                rec["done"] = progress["done"]
                rec["last_activity"] = time.time()
                try:
                    await self._store.write(rec, self._s.JOB_TTL_ACTIVE_S)
                except Exception:
                    pass
        except asyncio.CancelledError:
            return

    async def _run_job(self, job_id, cjid, items, mode, opts) -> None:
        from app.core.metrics import ASYNC_JOBS_TERMINAL, ASYNC_JOB_DURATION
        progress = {"done": 0}
        started = time.time()
        rec = await self._store.get(job_id) or {"job_id": job_id}
        rec.update({"status": "running", "started_at": started, "last_activity": started})
        try:
            await self._store.write(rec, self._s.JOB_TTL_ACTIVE_S)
        except Exception:
            pass

        hb = asyncio.create_task(self._heartbeat(job_id, progress))
        try:
            results, counts = await self._batch_runner(
                items, mode, opts, lambda done: progress.__setitem__("done", done)
            )
            hb.cancel(); await asyncio.gather(hb, return_exceptions=True)
            rec = await self._store.get(job_id) or rec
            rec.update({
                "status": "completed", "done": len(results),
                "success_count": counts.success_count,
                "failed_count": counts.failed_count,
                "error_count": counts.error_count,
                "results": [r.model_dump() for r in results],
                "finished_at": time.time(), "last_activity": time.time(),
            })
            await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
            if cjid:
                await self._store.refresh_index_ttl(cjid, self._s.JOB_RESULT_TTL_S)
            ASYNC_JOBS_TERMINAL.labels(status="completed").inc()
            ASYNC_JOB_DURATION.observe(time.time() - started)
        except asyncio.CancelledError:
            hb.cancel()
            raise                                   # shutdown() owns the record write
        except Exception as e:
            hb.cancel(); await asyncio.gather(hb, return_exceptions=True)
            rec = await self._store.get(job_id) or rec
            rec.update({"status": "failed", "error": str(e),
                        "finished_at": time.time(), "last_activity": time.time()})
            try:
                await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
                if cjid:
                    await self._store.refresh_index_ttl(cjid, self._s.JOB_RESULT_TTL_S)
            except Exception:
                pass
            ASYNC_JOBS_TERMINAL.labels(status="failed").inc()

    async def shutdown(self) -> None:
        job_ids = list(self._job_tasks.keys())
        tasks = list(self._job_tasks.values())
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=self._s.SHUTDOWN_GRACE_S)
        for job_id in job_ids:
            rec = await self._store.get(job_id)
            if rec and rec.get("status") in ("pending", "running"):
                rec.update({"status": "failed", "error": "service_shutdown",
                            "finished_at": time.time()})
                try:
                    await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
                except Exception:
                    pass
```

- [ ] **Step 2: Write `tests/test_async_jobmanager.py`**

Reuse `FakeRedis` (copy into this file or a shared `conftest.py`). A fake settings object + fake runner.
```python
import asyncio
import types
import pytest

from app.core.async_jobs import JobManager, JobStore, _JobCapacityExceeded, _JobsDisabled
from app.models.schemas import BatchItem, BatchCounts, DetectionResponse, DetectionMode
from tests.test_async_jobstore import FakeRedis


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=2, JOB_TTL_ACTIVE_S=7200,
                JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120, HEARTBEAT_INTERVAL_S=5,
                SHUTDOWN_GRACE_S=2)
    base.update(over)
    return types.SimpleNamespace(**base)


def _req(items, client_job_id=None):
    return types.SimpleNamespace(
        items=[BatchItem(url=u) for u in items], mode=DetectionMode.COMPLETE,
        proxy_url=None, use_nlp_detection=True, force_refresh=False,
        max_concurrency=10, homepage_fallback=True, client_job_id=client_job_id,
    )


async def _instant_runner(items, mode, opts, cb):
    cb(len(items))
    results = [DetectionResponse(ok=True, url=i.url, method="test") for i in items]
    return results, BatchCounts(success_count=len(items), failed_count=0, error_count=0)


@pytest.mark.asyncio
async def test_submit_completes_with_authoritative_counts():
    jm = JobManager(JobStore(None, client=FakeRedis()), _instant_runner, _settings())
    job_id, code = await jm.submit(_req(["https://a.fr", "https://b.fr"]))
    assert code == 202
    await asyncio.gather(*list(jm._job_tasks.values()))
    rec = await jm.get_record(job_id)
    assert rec["status"] == "completed" and rec["success_count"] == 2 and rec["done"] == 2


@pytest.mark.asyncio
async def test_idempotent_concurrent_submit_spawns_once():
    store = JobStore(None, client=FakeRedis())
    spawns = {"n": 0}
    async def counting_runner(items, mode, opts, cb):
        spawns["n"] += 1
        return await _instant_runner(items, mode, opts, cb)
    jm = JobManager(store, counting_runner, _settings())
    (id1, _), (id2, _) = await asyncio.gather(
        jm.submit(_req(["https://a.fr"], client_job_id="K")),
        jm.submit(_req(["https://a.fr"], client_job_id="K")),
    )
    assert id1 == id2
    await asyncio.gather(*list(jm._job_tasks.values()))
    assert spawns["n"] == 1


@pytest.mark.asyncio
async def test_capacity_rejected():
    async def slow_runner(items, mode, opts, cb):
        await asyncio.sleep(0.2)
        return await _instant_runner(items, mode, opts, cb)
    jm = JobManager(JobStore(None, client=FakeRedis()), slow_runner, _settings(MAX_ACTIVE_JOBS=1))
    await jm.submit(_req(["https://a.fr"]))
    with pytest.raises(_JobCapacityExceeded):
        await jm.submit(_req(["https://b.fr"]))
    await asyncio.gather(*list(jm._job_tasks.values()))


@pytest.mark.asyncio
async def test_disabled():
    jm = JobManager(JobStore(None, client=FakeRedis()), _instant_runner, _settings(ASYNC_JOBS_ENABLED=False))
    with pytest.raises(_JobsDisabled):
        await jm.submit(_req(["https://a.fr"]))


@pytest.mark.asyncio
async def test_shutdown_marks_running_failed():
    started = asyncio.Event()
    async def hang_runner(items, mode, opts, cb):
        started.set()
        await asyncio.sleep(60)
    jm = JobManager(JobStore(None, client=FakeRedis()), hang_runner, _settings())
    job_id, _ = await jm.submit(_req(["https://a.fr"]))
    await started.wait()
    await jm.shutdown()
    rec = await jm.get_record(job_id)
    assert rec["status"] == "failed" and rec["error"] == "service_shutdown"
```

- [ ] **Step 3: Run + commit**

Run: `python -m pytest apps-microservices/api-detection-langue-fr/tests/test_async_jobmanager.py -v` → 5 passed.
Commit: `feat(detection): JobManager async worker (idempotent submit, heartbeat, shutdown)`.

---

## Task 5: Async endpoints + lifespan wiring

**Goal:** Expose `POST /detect-batch-async` (202/200, differentiated 503) and `GET /detect-batch-async/{job_id}` (poll, computes stale); build `JobManager` in a FastAPI lifespan.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py` (add endpoints + imports)
- Modify: `apps-microservices/api-detection-langue-fr/main.py` (lifespan)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_async_endpoints.py`

**Acceptance Criteria:**
- [ ] Submit returns 202 + `job_id`; capacity 503 carries `Retry-After`; disabled/unavailable 503 has NO `Retry-After`.
- [ ] Poll returns 404 for unknown id, `completed` with `results` once done, `stale` for a frozen running record.
- [ ] `main.py` builds `app.state.job_manager` in lifespan and calls `shutdown()` on exit.

**Verify:** `cd "c:/Users/randr/Documents/Workspaces/RAG-HP-PUB" && python -m pytest apps-microservices/api-detection-langue-fr/tests/test_async_endpoints.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Add imports + endpoints to `app/api/routes.py`**

Extend imports:
```python
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from app.models.schemas import (
    AsyncBatchSubmitRequest, AsyncBatchSubmitResponse, AsyncBatchStatusResponse,
)
from app.core.async_jobs import (
    _JobsDisabled, _JobsUnavailable, _JobCapacityExceeded, poll_status,
)
```
Append endpoints (after `/detect-batch`):
```python
def _poll_hint() -> int:
    return min(max(settings.HEARTBEAT_INTERVAL_S, 5), settings.ASYNC_POLL_HINT_MAX_S)


@router.post("/detect-batch-async")
async def submit_batch_async(request: AsyncBatchSubmitRequest, http_request: Request):
    """Submit a batch for async processing. Returns 202 + job_id (or 200 if the
    client_job_id maps to an existing job). Poll GET /detect-batch-async/{job_id}."""
    jm = http_request.app.state.job_manager
    try:
        job_id, status_code = await jm.submit(request)
    except _JobsDisabled:
        # permanent: NO Retry-After → BO short-circuits
        raise HTTPException(status_code=503, detail={"detail": "Async jobs disabled", "retryable": False})
    except _JobsUnavailable:
        raise HTTPException(status_code=503, detail={"detail": "Job store unavailable", "retryable": False})
    except _JobCapacityExceeded:
        ra = str(settings.ASYNC_SUBMIT_RETRY_AFTER_S)
        raise HTTPException(
            status_code=503,
            detail={"detail": "Max active jobs reached", "retryable": True, "retry_after_seconds": int(ra)},
            headers={"Retry-After": ra},
        )
    body = AsyncBatchSubmitResponse(
        job_id=job_id, status="pending", total=len(request.items), poll_after_seconds=_poll_hint()
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


@router.get("/detect-batch-async/{job_id}", response_model=AsyncBatchStatusResponse)
async def poll_batch_async(job_id: str, http_request: Request) -> AsyncBatchStatusResponse:
    """Poll an async job. 404 if unknown/expired. Computes 'stale' on read."""
    jm = http_request.app.state.job_manager
    rec = await jm.get_record(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Unknown or expired job_id")
    status = poll_status(rec, time.time(), settings.STALE_THRESHOLD_S)
    results = rec.get("results") if status in ("completed", "failed", "stale") else None
    return AsyncBatchStatusResponse(
        job_id=rec["job_id"], status=status, total=rec["total"], done=rec.get("done", 0),
        success_count=rec.get("success_count", 0), failed_count=rec.get("failed_count", 0),
        error_count=rec.get("error_count", 0), results=results,
        processing_time_ms=None, error=rec.get("error"), poll_after_seconds=_poll_hint(),
    )
```

- [ ] **Step 2: Add lifespan to `main.py`**

Add imports + lifespan, and pass `lifespan=lifespan` to `FastAPI(...)`:
```python
from contextlib import asynccontextmanager
from app.core.config import settings as _settings
from app.core.async_jobs import JobStore, JobManager
from app.api.routes import router, _run_batch_core


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = JobStore(redis_url=_settings.REDIS_URL)
    app.state.job_manager = JobManager(store=store, batch_runner=_run_batch_core, settings=_settings)
    logger.info("Async JobManager initialised (lifespan startup)")
    yield
    await app.state.job_manager.shutdown()
    logger.info("Async JobManager shut down (lifespan shutdown)")
```
Change `app = FastAPI(...)` to include `lifespan=lifespan`. Remove the now-redundant `from app.api.routes import router` line at the top (it's imported in the lifespan import block — keep a single import; ensure `app.include_router(router, prefix="/api/v1")` still runs after `app` is defined).

> Circular-import note: `main → routes`, `main → async_jobs`, `routes → async_jobs`. `async_jobs` does NOT import `routes` (batch runner injected). `routes._fetch_with_admission` still lazily imports `_prod_admission` from `main`. No cycle at module load.

- [ ] **Step 3: Write `tests/test_async_endpoints.py`**

Inject a `JobManager` into `app.state` directly (bypasses lifespan — dependency-free).
```python
import asyncio
import types
import pytest
import httpx

from main import app
from app.core.async_jobs import JobManager, JobStore
from app.models.schemas import BatchCounts, DetectionResponse
from tests.test_async_jobstore import FakeRedis


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=2, JOB_TTL_ACTIVE_S=7200,
                JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120, HEARTBEAT_INTERVAL_S=5,
                SHUTDOWN_GRACE_S=2, ASYNC_SUBMIT_RETRY_AFTER_S=15, ASYNC_POLL_HINT_MAX_S=30)
    base.update(over)
    return types.SimpleNamespace(**base)


async def _runner(items, mode, opts, cb):
    cb(len(items))
    return ([DetectionResponse(ok=True, url=i.url, method="test") for i in items],
            BatchCounts(len(items), 0, 0))


@pytest.fixture
def client_with_jm(monkeypatch):
    jm = JobManager(JobStore(None, client=FakeRedis()), _runner, _settings())
    app.state.job_manager = jm
    # routes.py reads settings.* for thresholds — patch the values it uses
    import app.api.routes as routes
    monkeypatch.setattr(routes.settings, "STALE_THRESHOLD_S", 120, raising=False)
    monkeypatch.setattr(routes.settings, "HEARTBEAT_INTERVAL_S", 5, raising=False)
    monkeypatch.setattr(routes.settings, "ASYNC_POLL_HINT_MAX_S", 30, raising=False)
    monkeypatch.setattr(routes.settings, "ASYNC_SUBMIT_RETRY_AFTER_S", 15, raising=False)
    transport = httpx.ASGITransport(app=app)
    return jm, transport


@pytest.mark.asyncio
async def test_submit_then_poll_completed(client_with_jm):
    jm, transport = client_with_jm
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        await asyncio.gather(*list(jm._job_tasks.values()))
        p = await c.get(f"/api/v1/detect-batch-async/{job_id}")
        assert p.status_code == 200 and p.json()["status"] == "completed"
        assert p.json()["results"][0]["ok"] is True


@pytest.mark.asyncio
async def test_poll_unknown_404(client_with_jm):
    _, transport = client_with_jm
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.get("/api/v1/detect-batch-async/nope")).status_code == 404


@pytest.mark.asyncio
async def test_capacity_503_has_retry_after(monkeypatch):
    async def slow(items, mode, opts, cb):
        await asyncio.sleep(0.3); return ([], BatchCounts(0, 0, 0))
    jm = JobManager(JobStore(None, client=FakeRedis()), slow, _settings(MAX_ACTIVE_JOBS=1))
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://b.fr"}]})
        assert r.status_code == 503 and "retry-after" in {k.lower() for k in r.headers}
    await asyncio.gather(*list(jm._job_tasks.values()))


@pytest.mark.asyncio
async def test_disabled_503_no_retry_after():
    jm = JobManager(JobStore(None, client=FakeRedis()), _runner, _settings(ASYNC_JOBS_ENABLED=False))
    app.state.job_manager = jm
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/api/v1/detect-batch-async", json={"items": [{"url": "https://a.fr"}]})
        assert r.status_code == 503 and "retry-after" not in {k.lower() for k in r.headers}
```

- [ ] **Step 4: Run + commit**

Run: `python -m pytest apps-microservices/api-detection-langue-fr/tests/test_async_endpoints.py -v` → 4 passed.
Also run the full new-file set to confirm no cross-contamination:
`python -m pytest apps-microservices/api-detection-langue-fr/tests/test_async_schemas.py apps-microservices/api-detection-langue-fr/tests/test_batch_core_refactor.py apps-microservices/api-detection-langue-fr/tests/test_async_jobstore.py apps-microservices/api-detection-langue-fr/tests/test_async_jobmanager.py apps-microservices/api-detection-langue-fr/tests/test_async_endpoints.py -v`
Commit: `feat(detection): async batch endpoints + lifespan JobManager wiring`.
Then update the service `CLAUDE.md` (async endpoints table + env vars) in the same or a follow-up `docs:` commit.

---

## Task 6: BO `detectBatchUrlsAsync()` helper + constants

**Goal:** A BO helper that submits async, polls to terminal, and returns `['results', 'incomplete_urls', 'job_id', 'final_status']` with correct by-url+by-domain correlation. The discriminator for a retryable vs permanent 503 is the **`Retry-After` header presence** (BO's `call_api_hellopro` collapses the body to `message`, so the body `retryable` flag is not readable here).

**Files:**
- Modify: `BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php` (add constants after line 8509; add `_detection_absent_urls()` + `detectBatchUrlsAsync()` after `_log_detect_batch_duration()` ~line 8666)
- Create: `BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_smoke_detection_async_rindra_BO.php`

**Acceptance Criteria:**
- [ ] `_detection_absent_urls()` excludes a submitted URL that matches a result by base domain (alt-link FR success) — not flagged incomplete.
- [ ] `detectBatchUrlsAsync()` returns the 4-key shape; `completed` → `incomplete_urls=[]`.
- [ ] A 503 with no `Retry-After` throws immediately (no retry budget burn); a 503 with `Retry-After` retries.

**Verify:** `php "C:/Users/randr/Documents/Workspaces/Hellopro/BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_smoke_detection_async_rindra_BO.php"` → prints `ABSENT_URLS: ALL PASS` (pure-function asserts). The live-service smoke section runs only in the BO environment.

**Steps:**

- [ ] **Step 1: Add async constants** (after line 8509, the `DETECTION_TRANSIENT_CODES` const)

```php
// ─── async job API caller contract (POST /detect-batch-async + GET poll) ──
const DETECTION_ASYNC_SUBMIT_TIMEOUT_S = 30;   // submit is near-instant
const DETECTION_ASYNC_POLL_TIMEOUT_S   = 15;   // each poll is tiny
const DETECTION_ASYNC_MAX_WAIT_S       = 1800; // per-job wall-clock budget (30 min) — must be < JOB_RESULT_TTL_S server-side
const DETECTION_ASYNC_POLL_MIN_S       = 5;    // floor on the server poll hint
const DETECTION_ASYNC_BATCH_SIZE       = 100;  // chunk size for async callers
```

- [ ] **Step 2: Add the pure correlation helper** (after `_log_detect_batch_duration`)

```php
/**
 * URLs soumises ENTIÈREMENT absentes des résultats (à ré-enfiler).
 * Une URL soumise est "présente" si un résultat la matche par url trimée OU
 * par domaine de base (l'API peut renvoyer une URL alternative/redirigée en
 * cas de succès FR). Mirror de l'indexation de script_retry_identifier_site_fr.
 *
 * @param array $submitted_urls URLs soumises (verbatim)
 * @param array $results        résultats detect (['url'=>..., 'ok'=>...])
 * @return array URLs soumises absentes (verbatim, dédupliquées)
 */
function _detection_absent_urls(array $submitted_urls, array $results): array
{
    $by_url = [];
    $by_domain = [];
    foreach ($results as $r) {
        if (empty($r['url'])) continue;
        $by_url[trim(trim($r['url']), "/")] = true;
        $dom = recupere_domaine($r['url']);
        if ($dom && !isset($by_domain[$dom])) {
            $by_domain[$dom] = true; // keep-first sur collision de domaine
        }
    }
    $absent = [];
    $seen = [];
    foreach ($submitted_urls as $u) {
        if (isset($seen[$u])) continue;
        $seen[$u] = true;
        $key = trim(trim($u), "/");
        $dom = recupere_domaine($u);
        $present = isset($by_url[$key]) || ($dom && isset($by_domain[$dom]));
        if (!$present) $absent[] = $u;
    }
    return $absent;
}
```

- [ ] **Step 3: Add `detectBatchUrlsAsync()`**

```php
/**
 * Variante asynchrone de detectBatchUrls : submit → poll → résultats.
 * Découple le BO du plafond 180s synchrone. Voir spec RAG-HP-PUB
 * 2026-06-01-detection-langue-fr-async-job-api-design.md.
 *
 * @return array{results: array, incomplete_urls: array, job_id: ?string, final_status: string}
 * @throws DetectionApiException|DetectionApiBackpressureException si le submit échoue
 */
function detectBatchUrlsAsync(
    array $items, int $maxConcurrency = 10, string $mode = 'complete',
    bool $force_redetect = false, ?string $client_job_id = null
): ?array {
    $items = sanitizeUtf8Recursive($items);
    $submitted_urls = [];
    foreach ($items as $it) {
        if (!empty($it['url'])) $submitted_urls[] = $it['url'];
    }
    $submitted_urls = array_values(array_unique($submitted_urls));

    $payload = [
        'items'           => $items,
        'max_concurrency' => $maxConcurrency,
        'mode'            => $mode,
        'force_refresh'   => $force_redetect,
    ];
    if ($client_job_id !== null) $payload['client_job_id'] = $client_job_id;

    // ── Submit (retry 503 avec Retry-After / codes transitoires ; permanent 503 = pas de Retry-After → throw) ──
    $job_id = null;
    for ($attempt = 0; $attempt <= DETECTION_MAX_RETRIES; $attempt++) {
        $headers = [];
        $res = call_api_hellopro(
            'POST', 'detection_site_fr-service', '/api/v1/detect-batch-async',
            $payload, false, DETECTION_ASYNC_SUBMIT_TIMEOUT_S, $headers, DETECTION_CONNECT_TIMEOUT_S
        );
        $isError = is_array($res) && isset($res['success']) && $res['success'] === false;
        if (!$isError) {
            $job_id = $res['job_id'] ?? null;
            break;
        }
        $httpCode = (int) ($res['http_code'] ?? 0);

        if ($httpCode === 503) {
            $retryAfterRaw = $headers['retry-after'] ?? null;
            if ($retryAfterRaw === null) {
                // kill-switch / Redis down → permanent, ne pas brûler le budget retry
                throw new DetectionApiException(
                    "detect-batch-async submit indisponible (503 sans Retry-After): " . ($res['message'] ?? 'unknown')
                );
            }
            if ($attempt >= DETECTION_MAX_RETRIES) {
                throw new DetectionApiBackpressureException(
                    "detect-batch-async submit backpressure: 503 après " . (DETECTION_MAX_RETRIES + 1) . " tentatives"
                );
            }
            $retryAfter = is_numeric($retryAfterRaw) ? max(0.0, (float) $retryAfterRaw) : null;
            $waitS = $retryAfter ?? (DETECTION_BACKOFF_BASE_S * (2 ** $attempt));
            usleep((int) ($waitS * 1_000_000));
            continue;
        }
        if (in_array($httpCode, DETECTION_TRANSIENT_CODES, true)) {
            if ($attempt >= DETECTION_MAX_RETRIES) {
                throw new DetectionApiException("detect-batch-async submit échec: HTTP {$httpCode}");
            }
            usleep((int) ((DETECTION_BACKOFF_BASE_S * (2 ** $attempt)) * 1_000_000));
            continue;
        }
        throw new DetectionApiException(
            "detect-batch-async submit échec: HTTP {$httpCode}: " . ($res['message'] ?? 'unknown')
        );
    }
    if ($job_id === null) {
        throw new DetectionApiException("detect-batch-async: aucun job_id retourné");
    }

    // ── Poll jusqu'à statut terminal ou budget épuisé ──
    $deadline     = microtime(true) + DETECTION_ASYNC_MAX_WAIT_S;
    $final_status = 'timeout';
    $results      = [];
    while (microtime(true) < $deadline) {
        $headers = [];
        $poll = call_api_hellopro(
            'GET', 'detection_site_fr-service',
            '/api/v1/detect-batch-async/' . rawurlencode($job_id),
            [], false, DETECTION_ASYNC_POLL_TIMEOUT_S, $headers, DETECTION_CONNECT_TIMEOUT_S
        );
        $isError = is_array($poll) && isset($poll['success']) && $poll['success'] === false;
        if ($isError) {
            $code = (int) ($poll['http_code'] ?? 0);
            if ($code === 404) { $final_status = 'stale'; break; }   // expiré/inconnu → stale
            if ($code === 503) {
                $ra = $headers['retry-after'] ?? null;
                $wait = ($ra !== null && is_numeric($ra)) ? (float) $ra : DETECTION_BACKOFF_BASE_S;
                $remaining = $deadline - microtime(true);
                if ($remaining <= 0) break;
                usleep((int) (min($wait, $remaining) * 1_000_000));
                continue;
            }
            // erreur transport transitoire sur le poll → courte pause, on continue
            usleep((int) (DETECTION_ASYNC_POLL_MIN_S * 1_000_000));
            continue;
        }

        $status = $poll['status'] ?? 'running';
        if (in_array($status, ['completed', 'failed', 'stale'], true)) {
            $final_status = $status;
            $results = (isset($poll['results']) && is_array($poll['results'])) ? $poll['results'] : [];
            break;
        }
        // pending/running → dormir l'indice serveur, clampé au budget restant
        $hint      = (int) ($poll['poll_after_seconds'] ?? DETECTION_ASYNC_POLL_MIN_S);
        $sleep     = max($hint, DETECTION_ASYNC_POLL_MIN_S);
        $remaining = $deadline - microtime(true);
        if ($remaining <= 0) break;
        usleep((int) (min($sleep, $remaining) * 1_000_000));
    }

    $incomplete = ($final_status === 'completed')
        ? []
        : _detection_absent_urls($submitted_urls, $results);

    return [
        'results'         => $results,
        'incomplete_urls' => $incomplete,
        'job_id'          => $job_id,
        'final_status'    => $final_status,
    ];
}
```

- [ ] **Step 4: Create the smoke + pure-assert script**

`pct_smoke_detection_async_rindra_BO.php`:
```php
<?php
header('Content-Type: text/plain; charset=UTF-8');
require_once($_SERVER["DOCUMENT_ROOT"] . "include/connexion.php");
require_once($_SERVER['DOCUMENT_ROOT'] . "no_read_access/connexion_bdd_hellopro_ia.php");
require_once($_SERVER["DOCUMENT_ROOT"] . "fonctions/fonctions_generales.php");
require_once($_SERVER["DOCUMENT_ROOT"] . "fonctions/fonctions_hellopro.php");
require_once($_SERVER["DOCUMENT_ROOT"] . "admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_scrapping.php");

// ── 1) Pure-function asserts for _detection_absent_urls (no network) ──
$fail = 0;
$check = function ($label, $got, $want) use (&$fail) {
    $ok = (json_encode($got) === json_encode($want));
    if (!$ok) { $fail++; echo "FAIL $label got=" . json_encode($got) . " want=" . json_encode($want) . "\n"; }
};
// alt-url FR success: submitted /x, result returns /fr/ on same domain → present (NOT absent)
$check('alt_domain_match',
    _detection_absent_urls(['https://a.fr/x'], [['url' => 'https://a.fr/fr/', 'ok' => true]]),
    []);
// genuinely absent URL is flagged
$check('absent_flagged',
    _detection_absent_urls(['https://a.fr/x', 'https://b.fr'], [['url' => 'https://a.fr/x', 'ok' => false]]),
    ['https://b.fr']);
// present-but-non-ok is NOT absent
$check('present_nonok_not_absent',
    _detection_absent_urls(['https://a.fr'], [['url' => 'https://a.fr', 'ok' => false, 'method' => 'fetch_failed']]),
    []);
echo $fail === 0 ? "ABSENT_URLS: ALL PASS\n" : "ABSENT_URLS: $fail FAIL\n";

// ── 2) Live smoke (BO env only — hits the deployed service) ──
if (getenv('RUN_LIVE_SMOKE') === '1') {
    $res = detectBatchUrlsAsync([['url' => 'https://www.lemonde.fr']], 1, 'complete', false, sha1('smoke:async:' . date('Ymd')));
    echo "LIVE final_status=" . $res['final_status']
        . " results=" . count($res['results'])
        . " incomplete=" . count($res['incomplete_urls']) . "\n";
}
```

- [ ] **Step 5: Run + commit**

Run: `php "C:/Users/randr/Documents/Workspaces/Hellopro/BO/admin/repertoire_test/moulinettes_rindra/script_divers/ponctuel/roadmap_v1/pct_smoke_detection_async_rindra_BO.php"`
Expected (pure asserts; the require_once for DB may warn locally — if PHP/DB is unavailable on the dev box, the operator runs this in the BO environment): `ABSENT_URLS: ALL PASS`.
Commit (in Hellopro repo): `feat(detection): detectBatchUrlsAsync submit+poll helper + correlation`.

---

## Task 7: Migrate `script_identifier_site_fr_v2.php` to async

**Goal:** Switch the per-upload identifier to `detectBatchUrlsAsync` with chunk 100, and re-enqueue never-finished URLs.

**Files:**
- Modify: `BO/script/chatgpt/variante_categorie/script_identifier_site_fr_v2.php:16-80,193-202`

**Acceptance Criteria:**
- [ ] Chunk size = `DETECTION_ASYNC_BATCH_SIZE`; call uses `sha1($id_upload.':'.$chunk_idx)`.
- [ ] Per-chunk `incomplete_urls` re-enqueued (`nb_tentatives=1`), counted in `$nb_incomplete`, surfaced in the email.
- [ ] Existing per-result upsert + admission_rejected handling unchanged.

**Verify:** `php -l "C:/Users/randr/Documents/Workspaces/Hellopro/BO/script/chatgpt/variante_categorie/script_identifier_site_fr_v2.php"` → `No syntax errors detected`. Functional verification = operator smoke per spec §8.5.

**Steps:**

- [ ] **Step 1: Add `$nb_incomplete` init + chunk size + indexed loop**

Replace lines 19–25:
```php
    $nb_total = count($tab_siteweb);
    $nb_succes = 0;
    $nb_retry  = 0;
    $nb_incomplete = 0;

    $tab_siteweb = array_chunk($tab_siteweb, DETECTION_ASYNC_BATCH_SIZE);

    foreach($tab_siteweb as $chunk_idx => $payload_siteweb) {
```

- [ ] **Step 2: Swap the call to async**

Replace line 27 `$res = detectBatchUrls($payload_siteweb);` with:
```php
            $res = detectBatchUrlsAsync(
                $payload_siteweb, 10, 'complete', false,
                sha1($id_upload . ':' . $chunk_idx)
            );
```

- [ ] **Step 3: Re-enqueue incomplete URLs (per chunk, after the inner result loop)**

After the inner `foreach($tab_res as $res_check) { ... }` closes (current line 53) and BEFORE the `} catch(Exception $e) {` (line 54), insert:
```php
            // URLs jamais traitées (stale/failed/timeout côté service) → file de retry.
            // nb_tentatives=1 : un round échoué côté client (pas la faute de l'URL).
            foreach (($res['incomplete_urls'] ?? []) as $u) {
                enfiler_url_retry_fr($u, (int) $id_upload, $res['final_status'] ?? 'incomplete', 1);
                $nb_incomplete++;
            }
```

- [ ] **Step 4: Surface `$nb_incomplete` in the return + email**

Replace the return (lines 75–79):
```php
    return [
        'nb_total'      => $nb_total,
        'nb_succes'     => $nb_succes,
        'nb_retry'      => $nb_retry,
        'nb_incomplete' => $nb_incomplete,
    ];
```
After line 198 (the `nb_retry` email line), add:
```php
    $messages .= "- URLs jamais finalisées (service redémarré/saturé) ré-enfilées : {$stats_identification['nb_incomplete']}<br>";
```
And extend the final `HpLogger::LogInformation` (lines 161–165) to include `, incomplete={$stats_identification['nb_incomplete']}`.

- [ ] **Step 5: Lint + commit**

Run: `php -l ".../script_identifier_site_fr_v2.php"` → `No syntax errors detected`.
Commit (Hellopro): `feat(detection): migrate script_identifier_site_fr_v2 to async detect`.

---

## Task 8: Migrate `script_retry_identifier_site_fr.php` to async

**Goal:** Switch the cron retry to `detectBatchUrlsAsync` with chunk 100; treat never-finished URLs as touch-only (no `nb_tentatives` burn); initialize the counters.

**Files:**
- Modify: `BO/script/chatgpt/variante_categorie/script_retry_identifier_site_fr.php:33,124-243,265-277`

**Acceptance Criteria:**
- [ ] `RETRY_BATCH_SIZE = 100`; call uses `sha1('retry:'.$id_upload.':'.$batch_idx)`.
- [ ] A URL in `incomplete_urls` is touch-only (date updated, `nb_tentatives` unchanged) — NOT `marquer_echec_retry`.
- [ ] `$nb_admission_rejected` and `$nb_incomplete` are initialized; both surfaced in the email.

**Verify:** `php -l "C:/Users/randr/Documents/Workspaces/Hellopro/BO/script/chatgpt/variante_categorie/script_retry_identifier_site_fr.php"` → `No syntax errors detected`. Functional verification = one cron cycle per spec §8.5.

**Steps:**

- [ ] **Step 1: Bump batch size**

Line 33: `const RETRY_BATCH_SIZE = 5;` → `const RETRY_BATCH_SIZE = 100;` (update the inline comment to "réduit pour async: 100").

- [ ] **Step 2: Initialize counters**

Replace lines 125–128:
```php
$nb_traite            = 0;
$nb_abandonne         = 0;
$nb_re_echec          = 0;
$nb_admission_rejected = 0;   // était implicitement null → init explicite
$nb_incomplete         = 0;
$succes_par_upload    = [];
```

- [ ] **Step 3: Swap the call + build the incomplete set**

Replace line 144 `$res = detectBatchUrls($payload_siteweb);` with:
```php
            $res = detectBatchUrlsAsync(
                $payload_siteweb, 10, 'complete', false,
                sha1('retry:' . $id_upload . ':' . $batch_idx)
            );
```
After line 145 (`$tab_res = $res['results'];`), add the normalized incomplete set:
```php
            // Ensemble des URLs jamais finalisées (clé normalisée comme $results_by_url)
            $incomplete_set = [];
            foreach (($res['incomplete_urls'] ?? []) as $u) {
                $incomplete_set[trim(trim($u), "/")] = true;
            }
```

- [ ] **Step 4: Split the `r_match === null` branch into touch-only vs genuine-echec**

Replace the `else { ... }` block (lines 199–208) with:
```php
                } else {
                    $key = trim(trim($lig['url_dfr_retry']), "/");
                    if (isset($incomplete_set[$key])) {
                        // Job stale/failed/timeout (service redémarré/saturé) :
                        // touch-only, NE PAS brûler une tentative. Re-piqué au prochain tick.
                        HpLogger::LogInformation(
                            $handle_log,
                            "Upload $id_upload — URL " . $lig['url_dfr_retry']
                            . " → incomplète ({$res['final_status']}), row laissée en pending (nb_tentatives non incrémenté)"
                        );
                        $sql_touch = "
                            UPDATE domaine_fr_retry
                            SET date_derniere_tentative_dfr_retry = NOW()
                            WHERE id_dfr_retry = '" . hellopro_traitement_donnee_annuaire_bo($id_dfr_retry) . "'
                        ";
                        mysqli_query($GLOBALS['LINK_MYSQLI_HELLOPRO_IA'], $sql_touch)
                            or die(hellopro_mysql_error($sql_touch, $GLOBALS['LINK_MYSQLI_HELLOPRO_IA']));
                        $nb_incomplete++;
                    } else {
                        // L'API a répondu mais sans résultat exploitable pour cette URL
                        $abandon = marquer_echec_retry(
                            $id_dfr_retry,
                            $nb_tent_avant,
                            "Aucun résultat retourné par detect-batch pour l'URL"
                        );
                        $nb_re_echec++;
                        if ($abandon) $nb_abandonne++;
                    }
                }
```

- [ ] **Step 5: Surface `$nb_incomplete` in the final log + email**

Extend the final `HpLogger::LogInformation` (lines 239–243) to append `, incomplete=$nb_incomplete`.
After line 271 (the `admission_rejected` email line), add:
```php
$messages .= "- URLs jamais finalisées (service redémarré) re-piquées sans brûler de tentative : $nb_incomplete<br>";
```

- [ ] **Step 6: Lint + commit**

Run: `php -l ".../script_retry_identifier_site_fr.php"` → `No syntax errors detected`.
Commit (Hellopro): `feat(detection): migrate retry cron to async detect (incomplete = touch-only)`.

---

## Self-Review (completed by plan author)

- **Spec coverage:** §4.1 endpoints → T5; §4.3 JobStore/TTL → T3; §4.4 JobManager (race-free submit, heartbeat, shutdown) → T4; §4.5 `_run_batch_core` refactor → T2; §4.6 dedup predicate (atomic, exists-any-status) → T4; §4.7 stale → T3 `poll_status` + T5 wiring; §4.8 lifespan → T5; §4.9 metrics + poll hint → T1/T5; §4.10 config → T1; §4.11 shared pool (async fetches reuse prod admission via `_detect_single_url`→`_fetch_with_admission`, endpoint label folds into `/api/v1/detect`) → inherent in T2/T4 (no code change needed, documented); §5.1 helper + correlation → T6; §5.2 constants + invariant → T6; §5.3 migrations → T7/T8; §5.4 client_job_id → T6/T7/T8; §6 failure contract → T6 poll loop. All covered.
- **Refinement vs spec:** (a) 503 retryable discriminator is the `Retry-After` header (BO `call_api_hellopro` discards the body flag) — noted in T6. (b) Retry-cron incomplete handling is folded into the existing `r_match===null` branch (not a separate post-loop) to avoid double-handling with `marquer_echec_retry` — noted in T8. Both are faithful to spec intent.
- **Type consistency:** `BatchOpts`/`BatchCounts` defined in schemas (T1), consumed by `_run_batch_core` (T2) and `JobManager` (T4). `poll_status` defined T3, used T5. `_detection_absent_urls` defined + used T6, referenced T7/T8. `JobManager.get_record` used by T5. Consistent.
- **Placeholder scan:** the `_run_batch_core` body-move (T2 Step 4) is the only "move verbatim" instruction — it provides the exact substitution table + both new returns + the changed `_increment_count` + a characterization test guard, which is complete for a mechanical move.
