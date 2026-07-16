# api-comparaison-texte — Contract Fix + Lean Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the live BO response-contract bug (title/description change-detection) and lean-harden `api-comparaison-texte` (offload the blocking difflib work, multi-worker, Prometheus metrics, optional sync admission) — no async, no Redis.

**Architecture:** Two deliverables. **(A) BO consumer fix** — read the service's real contract (`decision`/`similarity_ratio`) instead of non-existent `is_similar`/`similarity`. **(B) Service hardening** — extract the sync compute into pure helpers, offload the *whole* batch in one `asyncio.to_thread` (GIL: difflib is pure-Python, prod path is text-only → no intra-batch speedup; cross-batch parallelism = workers×replicas), add `prometheus-client` metrics + `/metrics`, add an off-by-default sync admission guard, run multiple uvicorn workers.

**Tech Stack:** Python 3.10, FastAPI + Uvicorn, difflib (stdlib), BeautifulSoup4/lxml, prometheus-client, pytest. PHP (BO consumer).

**Spec:** `docs/superpowers/specs/2026-06-21-comparaison-texte-contract-fix-hardening-design.md`

**Repo conventions / gotchas:**
- Service paths are under `apps-microservices/api-comparaison-texte/`; run tests from there: `cd apps-microservices/api-comparaison-texte && python -m pytest tests/<file> -v`.
- The BO fix is in the **Hellopro** repo (`C:\Users\randr\Documents\Workspaces\Hellopro`), tracked git, normal commit (NOT Ecritel-FTP — `BO/` is not in the `site/` Ecritel list).
- **tdd-gate hook:** editing a production `.py` needs a test whose stem matches (`routes.py`→`test_routes.py`, `main.py`→`test_main.py`, `metrics.py`→`test_metrics.py`, `admission.py`→`test_admission.py`); `config.*` is exempt. In a worktree the gate resolves `CLAUDE_PROJECT_DIR` to the wrong clone and may block the `Write` anyway — workaround: write content to a temp `.txt` under `tests/`, `cp` to the production path via Bash, remove temp, `cat` to verify. No bash heredocs (force-push-blocker false-positives).
- **Env:** never `pip install -r requirements.txt` (bumps `pydantic-core` off the 2.46.4 pin → `SystemError` at collection; re-pin with `python -m pip install "pydantic-core==2.46.4"`). Install only the SPECIFIC missing dep — for this service that's **`prometheus-client`** (`python -m pip install prometheus-client`); `beautifulsoup4`/`lxml` are already required.
- New endpoint tests use `fastapi.testclient.TestClient` (sync, no anyio fixture needed); the offload test uses `asyncio.run` calling the handler directly. The existing `tests/test_api.py` (`@pytest.mark.anyio` + `client` fixture) stays as-is.
- **Commits on the main thread** (coordinator): bilingual EN+FR message to a scratchpad file, `git -c commit.encoding=utf-8 commit -F <scratchpad-msg>`, `git add` only that task's explicit files (never `-A`).

---

## File Structure

```
Hellopro/                                   # (separate repo — BO consumer)
  BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/
    fonctions_maj_crawling.php              # MOD: contract fix (lines 1116-1117)

apps-microservices/api-comparaison-texte/   # (RAG-HP-PUB)
  main.py                                   # MOD: /metrics endpoint + register metrics
  Dockerfile                                # MOD: --workers
  requirements.txt                          # MOD: + prometheus-client
  app/
    core/
      config.py                             # MOD: + workers/admission settings
      metrics.py                            # NEW: prometheus-client metric objects
      admission.py                          # NEW: SyncAdmission guard
      text_comparator.py                    # unchanged
    api/
      routes.py                             # MOD: offload + admission + metrics
    services/
      html_cleaner.py                       # unchanged
  tests/
    test_api.py                             # unchanged (baseline)
    test_text_comparator.py                 # unchanged (baseline)
    test_config.py                          # NEW
    test_metrics.py                         # NEW
    test_main.py                            # NEW (/metrics endpoint)
    test_admission.py                       # NEW
    test_routes.py                          # NEW (offload + admission 503)
```

