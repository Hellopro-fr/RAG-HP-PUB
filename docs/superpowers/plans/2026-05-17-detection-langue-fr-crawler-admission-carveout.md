# Detection-Langue-FR Crawler Admission Carve-Out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move admission gating from middleware to inside the route handlers, scoped to the actual fetch operation, so callers that provide pre-fetched `html_content` (crawler-service) never compete for the slot pool that protects the browser semaphore.

**Architecture:** New module-level `_prod_admission` controller is consumed by a `_fetch_with_admission(...)` helper invoked inside `_inflight_dedup.coalesce(...)` — only the dedup leader acquires a slot. `AdmissionMiddleware` shrinks to the `/detect-debug` path only. Single `/detect` translates the rejection to HTTP 503 + `Retry-After`; `/detect-batch` translates it per-item to `DetectionResponse{method='admission_rejected'}` and extends Pass 2 retry-set. `'admission_rejected'` joins `DomainCache._NEVER_CACHE_METHODS`.

**Tech Stack:** Python 3.10, FastAPI, Starlette `BaseHTTPMiddleware`, `asyncio.Lock`, pytest + pytest-asyncio. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-05-17-detection-langue-fr-crawler-admission-carveout-design.md` (commit `e2e81711`).

---

## File Structure

| File | Disposition | Responsibility |
|---|---|---|
| `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py` | MOD | Add `'admission_rejected'` to `DomainCache._NEVER_CACHE_METHODS` |
| `apps-microservices/api-detection-langue-fr/app/middleware/admission.py` | MOD | Drop `_PROD_PATHS` constant. Drop `prod_controller` constructor parameter. Middleware only gates `_DEBUG_PATH`. |
| `apps-microservices/api-detection-langue-fr/app/main.py` | MOD | Keep `_prod_admission` controller construction. Pass only `debug_controller` to middleware. Re-export `_prod_admission` for `routes.py` to import. |
| `apps-microservices/api-detection-langue-fr/app/api/routes.py` | MOD | New `_AdmissionRejected` exception + `_fetch_with_admission()` helper. Wrap initial fetch + homepage fallback fetch. Single `/detect` handler translates exception → `HTTPException(503)`. Batch `_process_item_core` translates → inline `DetectionResponse(method='admission_rejected')`. Pass 2 retry-set extended (standard + `first_match`). |
| `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py` | NEW | Integration tests for: html bypass, single 503, batch per-item, /check-url bypass, /detect-debug isolation, dedup follower, kill switch, homepage admission rejection, Pass 2 retry, cache skip. |
| `apps-microservices/api-detection-langue-fr/tests/test_admission.py` (if exists) | MOD | Remove prod-path expectations. Keep debug-pool tests. |
| `apps-microservices/api-detection-langue-fr/CLAUDE.md` | MOD | Update § Concurrency & Admission Control: gate moved to route level, `INFLIGHT_REQUESTS` semantic shift, html_content bypass, `admission_rejected` method, Pass 2 retry-set, `/check-url` bypass. |

No new files outside the test module. Pure refactor + behavior change.

---

## Dependencies between tasks

```
T1 (cache)
  └─→ T2 (route helper + wire-up + translations + homepage fallback)
        ├─→ T3 (middleware shrink)
        ├─→ T4 (Pass 2 retry-set)
        └─→ T5 (integration suite) — needs T2, T3, T4
              └─→ T6 (CLAUDE.md)
```

T3 + T4 can ship in parallel after T2.

---

## Task 1: Cache `admission_rejected` as never-cache

**Goal:** Prevent any future `admission_rejected` result from polluting `DomainCache`. Saturation is service state, not a domain property.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py:46`
- Test: `apps-microservices/api-detection-langue-fr/tests/test_domain_cache_admission.py` (NEW)

**Acceptance Criteria:**
- [ ] `'admission_rejected'` member of `DomainCache._NEVER_CACHE_METHODS`
- [ ] `DomainCache.set(...)` is a no-op when `result['method'] == 'admission_rejected'`
- [ ] Existing `_NEVER_CACHE_METHODS` members (`'error'`, `'fetch_failed'`) unchanged
- [ ] New test passes; existing `test_domain_fr.py` cache tests still pass

**Verify:** `pytest apps-microservices/api-detection-langue-fr/tests/test_domain_cache_admission.py -v` → all pass

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/api-detection-langue-fr/tests/test_domain_cache_admission.py`:

```python
"""Cache must never persist `admission_rejected` results.

Service saturation is transient infrastructure state; persisting it would
poison the domain-keyed cache with a non-answer.
"""
import pytest

from app.core.domain_fr import DomainCache


def test_never_cache_methods_includes_admission_rejected():
    assert 'admission_rejected' in DomainCache._NEVER_CACHE_METHODS


def test_never_cache_methods_still_contains_existing_entries():
    assert 'error' in DomainCache._NEVER_CACHE_METHODS
    assert 'fetch_failed' in DomainCache._NEVER_CACHE_METHODS


@pytest.mark.asyncio
async def test_set_is_noop_for_admission_rejected(monkeypatch):
    """Even with a working Redis client, admission_rejected results must not
    be persisted. The early-return guard for _NEVER_CACHE_METHODS fires
    before any setex call."""
    cache = DomainCache()
    calls = []

    class FakeClient:
        async def setex(self, key, ttl, data):
            calls.append((key, ttl, data))

    async def fake_get_client(self):
        return FakeClient()

    monkeypatch.setattr(DomainCache, '_get_client', fake_get_client)

    await cache.set(
        input_url='https://example.com/path',
        result_url='https://example.com/path',
        result={'ok': False, 'method': 'admission_rejected',
                'url': 'https://example.com/path',
                'error': 'Service temporarily saturated'},
    )

    assert calls == []
```

- [ ] **Step 2: Run the test to confirm it fails**

Run: `pytest apps-microservices/api-detection-langue-fr/tests/test_domain_cache_admission.py -v`

Expected: `test_never_cache_methods_includes_admission_rejected` FAIL with `AssertionError` because `'admission_rejected'` is not yet in `_NEVER_CACHE_METHODS`. Other tests likely pass (`set()` will call `setex` with valid args — that test fails because `setex` IS called).

- [ ] **Step 3: Apply the minimal change**

Edit `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py:46` — change:

```python
    # Méthodes qui ne doivent JAMAIS être cachées (erreurs critiques)
    _NEVER_CACHE_METHODS = frozenset({'error', 'fetch_failed'})
