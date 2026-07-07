# content-extractor-api-service — Async + Cache + Sync Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the single-worker event-loop-blocking constraint, add Redis result-caching + batched async submit→poll endpoints, and add sync admission control to `content-extractor-api-service`, so it serves the future 7-replica crawler without the 30 s gateway timeout.

**Architecture:** Two axes. **Axis 1** (Phase 1a): move the CPU-bound boilerpy3/`HeaderFooterExtractor` work off the event loop via `asyncio.to_thread` and run multiple uvicorn worker processes (GIL → processes give parallelism). **Axis 2**: a hybrid request shape — hardened sync endpoints (unchanged contract, +cache, +admission 503) plus batched async endpoints (`/clean-async`, `/extract/header-footer-async` → `GET /jobs/{job_id}`), backed by a Redis job store and a versioned content-hash result cache. Reuses three in-repo templates verbatim-with-edits: `api-detection-langue-fr` async job subsystem, `image-comparison-service` feature-cache + slot model, `common-utils` `cache_service`.

**Tech Stack:** Python 3.10, FastAPI + Uvicorn, boilerpy3, BeautifulSoup (`HeaderFooterExtractor` in `libs/common-utils`), Redis via `common_utils.redis.cache_service`, prometheus_client, pytest.

**Spec:** `docs/superpowers/specs/2026-06-20-content-extractor-async-cache-design.md`

**Repo conventions / gotchas baked into this plan:**
- All paths below are relative to repo root `C:\Users\randr\Documents\Workspaces\RAG-HP-PUB`.
- Run tests from the service dir: `cd apps-microservices/content-extractor-api-service && python -m pytest tests/<file> -v`.
- **tdd-gate hook:** editing a production `.py` file requires a test file whose stem matches (`extractor_core.py` → `test_extractor_core.py`). `config.*` is gate-exempt. Each task creates/extends the matching test FIRST.
- **pydantic-core env drift:** if pytest collection fails with `SystemError`, run `python -m pip install "pydantic-core==2.46.4"` (global Python312) before retrying.
- Do **not** run the whole suite (`tests/test_api.py`/`test_domain_fr.py` are pre-existing broken in OTHER services; not here, but keep targeted).
- Async unit tests use `asyncio.run(...)` inside sync test functions — **no `pytest-asyncio` dependency required.**

---

## File Structure

```
apps-microservices/content-extractor-api-service/
  main.py                         # MOD: lifespan (redis pool + JobManager), include async router
  Dockerfile                      # MOD: --workers ${UVICORN_WORKERS}
  requirements.txt                # MOD: + redis, + (test) nothing new
  app/
    core/
      config.py                   # MOD: + all new settings
      metrics.py                  # MOD: + cache/admission/async metrics
      extractor_core.py           # NEW: pure sync clean_core + header_footer_core
      result_cache.py             # NEW: versioned content-hash cache (guarded, graceful-degrade)
      extractor_service.py        # NEW: async run_clean / run_header_footer / run_batch
      admission.py                # NEW: sync inflight guard
      async_jobs.py               # NEW: JobStore + JobManager + poll_status
    routers/
      clean.py                    # MOD: call extractor_service + admission
      extract.py                  # MOD: call extractor_service + admission
      async_jobs.py               # NEW: /clean-async, /extract/header-footer-async, /jobs/{id}
    schemas/
      async_jobs.py               # NEW: item + submit + status schemas
  tests/
    test_extractor_core.py        # NEW
    test_extractor_service.py     # NEW
    test_result_cache.py          # NEW
    test_admission.py             # NEW
    test_async_jobs.py            # NEW (core + router)
    test_main.py                  # NEW (lifespan smoke)
    test_clean.py                 # MOD (extend)
    test_extract.py               # MOD (extend)

apps-microservices/api-gateway/
  app/core/settings.py            # MOD: DOWNSTREAM_TIMEOUTS_S["extractor-service"]
  tests/test_settings.py          # NEW/MOD
```

---

## Phase 1a — Pure timeout fix (NO Redis)

### Task 0: Extend `config.py` with all new settings

**Goal:** Add every new env-driven setting in one place so later tasks never re-edit config.

**Files:**
- Modify: `apps-microservices/content-extractor-api-service/app/core/config.py`
- Test: `apps-microservices/content-extractor-api-service/tests/test_config.py` (new)

**Acceptance Criteria:**
- [ ] `Settings` exposes the new fields with the spec defaults.
- [ ] Existing fields unchanged.
- [ ] `python -c "from app.core.config import settings; print(settings.MAX_ACTIVE_JOBS)"` prints `8`.

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_config.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write the test** — `tests/test_config.py`

```python
from app.core.config import settings


def test_existing_defaults_unchanged():
    assert settings.PORT == 8600
    assert settings.MAX_PAYLOAD_SIZE_MB == 10


def test_new_defaults():
    assert settings.UVICORN_WORKERS == 2
    assert settings.REDIS_URL.startswith("redis://")
    assert settings.RESULT_CACHE_ENABLED is True
    assert settings.RESULT_CACHE_TTL_S == 86400
    assert settings.RESULT_CACHE_VERSION == "v1"
    assert settings.SYNC_MAX_INFLIGHT == 0
    assert settings.ASYNC_JOBS_ENABLED is True
    assert settings.MAX_ACTIVE_JOBS == 8
    assert settings.DEFAULT_MAX_CONCURRENCY == 4
    assert settings.JOB_TTL_ACTIVE_S == 7200
    assert settings.JOB_RESULT_TTL_S == 3600
    assert settings.STALE_THRESHOLD_S == 120
    assert settings.HEARTBEAT_INTERVAL_S == 5
    assert settings.ASYNC_SUBMIT_RETRY_AFTER_S == 15
    assert settings.ASYNC_POLL_HINT_MAX_S == 30
    assert settings.SHUTDOWN_GRACE_S == 5
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: ... UVICORN_WORKERS`).

- [ ] **Step 3: Replace `config.py` with:**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "Content Extractor API"
    APP_VERSION: str = "1.0.0"
    PORT: int = 8600
    LOG_LEVEL: str = "info"
    MAX_PAYLOAD_SIZE_MB: int = 10

    # --- Axis 1: workers (GIL -> processes give CPU parallelism, not threads) ---
    UVICORN_WORKERS: int = 2

    # --- Redis (job store + result cache). cache_service.init_redis_pool() reads
    # REDIS_URL from the environment itself; this mirrors it for documentation. ---
    REDIS_URL: str = "redis://redis:6379"

    # --- Result cache ---
    RESULT_CACHE_ENABLED: bool = True
    RESULT_CACHE_TTL_S: int = 86400          # 24h (HTML drifts; crawler re-crawls)
    RESULT_CACHE_VERSION: str = "v1"         # bump on extractor/boilerpy3 algo change

    # --- Sync admission (0 = disabled, always admit) ---
    SYNC_MAX_INFLIGHT: int = 0

    # --- Async job API ---
    ASYNC_JOBS_ENABLED: bool = True
    MAX_ACTIVE_JOBS: int = 8                 # per-worker in-flight async jobs
    DEFAULT_MAX_CONCURRENCY: int = 4         # per-job item concurrency (NEW; CPU-bound)
    JOB_TTL_ACTIVE_S: int = 7200
    JOB_RESULT_TTL_S: int = 3600
    STALE_THRESHOLD_S: int = 120
    HEARTBEAT_INTERVAL_S: int = 5
    ASYNC_SUBMIT_RETRY_AFTER_S: int = 15
    ASYNC_POLL_HINT_MAX_S: int = 30
    SHUTDOWN_GRACE_S: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/content-extractor-api-service/app/core/config.py apps-microservices/content-extractor-api-service/tests/test_config.py
git commit -F .git/EXTRACTOR_TASK_MSG.txt   # (message authored by the executor; see commit note)
```

> **Commit note (applies to every task):** the executor writes the bilingual message to `.git/EXTRACTOR_TASK_MSG.txt` via the Write tool (UTF-8), then `git -c commit.encoding=utf-8 commit -F .git/EXTRACTOR_TASK_MSG.txt`, and `git add` only the explicit files for that task (never `-A`). This avoids the documented concurrent-session `COMMIT_EDITMSG` race + Windows cp1252 mangling.

---

### Task 1: `extractor_core.py` — pure synchronous cores

**Goal:** Extract the boilerpy3 + `HeaderFooterExtractor` logic out of the routers into pure, sync, side-effect-free functions producing the exact response-body dicts the current handlers return.

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/core/extractor_core.py`
- Test: `apps-microservices/content-extractor-api-service/tests/test_extractor_core.py`