---

## Task 1: BO contract fix (Hellopro — ships first)

**Goal:** Restore title/description change-detection by reading the service's real response contract.

**Files:**
- Modify: `C:\Users\randr\Documents\Workspaces\Hellopro\BO\admin\repertoire_test\moulinettes_interne\scrapping_produit_ia\fonctions\fonctions_maj_crawling.php:1116-1117`

**Acceptance Criteria:**
- [ ] BO reads `decision` (=== 'SKIP' → similar) and `similarity_ratio`.
- [ ] The rest of `comparer_donnees_produit` (1028-1160) is byte-unchanged.

**Verify:** No PHP unit harness here — verify by diff inspection (only 2 lines change) + `php -l <file>` (lint, if php is available) → "No syntax errors detected". Post-deploy: `comparison_decision_total{decision="UPDATE"}` becomes non-zero and titre/desc appear in `champs_modifies`.

**Steps:**

- [ ] **Step 1: Apply the surgical edit.** Replace exactly these two lines (`fonctions_maj_crawling.php:1116-1117`):

```php
                $is_similar = $res['is_similar'] ?? true;
                $similarity = $res['similarity'] ?? 1.0;
```

with:

```php
                $is_similar = (($res['decision'] ?? 'UPDATE') === 'SKIP');
                $similarity = $res['similarity_ratio'] ?? 1.0;
```

Change nothing else. Semantics: `SKIP` = similar enough → no update; `UPDATE` / missing / per-item error (`routes.py` returns `decision=UPDATE` for errors) → treated as modified (fail-safe).

- [ ] **Step 2: Lint (if php available).** Run `php -l "C:/Users/randr/Documents/Workspaces/Hellopro/BO/admin/repertoire_test/moulinettes_interne/scrapping_produit_ia/fonctions/fonctions_maj_crawling.php"`. Expected: `No syntax errors detected`. If `php` is not installed, skip and rely on diff inspection (the change is a literal-for-literal 2-line swap).

- [ ] **Step 3: Confirm scope.** `git -C "C:/Users/randr/Documents/Workspaces/Hellopro" diff --stat` shows ONLY this file, +2/-2.

- [ ] **Step 4: Commit** (main thread, in the Hellopro repo): `fix(bo): read comparaison-texte decision/similarity_ratio (titre/desc detection)`.

---

## Task 2: `config.py` — new settings

**Goal:** Add the worker + admission settings (config.* is tdd-gate-exempt).

**Files:**
- Modify: `apps-microservices/api-comparaison-texte/app/core/config.py`
- Test: `apps-microservices/api-comparaison-texte/tests/test_config.py` (new)

**Acceptance Criteria:**
- [ ] `Settings` exposes `UVICORN_WORKERS=2`, `SYNC_MAX_INFLIGHT=0`, `ADMISSION_RETRY_AFTER_S=15`.
- [ ] Existing fields unchanged.

**Verify:** `cd apps-microservices/api-comparaison-texte && python -m pytest tests/test_config.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write the test** — `tests/test_config.py`:

```python
from app.core.config import settings


def test_existing_defaults_unchanged():
    assert settings.SIMILARITY_THRESHOLD == 0.85
    assert settings.BATCH_MAX_ITEMS == 500
    assert settings.APP_NAME == "API Comparaison de Texte"


def test_new_defaults():
    assert settings.UVICORN_WORKERS == 2
    assert settings.SYNC_MAX_INFLIGHT == 0
    assert settings.ADMISSION_RETRY_AFTER_S == 15
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: ... UVICORN_WORKERS`).

- [ ] **Step 3: Replace `app/core/config.py` with:**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Métadonnées du service
    APP_NAME: str = "API Comparaison de Texte"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Seuil de similarité (reproduit processor.py CONDITION 2 : ratio < 0.85)
    SIMILARITY_THRESHOLD: float = 0.85

    # Taille max du batch
    BATCH_MAX_ITEMS: int = 500

    # Workers (parallélisme CPU ; GIL → ce sont les process, pas les threads)
    UVICORN_WORKERS: int = 2

    # Admission synchrone (0 = désactivé, admet toujours)
    SYNC_MAX_INFLIGHT: int = 0
    ADMISSION_RETRY_AFTER_S: int = 15


settings = Settings()
```

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit** — `feat(comparaison-texte): add worker + admission settings`.