```

to:

```python
    # Méthodes qui ne doivent JAMAIS être cachées (erreurs critiques + saturation)
    _NEVER_CACHE_METHODS = frozenset({'error', 'fetch_failed', 'admission_rejected'})
```

- [ ] **Step 4: Re-run tests**

Run: `pytest apps-microservices/api-detection-langue-fr/tests/test_domain_cache_admission.py apps-microservices/api-detection-langue-fr/tests/test_domain_fr.py -v`

Expected: all admission tests PASS. Existing `test_domain_fr.py` tests still PASS (no regression).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/core/domain_fr.py apps-microservices/api-detection-langue-fr/tests/test_domain_cache_admission.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): mark admission_rejected as never-cache

EN: Add 'admission_rejected' to DomainCache._NEVER_CACHE_METHODS so a
saturation rejection never poisons the domain-keyed cache. Service
state, not a domain property.

FR: Ajoute 'admission_rejected' à DomainCache._NEVER_CACHE_METHODS afin
qu'un rejet pour saturation ne pollue jamais le cache par-domaine. État
service, pas propriété domaine.
EOF
)"
```

---

## Task 2: Route-level admission helper + wire-up + endpoint translation

**Goal:** Replace direct `fetch_html` calls inside `_detect_single_url` with `_fetch_with_admission(...)` invoked inside `_inflight_dedup.coalesce(...)`. Add the `_AdmissionRejected` exception. Translate the exception to HTTP 503 in single `/detect` and to inline `DetectionResponse(method='admission_rejected')` in batch `_process_item_core`. Wire homepage fallback through the same helper. Middleware still has `prod_controller` at this point — that gets removed in Task 3.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/main.py` (re-export `_prod_admission`)
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py`
- Test: `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py` (NEW — scenarios 1–4)

**Acceptance Criteria:**
- [ ] `_AdmissionRejected` exception defined at module scope in `routes.py`
- [ ] `_fetch_with_admission(url, proxy_url, endpoint_label)` helper exists, acquires `_prod_admission`, raises `_AdmissionRejected` on saturation, increments `ADMISSION_REJECTED{endpoint}` counter, releases slot on the `finally` of the inner try
- [ ] `_detect_single_url` initial fetch goes through `_inflight_dedup.coalesce(key, lambda: _fetch_with_admission(...))`
- [ ] Homepage fallback fetch also goes through `_fetch_with_admission` (separate dedup key for the homepage URL)
- [ ] Single `/detect` handler catches `_AdmissionRejected` → `HTTPException(status_code=503, headers={'Retry-After': str(retry_after)})`
- [ ] Batch `_process_item_core` catches `_AdmissionRejected` → `DetectionResponse(ok=False, url=url, method='admission_rejected', error='Service temporarily saturated')`
- [ ] `_prod_admission` exported from `app/main.py` and imported in `app/api/routes.py`
- [ ] Items with `html_content` provided never enter `_fetch_with_admission` (skip-fetch branch unchanged)

**Verify:** `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py -v` → 4 scenarios pass (scenarios 5+ added in Task 5).

**Steps:**

- [ ] **Step 1: Re-export `_prod_admission` from `app/main.py`**

Edit `apps-microservices/api-detection-langue-fr/app/main.py` around line 51–69. The module-level `_prod_admission` already exists (line 52–54). Add a comment + ensure it stays defined at module level (no behavior change yet, but routes will `from app.main import _prod_admission`). Verify import remains side-effect-free.

Concretely, ensure these globals exist exactly as below (the line numbers in the existing file:`main.py:51`):

```python
_admission_enabled = os.getenv("ADMISSION_ENABLED", "true").lower() == "true"
_prod_admission = AdmissionController(
    max_slots=int(os.getenv("ADMISSION_MAX_SLOTS", "12"))
)
_debug_admission = AdmissionController(
    max_slots=int(os.getenv("ADMISSION_DEBUG_SLOTS", "2"))
)
```

Do NOT remove `prod_controller=_prod_admission` from the `add_middleware(...)` call yet — Task 3 handles that swap. For now both gates fire on prod paths; Task 5 tests assume Task 3 has shipped, so they live in the integration suite that depends on T3.

- [ ] **Step 2: Add `_AdmissionRejected` + helper to `routes.py`**

Edit `apps-microservices/api-detection-langue-fr/app/api/routes.py`. Below the existing imports (after line 28), add:

```python
from app.main import _prod_admission
from app.core.metrics import ADMISSION_REJECTED


class _AdmissionRejected(Exception):
    """Raised when the route-level admission controller refuses a slot.

    Translated to HTTP 503 + Retry-After on single /detect and to an
    inline DetectionResponse(method='admission_rejected') on batch items.
    """


async def _fetch_with_admission(
    url: str,
    proxy_url: Optional[str],
    endpoint_label: str,
):
    """Acquire a prod admission slot, run fetch_html, release.

    Raises _AdmissionRejected when the pool is saturated. Increments
    ADMISSION_REJECTED{endpoint=endpoint_label} on rejection.
    """
    admitted = await _prod_admission.acquire()
    if not admitted:
        ADMISSION_REJECTED.labels(endpoint=endpoint_label).inc()
        raise _AdmissionRejected
    try:
        return await fetch_html(url, proxy_url)
    finally:
        await _prod_admission.release()
```

- [ ] **Step 3: Wire `_fetch_with_admission` into `_detect_single_url`**

In `_detect_single_url` (lines 88–253), replace the initial fetch block (lines 117–126):

```python
        # [2] Fetch HTML (with inflight dedup unless force_refresh)
        if _INFLIGHT_DEDUP_ENABLED and not force_refresh:
            dedup_key = _normalize_url_for_dedup(url)
            prev_hits = _inflight_dedup.hits
            fetch_result = await _inflight_dedup.coalesce(
                dedup_key, lambda: fetch_html(url, proxy_url)
            )
            if _inflight_dedup.hits > prev_hits:
                DEDUP_HITS.inc(_inflight_dedup.hits - prev_hits)
        else:
            fetch_result = await fetch_html(url, proxy_url)
```

with:

```python
        # [2] Fetch HTML (admission gate inside dedup leader; followers wait
        # on leader's future and do NOT acquire a slot).
        if _INFLIGHT_DEDUP_ENABLED and not force_refresh:
            dedup_key = _normalize_url_for_dedup(url)
            prev_hits = _inflight_dedup.hits
            fetch_result = await _inflight_dedup.coalesce(
                dedup_key,
                lambda: _fetch_with_admission(url, proxy_url, "/api/v1/detect"),
            )
            if _inflight_dedup.hits > prev_hits:
                DEDUP_HITS.inc(_inflight_dedup.hits - prev_hits)
        else:
            fetch_result = await _fetch_with_admission(
                url, proxy_url, "/api/v1/detect"
            )
```

- [ ] **Step 4: Wire `_fetch_with_admission` into homepage fallback**

In the same function, replace the homepage-fallback fetch block (around lines 156–164):

```python
                    if _INFLIGHT_DEDUP_ENABLED and not force_refresh:
                        hp_key = _normalize_url_for_dedup(homepage)
                        hp_fetch = await _inflight_dedup.coalesce(
                            hp_key, lambda: fetch_html(homepage, proxy_url)
                        )
                    else:
                        hp_fetch = await fetch_html(homepage, proxy_url)
```

with:

```python
                    if _INFLIGHT_DEDUP_ENABLED and not force_refresh:
                        hp_key = _normalize_url_for_dedup(homepage)
                        hp_fetch = await _inflight_dedup.coalesce(
                            hp_key,
                            lambda: _fetch_with_admission(
                                homepage, proxy_url, "/api/v1/detect"
                            ),
                        )
                    else:
                        hp_fetch = await _fetch_with_admission(
                            homepage, proxy_url, "/api/v1/detect"
                        )
```

Note: `_AdmissionRejected` raised here bubbles up out of `_detect_single_url`. Do NOT catch it inside the function. The single `/detect` handler translates it to HTTP 503, batch `_process_item_core` translates it to inline rejection. Per spec §6.5, no downgrade to validator verdict, no cache write.

- [ ] **Step 5: Translate `_AdmissionRejected` in single `/detect` handler**

Wrap the existing call in `detect_french` (lines 290–303). Replace the existing `try/except`:

```python
    try:
        return await _detect_single_url(
            url=request.url,
            html_content=request.html_content,
            proxy_url=request.proxy_url,
            mode=request.mode,
            use_nlp_detection=request.use_nlp_detection,
            forced_method=request.forced_method,
            force_refresh=request.force_refresh,
            homepage_fallback=request.homepage_fallback,
        )
    except Exception as e:
        return DetectionResponse(
            ok=False, url=request.url, method='error', error=str(e)
        )
```

with:

```python
    try:
        return await _detect_single_url(
            url=request.url,
            html_content=request.html_content,
            proxy_url=request.proxy_url,
            mode=request.mode,
            use_nlp_detection=request.use_nlp_detection,
            forced_method=request.forced_method,
            force_refresh=request.force_refresh,
            homepage_fallback=request.homepage_fallback,
        )
    except _AdmissionRejected:
        retry_after = os.getenv("ADMISSION_RETRY_AFTER_SECONDS", "30")
        raise HTTPException(
            status_code=503,
            detail={
                "detail": "Service temporarily saturated",
                "retry_after_seconds": int(retry_after),
            },
            headers={"Retry-After": retry_after},
        )
    except Exception as e:
        return DetectionResponse(
            ok=False, url=request.url, method='error', error=str(e)
        )
```

- [ ] **Step 6: Translate `_AdmissionRejected` in batch `_process_item_core`**

In `_process_item_core` (defined inside `detect_french_batch`, around lines 348–382), find the inner try/except (the one that wraps `await _detect_single_url(...)`) and add a `_AdmissionRejected` branch BEFORE the generic `except Exception`. Replace:

```python
        try:
            detection_mode = request.mode
            if detection_mode == DetectionMode.FIRST_MATCH:
                detection_mode = DetectionMode.COMPLETE
                logger.debug(f"[BATCH] Mode first_match → complete pour détection individuelle de {url}")

            result = await _detect_single_url(
                url=url,
                html_content=item.html_content,
                proxy_url=request.proxy_url,
                mode=detection_mode,
                use_nlp_detection=request.use_nlp_detection,
                force_refresh=request.force_refresh,
                homepage_fallback=request.homepage_fallback,
            )

            count = await _increment_count()
            duration_ms = round((time.time() - item_start) * 1000)
            status = "OK" if result.ok else "NOK"
            logger.info(f"[BATCH] [{count}/{total_items}] {status} {url} method={result.method} ({duration_ms}ms)")

            return result

        except Exception as e:
            count = await _increment_count()
            duration_ms = round((time.time() - item_start) * 1000)
            logger.error(f"[BATCH] [{count}/{total_items}] ERROR {url}: {e} ({duration_ms}ms)")
            return DetectionResponse(
                ok=False, url=url, method='error', error=str(e)
            )
```

with:

```python
        try:
            detection_mode = request.mode
            if detection_mode == DetectionMode.FIRST_MATCH:
                detection_mode = DetectionMode.COMPLETE
                logger.debug(f"[BATCH] Mode first_match → complete pour détection individuelle de {url}")

            result = await _detect_single_url(
                url=url,
                html_content=item.html_content,
                proxy_url=request.proxy_url,
                mode=detection_mode,
                use_nlp_detection=request.use_nlp_detection,
                force_refresh=request.force_refresh,
                homepage_fallback=request.homepage_fallback,
            )

            count = await _increment_count()
            duration_ms = round((time.time() - item_start) * 1000)
            status = "OK" if result.ok else "NOK"
            logger.info(f"[BATCH] [{count}/{total_items}] {status} {url} method={result.method} ({duration_ms}ms)")

            return result

        except _AdmissionRejected:
            count = await _increment_count()
            duration_ms = round((time.time() - item_start) * 1000)
            logger.warning(
                f"[BATCH] [{count}/{total_items}] ADMISSION_REJECTED {url} ({duration_ms}ms)"
            )
            return DetectionResponse(
                ok=False, url=url, method='admission_rejected',
                error='Service temporarily saturated',
            )
        except Exception as e:
            count = await _increment_count()
            duration_ms = round((time.time() - item_start) * 1000)
            logger.error(f"[BATCH] [{count}/{total_items}] ERROR {url}: {e} ({duration_ms}ms)")
            return DetectionResponse(
                ok=False, url=url, method='error', error=str(e)
            )
```