**Acceptance Criteria:**
- [ ] `clean_core(html, OutputFormat.TEXT)` returns the same string as `DefaultExtractor().get_content(html)`.
- [ ] `clean_core(html, OutputFormat.HTML)` returns the same string as `KeepEverythingExtractor().get_marked_html(html)`.
- [ ] `header_footer_core(main, refs, debug=False)` returns a dict with keys `header, footer, header_method, footer_method`.
- [ ] `header_footer_core(main, refs, debug=True)` additionally returns `strategies, intersections_class, intersections_structural, cleaned_htmls, gap_analysis`.

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_extractor_core.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write the test** — `tests/test_extractor_core.py`

```python
from boilerpy3 import extractors as Bpy

from app.core import extractor_core
from app.schemas.clean import OutputFormat

MAIN = "<html><body><header>Nav Home About</header><main>Real article body here.</main><footer>Copyright 2026 Contact</footer></body></html>"
REF1 = "<html><body><header>Nav Home About</header><main>Another page entirely.</main><footer>Copyright 2026 Contact</footer></body></html>"
REF2 = "<html><body><header>Nav Home About</header><main>Third distinct page.</main><footer>Copyright 2026 Contact</footer></body></html>"


def test_clean_core_text_matches_boilerpy():
    expected = Bpy.DefaultExtractor().get_content(MAIN)
    assert extractor_core.clean_core(MAIN, OutputFormat.TEXT) == expected


def test_clean_core_html_matches_boilerpy():
    expected = Bpy.KeepEverythingExtractor().get_marked_html(MAIN)
    assert extractor_core.clean_core(MAIN, OutputFormat.HTML) == expected


def test_header_footer_core_basic_keys():
    body = extractor_core.header_footer_core(MAIN, [REF1, REF2], debug=False)
    assert set(body) == {"header", "footer", "header_method", "footer_method"}


def test_header_footer_core_debug_keys():
    body = extractor_core.header_footer_core(MAIN, [REF1, REF2], debug=True)
    for k in ("strategies", "intersections_class", "intersections_structural",
              "cleaned_htmls", "gap_analysis", "header_method", "footer_method"):
        assert k in body
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: app.core.extractor_core`).

- [ ] **Step 3: Create `app/core/extractor_core.py`:**

```python
"""Pure, synchronous extraction cores shared by the sync routers and the async
batch worker. No I/O, no async — callers offload these via asyncio.to_thread so
the event loop stays free. Behaviour is byte-for-byte identical to the former
inline router bodies (see app/routers/clean.py, app/routers/extract.py pre-refactor)."""
import logging

from boilerpy3 import extractors as BoilerpyExtractor
from common_utils.extractor.HeaderFooterExtractor import HeaderFooterExtractor

from app.schemas.clean import OutputFormat

logger = logging.getLogger(__name__)


def clean_core(html: str, fmt: OutputFormat) -> str:
    """Remove boilerplate. Marked HTML for fmt=HTML, plain text for fmt=TEXT."""
    if fmt == OutputFormat.HTML:
        return BoilerpyExtractor.KeepEverythingExtractor().get_marked_html(html)
    return BoilerpyExtractor.DefaultExtractor().get_content(html)


def header_footer_core(main_html: str, reference_htmls: list[str], debug: bool) -> dict:
    """Multi-strategy header/footer extraction. Returns the response BODY dict
    (ExtractResponse fields; plus the debug fields when debug=True)."""
    extractor = HeaderFooterExtractor(main_html)

    if debug:
        result = extractor.extract_all_debug(reference_htmls)
        header_method = result.get("header_method_used", "none")
        footer_method = result.get("footer_method_used", "none")
        return {
            "header": result.get("header_selected", ""),
            "footer": result.get("footer_selected", ""),
            "header_method": header_method,
            "footer_method": footer_method,
            "strategies": {
                "original": {
                    "header": result.get("header_old", ""),
                    "footer": result.get("footer_old", ""),
                },
                "class_intersection": {
                    "header": result.get("header_class", ""),
                    "footer": result.get("footer_class", ""),
                },
                "structural_intersection": {
                    "header": result.get("header_structural", ""),
                    "footer": result.get("footer_structural", ""),
                },
            },
            "intersections_class": result.get("intersections_class", []),
            "intersections_structural": result.get("intersections_structural", []),
            "cleaned_htmls": {
                k: v for k, v in result.items() if k.startswith("cleaned_html_")
            },
            "gap_analysis": result.get("gap_analysis", []),
        }

    result = extractor.extract_with_fallback(reference_htmls)
    return {
        "header": result.get("header", ""),
        "footer": result.get("footer", ""),
        "header_method": result.get("header_method", "none"),
        "footer_method": result.get("footer_method", "none"),
    }
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit** (`feat(content-extractor): pure sync extraction cores`).

---

### Task 2: `extractor_service.py` (offload only) + router refactor + Dockerfile workers

**Goal:** Introduce the async orchestration layer that offloads the cores to a thread (no cache yet), point both sync routers at it, and run multiple uvicorn workers. This is the change that removes the `0 bytes / 30 s` timeout.

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/core/extractor_service.py`
- Modify: `apps-microservices/content-extractor-api-service/app/routers/clean.py`
- Modify: `apps-microservices/content-extractor-api-service/app/routers/extract.py`
- Modify: `apps-microservices/content-extractor-api-service/Dockerfile`
- Test: extend `tests/test_clean.py`, `tests/test_extract.py`; new `tests/test_extractor_service.py`

**Acceptance Criteria:**
- [ ] `/clean` and `/extract/header-footer` return identical responses to before.
- [ ] Handlers no longer call boilerpy3/`HeaderFooterExtractor` directly — they call `extractor_service`.
- [ ] `extractor_service.run_clean` / `run_header_footer` offload via `asyncio.to_thread`.
- [ ] Dockerfile CMD runs `--workers ${UVICORN_WORKERS:-2}`.

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_extractor_service.py tests/test_clean.py tests/test_extract.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write the test** — `tests/test_extractor_service.py`

```python
import asyncio

from app.core import extractor_service
from app.schemas.clean import OutputFormat

MAIN = "<html><body><header>Nav</header><main>Body text here.</main><footer>Footer</footer></body></html>"
REF1 = "<html><body><header>Nav</header><main>Other.</main><footer>Footer</footer></body></html>"
REF2 = "<html><body><header>Nav</header><main>Third.</main><footer>Footer</footer></body></html>"


def test_run_clean_returns_body_dict():
    body = asyncio.run(extractor_service.run_clean(MAIN, OutputFormat.TEXT))
    assert set(body) == {"content", "format", "content_length"}
    assert body["format"] == "text"
    assert body["content_length"] == len(body["content"])


def test_run_header_footer_returns_body_dict():
    body = asyncio.run(extractor_service.run_header_footer(MAIN, [REF1, REF2], debug=False))
    assert {"header", "footer", "header_method", "footer_method"} <= set(body)


def test_run_clean_does_not_block_event_loop():
    # The CPU core must run in a thread: a concurrent coroutine makes progress.
    async def scenario():
        ticked = {"n": 0}

        async def ticker():
            for _ in range(5):
                await asyncio.sleep(0.001)
                ticked["n"] += 1

        big = "<html><body>" + ("<p>x</p>" * 20000) + "</body></html>"
        await asyncio.gather(extractor_service.run_clean(big, OutputFormat.TEXT), ticker())
        return ticked["n"]

    assert asyncio.run(scenario()) == 5
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: app.core.extractor_service`).

- [ ] **Step 3: Create `app/core/extractor_service.py`** (offload-only version; cache is added in Task 5):

```python
"""Async orchestration over the pure cores. The CPU work runs in a thread
(asyncio.to_thread) so the event loop is never blocked. Shared by the sync
routers and (later) the async batch worker. Cache-aside is layered in by Task 5."""
import asyncio
import logging

from app.core import extractor_core
from app.core.metrics import EXTRACTION_METHOD
from app.schemas.clean import OutputFormat

logger = logging.getLogger(__name__)


async def run_clean(html: str, fmt: OutputFormat, force_refresh: bool = False) -> dict:
    content = await asyncio.to_thread(extractor_core.clean_core, html, fmt)
    return {"content": content, "format": fmt.value, "content_length": len(content)}


async def run_header_footer(main_html: str, reference_htmls: list[str],
                            debug: bool = False, force_refresh: bool = False) -> dict:
    body = await asyncio.to_thread(
        extractor_core.header_footer_core, main_html, reference_htmls, debug
    )
    EXTRACTION_METHOD.labels(method=body.get("header_method", "none")).inc()
    EXTRACTION_METHOD.labels(method=body.get("footer_method", "none")).inc()
    return body
```