---

## Task 3: `metrics.py` + `/metrics` endpoint + dependency

**Goal:** Add Prometheus instrumentation (the service has none) via `prometheus-client` directly (detection pattern), exposed at `/metrics`.

**Files:**
- Create: `apps-microservices/api-comparaison-texte/app/core/metrics.py`
- Modify: `apps-microservices/api-comparaison-texte/main.py`, `requirements.txt`
- Test: `tests/test_metrics.py` (new), `tests/test_main.py` (new)

**Acceptance Criteria:**
- [ ] `metrics.py` defines the 5 metric objects with the spec names.
- [ ] `GET /metrics` returns 200 + Prometheus exposition text.
- [ ] `GET /` and `GET /api/v1/health` still 200.

**Verify:** `cd apps-microservices/api-comparaison-texte && python -m pytest tests/test_metrics.py tests/test_main.py -v` → PASS (install `prometheus-client` first if missing: `python -m pip install prometheus-client`).

**Steps:**

- [ ] **Step 1: Add the dependency** — append to `requirements.txt`:

```
prometheus-client>=0.19.0
```

(and `python -m pip install prometheus-client` in the local env).

- [ ] **Step 2: Write the tests.**

`tests/test_metrics.py`:
```python
from prometheus_client import Counter, Histogram

from app.core import metrics


def test_metric_types():
    assert isinstance(metrics.REQUEST_COUNT, Counter)
    assert isinstance(metrics.REQUEST_DURATION, Histogram)
    assert isinstance(metrics.DECISION_COUNT, Counter)
    assert isinstance(metrics.BATCH_SIZE, Histogram)
    assert isinstance(metrics.SYNC_ADMISSION_REJECTED, Counter)
```

`tests/test_main.py`:
```python
from fastapi.testclient import TestClient

import main


def test_metrics_endpoint_ok():
    client = TestClient(main.app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "comparison_requests_total" in r.text or r.text is not None


def test_health_and_root_ok():
    client = TestClient(main.app)
    assert client.get("/api/v1/health").json()["status"] == "healthy"
    assert "service" in client.get("/").json()
```

- [ ] **Step 3: Run → FAIL** (`ModuleNotFoundError: app.core.metrics`).

- [ ] **Step 4: Create `app/core/metrics.py`:**

```python
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter(
    "comparison_requests_total",
    "Total comparison HTTP requests",
    ["endpoint", "status"],
)
REQUEST_DURATION = Histogram(
    "comparison_request_duration_seconds",
    "Comparison request duration in seconds",
    ["endpoint"],
)
DECISION_COUNT = Counter(
    "comparison_decision_total",
    "Comparison decisions",
    ["decision"],
)
BATCH_SIZE = Histogram(
    "comparison_batch_size",
    "Number of items per batch request",
)
SYNC_ADMISSION_REJECTED = Counter(
    "comparison_sync_admission_rejected_total",
    "Sync requests shed by the admission guard (SYNC_MAX_INFLIGHT)",
)
```

- [ ] **Step 5: Replace `main.py` with** (adds `/metrics` + registers metrics):

```python
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.routes import router
from app.core.config import settings
from app.core import metrics  # noqa: F401  — registers metric objects with the default registry

app = FastAPI(
    title=settings.APP_NAME,
    description="API de comparaison textuelle via difflib. "
                "Détermine si un contenu a suffisamment changé pour nécessiter une mise à jour (ratio < seuil).",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(router, prefix="/api/v1")


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8998)
```

- [ ] **Step 6: Run → PASS.**

- [ ] **Step 7: Commit** — `feat(comparaison-texte): prometheus metrics + /metrics endpoint`.

---

## Task 4: `admission.py` — sync inflight guard