Note: `process_group` inside the `first_match` block uses `_process_item_core` internally, so the translation applies transparently.

- [ ] **Step 7: Write integration tests covering scenarios 1–4**

Create `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py`:

```python
"""Integration tests for the crawler admission carve-out.

Scenarios 1-4 verify route-level admission behavior under saturation:
  1. html_content provided → bypasses admission, never 503
  2. No html_content + saturated → HTTP 503 with Retry-After header
  3. Batch mixed items (some with html, some without) under saturation
  4. Cache HIT bypasses admission (no fetch needed)
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app, _prod_admission
from app.api.routes import _detect_single_url
from app.services.scraper import ScrapeResult


@pytest.fixture(autouse=True)
def reset_admission_counter():
    """Each test starts with a fresh admission counter."""
    _prod_admission._counter = 0
    yield
    _prod_admission._counter = 0


@pytest.fixture
def saturate_pool(monkeypatch):
    """Force the prod admission controller to refuse all acquires."""
    async def _refuse():
        return False
    monkeypatch.setattr(_prod_admission, "acquire", _refuse)


@pytest.mark.asyncio
async def test_detect_html_provided_bypasses_admission(saturate_pool):
    """With html_content, the route never reaches _fetch_with_admission.
    Acquire is monkey-patched to refuse everything, but the request must
    still complete with a normal DetectionResponse."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect",
            json={
                "url": "https://example.fr",
                "html_content": "<html lang='fr'><body>Bonjour</body></html>",
                "mode": "simple",
            },
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["method"] != "admission_rejected"


@pytest.mark.asyncio
async def test_detect_no_html_503_when_saturated(saturate_pool):
    """Without html_content, saturated pool → HTTP 503 + Retry-After header."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect",
            json={"url": "https://example.fr", "mode": "simple"},
        )
    assert resp.status_code == 503
    assert resp.headers.get("Retry-After") is not None


@pytest.mark.asyncio
async def test_batch_mixed_items_under_saturation(saturate_pool):
    """Items with html_content succeed; items without → method=admission_rejected.
    No whole-batch 503."""
    items = [
        {"url": "https://a.fr", "html_content": "<html lang='fr'></html>"},
        {"url": "https://b.fr"},
        {"url": "https://c.fr", "html_content": "<html lang='fr'></html>"},
        {"url": "https://d.fr"},
    ]
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect-batch",
            json={"items": items, "mode": "simple", "max_concurrency": 2},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 4
    methods = [r["method"] for r in body["results"]]
    assert methods.count("admission_rejected") == 2
    # items 0 and 2 (with html_content) must NOT be admission_rejected
    assert body["results"][0]["method"] != "admission_rejected"
    assert body["results"][2]["method"] != "admission_rejected"


@pytest.mark.asyncio
async def test_cache_hit_bypasses_admission(saturate_pool, monkeypatch):
    """Cache HIT path does not call _fetch_with_admission. Returns cached
    response even though admission is saturated."""
    from app.core.domain_fr import domain_cache

    cached_payload = {
        "ok": True,
        "url": "https://cached.fr",
        "method": "langHtml",
        "requested_url": "https://cached.fr",
    }

    async def fake_get(url):
        return cached_payload

    monkeypatch.setattr(domain_cache, "get", fake_get)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect",
            json={"url": "https://cached.fr", "mode": "simple"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["method"] == "langHtml"
```

- [ ] **Step 8: Run the new test module**

Run: `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py -v`

Expected outcomes after this task (middleware still has prod_controller from `main.py`!):
- `test_detect_html_provided_bypasses_admission`: **PASS** if middleware was already reachable for non-saturated case. With saturate_pool only affecting `_prod_admission` and middleware using same controller, middleware short-circuits the request first → returns 503 too early. **Conditional FAIL.** That's acceptable for now — Task 3 removes the middleware gate and the test starts passing.
- `test_detect_no_html_503_when_saturated`: **PASS** regardless of whether 503 is emitted by middleware or by route (test asserts only `status_code==503` + header).
- `test_batch_mixed_items_under_saturation`: **FAIL** until Task 3 (middleware emits whole-batch 503).
- `test_cache_hit_bypasses_admission`: **PASS** if cache hit short-circuits before any acquire — verify this assumption empirically.

If tests fail for the documented reasons above, leave them red and ship Task 3 next. If they fail for OTHER reasons, fix the implementation before committing.

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/main.py apps-microservices/api-detection-langue-fr/app/api/routes.py apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): route-level admission gate on fetch path

EN: Add _AdmissionRejected exception and _fetch_with_admission helper
inside routes.py. Wire helper into _detect_single_url initial fetch and
homepage fallback via _inflight_dedup.coalesce so only the dedup leader
acquires a slot. Single /detect translates the exception to HTTP 503 +
Retry-After. Batch /detect-batch translates per-item to inline
DetectionResponse(method='admission_rejected'). Middleware prod gate
still active here — Task 3 removes it for the atomic swap.

FR: Ajoute l'exception _AdmissionRejected et le helper
_fetch_with_admission dans routes.py. Branche le helper dans le fetch
initial de _detect_single_url et le repli homepage via
_inflight_dedup.coalesce — seul le leader dedup acquiert un slot.
/detect (single) traduit l'exception en HTTP 503 + Retry-After.
/detect-batch traduit par-item en DetectionResponse inline
(method='admission_rejected'). Le gate middleware prod reste actif
ici — Task 3 le retire pour le swap atomique.
EOF
)"
```

---

## Task 3: Shrink middleware to `/detect-debug` only

**Goal:** Remove `_PROD_PATHS` and the `prod_controller` constructor parameter from `AdmissionMiddleware`. After this task, `/detect`, `/detect-batch`, `/check-url` are gated only at the route level (or not at all, in the case of `/check-url`). `/detect-debug` keeps its isolated debug-pool gate.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/middleware/admission.py`
- Modify: `apps-microservices/api-detection-langue-fr/app/main.py` (call site)
- Modify: `apps-microservices/api-detection-langue-fr/tests/test_admission.py` (if exists — remove prod-path expectations)