- [ ] **Step 4: Refactor `app/routers/clean.py`** to:

```python
import logging
import time

from fastapi import APIRouter, HTTPException

from app.schemas.clean import CleanRequest, CleanResponse
from app.core import extractor_service
from app.core.metrics import REQUEST_COUNT, REQUEST_DURATION

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/clean", response_model=CleanResponse)
async def clean_html(request: CleanRequest):
    """Remove boilerplate from HTML and return cleaned content."""
    start_time = time.monotonic()
    try:
        body = await extractor_service.run_clean(request.html, request.format)
    except Exception:
        logger.exception("Extraction failed")
        REQUEST_COUNT.labels(method="POST", endpoint="/clean", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )
    duration = time.monotonic() - start_time
    logger.info("Cleaned HTML in %.3fs, format=%s, length=%d",
                duration, request.format.value, body["content_length"])
    REQUEST_COUNT.labels(method="POST", endpoint="/clean", status="200").inc()
    REQUEST_DURATION.labels(method="POST", endpoint="/clean").observe(duration)
    return CleanResponse(**body)
```

- [ ] **Step 5: Refactor `app/routers/extract.py`** to:

```python
import logging
import time

from fastapi import APIRouter, HTTPException

from app.schemas.extract import ExtractRequest, ExtractResponse, ExtractDebugResponse
from app.core import extractor_service
from app.core.metrics import REQUEST_COUNT, REQUEST_DURATION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/extract")


@router.post("/header-footer", response_model=ExtractResponse | ExtractDebugResponse)
async def extract_header_footer(request: ExtractRequest):
    """Extract header and footer from HTML using multi-strategy comparison."""
    start_time = time.monotonic()
    try:
        body = await extractor_service.run_header_footer(
            request.main_html, request.reference_htmls, request.debug
        )
    except Exception:
        logger.exception("Header/footer extraction failed")
        REQUEST_COUNT.labels(method="POST", endpoint="/extract/header-footer", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )
    duration = time.monotonic() - start_time
    REQUEST_COUNT.labels(method="POST", endpoint="/extract/header-footer", status="200").inc()
    REQUEST_DURATION.labels(method="POST", endpoint="/extract/header-footer").observe(duration)
    return ExtractDebugResponse(**body) if request.debug else ExtractResponse(**body)
```

- [ ] **Step 6: Edit `Dockerfile` line 28** — replace the CMD with a shell form that honours `UVICORN_WORKERS`:

```dockerfile
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8600 --proxy-headers --workers ${UVICORN_WORKERS:-2}"]
```

- [ ] **Step 7: Sanity-extend `tests/test_clean.py` / `tests/test_extract.py`** — append one assertion each that the existing happy path still returns 200 with the expected keys (the existing tests already cover this; if they pass unchanged, no edit is required — confirm by running them).

- [ ] **Step 8: Run → PASS.** (`test_run_clean_does_not_block_event_loop` proves the offload.)

- [ ] **Step 9: Commit** (`feat(content-extractor): offload CPU to thread + multi-worker (axis-1 timeout fix)`).

---

### Task 3: `admission.py` — sync inflight guard

**Goal:** Add an in-process admission guard so overload sheds as `503 + Retry-After` instead of degrading into timeouts. Disabled by default (`SYNC_MAX_INFLIGHT=0`).

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/core/admission.py`
- Modify: `apps-microservices/content-extractor-api-service/app/core/metrics.py` (+`SYNC_ADMISSION_REJECTED`)
- Modify: `app/routers/clean.py`, `app/routers/extract.py` (wrap the service call)
- Test: `tests/test_admission.py`

**Acceptance Criteria:**
- [ ] `SyncAdmission(0).try_acquire()` always returns `True` (disabled).
- [ ] `SyncAdmission(1)`: first `try_acquire()` True, second False until `release()`.
- [ ] When the guard rejects, the router returns `503` with a `Retry-After` header.

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_admission.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write the test** — `tests/test_admission.py`

```python
from app.core.admission import SyncAdmission


def test_disabled_always_admits():
    a = SyncAdmission(0)
    assert all(a.try_acquire() for _ in range(100))


def test_caps_at_max_and_releases():
    a = SyncAdmission(1)
    assert a.try_acquire() is True
    assert a.try_acquire() is False
    a.release()
    assert a.try_acquire() is True


def test_release_floors_at_zero():
    a = SyncAdmission(2)
    a.release()
    a.release()
    assert a.try_acquire() is True
    assert a.try_acquire() is True
    assert a.try_acquire() is False
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: app.core.admission`).

- [ ] **Step 3: Create `app/core/admission.py`:**

```python
"""In-process sync admission guard. SYNC_MAX_INFLIGHT=0 disables it (always admit).
Mirrors image-comparison's try_acquire/release slot model: the check + reserve are
synchronous with NO await between them, so there is no yield point and no race."""
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class SyncAdmission:
    def __init__(self, max_inflight: int) -> None:
        self._max = max_inflight
        self._inflight = 0

    def try_acquire(self) -> bool:
        if self._max <= 0:                       # disabled -> always admit
            return True
        if self._inflight >= self._max:
            return False
        self._inflight += 1
        return True

    def release(self) -> None:
        if self._max <= 0:
            return
        self._inflight = max(0, self._inflight - 1)


admission = SyncAdmission(settings.SYNC_MAX_INFLIGHT)
```

- [ ] **Step 4: Append to `app/core/metrics.py`:**

```python
SYNC_ADMISSION_REJECTED = Counter(
    "extract_sync_admission_rejected_total",
    "Sync requests shed by the admission guard (SYNC_MAX_INFLIGHT)",
)
```

- [ ] **Step 5: Wrap the service call in `app/routers/clean.py`** — replace the body of `clean_html` with:

```python
@router.post("/clean", response_model=CleanResponse)
async def clean_html(request: CleanRequest):
    """Remove boilerplate from HTML and return cleaned content."""
    from app.core.admission import admission
    from app.core.config import settings
    from app.core.metrics import SYNC_ADMISSION_REJECTED

    if not admission.try_acquire():
        SYNC_ADMISSION_REJECTED.inc()
        raise HTTPException(
            status_code=503,
            detail={"detail": "Service saturated", "error_code": "ADMISSION_REJECTED"},
            headers={"Retry-After": str(settings.ASYNC_SUBMIT_RETRY_AFTER_S)},
        )
    start_time = time.monotonic()
    try:
        body = await extractor_service.run_clean(request.html, request.format)
    except Exception:
        logger.exception("Extraction failed")
        REQUEST_COUNT.labels(method="POST", endpoint="/clean", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )
    finally:
        admission.release()
    duration = time.monotonic() - start_time
    logger.info("Cleaned HTML in %.3fs, format=%s, length=%d",
                duration, request.format.value, body["content_length"])
    REQUEST_COUNT.labels(method="POST", endpoint="/clean", status="200").inc()
    REQUEST_DURATION.labels(method="POST", endpoint="/clean").observe(duration)
    return CleanResponse(**body)
```

> Note: the 503 path runs **before** `try_acquire` succeeds, so it never calls `release()`. The `finally` only runs after a successful acquire.

- [ ] **Step 6: Apply the same guard to `app/routers/extract.py`** `extract_header_footer` — insert the identical `try_acquire`/503 block before `start_time`, wrap the `run_header_footer` call in `try/.../finally: admission.release()`:

```python
@router.post("/header-footer", response_model=ExtractResponse | ExtractDebugResponse)
async def extract_header_footer(request: ExtractRequest):
    """Extract header and footer from HTML using multi-strategy comparison."""
    from app.core.admission import admission
    from app.core.config import settings
    from app.core.metrics import SYNC_ADMISSION_REJECTED

    if not admission.try_acquire():
        SYNC_ADMISSION_REJECTED.inc()
        raise HTTPException(
            status_code=503,
            detail={"detail": "Service saturated", "error_code": "ADMISSION_REJECTED"},
            headers={"Retry-After": str(settings.ASYNC_SUBMIT_RETRY_AFTER_S)},
        )
    start_time = time.monotonic()
    try:
        body = await extractor_service.run_header_footer(
            request.main_html, request.reference_htmls, request.debug
        )
    except Exception:
        logger.exception("Header/footer extraction failed")
        REQUEST_COUNT.labels(method="POST", endpoint="/extract/header-footer", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Extraction failed", "error_code": "INTERNAL_ERROR"},
        )
    finally:
        admission.release()
    duration = time.monotonic() - start_time
    REQUEST_COUNT.labels(method="POST", endpoint="/extract/header-footer", status="200").inc()
    REQUEST_DURATION.labels(method="POST", endpoint="/extract/header-footer").observe(duration)
    return ExtractDebugResponse(**body) if request.debug else ExtractResponse(**body)