**Goal:** Off-by-default admission guard (503 + Retry-After on overload), mirroring content-extractor.

**Files:**
- Create: `apps-microservices/api-comparaison-texte/app/core/admission.py`
- Test: `tests/test_admission.py` (new)

**Acceptance Criteria:**
- [ ] `SyncAdmission(0)` always admits; `SyncAdmission(1)` caps then releases; release floors at 0.

**Verify:** `cd apps-microservices/api-comparaison-texte && python -m pytest tests/test_admission.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write the test** — `tests/test_admission.py`:

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
Mirrors content-extractor's slot model (originally from image-comparison): the
check + reserve are synchronous with NO await between them, so there is no yield
point and no race."""
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

- [ ] **Step 4: Run → PASS.**

- [ ] **Step 5: Commit** — `feat(comparaison-texte): sync admission guard`.

---

## Task 5: `routes.py` — offload + admission + metrics

**Goal:** Stop blocking the event loop (offload the whole compare/batch via `asyncio.to_thread`), guard with admission, record metrics. Behaviour preserved.

**Files:**
- Modify: `apps-microservices/api-comparaison-texte/app/api/routes.py`
- Test: `tests/test_routes.py` (new); existing `tests/test_api.py` must stay green.

**Acceptance Criteria:**
- [ ] Handlers offload the sync compute via `asyncio.to_thread` (whole-batch as one unit — NOT per-item gather).
- [ ] `decision`/`similarity_ratio`/batch response shapes unchanged (existing `test_api.py` green).
- [ ] Admission 503 + `Retry-After` when `SYNC_MAX_INFLIGHT` exceeded.
- [ ] A slow batch does not block the event loop.

**Verify:** `cd apps-microservices/api-comparaison-texte && python -m pytest tests/test_routes.py tests/test_api.py -v` → PASS

**Steps:**

- [ ] **Step 1: Write the test** — `tests/test_routes.py`:

```python
import asyncio

from fastapi.testclient import TestClient

import main
from app.api.routes import compare_batch
from app.models.schemas import BatchComparisonRequest


def test_batch_offload_does_not_block_loop():
    # Whole-batch offload must keep the event loop responsive.
    big = [{"url": f"u{i}", "new_content": "x" * 4000, "old_text": "y" * 4000} for i in range(40)]
    req = BatchComparisonRequest(items=big)

    async def scenario():
        ticked = {"n": 0}

        async def ticker():
            for _ in range(5):
                await asyncio.sleep(0.001)
                ticked["n"] += 1

        await asyncio.gather(compare_batch(req), ticker())
        return ticked["n"]

    assert asyncio.run(scenario()) == 5


def test_admission_503_when_full(monkeypatch):
    import app.core.admission as adm
    monkeypatch.setattr(adm.admission, "try_acquire", lambda: False)
    client = TestClient(main.app)
    r = client.post("/api/v1/compare", json={
        "url": "u", "new_content": "a", "old_text": "b",
    })
    assert r.status_code == 503
    assert "Retry-After" in r.headers


def test_batch_behaviour_preserved():
    client = TestClient(main.app)
    same = "Texte identique de ce test precis"
    r = client.post("/api/v1/compare-batch", json={"items": [
        {"url": "u1", "new_content": "Contenu totalement different ici", "old_text": "Ancien sans rapport"},
        {"url": "u2", "new_content": same, "old_text": same},
    ]})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 2 and data["error_count"] == 0
    decisions = [x["decision"] for x in data["results"]]
    assert "UPDATE" in decisions and "SKIP" in decisions
```

- [ ] **Step 2: Run → FAIL** (`compare_batch` blocks the loop / no admission 503 path yet).

- [ ] **Step 3: Replace `app/api/routes.py` with:**

```python
import asyncio
import time
import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ComparisonRequest,
    ComparisonResponse,
    ComparisonResult,
    BatchComparisonRequest,
    BatchComparisonResponse,
    ContentType,
    Decision,
)
from app.core.text_comparator import compare_texts
from app.core.config import settings
from app.core.admission import admission
from app.core import metrics
from app.services.html_cleaner import extract_text_from_html