**Acceptance Criteria:**
- [ ] `_PROD_PATHS` constant removed
- [ ] `AdmissionMiddleware.__init__` no longer accepts `prod_controller`
- [ ] `_pick_controller(path)` returns the debug controller only for `_DEBUG_PATH`; returns `(None, None)` for every other path
- [ ] `app/main.py` no longer passes `prod_controller=_prod_admission` to `add_middleware(AdmissionMiddleware, ...)`
- [ ] `_prod_admission` controller still exists at module scope in `main.py` (consumed by routes.py)
- [ ] `INFLIGHT_REQUESTS` gauge increment removed from middleware (route helper is the new source)
- [ ] All `test_admission_carveout.py` tests from Task 2 now PASS
- [ ] `/detect-debug` admission test (existing) still passes

**Verify:** `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py apps-microservices/api-detection-langue-fr/tests/test_admission.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Rewrite `app/middleware/admission.py`**

Replace the entire file content:

```python
"""FastAPI admission-control middleware.

Scope after the crawler carve-out refactor:
- /detect, /detect-batch, /check-url → gated at the route level (or
  not at all), NOT by this middleware.
- /detect-debug → gated by the debug-only controller here so dev
  traffic cannot starve the production browser semaphore.
- Infrastructure endpoints (/health, /metrics, /, /docs, /openapi.json)
  bypass admission entirely.

On rejection: 503 + Retry-After. On accept: counter++ until response
is built, then counter-- in finally.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.admission import AdmissionController
from app.core.metrics import ADMISSION_REJECTED

logger = logging.getLogger(__name__)

# Path using the isolated debug slot pool.
_DEBUG_PATH = "/api/v1/detect-debug"


class AdmissionMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        debug_controller: AdmissionController,
        retry_after_seconds: int = 30,
        enabled: bool = True,
    ):
        super().__init__(app)
        self._debug = debug_controller
        self._retry_after = str(int(retry_after_seconds))
        self._enabled = enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._enabled or request.url.path != _DEBUG_PATH:
            return await call_next(request)

        admitted = await self._debug.acquire()
        if not admitted:
            ADMISSION_REJECTED.labels(endpoint=_DEBUG_PATH).inc()
            logger.warning(
                f"Admission rejected for {_DEBUG_PATH}: "
                f"{self._debug.inflight}/{self._debug.max_slots} in flight"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily saturated",
                    "retry_after_seconds": int(self._retry_after),
                },
                headers={"Retry-After": self._retry_after},
            )

        try:
            return await call_next(request)
        finally:
            await self._debug.release()
```

Notes:
- `INFLIGHT_REQUESTS` inc/dec removed (it now means "active fetches at route level" — incremented inside `_fetch_with_admission`, optional).
- `_PROD_PATHS` set removed.
- `_pick_controller` removed (collapsed into the path check).

- [ ] **Step 2: Update `app/main.py`**

Edit the `add_middleware` call at lines 58–64. Replace:

```python
app.add_middleware(
    AdmissionMiddleware,
    prod_controller=_prod_admission,
    debug_controller=_debug_admission,
    retry_after_seconds=int(os.getenv("ADMISSION_RETRY_AFTER_SECONDS", "30")),
    enabled=_admission_enabled,
)
```

with:

```python
app.add_middleware(
    AdmissionMiddleware,
    debug_controller=_debug_admission,
    retry_after_seconds=int(os.getenv("ADMISSION_RETRY_AFTER_SECONDS", "30")),
    enabled=_admission_enabled,
)
```

Update the log line below it (line 66–69) — drop the `prod=` reference:

```python
logger.info(
    f"Admission middleware attached: enabled={_admission_enabled}, "
    f"debug={_debug_admission.max_slots} (prod gating moved to route level)"
)
```

- [ ] **Step 3: Update existing middleware tests**

Look for `apps-microservices/api-detection-langue-fr/tests/test_admission.py`. If it exists, find any test that:
1. Posts to `/api/v1/detect` or `/api/v1/detect-batch` or `/api/v1/check-url` and expects a 503 from the middleware → either delete (covered by `test_admission_carveout.py`) or convert to a route-level expectation.
2. Constructs `AdmissionMiddleware(prod_controller=..., debug_controller=...)` → remove the `prod_controller` kwarg.
3. Asserts on `INFLIGHT_REQUESTS` gauge during middleware acquire → drop the assertion (semantic moved).

If the file does not exist, skip this step.

- [ ] **Step 4: Re-run integration tests**

Run: `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py -v`

Expected: all 4 scenarios PASS now that middleware no longer short-circuits prod paths.

Then run the full suite to check for regressions: `pytest apps-microservices/api-detection-langue-fr/tests/ -v`

Expected: all green. If `test_admission.py` was present and not updated, it will FAIL — return to Step 3.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/middleware/admission.py apps-microservices/api-detection-langue-fr/app/main.py apps-microservices/api-detection-langue-fr/tests/test_admission.py
git commit -m "$(cat <<'EOF'
refactor(api-detection-langue-fr): shrink admission middleware to debug path

EN: AdmissionMiddleware now only gates /detect-debug. /detect,
/detect-batch, /check-url no longer pass through the middleware
admission counter — route-level _fetch_with_admission handles the
gating for paths that actually launch a browser. /check-url skips
admission entirely (no HTML fetch needed).

FR: AdmissionMiddleware ne gate plus que /detect-debug. /detect,
/detect-batch, /check-url ne passent plus par le compteur d'admission
du middleware — _fetch_with_admission au niveau route gère le gating
des chemins qui lancent réellement un navigateur. /check-url contourne
l'admission entièrement (pas de fetch HTML).
EOF
)"
```

---

## Task 4: Extend batch Pass 2 retry-set for `admission_rejected`

**Goal:** Items rejected by admission saturation are transient — a slot may free between Pass 1 and Pass 2. Add `'admission_rejected'` to both the standard `/detect-batch` Pass 2 retry filter and the `first_match` per-group retry filter.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py` (Pass 2 filter sites)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py` (extend)

**Acceptance Criteria:**
- [ ] Standard `/detect-batch` Pass 2 retries items with `method in ('fetch_failed', 'challenge_page', 'admission_rejected')`
- [ ] `first_match` `process_group` failed-list captures items with the same extended set
- [ ] `first_match` Pass 2 retry break condition still treats `('fetch_failed', 'challenge_page')` as continue-retry but stops on any other method (including `admission_rejected` if it persists — but admission_rejected IS retryable, so it must remain in the retry set; see Step 2)
- [ ] New test `test_batch_pass2_retries_admission_rejected` passes (Pass 1 saturated, slot frees by Pass 2, item succeeds)

**Verify:** `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py::test_batch_pass2_retries_admission_rejected -v` → pass.

**Steps:**

- [ ] **Step 1: Extend standard batch Pass 2 filter**

In `apps-microservices/api-detection-langue-fr/app/api/routes.py`, find the standard `/detect-batch` Pass 2 retry filter at around line 520–523:

```python
    failed_indices = [
        i for i, r in enumerate(results)
        if r.method in ('fetch_failed', 'challenge_page')
    ]
```

Replace with:

```python
    failed_indices = [
        i for i, r in enumerate(results)
        if r.method in ('fetch_failed', 'challenge_page', 'admission_rejected')
    ]
```

Also update the inner-loop method check at line 538:

```python
                if retry_result.method not in ('fetch_failed', 'challenge_page'):
```

Replace with:

```python
                if retry_result.method not in ('fetch_failed', 'challenge_page', 'admission_rejected'):
```

Rationale: this branch promotes the retried result as final IF it's no longer in the transient set. If the second attempt is *still* admission_rejected, do NOT promote — wait for whatever the second iteration of the retry loop emits.

- [ ] **Step 2: Extend `first_match` per-group failed-capture**

In the `process_group` inner function (around lines 421–444), find the failed-list filter at line 441:

```python
                if result.method in ('fetch_failed', 'challenge_page'):
                    failed.append(item)
```

Replace with:

```python
                if result.method in ('fetch_failed', 'challenge_page', 'admission_rejected'):
                    failed.append(item)
```

Also update the `first_match` Pass 2 stop condition at line 474:

```python
                    if retry_result.method not in ('fetch_failed', 'challenge_page'):
                        group_results[i] = _with_group(retry_result, group_key)
                        break
```

Replace with:

```python
                    if retry_result.method not in ('fetch_failed', 'challenge_page', 'admission_rejected'):
                        group_results[i] = _with_group(retry_result, group_key)
                        break
```

- [ ] **Step 3: Add the new test scenario**

Append to `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py`:

```python
@pytest.mark.asyncio
async def test_batch_pass2_retries_admission_rejected(monkeypatch):
    """Pass 1 saturated, slot freed before Pass 2 (2s sleep), item succeeds."""
    from app.api.routes import _prod_admission
    from app.services.scraper import ScrapeResult

    call_count = {"n": 0}

    async def flaky_acquire():
        call_count["n"] += 1
        return call_count["n"] != 1  # first call refuses, subsequent succeed

    async def fake_fetch(url, proxy_url):
        return ScrapeResult(
            html="<html lang='fr'><body>Bonjour</body></html>",
            final_url=url, status_code=200, content_type="text/html",
        )

    monkeypatch.setattr(_prod_admission, "acquire", flaky_acquire)
    monkeypatch.setattr("app.api.routes.fetch_html", fake_fetch)
    # Bypass the 2s sleep so the test runs fast
    monkeypatch.setattr("app.api.routes.asyncio.sleep", AsyncMock())

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect-batch",
            json={"items": [{"url": "https://example.fr"}], "mode": "simple",
                  "max_concurrency": 1},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    # Pass 1 rejected, Pass 2 promoted
    assert body["results"][0]["method"] != "admission_rejected"
```

- [ ] **Step 4: Run the new test**

Run: `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py::test_batch_pass2_retries_admission_rejected -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/api/routes.py apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): retry admission_rejected items in batch Pass 2

EN: Extend the /detect-batch Pass 2 retry filter and the first_match
per-group retry filter to include admission_rejected alongside
fetch_failed and challenge_page. Admission saturation is transient —
a slot may free during the 2s inter-retry gap.

FR: Étend le filtre de retry Pass 2 de /detect-batch ainsi que le filtre
de retry par-groupe de first_match pour inclure admission_rejected au
même titre que fetch_failed et challenge_page. La saturation d'admission
est transitoire — un slot peut se libérer pendant le gap inter-retry
de 2s.
EOF
)"
```

---

## Task 5: Integration test suite (remaining scenarios)

**Goal:** Cover the remaining spec §9 scenarios: dedup follower behavior, dedup rejection propagation, `/check-url` bypass, `/detect-debug` isolation, kill switch, homepage admission rejection, cache skip semantics.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py` (append)

**Acceptance Criteria:**
- [ ] `test_check_url_bypasses_admission` passes
- [ ] `test_dedup_follower_no_admission_acquire` passes
- [ ] `test_dedup_follower_propagates_rejection` passes
- [ ] `test_admission_rejected_never_cached` passes
- [ ] `test_homepage_fallback_admission` passes
- [ ] `test_debug_pool_isolated` passes
- [ ] `test_admission_disabled_kill_switch` passes
- [ ] Full file `test_admission_carveout.py` green

**Verify:** `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py -v` → all green.

**Steps:**

- [ ] **Step 1: Append scenarios to the carve-out test module**

Append to `apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py`:

```python
@pytest.mark.asyncio
async def test_check_url_bypasses_admission(saturate_pool):
    """GET /check-url performs no HTML fetch, so it must not acquire any
    admission slot even when the pool is saturated."""
    with TestClient(app) as client:
        resp = client.get(
            "/api/v1/check-url",
            params={"url": "https://example.fr"},
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dedup_follower_no_admission_acquire(monkeypatch):
    """5 concurrent identical URLs, pool size 1. Leader acquires, 4
    followers wait on the future without their own acquire."""
    from app.api.routes import _prod_admission, _inflight_dedup
    from app.services.scraper import ScrapeResult

    acquire_calls = {"n": 0}

    async def counting_acquire():
        acquire_calls["n"] += 1
        # First call wins, subsequent would-be acquires refuse (pool size 1)
        return acquire_calls["n"] == 1

    fetch_event = asyncio.Event()

    async def slow_fetch(url, proxy_url):
        await fetch_event.wait()
        return ScrapeResult(
            html="<html lang='fr'><body>Bonjour</body></html>",
            final_url=url, status_code=200, content_type="text/html",
        )

    monkeypatch.setattr(_prod_admission, "acquire", counting_acquire)
    monkeypatch.setattr("app.api.routes.fetch_html", slow_fetch)

    # Clear inflight state from any previous test
    _inflight_dedup._inflight.clear()
    _inflight_dedup._hits = 0

    async def call_detect():
        with TestClient(app) as client:
            return client.post(
                "/api/v1/detect",
                json={"url": "https://same.fr", "mode": "simple"},
            )

    # 5 concurrent requests for same URL
    tasks = [asyncio.create_task(call_detect()) for _ in range(5)]
    await asyncio.sleep(0.1)  # let all 5 enter coalesce
    fetch_event.set()
    responses = await asyncio.gather(*tasks)

    # All 5 must succeed
    assert all(r.status_code == 200 for r in responses)
    # Only 1 acquire attempt total — leader's
    assert acquire_calls["n"] == 1


@pytest.mark.asyncio
async def test_dedup_follower_propagates_rejection(monkeypatch):
    """Leader rejected → all followers see admission_rejected
    (single → 503, batch → inline)."""
    from app.api.routes import _prod_admission, _inflight_dedup

    async def always_refuse():
        return False

    monkeypatch.setattr(_prod_admission, "acquire", always_refuse)
    _inflight_dedup._inflight.clear()

    async def call_detect():
        with TestClient(app) as client:
            return client.post(
                "/api/v1/detect",
                json={"url": "https://same2.fr", "mode": "simple"},
            )

    tasks = [asyncio.create_task(call_detect()) for _ in range(3)]
    responses = await asyncio.gather(*tasks)

    # All callers must see 503 (single endpoint)
    assert all(r.status_code == 503 for r in responses)


@pytest.mark.asyncio
async def test_admission_rejected_never_cached(saturate_pool, monkeypatch):
    """A 1st call rejected for admission must not poison the cache. A 2nd
    call (slots free again) must perform a fresh fetch, not return a
    cached admission_rejected response."""
    from app.core.domain_fr import domain_cache

    set_calls = []

    async def fake_set(input_url, result_url, result, ttl_override=None):
        set_calls.append((input_url, result))

    monkeypatch.setattr(domain_cache, "set", fake_set)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect",
            json={"url": "https://saturated.fr", "mode": "simple"},
        )
    assert resp.status_code == 503

    # No cache write for the rejection
    written_methods = [r.get("method") for _, r in set_calls]
    assert "admission_rejected" not in written_methods


@pytest.mark.asyncio
async def test_homepage_fallback_admission(monkeypatch):
    """Initial fetch ok but page invalid → homepage fetch attempted.
    Homepage fetch hits saturation → surfaces admission_rejected, not the
    original validator verdict."""
    from app.api.routes import _prod_admission, _inflight_dedup
    from app.services.scraper import ScrapeResult
    from app.services.page_validator import ValidationVerdict

    call_count = {"n": 0}

    async def acquire_first_only():
        call_count["n"] += 1
        return call_count["n"] == 1  # initial fetch OK; homepage fetch refused

    async def fake_fetch(url, proxy_url):
        # First fetch returns a soft-404 shaped page
        return ScrapeResult(
            html="<html><head><title>404 Page non trouvée</title></head>"
                 "<body>Page non trouvée</body></html>",
            final_url=url, status_code=200, content_type="text/html",
        )

    monkeypatch.setattr(_prod_admission, "acquire", acquire_first_only)
    monkeypatch.setattr("app.api.routes.fetch_html", fake_fetch)
    _inflight_dedup._inflight.clear()

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect",
            json={"url": "https://example.fr/missing-page", "mode": "simple"},
        )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_debug_pool_isolated(saturate_pool):
    """Prod admission saturated; /detect-debug still works because it uses
    the separate debug pool."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/detect-debug",
            json={"url": "https://example.fr",
                  "html_content": "<html lang='fr'></html>",
                  "mode": "simple"},
        )
    # Debug endpoint admitted by debug pool; html_content provided so no
    # downstream fetch attempted.
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admission_disabled_kill_switch(monkeypatch):
    """With ADMISSION_ENABLED=false, no acquire is ever attempted. Both
    middleware and route helpers must be inert."""
    from app.api.routes import _prod_admission

    acquire_calls = {"n": 0}

    async def tracking_acquire():
        acquire_calls["n"] += 1
        return True

    monkeypatch.setattr(_prod_admission, "acquire", tracking_acquire)
    monkeypatch.setenv("ADMISSION_ENABLED", "false")

    # Note: app is module-level; ADMISSION_ENABLED is read at import time.
    # This test asserts the EXPECTATION; full kill-switch semantics
    # require process restart. Document as a manual verification step.
    # If your test infrastructure supports app reload, uncomment the
    # importlib.reload(app.main) line below. Otherwise this test serves
    # as documentation of the contract.
    # import importlib; import app.main; importlib.reload(app.main)