```

- [ ] **Step 7: Add a router-level 503 test to `tests/test_admission.py`:**

```python
import importlib

from fastapi.testclient import TestClient


def test_router_returns_503_with_retry_after(monkeypatch):
    monkeypatch.setenv("SYNC_MAX_INFLIGHT", "1")
    # Reload config + admission so the new env is picked up.
    import app.core.config as config
    importlib.reload(config)
    import app.core.admission as adm
    importlib.reload(adm)
    # Force the singleton to be full.
    adm.admission._inflight = adm.admission._max

    import app.routers.clean as clean_router
    importlib.reload(clean_router)
    import main
    importlib.reload(main)

    client = TestClient(main.app)
    r = client.post("/clean", json={"html": "<p>x</p>", "format": "text"})
    assert r.status_code == 503
    assert "Retry-After" in r.headers
```

> If reload coupling proves brittle in execution, simplify this to a direct unit test of the guard (Steps 1-3) and assert the 503 branch by calling `clean_html` with a monkeypatched `admission.try_acquire` returning `False`. The core guard behaviour is the load-bearing part.

- [ ] **Step 8: Run → PASS.**

- [ ] **Step 9: Commit** (`feat(content-extractor): sync admission guard (503 on overload)`).

---

## Phase 1b — Result cache (adds Redis, graceful-degrade)

### Task 4: `result_cache.py` — versioned content-hash cache

**Goal:** A cache-aside layer that NEVER raises (Redis-absent → miss/no-op), with debug-aware key canonicalisation.

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/core/result_cache.py`
- Modify: `apps-microservices/content-extractor-api-service/app/core/metrics.py` (+cache counters)
- Modify: `apps-microservices/content-extractor-api-service/requirements.txt` (+`redis`)
- Test: `tests/test_result_cache.py`

**Acceptance Criteria:**
- [ ] `clean_key` is deterministic; differs by `format`.
- [ ] `header_footer_key` is **order-insensitive when `debug=False`**, **order-sensitive when `debug=True`**.
- [ ] `get`/`set` return `None`/no-op and **never raise** when `cache_service.redis_client is None`.
- [ ] On a fake client: `set` then `get` round-trips the body dict; a bumped `RESULT_CACHE_VERSION` misses.

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_result_cache.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write the test** — `tests/test_result_cache.py`

```python
import asyncio
import importlib

from common_utils.redis import cache_service
from app.core import result_cache


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def get(self, k):
        return self.store.get(k)

    async def set(self, k, v, ex=None):
        self.store[k] = v
        return True


def test_clean_key_deterministic_and_format_sensitive():
    a = result_cache.clean_key("<p>x</p>", "text")
    b = result_cache.clean_key("<p>x</p>", "text")
    c = result_cache.clean_key("<p>x</p>", "html")
    assert a == b
    assert a != c


def test_hf_key_order_insensitive_when_not_debug():
    k1 = result_cache.header_footer_key("M", ["A", "B"], debug=False)
    k2 = result_cache.header_footer_key("M", ["B", "A"], debug=False)
    assert k1 == k2


def test_hf_key_order_sensitive_when_debug():
    k1 = result_cache.header_footer_key("M", ["A", "B"], debug=True)
    k2 = result_cache.header_footer_key("M", ["B", "A"], debug=True)
    assert k1 != k2


def test_get_set_never_raise_without_client(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    assert asyncio.run(result_cache.get("k")) is None
    # Must not raise:
    asyncio.run(result_cache.set("k", {"content": "x"}))


def test_roundtrip_with_fake_client(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache_service, "redis_client", fake, raising=False)
    key = result_cache.clean_key("<p>y</p>", "text")
    asyncio.run(result_cache.set(key, {"content": "y", "format": "text", "content_length": 1}))
    got = asyncio.run(result_cache.get(key))
    assert got == {"content": "y", "format": "text", "content_length": 1}
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: app.core.result_cache`).

- [ ] **Step 3: Create `app/core/result_cache.py`:**

```python
"""Redis-backed result cache for extraction outputs. Cache-aside, versioned key,
graceful-degrade.

CRITICAL: the shared cache_service helpers RAISE ConnectionError when there is no
Redis client (cache_service.py:145-146,156-157,168-169). Graceful degradation is a
property of THIS layer: every access is guarded on cache_service.redis_client being
truthy first (mirrors image-comparison feature_cache.py:65,92). Never raises."""
import hashlib
import logging
from typing import Optional

from common_utils.redis import cache_service

from app.core.config import settings

logger = logging.getLogger(__name__)

_PREFIX = "extract"


def _key(job_type: str, digest: str) -> str:
    return f"{_PREFIX}:{job_type}:{settings.RESULT_CACHE_VERSION}:{digest}"


def clean_key(html: str, fmt: str) -> str:
    digest = hashlib.sha256(f"{fmt}\x00{html}".encode("utf-8")).hexdigest()
    return _key("clean", digest)


def header_footer_key(main_html: str, reference_htmls: list[str], debug: bool) -> str:
    # debug=False: the returned header/footer strings are order-independent
    # (HeaderFooterExtractor uses set-membership across refs) -> sort for a wider hit.
    # debug=True: the response carries order-dependent text_ref1/text_ref2 -> preserve order.
    refs = sorted(reference_htmls) if not debug else list(reference_htmls)
    parts = [main_html] + refs + [str(debug)]
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
    return _key("hf", digest)


async def get(key: str) -> Optional[dict]:
    """Cached body dict, or None on miss/disabled/no-client/error. Never raises."""
    if not settings.RESULT_CACHE_ENABLED:
        return None
    if not cache_service.redis_client:          # guard: bare helper raises if None
        return None
    try:
        return await cache_service.get_json(key)
    except Exception as e:
        logger.warning("result_cache get failed (%s: %s) — miss", type(e).__name__, e)
        return None


async def set(key: str, body: dict) -> None:
    """Write a result body. No-op when disabled/no-client; swallows all errors."""
    if not settings.RESULT_CACHE_ENABLED:
        return
    if not cache_service.redis_client:
        return
    try:
        await cache_service.set_json(key, body, ttl=settings.RESULT_CACHE_TTL_S)
    except Exception as e:
        logger.warning("result_cache set failed (%s: %s) — not cached", type(e).__name__, e)
```

- [ ] **Step 4: Append to `app/core/metrics.py`:**

```python
CACHE_HITS = Counter(
    "extract_cache_hits_total", "Result cache hits", ["job_type"],
)
CACHE_MISSES = Counter(
    "extract_cache_misses_total", "Result cache misses", ["job_type"],
)
```

- [ ] **Step 5: Add `redis` to `requirements.txt`** (it ships transitively via common-utils, but make it explicit):

```
redis>=4.2
```

- [ ] **Step 6: Run → PASS.**

- [ ] **Step 7: Commit** (`feat(content-extractor): versioned result cache (guarded, graceful-degrade)`).

---

### Task 5: Wire cache into `extractor_service`

**Goal:** Make `run_clean` / `run_header_footer` cache-aside, honour `force_refresh`, and emit hit/miss metrics.

**Files:**
- Modify: `apps-microservices/content-extractor-api-service/app/core/extractor_service.py`
- Test: extend `tests/test_extractor_service.py`

**Acceptance Criteria:**
- [ ] Cache hit returns the cached body without calling the core; increments `CACHE_HITS`.
- [ ] Cache miss computes, writes, increments `CACHE_MISSES`.
- [ ] `force_refresh=True` skips the read but still writes.

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_extractor_service.py -v` → PASS

**Steps:**

- [ ] **Step 1: Extend `tests/test_extractor_service.py`:**

```python
def test_run_clean_uses_cache(monkeypatch):
    calls = {"n": 0}

    async def fake_get(key):
        return {"content": "CACHED", "format": "text", "content_length": 6} if calls["n"] else None

    async def fake_set(key, body):
        calls["n"] += 1

    monkeypatch.setattr(extractor_service.result_cache, "get", fake_get)
    monkeypatch.setattr(extractor_service.result_cache, "set", fake_set)

    first = asyncio.run(extractor_service.run_clean(MAIN, OutputFormat.TEXT))   # miss -> compute + set
    second = asyncio.run(extractor_service.run_clean(MAIN, OutputFormat.TEXT))  # hit
    assert second["content"] == "CACHED"
    assert first["content"] != "CACHED"