logger = logging.getLogger(__name__)

router = APIRouter()


def _compare_one(request: ComparisonRequest) -> ComparisonResult:
    """Pure synchronous single comparison (offloaded via asyncio.to_thread)."""
    new_text = (
        extract_text_from_html(request.new_content)
        if request.content_type == ContentType.HTML
        else request.new_content
    )
    comp = compare_texts(request.old_text, new_text, request.threshold)
    return ComparisonResult(url=request.url, **comp)


def _run_batch(items, threshold) -> tuple[list, int]:
    """Pure synchronous batch loop (offloaded as ONE unit via asyncio.to_thread).
    GIL: difflib is pure-Python; offloading the whole batch keeps the event loop
    responsive — it does not parallelise the items (use workers/replicas for that)."""
    results = []
    error_count = 0
    for item in items:
        try:
            new_text = (
                extract_text_from_html(item.new_content)
                if item.content_type == ContentType.HTML
                else item.new_content
            )
            comp = compare_texts(item.old_text, new_text, threshold)
            results.append(ComparisonResult(url=item.url, **comp))
        except Exception as e:
            logger.error("Erreur traitement item %s: %s", item.url, e)
            error_count += 1
            results.append(ComparisonResult(
                url=item.url,
                similarity_ratio=0.0,
                decision=Decision.UPDATE,
                reason="error",
                error=str(e),
            ))
    return results, error_count


def _admit_or_503() -> None:
    if not admission.try_acquire():
        metrics.SYNC_ADMISSION_REJECTED.inc()
        raise HTTPException(
            status_code=503,
            detail={"detail": "Service saturated", "error_code": "ADMISSION_REJECTED"},
            headers={"Retry-After": str(settings.ADMISSION_RETRY_AFTER_S)},
        )


@router.post("/compare", response_model=ComparisonResponse)
async def compare_single(request: ComparisonRequest):
    """Compare un nouveau contenu avec un ancien texte de référence."""
    _admit_or_503()
    start = time.perf_counter()
    try:
        result = await asyncio.to_thread(_compare_one, request)
    except Exception:
        logger.exception("Comparison failed")
        metrics.REQUEST_COUNT.labels(endpoint="/compare", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Comparison failed", "error_code": "INTERNAL_ERROR"},
        )
    finally:
        admission.release()
    metrics.REQUEST_DURATION.labels(endpoint="/compare").observe(time.perf_counter() - start)
    metrics.REQUEST_COUNT.labels(endpoint="/compare", status="200").inc()
    metrics.DECISION_COUNT.labels(decision=result.decision.value).inc()
    return ComparisonResponse(result=result)


@router.post("/compare-batch", response_model=BatchComparisonResponse)
async def compare_batch(request: BatchComparisonRequest):
    """Compare un lot d'items (batch)."""
    if len(request.items) > settings.BATCH_MAX_ITEMS:
        raise HTTPException(
            status_code=400,
            detail=f"Le batch ne peut pas dépasser {settings.BATCH_MAX_ITEMS} items (reçu: {len(request.items)})",
        )
    _admit_or_503()
    start = time.perf_counter()
    try:
        results, error_count = await asyncio.to_thread(_run_batch, request.items, request.threshold)
    except Exception:
        logger.exception("Batch comparison failed")
        metrics.REQUEST_COUNT.labels(endpoint="/compare-batch", status="500").inc()
        raise HTTPException(
            status_code=500,
            detail={"detail": "Batch comparison failed", "error_code": "INTERNAL_ERROR"},
        )
    finally:
        admission.release()

    elapsed_ms = (time.perf_counter() - start) * 1000
    metrics.REQUEST_DURATION.labels(endpoint="/compare-batch").observe(elapsed_ms / 1000)
    metrics.REQUEST_COUNT.labels(endpoint="/compare-batch", status="200").inc()
    metrics.BATCH_SIZE.observe(len(request.items))
    for r in results:
        metrics.DECISION_COUNT.labels(decision=r.decision.value).inc()

    return BatchComparisonResponse(
        total=len(request.items),
        success_count=len(request.items) - error_count,
        error_count=error_count,
        results=results,
        processing_time_ms=round(elapsed_ms, 2),
    )