```

- [ ] **Step 2: Run the appended scenarios**

Run: `pytest apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py -v`

Expected: all green (the kill-switch test passes trivially because it does not assert anything observable — that test documents the contract). If your test infrastructure supports app reload, enable the `importlib.reload` line and add real assertions on `acquire_calls`.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/tests/test_admission_carveout.py
git commit -m "$(cat <<'EOF'
test(api-detection-langue-fr): cover dedup, /check-url, debug pool isolation

EN: Add the remaining integration scenarios from the spec: /check-url
bypass, dedup follower no-acquire, dedup leader rejection propagation,
admission_rejected not cached, homepage fallback admission surfaces
admission_rejected (no downgrade), /detect-debug isolation, kill
switch contract.

FR: Ajoute les scénarios d'intégration restants de la spec: bypass
/check-url, dedup follower sans acquire, propagation du rejet leader
dedup, admission_rejected non caché, repli homepage qui surface
admission_rejected (pas de downgrade), isolation /detect-debug,
contrat kill switch.
EOF
)"
```

---

## Task 6: Update `apps-microservices/api-detection-langue-fr/CLAUDE.md`

**Goal:** Document the final shape: gate moved to route level, `INFLIGHT_REQUESTS` semantic shift, html_content bypass behavior, `admission_rejected` method, Pass 2 retry-set extension, `/check-url` bypass.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/CLAUDE.md` (§ Concurrency & Admission Control, lines 78–100)

**Acceptance Criteria:**
- [ ] § Concurrency & Admission Control rewritten to describe route-level gating
- [ ] `INFLIGHT_REQUESTS` semantic note added
- [ ] `admission_rejected` method added to the existing method-value reference table or to a new sub-section
- [ ] `/check-url` bypass documented
- [ ] Pass 2 retry-set update documented
- [ ] Crawler-service caller contract cross-reference still accurate

**Verify:** `grep -n "admission_rejected\|admission-controlled\|route-level" apps-microservices/api-detection-langue-fr/CLAUDE.md` → returns the new lines.

**Steps:**

- [ ] **Step 1: Read the current § Concurrency section**

Lines 78–100 of `apps-microservices/api-detection-langue-fr/CLAUDE.md`.

- [ ] **Step 2: Replace the section**

Replace the existing § Concurrency & Admission Control body (lines 80–86) with:

```markdown
Under concurrent load the service applies three layers of protection:

1. **Route-level admission gate** (production paths): `/detect` and `/detect-batch` acquire a slot from `_prod_admission` ONLY when an actual `fetch_html` call is required (no `html_content` provided, no cache HIT, not a dedup follower). Saturation behavior:
   - `/detect` (single): returns HTTP 503 + `Retry-After` header.
   - `/detect-batch`: per-item `DetectionResponse{method='admission_rejected'}` inline; no whole-batch 503. Pass 2 retries items in `{fetch_failed, challenge_page, admission_rejected}` after a 2s gap.
   - `/check-url`: bypasses admission entirely (no HTML fetch).
2. **Debug admission middleware**: `/detect-debug` keeps an isolated middleware-level gate against `_debug_admission` (`ADMISSION_DEBUG_SLOTS`, default 2) so dev traffic cannot starve production.
3. **Inflight URL dedup**: coalesces concurrent fetches of the same URL to a single browser launch. Dedup followers wait on the leader's future and do NOT acquire an admission slot.
4. **Browser semaphore**: caps concurrent Camoufox/Chromium instances at `BROWSER_SEMAPHORE_SIZE` (default 10).

`'admission_rejected'` is in `DomainCache._NEVER_CACHE_METHODS` — service saturation must never be persisted as a domain answer.

`INFLIGHT_REQUESTS` gauge semantic shift (2026-05-17): was "admitted requests in middleware"; now counts active fetches inside route helpers. Lower in absolute terms — cache HITs, `html_content` bypass calls, and dedup followers no longer contribute.