def test_force_refresh_skips_read(monkeypatch):
    seen = {"get": 0}

    async def fake_get(key):
        seen["get"] += 1
        return {"content": "CACHED", "format": "text", "content_length": 6}

    async def fake_set(key, body):
        pass

    monkeypatch.setattr(extractor_service.result_cache, "get", fake_get)
    monkeypatch.setattr(extractor_service.result_cache, "set", fake_set)
    body = asyncio.run(extractor_service.run_clean(MAIN, OutputFormat.TEXT, force_refresh=True))
    assert seen["get"] == 0
    assert body["content"] != "CACHED"
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: module ... has no attribute 'result_cache'`).

- [ ] **Step 3: Replace `app/core/extractor_service.py` with the cached version:**

```python
"""Async orchestration over the pure cores: cache-aside + thread-offloaded CPU.
Shared by the sync routers and the async batch worker (DRY). The CPU work runs in
a thread (asyncio.to_thread) so the event loop is never blocked."""
import asyncio
import logging

from app.core import extractor_core, result_cache
from app.core.metrics import CACHE_HITS, CACHE_MISSES, EXTRACTION_METHOD
from app.schemas.clean import OutputFormat

logger = logging.getLogger(__name__)


async def run_clean(html: str, fmt: OutputFormat, force_refresh: bool = False) -> dict:
    key = result_cache.clean_key(html, fmt.value)
    if not force_refresh:
        cached = await result_cache.get(key)
        if cached is not None:
            CACHE_HITS.labels(job_type="clean").inc()
            return cached
    CACHE_MISSES.labels(job_type="clean").inc()
    content = await asyncio.to_thread(extractor_core.clean_core, html, fmt)
    body = {"content": content, "format": fmt.value, "content_length": len(content)}
    await result_cache.set(key, body)
    return body


async def run_header_footer(main_html: str, reference_htmls: list[str],
                            debug: bool = False, force_refresh: bool = False) -> dict:
    key = result_cache.header_footer_key(main_html, reference_htmls, debug)
    if not force_refresh:
        cached = await result_cache.get(key)
        if cached is not None:
            CACHE_HITS.labels(job_type="header_footer").inc()
            return cached
    CACHE_MISSES.labels(job_type="header_footer").inc()
    body = await asyncio.to_thread(
        extractor_core.header_footer_core, main_html, reference_htmls, debug
    )
    EXTRACTION_METHOD.labels(method=body.get("header_method", "none")).inc()
    EXTRACTION_METHOD.labels(method=body.get("footer_method", "none")).inc()
    await result_cache.set(key, body)
    return body
```

- [ ] **Step 4: Run → PASS** (offload + cache tests).

- [ ] **Step 5: Commit** (`feat(content-extractor): cache-aside wiring + hit/miss metrics`).

---

## Phase 2 — Async job subsystem

### Task 6: `schemas/async_jobs.py`

**Goal:** Pydantic models for the two submit bodies, the submit response, and the unified poll response.

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/schemas/async_jobs.py`
- Test: `tests/test_async_jobs.py` (new — schema section)

**Acceptance Criteria:**
- [ ] `CleanAsyncRequest` requires ≥1 item, each `{html, format}`; `max_concurrency` defaults 4 (1..50).
- [ ] `HeaderFooterAsyncRequest` items each `{main_html, reference_htmls(≥2), debug}`.
- [ ] `AsyncJobStatusResponse` has `job_id, job_type, status, total, done, results?, error?, poll_after_seconds`.

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_async_jobs.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write the test** — `tests/test_async_jobs.py` (schema part):

```python
import pytest
from pydantic import ValidationError

from app.schemas.async_jobs import (
    CleanAsyncRequest, HeaderFooterAsyncRequest, AsyncJobStatusResponse,
)


def test_clean_async_request_valid():
    req = CleanAsyncRequest(items=[{"html": "<p>x</p>", "format": "text"}])
    assert req.max_concurrency == 4
    assert req.items[0].html == "<p>x</p>"


def test_clean_async_request_rejects_empty():
    with pytest.raises(ValidationError):
        CleanAsyncRequest(items=[])


def test_hf_async_request_requires_two_refs():
    with pytest.raises(ValidationError):
        HeaderFooterAsyncRequest(items=[{"main_html": "<p>m</p>", "reference_htmls": ["<p>a</p>"]}])


def test_status_response_shape():
    r = AsyncJobStatusResponse(
        job_id="j", job_type="clean", status="completed", total=1, done=1,
        results=[{"content": "x"}], poll_after_seconds=2,
    )
    assert r.error is None
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: app.schemas.async_jobs`).

- [ ] **Step 3: Create `app/schemas/async_jobs.py`:**

```python
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.clean import OutputFormat


class CleanItem(BaseModel):
    html: str = Field(..., min_length=1)
    format: OutputFormat = Field(default=OutputFormat.TEXT)


class HeaderFooterItem(BaseModel):
    main_html: str = Field(..., min_length=1)
    reference_htmls: list[str] = Field(..., min_length=2)
    debug: bool = Field(default=False)


class CleanAsyncRequest(BaseModel):
    items: list[CleanItem] = Field(..., min_length=1, max_length=100)
    max_concurrency: int = Field(default=4, ge=1, le=50)   # default == DEFAULT_MAX_CONCURRENCY
    force_refresh: bool = Field(default=False)
    client_job_id: Optional[str] = Field(default=None)


class HeaderFooterAsyncRequest(BaseModel):
    items: list[HeaderFooterItem] = Field(..., min_length=1, max_length=100)
    max_concurrency: int = Field(default=4, ge=1, le=50)
    force_refresh: bool = Field(default=False)
    client_job_id: Optional[str] = Field(default=None)


class AsyncSubmitResponse(BaseModel):
    job_id: str
    status: str
    total: int
    poll_after_seconds: int


class AsyncJobStatusResponse(BaseModel):
    job_id: str
    job_type: str
    status: str                                  # pending|running|completed|failed|stale
    total: int
    done: int
    results: Optional[list[dict]] = None
    error: Optional[str] = None
    poll_after_seconds: int
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit** (`feat(content-extractor): async job schemas`).

---

### Task 7: `async_jobs.py` core — JobStore + JobManager + poll_status

**Goal:** The Redis-backed, generic (job_type-parameterised) async job subsystem, adapted from `api-detection-langue-fr/app/core/async_jobs.py` but using the shared `cache_service` pool.

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/core/async_jobs.py`
- Modify: `apps-microservices/content-extractor-api-service/app/core/metrics.py` (+async metrics)
- Test: extend `tests/test_async_jobs.py`

**Acceptance Criteria:**
- [ ] `poll_status` returns `stale` for a pending record whose `last_activity` is older than the threshold; otherwise the stored status.
- [ ] `submit` raises `_JobsDisabled` when `ASYNC_JOBS_ENABLED=False`, `_JobsUnavailable` when Redis is down, `_JobCapacityExceeded` at `MAX_ACTIVE_JOBS`.
- [ ] Idempotent re-submit with the same `client_job_id` returns the existing job id + status 200.
- [ ] A completed job's record has `status="completed"` and `results` = the runner output.
- [ ] `shutdown()` marks a still-running job `failed` with `error="service_shutdown"`.

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_async_jobs.py -v` → PASS

**Steps:**

- [ ] **Step 1: Append async metrics to `app/core/metrics.py`** (note the import line at top must become `from prometheus_client import Counter, Gauge, Histogram`):

```python
ASYNC_JOBS_SUBMITTED = Counter(
    "extract_async_jobs_submitted_total", "Async batch jobs accepted (202)",
)
ASYNC_JOBS_ACTIVE = Gauge(
    "extract_async_jobs_active", "Currently reserved/in-flight async jobs",
)
ASYNC_JOBS_TERMINAL = Counter(
    "extract_async_jobs_terminal_total", "Async jobs reaching a terminal status", ["status"],
)
ASYNC_JOB_DURATION = Histogram(
    "extract_async_job_duration_seconds", "Async job wall-clock from running to terminal",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800),
)
ASYNC_JOB_CAPACITY_REJECTED = Counter(
    "extract_async_job_capacity_rejected_total", "Submits rejected because MAX_ACTIVE_JOBS reached",
)
```

- [ ] **Step 2: Write the test** — extend `tests/test_async_jobs.py`:

```python
import asyncio
import time
import types

from common_utils.redis import cache_service
from app.core import async_jobs
from app.core.async_jobs import (
    JobStore, JobManager, poll_status,
    _JobsDisabled, _JobsUnavailable, _JobCapacityExceeded,
)