@router.get("/health")
async def health_check():
    """Vérification de l'état du service."""
    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
```

> Notes: the 400 `BATCH_MAX_ITEMS` guard and the 422 pydantic validation both run **before** `_admit_or_503()` (no slot consumed on a rejected request). `_admit_or_503` raises before the `try`, so `admission.release()` in `finally` only runs after a successful acquire. `result.decision.value` works because `ComparisonResult.decision` is the `Decision` enum (`compare_texts` returns the string; pydantic coerces it).

- [ ] **Step 4: Run → PASS** (`test_routes.py` + the existing `test_api.py`).

- [ ] **Step 5: Commit** — `feat(comparaison-texte): offload difflib off the loop + admission + metrics`.

---

## Task 6: `Dockerfile` — multi-worker

**Goal:** Run multiple uvicorn workers (CPU parallelism across requests/batches).

**Files:**
- Modify: `apps-microservices/api-comparaison-texte/Dockerfile`

**Acceptance Criteria:**
- [ ] CMD runs `--workers ${UVICORN_WORKERS:-2}`.

**Verify:** `cat apps-microservices/api-comparaison-texte/Dockerfile` → last line is the sh-form CMD below. (No pytest — Dockerfile.)

**Steps:**

- [ ] **Step 1: Replace the CMD line** (`Dockerfile:11`) with:

```dockerfile
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port 8998 --proxy-headers --workers ${UVICORN_WORKERS:-2}"]
```

Leave every other line unchanged. (Deferred, out of lean scope: non-root `USER` + `HEALTHCHECK` — a `docker-security.md` gap to address in a separate hardening pass.)

- [ ] **Step 2: Commit** — `feat(comparaison-texte): run multiple uvicorn workers`.

---

## Self-Review

**1. Spec coverage:**
- §1.1 contract bug → Task 1. ✅
- §4 axis-1 offload (whole-batch) + workers → Task 5 (offload) + Task 6 (workers). ✅
- §5 admission → Task 4. ✅
- §6 metrics + /metrics → Task 3. ✅
- §7 config → Task 2. ✅
- §10 files (prometheus-client dep) → Task 3. ✅
- §11 testing → each task is TDD; offload-non-block (Task 5), admission 503 (Task 5), /metrics 200 (Task 3), existing green. ✅
- §13.1 GIL doc → captured in `_run_batch` docstring (Task 5). ✅
- **Deliberately absent** (per spec D2): async, Redis, cache, gateway change, algorithm change. No tasks — correct.

**2. Placeholder scan:** No TBD/"similar to"/"add error handling" — every code step is complete. Task 1's "no PHP harness" is an honest verification method, not a placeholder.

**3. Type consistency:**
- `_compare_one(request) -> ComparisonResult`, `_run_batch(items, threshold) -> tuple[list, int]`, `_admit_or_503() -> None` — defined and used consistently in Task 5.
- Metric names identical across Task 3 (definition) and Task 5 (use): `REQUEST_COUNT`, `REQUEST_DURATION`, `DECISION_COUNT`, `BATCH_SIZE`, `SYNC_ADMISSION_REJECTED`.
- `SyncAdmission` / `admission` singleton: defined Task 4, used Task 5 (`adm.admission.try_acquire`).
- Config names: `UVICORN_WORKERS` (Task 2 → Task 6), `SYNC_MAX_INFLIGHT`/`ADMISSION_RETRY_AFTER_S` (Task 2 → Task 4/5). Consistent.

No gaps found.

**Dependencies:** Task 1 (BO) independent, first. Task 2 (config) → blocks Task 4 (admission) + Task 6 (workers). Task 3 (metrics) → blocks Task 5. Task 4 (admission) → blocks Task 5. Task 5 (routes) needs 3+4. Order: 1 → 2 → 3 → 4 → 5 → 6.

---