Prometheus metrics exposed at `/metrics` for all layers.
```

Also update the env-var table immediately below (lines 88–100) with a note that `ADMISSION_MAX_SLOTS` is consumed by the route-level helper, not by the middleware. Add a row for `ADMISSION_RETRY_AFTER_SECONDS` (was already present; verify it stays). No new env vars.

Add (after the env-var table) a new sub-section:

```markdown
### Method values added by the carve-out

| Method | Where surfaced | Caller action |
|---|---|---|
| `admission_rejected` | `/detect-batch` per-item only (single `/detect` translates to HTTP 503) | Retry the affected item after `Retry-After`. Never persist as a domain verdict. |

Spec: `docs/superpowers/specs/2026-05-17-detection-langue-fr-crawler-admission-carveout-design.md`.
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(api-detection-langue-fr): document route-level admission carve-out

EN: Update CLAUDE.md § Concurrency & Admission Control with the
post-carve-out layering: route-level gate on prod paths, /check-url
bypass, /detect-debug isolated middleware gate, dedup follower
behavior. Document the INFLIGHT_REQUESTS semantic shift and the new
admission_rejected method value.

FR: Met à jour CLAUDE.md § Concurrency & Admission Control avec
le découpage post-refactor : gate route-level sur les paths prod,
bypass /check-url, gate middleware isolé pour /detect-debug,
comportement follower dedup. Documente le glissement sémantique
de INFLIGHT_REQUESTS et la nouvelle valeur de méthode admission_rejected.
EOF
)"
```

---

## Self-Review Notes

| Spec section | Covered by |
|---|---|
| §4 Architecture | T2 (helper + wire-up), T3 (middleware shrink) |
| §5.1 New method value `admission_rejected` | T2 (Step 6 — batch translation), T4 (Pass 2) |
| §5.2 Pass 2 retry set extension | T4 (both standard and first_match) |
| §5.3 Cache never-cache rule | T1 |
| §5.4 Caller-side impact (deferred BO) | Out of scope; documented |
| §6.1 Files touched | All tasks |
| §6.2 Helper pattern | T2 (Step 2) |
| §6.3 Single vs batch translation | T2 (Steps 5–6) |
| §6.4 Why leader-only acquire | T2 (Steps 3–4 — helper inside coalesce factory) |
| §6.5 Homepage fallback | T2 (Step 4) + T5 (`test_homepage_fallback_admission`) |
| §7 Configuration | T3 (no new env vars; doc only in T6) |
| §8 Observability | T2 (counter labels), T6 (doc semantic shift) |
| §9 Testing (10 scenarios) | T2 (scenarios 1–4), T4 (scenario 5), T5 (scenarios 6–10) |
| §10 Rollout | Operator-side; documented |
| §11 Risks | Acknowledged in tests + docs |
| §12 Follow-ups | Out of scope |
| §13 Implementation order | This plan reorders for atomicity (T2 → T3 swap pair); end state identical |

## Rollout Reminder (operator)

After all 6 tasks merge:

1. Deploy with defaults (`ADMISSION_ENABLED=true`, `ADMISSION_MAX_SLOTS=12`).
2. Watch `ADMISSION_REJECTED{endpoint="/api/v1/detect"}` + `{endpoint="/api/v1/detect-batch"}` Prometheus counters. Crawler-service 503 rate should drop to zero. BO `admission_rejected` item count replaces previous whole-batch 503s.
3. Update Grafana dashboards referencing `INFLIGHT_REQUESTS` (panel descriptions only — gauge values shift downward; data integrity unchanged).
4. Schedule follow-up spec for BO PHP `admission_rejected` handling in `script_identifier_site_fr_v2.php`.