class FakeRedis:
    def __init__(self):
        self.kv = {}

    async def ping(self):
        return True

    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.kv:
            return None
        self.kv[k] = v
        return True

    async def setex(self, k, ttl, v):
        self.kv[k] = v
        return True

    async def get(self, k):
        return self.kv.get(k)

    async def delete(self, k):
        self.kv.pop(k, None)

    async def expire(self, k, ttl):
        return True


def _settings(**over):
    base = dict(ASYNC_JOBS_ENABLED=True, MAX_ACTIVE_JOBS=8, JOB_TTL_ACTIVE_S=7200,
                JOB_RESULT_TTL_S=3600, STALE_THRESHOLD_S=120, HEARTBEAT_INTERVAL_S=5,
                SHUTDOWN_GRACE_S=5)
    base.update(over)
    return types.SimpleNamespace(**base)


def _req(items, client_job_id=None, max_concurrency=4, force_refresh=False):
    return types.SimpleNamespace(items=items, client_job_id=client_job_id,
                                 max_concurrency=max_concurrency, force_refresh=force_refresh)


async def _echo_runner(job_type, items, max_concurrency, force_refresh, progress_cb=None):
    out = [{"echo": i} for i in range(len(items))]
    if progress_cb:
        progress_cb(len(items))
    return out


def test_poll_status_stale():
    rec = {"status": "running", "created_at": 0, "last_activity": 0}
    assert poll_status(rec, now=1000, stale_threshold_s=120) == "stale"
    assert poll_status({"status": "completed"}, now=1000, stale_threshold_s=120) == "completed"


def test_submit_disabled(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings(ASYNC_JOBS_ENABLED=False))
    try:
        asyncio.run(jm.submit("clean", _req([1])))
        assert False
    except _JobsDisabled:
        pass


def test_submit_and_complete(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings())

    async def scenario():
        job_id, code = await jm.submit("clean", _req([1, 2, 3]))
        assert code == 202
        for _ in range(50):
            rec = await jm.get_record(job_id)
            if rec and rec["status"] == "completed":
                return rec
            await asyncio.sleep(0.01)
        return await jm.get_record(job_id)

    rec = asyncio.run(scenario())
    assert rec["status"] == "completed"
    assert rec["done"] == 3
    assert len(rec["results"]) == 3


def test_idempotent_resubmit(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings())

    async def scenario():
        a, ca = await jm.submit("clean", _req([1], client_job_id="K"))
        b, cb = await jm.submit("clean", _req([1], client_job_id="K"))
        return a, b, cb

    a, b, cb = asyncio.run(scenario())
    assert a == b and cb == 200


def test_capacity_exceeded(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings(MAX_ACTIVE_JOBS=0))
    try:
        asyncio.run(jm.submit("clean", _req([1])))
        assert False
    except _JobCapacityExceeded:
        pass


def test_unavailable_when_no_client(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", None, raising=False)
    jm = JobManager(JobStore(), _echo_runner, _settings())
    try:
        asyncio.run(jm.submit("clean", _req([1])))
        assert False
    except _JobsUnavailable:
        pass
```

- [ ] **Step 3: Run → FAIL** (`ModuleNotFoundError: app.core.async_jobs`).

- [ ] **Step 4: Create `app/core/async_jobs.py`:**

```python
"""Async job store + manager for content-extractor batch endpoints. Job state lives
in Redis via the shared common_utils.redis.cache_service pool. The worker runs
in-process via asyncio, reusing a batch runner injected at construction (generic
over job_type). Adapted from api-detection-langue-fr/app/core/async_jobs.py."""
import asyncio
import json
import logging
import time
import uuid
from typing import Optional, Callable, Awaitable

from common_utils.redis import cache_service

logger = logging.getLogger(__name__)

_JOB_KEY = "extract:job:{}"
_IDX_KEY = "extract:jobidx:{}"


class _JobsDisabled(Exception):
    """ASYNC_JOBS_ENABLED is false (permanent 503, not retryable)."""


class _JobsUnavailable(Exception):
    """Redis unreachable / first write failed (permanent 503, not retryable)."""


class _JobCapacityExceeded(Exception):
    """MAX_ACTIVE_JOBS reached (transient 503 + Retry-After)."""


class JobStore:
    """Redis CRUD over the shared cache_service pool. write() RAISES on no-client so
    the submit path can detect an unavailable Redis (do NOT swallow there)."""

    def _client(self):
        return cache_service.redis_client

    async def ping(self) -> bool:
        client = self._client()
        if not client:
            return False
        try:
            return bool(await client.ping())
        except Exception as e:
            logger.warning("[async-jobs] ping failed: %s", e)
            return False

    async def claim_index(self, cjid: str, job_id: str, ttl: int) -> bool:
        client = self._client()
        ok = await client.set(_IDX_KEY.format(cjid), job_id, nx=True, ex=ttl)
        return bool(ok)

    async def get_index(self, cjid: str) -> Optional[str]:
        client = self._client()
        try:
            return await client.get(_IDX_KEY.format(cjid))
        except Exception:
            return None

    async def delete_index(self, cjid: str) -> None:
        client = self._client()
        try:
            await client.delete(_IDX_KEY.format(cjid))
        except Exception:
            pass

    async def refresh_index_ttl(self, cjid: str, ttl: int) -> None:
        client = self._client()
        try:
            await client.expire(_IDX_KEY.format(cjid), ttl)
        except Exception:
            pass

    async def write(self, record: dict, ttl: int) -> None:
        client = self._client()
        if not client:
            raise RuntimeError("Redis client unavailable")
        await client.setex(_JOB_KEY.format(record["job_id"]), ttl, json.dumps(record))

    async def get(self, job_id: str) -> Optional[dict]:
        client = self._client()
        if not client:
            return None
        try:
            data = await client.get(_JOB_KEY.format(job_id))
            return json.loads(data) if data else None
        except Exception as e:
            logger.debug("[async-jobs] get error: %s", e)
            return None


def poll_status(record: dict, now: float, stale_threshold_s: int) -> str:
    """BO-visible status. 'stale' is derived on read for a pending/running record
    whose heartbeat froze (dead worker). Never mutates."""
    status = record.get("status", "pending")
    if status in ("pending", "running"):
        last = max(record.get("created_at", 0.0), record.get("last_activity", 0.0))
        if (now - last) > stale_threshold_s:
            return "stale"
    return status


class JobManager:
    def __init__(self, store: JobStore, batch_runner: Callable[..., Awaitable], settings) -> None:
        self._store = store
        self._batch_runner = batch_runner            # extractor_service.run_batch, injected
        self._s = settings
        self._job_tasks: dict[str, asyncio.Task] = {}
        self._inflight = 0                            # reserve counter (sync-guarded)

    async def get_record(self, job_id: str) -> Optional[dict]:
        return await self._store.get(job_id)

    async def submit(self, job_type: str, req) -> tuple[str, int]:
        """Returns (job_id, http_status). 202 new, 200 idempotent re-submit."""
        if not self._s.ASYNC_JOBS_ENABLED:
            raise _JobsDisabled()
        if not await self._store.ping():
            raise _JobsUnavailable()

        job_id = uuid.uuid4().hex
        cjid = req.client_job_id

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
            "job_id": job_id, "client_job_id": cjid, "job_type": job_type,
            "status": "pending", "total": len(req.items), "done": 0,
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

        task = asyncio.create_task(
            self._run_job(job_id, cjid, job_type, list(req.items),
                          req.max_concurrency, req.force_refresh)
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

    async def _run_job(self, job_id, cjid, job_type, items, max_concurrency, force_refresh) -> None:
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
            results = await self._batch_runner(
                job_type, items, max_concurrency, force_refresh,
                lambda done: progress.__setitem__("done", done),
            )
            hb.cancel()
            await asyncio.gather(hb, return_exceptions=True)
            rec = await self._store.get(job_id) or rec
            rec.update({
                "status": "completed", "done": len(results), "results": results,
                "finished_at": time.time(), "last_activity": time.time(),
            })
            await self._store.write(rec, self._s.JOB_RESULT_TTL_S)
            if cjid:
                await self._store.refresh_index_ttl(cjid, self._s.JOB_RESULT_TTL_S)
            ASYNC_JOBS_TERMINAL.labels(status="completed").inc()
            ASYNC_JOB_DURATION.observe(time.time() - started)
        except asyncio.CancelledError:
            hb.cancel()
            raise                                     # shutdown() owns the record write
        except Exception as e:
            hb.cancel()
            await asyncio.gather(hb, return_exceptions=True)
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

- [ ] **Step 5: Run → PASS.**

- [ ] **Step 6: Commit** (`feat(content-extractor): async job store + manager (Redis, in-process worker)`).

---

### Task 8: `extractor_service.run_batch` — the injected batch runner

**Goal:** The runner the JobManager injects: dispatch by `job_type`, process items concurrently under a semaphore, write results to a **fixed-size indexed** list (order-aligned), isolate per-item failures.

**Files:**
- Modify: `apps-microservices/content-extractor-api-service/app/core/extractor_service.py`
- Test: extend `tests/test_extractor_service.py`

**Acceptance Criteria:**
- [ ] `run_batch` returns a list the same length/order as `items`.
- [ ] A failing item yields `{"error": ...}` in its slot; other items still succeed.
- [ ] `progress_cb` is called with the running done-count.

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_extractor_service.py -v` → PASS

**Steps:**

- [ ] **Step 1: Extend `tests/test_extractor_service.py`:**

```python
import types


def test_run_batch_order_and_failure_isolation(monkeypatch):
    async def fake_run_clean(html, fmt, force_refresh=False):
        if html == "BOOM":
            raise RuntimeError("kaboom")
        return {"content": html, "format": fmt.value, "content_length": len(html)}

    monkeypatch.setattr(extractor_service, "run_clean", fake_run_clean)

    items = [
        types.SimpleNamespace(html="A", format=OutputFormat.TEXT),
        types.SimpleNamespace(html="BOOM", format=OutputFormat.TEXT),
        types.SimpleNamespace(html="C", format=OutputFormat.TEXT),
    ]
    seen = {"max": 0}
    results = asyncio.run(extractor_service.run_batch(
        "clean", items, max_concurrency=2, force_refresh=False,
        progress_cb=lambda d: seen.__setitem__("max", d),
    ))
    assert [r.get("content", r.get("error")) for r in results] == ["A", "kaboom", "C"]
    assert seen["max"] == 3
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: ... run_batch`).

- [ ] **Step 3: Append `run_batch` to `app/core/extractor_service.py`:**

```python
async def run_batch(job_type, items, max_concurrency, force_refresh, progress_cb=None) -> list[dict]:
    """Batch runner injected into JobManager. Processes items concurrently under a
    semaphore and writes each result into a FIXED-SIZE list indexed by submit
    position (order-aligned even under concurrency). Per-item failure is isolated:
    the failing slot gets {"error": str(e)}; the job does not fail as a whole."""
    results: list = [None] * len(items)
    sem = asyncio.Semaphore(max_concurrency)
    done = 0
    lock = asyncio.Lock()

    async def _one(i, item):
        nonlocal done
        async with sem:
            try:
                if job_type == "clean":
                    results[i] = await run_clean(item.html, item.format, force_refresh)
                else:
                    results[i] = await run_header_footer(
                        item.main_html, item.reference_htmls, item.debug, force_refresh
                    )
            except Exception as e:
                logger.warning("batch item %d (%s) failed: %s", i, job_type, e)
                results[i] = {"error": str(e)}
            async with lock:
                done += 1
                if progress_cb is not None:
                    progress_cb(done)

    await asyncio.gather(*(_one(i, it) for i, it in enumerate(items)))
    return results
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit** (`feat(content-extractor): indexed, failure-isolated batch runner`).

---

### Task 9: Async routers + `main.py` lifespan wiring

**Goal:** Expose `POST /clean-async`, `POST /extract/header-footer-async`, `GET /jobs/{job_id}`; wire the Redis pool + JobManager into the app lifespan.

**Files:**
- Create: `apps-microservices/content-extractor-api-service/app/routers/async_jobs.py`
- Modify: `apps-microservices/content-extractor-api-service/main.py`
- Test: extend `tests/test_async_jobs.py` (router); new `tests/test_main.py`

**Acceptance Criteria:**
- [ ] `POST /clean-async` returns 202 + `{job_id,...}` when Redis is up; eventually `GET /jobs/{id}` → `completed` with `results`.
- [ ] `POST /clean-async` returns 503 **without** `Retry-After` when `ASYNC_JOBS_ENABLED=false`.
- [ ] `GET /jobs/{unknown}` → 404.
- [ ] App starts/stops cleanly with the lifespan (smoke).

**Verify:** `cd apps-microservices/content-extractor-api-service && python -m pytest tests/test_async_jobs.py tests/test_main.py -v` → PASS

**Steps:**

- [ ] **Step 1: Create `app/routers/async_jobs.py`:**

```python
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.async_jobs import (
    poll_status, _JobsDisabled, _JobsUnavailable, _JobCapacityExceeded,
)
from app.schemas.async_jobs import (
    CleanAsyncRequest, HeaderFooterAsyncRequest,
    AsyncSubmitResponse, AsyncJobStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _poll_hint() -> int:
    return min(max(settings.HEARTBEAT_INTERVAL_S, 2), settings.ASYNC_POLL_HINT_MAX_S)


async def _submit(job_type: str, request, http_request: Request):
    jm = http_request.app.state.job_manager
    try:
        job_id, status_code = await jm.submit(job_type, request)
    except _JobsDisabled:
        raise HTTPException(status_code=503,
                            detail={"detail": "Async jobs disabled", "retryable": False})
    except _JobsUnavailable:
        raise HTTPException(status_code=503,
                            detail={"detail": "Job store unavailable", "retryable": False})
    except _JobCapacityExceeded:
        ra = str(settings.ASYNC_SUBMIT_RETRY_AFTER_S)
        raise HTTPException(
            status_code=503,
            detail={"detail": "Max active jobs reached", "retryable": True,
                    "retry_after_seconds": int(ra)},
            headers={"Retry-After": ra},
        )
    body = AsyncSubmitResponse(job_id=job_id, status="pending",
                               total=len(request.items), poll_after_seconds=_poll_hint())
    return JSONResponse(status_code=status_code, content=body.model_dump())


@router.post("/clean-async")
async def submit_clean_async(request: CleanAsyncRequest, http_request: Request):
    return await _submit("clean", request, http_request)


@router.post("/extract/header-footer-async")
async def submit_header_footer_async(request: HeaderFooterAsyncRequest, http_request: Request):
    return await _submit("header_footer", request, http_request)


@router.get("/jobs/{job_id}", response_model=AsyncJobStatusResponse)
async def poll_job(job_id: str, http_request: Request) -> AsyncJobStatusResponse:
    jm = http_request.app.state.job_manager
    rec = await jm.get_record(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Unknown or expired job_id")
    status = poll_status(rec, time.time(), settings.STALE_THRESHOLD_S)
    results = rec.get("results") if status in ("completed", "failed", "stale") else None
    return AsyncJobStatusResponse(
        job_id=rec["job_id"], job_type=rec.get("job_type", ""), status=status,
        total=rec["total"], done=rec.get("done", 0), results=results,
        error=rec.get("error"), poll_after_seconds=_poll_hint(),
    )
```

- [ ] **Step 2: Modify `main.py`** — add the imports, the lifespan, attach it to `FastAPI(...)`, and include the async router. The full file becomes:

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.wsgi import WSGIMiddleware
from common_utils.logging import setup_logging
from common_utils.metrics.prometheus import get_metrics_app
from common_utils.redis.cache_service import init_redis_pool, close_redis_pool

from app.core.config import settings
from app.core.async_jobs import JobStore, JobManager
from app.core.extractor_service import run_batch
from app.routers import clean, extract, async_jobs

setup_logging("content-extractor-api-service")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis_pool()
    store = JobStore()
    app.state.job_manager = JobManager(store=store, batch_runner=run_batch, settings=settings)
    logger.info("Async JobManager initialised (lifespan startup)")
    yield
    await app.state.job_manager.shutdown()
    await close_redis_pool()
    logger.info("Async JobManager shut down (lifespan shutdown)")


app = FastAPI(
    title=settings.APP_NAME,
    description="HTML cleaning and header/footer extraction API",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Prometheus metrics
metrics_app = get_metrics_app()
app.mount("/metrics", WSGIMiddleware(metrics_app))

# CORS — internal service, not exposed publicly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Internal service only — not exposed publicly
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def check_payload_size(request: Request, call_next):
    """Reject requests exceeding MAX_PAYLOAD_SIZE_MB."""
    content_length = request.headers.get("content-length")
    max_bytes = settings.MAX_PAYLOAD_SIZE_MB * 1024 * 1024
    if content_length and int(content_length) > max_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "detail": f"Payload exceeds {settings.MAX_PAYLOAD_SIZE_MB}MB limit",
                "error_code": "PAYLOAD_TOO_LARGE",
            },
        )
    return await call_next(request)


app.include_router(clean.router)
app.include_router(extract.router)
app.include_router(async_jobs.router)


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
```

- [ ] **Step 3: Add router tests to `tests/test_async_jobs.py`** (uses the TestClient with the lifespan + a fake Redis):

```python
from fastapi.testclient import TestClient


def test_router_submit_poll_complete(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    # Skip init_redis_pool (no real Redis): patch it to a no-op so lifespan keeps our fake.
    import main
    monkeypatch.setattr(main, "init_redis_pool", lambda: asyncio.sleep(0))
    monkeypatch.setattr(main, "close_redis_pool", lambda: asyncio.sleep(0))

    with TestClient(main.app) as client:
        r = client.post("/clean-async", json={"items": [{"html": "<p>x</p>", "format": "text"}]})
        assert r.status_code == 202
        job_id = r.json()["job_id"]
        # Poll until terminal.
        for _ in range(50):
            p = client.get(f"/jobs/{job_id}")
            if p.json()["status"] == "completed":
                break
            time.sleep(0.02)
        body = client.get(f"/jobs/{job_id}").json()
        assert body["status"] == "completed"
        assert body["job_type"] == "clean"
        assert len(body["results"]) == 1


def test_router_disabled_503_no_retry_after(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    monkeypatch.setenv("ASYNC_JOBS_ENABLED", "false")
    import importlib, app.core.config as config
    importlib.reload(config)
    import main
    importlib.reload(main)
    monkeypatch.setattr(main, "init_redis_pool", lambda: asyncio.sleep(0))
    monkeypatch.setattr(main, "close_redis_pool", lambda: asyncio.sleep(0))
    with TestClient(main.app) as client:
        r = client.post("/clean-async", json={"items": [{"html": "<p>x</p>", "format": "text"}]})
        assert r.status_code == 503
        assert "Retry-After" not in r.headers


def test_router_unknown_job_404(monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis(), raising=False)
    import main
    monkeypatch.setattr(main, "init_redis_pool", lambda: asyncio.sleep(0))
    monkeypatch.setattr(main, "close_redis_pool", lambda: asyncio.sleep(0))
    with TestClient(main.app) as client:
        assert client.get("/jobs/does-not-exist").status_code == 404
```

> **Execution note:** `JobManager` is constructed inside the lifespan reading the module-level `settings`. The `ASYNC_JOBS_ENABLED=false` test reloads `config` then `main` so the lifespan sees the new value. If module-reload ordering proves brittle, an equivalent unit test asserting the router maps `_JobsDisabled → 503 no-header` (call `_submit` with a stub `app.state.job_manager.submit` raising `_JobsDisabled`) is acceptable and preferred for stability.

- [ ] **Step 4: Create `tests/test_main.py`** (lifespan smoke):

```python
import asyncio

from fastapi.testclient import TestClient


def test_app_starts_and_health_ok(monkeypatch):
    import main
    monkeypatch.setattr(main, "init_redis_pool", lambda: asyncio.sleep(0))
    monkeypatch.setattr(main, "close_redis_pool", lambda: asyncio.sleep(0))
    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert hasattr(main.app.state, "job_manager")
```

- [ ] **Step 5: Run → PASS.**

- [ ] **Step 6: Commit** (`feat(content-extractor): async submit/poll endpoints + lifespan wiring`).

---

## Phase 3 — Scale + gateway + docs

### Task 10: api-gateway downstream timeout for `extractor-service`

> **Correction (2026-06-21):** the serving gateway is `api-gateway-go` (Go), not the Python `api-gateway` below — the effective change landed in `api-gateway-go/internal/config/service_map.go` `BuildDownstreamTimeouts()` (`"extractor-service": 60`, commit `d6120318`); the Python edit is kept for 1:1-port parity only.

**Goal:** Give the extractor route a finite downstream timeout (resolves the BO call's exposure to gateway defaults). Route key proven `"extractor-service"`.

**Files:**
- Modify: `apps-microservices/api-gateway/app/core/settings.py` (lines 80-82, the `DOWNSTREAM_TIMEOUTS_S` dict)
- Test: `apps-microservices/api-gateway/tests/test_settings.py` (new or extend)

**Acceptance Criteria:**
- [ ] `Configuration().DOWNSTREAM_TIMEOUTS_S["extractor-service"] == 60.0`.
- [ ] The existing `api-detection-langue-fr-service` entry is unchanged.

**Verify:** `cd apps-microservices/api-gateway && python -m pytest tests/test_settings.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write/extend the test** — `apps-microservices/api-gateway/tests/test_settings.py`

```python
from app.core.settings import Configuration


def test_extractor_downstream_timeout_present():
    cfg = Configuration()
    assert cfg.DOWNSTREAM_TIMEOUTS_S.get("extractor-service") == 60.0


def test_detection_timeout_unchanged():
    cfg = Configuration()
    assert cfg.DOWNSTREAM_TIMEOUTS_S.get("api-detection-langue-fr-service") == 180.0
```

- [ ] **Step 2: Run → FAIL** (KeyError/None for `extractor-service`).

- [ ] **Step 3: Edit `apps-microservices/api-gateway/app/core/settings.py`** — add the entry inside the existing dict (the new line at `:82`, before the closing brace):

```python
    DOWNSTREAM_TIMEOUTS_S: Dict[str, float] = {
        "api-detection-langue-fr-service": 180.0,
        "extractor-service": 60.0,
    }
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit** (`feat(api-gateway): downstream timeout for extractor-service (60s)`).

---

### Task 11: Documentation

**Goal:** Update the service CLAUDE.md and the root service map so the new surface is discoverable. (Docs are gate-exempt; no tests.)

**Files:**
- Modify: `apps-microservices/content-extractor-api-service/CLAUDE.md`
- Modify (small): root `CLAUDE.md` only if the service table needs the "Redis" note (optional).

**Acceptance Criteria:**
- [ ] CLAUDE.md documents the new endpoints, the Redis dependency (job store + cache), all new env vars, the 503/Retry-After discriminator, and the sync admission flag.

**Steps:**

- [ ] **Step 1: Update `apps-microservices/content-extractor-api-service/CLAUDE.md`** — add an "Async Job API + Result Cache" section (endpoints `/clean-async`, `/extract/header-footer-async`, `/jobs/{job_id}`; the `extract:*` Redis keys; the env-var table from spec §11; the 503 discriminator; `SYNC_MAX_INFLIGHT`; `UVICORN_WORKERS`), and change "No RabbitMQ, Redis, or database" to note **Redis required for async, optional for sync (cache degrades gracefully)**. Reference the spec + this plan path.

- [ ] **Step 2: Commit** (`docs(content-extractor): document async API, cache, admission, workers`).

---

## Self-Review

**1. Spec coverage:**
- §5.1 axis-1 offload + workers → Task 2. ✅
- §5.2 hybrid sync/async → Tasks 2/3 (sync), 6-9 (async). ✅
- §7 contracts (sync unchanged, async submit/poll, 503 discriminator) → Tasks 2/3, 9. ✅
- §8 cache (versioned key, debug-aware sort, guarded graceful-degrade) → Tasks 4/5. ✅
- §9 job subsystem (JobStore/JobManager/poll_status, soft cap, indexed results) → Tasks 7/8. ✅
- §10 admission → Task 3. ✅
- §11 config → Task 0. ✅
- §13 graceful-degrade (guard before bare helpers + test) → Task 4 (`test_get_set_never_raise_without_client`). ✅
- §14 gateway key `extractor-service` → Task 10. ✅
- §15 metrics → Tasks 3 (admission), 5 (cache), 7 (async). ✅
- §16 testing → every task is TDD. ✅
- §17 phases → Phase headers 1a/1b/2/3 map to task groups. ✅
- Hard global cap (§9) is explicitly deferred (soft cap shipped) — not a task, matches spec. ✅

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N" — every code step has full code. The two router/lifespan tests carry an explicit, complete fallback (unit-test the branch) rather than a placeholder. ✅

**3. Type consistency:**
- `run_clean(html, fmt, force_refresh=False)`, `run_header_footer(main_html, reference_htmls, debug=False, force_refresh=False)`, `run_batch(job_type, items, max_concurrency, force_refresh, progress_cb=None)` — signatures identical across Tasks 2/5/8 and the JobManager call in Task 7. ✅
- `JobManager.submit(job_type, req)` (Task 7) matches the router `jm.submit(job_type, request)` (Task 9). ✅
- `_run_job(... max_concurrency, force_refresh)` calls `_batch_runner(job_type, items, max_concurrency, force_refresh, progress_cb)` — matches `run_batch` signature. ✅
- `result_cache.get/set/clean_key/header_footer_key` names consistent across Tasks 4/5. ✅
- metrics import line upgraded to `Counter, Gauge, Histogram` in Task 7 (Gauge/Histogram first used there). ✅

No gaps found.

---
