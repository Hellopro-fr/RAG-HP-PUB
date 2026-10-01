# api-detection-langue-fr — Concurrency Defense Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the three-layer defense (in-service admission + container limits + caller contract) from the design spec to eliminate observed TargetClosedError flood, prevent event-loop starvation, and provide actionable backpressure to callers.

**Architecture:** Four sequential phases, each independently reversible. Phase 1 fixes bugs. Phase 2 adds observability + container ceilings. Phase 3 adds admission control + URL dedup. Phase 4 rolls out the caller-side contract to api-gateway and crawler-service.

**Tech Stack:** Python 3.10 (FastAPI, Uvicorn, prometheus-client, pytest, pytest-asyncio, httpx), Playwright 1.40+ (Camoufox primary, Chromium fallback), Docker Compose, TypeScript/Node.js 22 (axios, p-limit), shared `libs/common-utils`.

**Spec:** `docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md`

---

## Phase 1 — In-service bug fixes (low risk)

### Task 1: Fix route handler leak + env-configurable browser semaphore

**Goal:** Eliminate the `TargetClosedError` flood by draining in-flight route callbacks before closing Playwright pages, guarantee browser cleanup via `try/finally` on all exception paths, and expose the browser semaphore size as an env var.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/scraper.py`
- Modify: `apps-microservices/api-detection-langue-fr/app/services/scraper.py` (same — `scrape_html_with_redirects` function too)
- Modify: `apps-microservices/api-detection-langue-fr/tests/test_scraper.py` (exists per Grep; add new test class)

**Acceptance Criteria:**
- [ ] `_BROWSER_SEMAPHORE` size reads from `BROWSER_SEMAPHORE_SIZE` env (default 10)
- [ ] `page.unroute_all(behavior='ignoreErrors')` is called before `context.close()` in both `scrape_html` and `scrape_html_with_redirects`
- [ ] Browser lifecycle is wrapped in `try/finally` so `context.close()` / `browser.close()` always run, even on unexpected exceptions
- [ ] Existing navigation-error behavior (re-raise on `_PERMANENT_NAV_ERRORS`) preserved — the cleanup happens in the `finally` block, the re-raise still propagates
- [ ] New unit tests pass: env var read, unroute_all called before close, finally block runs on mid-fetch exception

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_scraper.py -v` → all tests pass (new ones plus any existing passing ones)

**Steps:**

- [ ] **Step 1: Write failing tests**

Add a new test class to `tests/test_scraper.py`. If the file exists with TestBrowserSelection (per Grep results), append at the end:

```python
# tests/test_scraper.py — additions

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


class TestBrowserSemaphoreEnv:
    """Tests for BROWSER_SEMAPHORE_SIZE env var."""

    def test_semaphore_size_from_env(self, monkeypatch):
        """BROWSER_SEMAPHORE_SIZE env var sets the semaphore value."""
        monkeypatch.setenv("BROWSER_SEMAPHORE_SIZE", "3")
        # Reload module to pick up env var
        import importlib
        from app.services import scraper
        importlib.reload(scraper)
        assert scraper._BROWSER_SEMAPHORE._value == 3

    def test_semaphore_size_default(self, monkeypatch):
        """Default is 10 when env var absent."""
        monkeypatch.delenv("BROWSER_SEMAPHORE_SIZE", raising=False)
        import importlib
        from app.services import scraper
        importlib.reload(scraper)
        assert scraper._BROWSER_SEMAPHORE._value == 10


class TestRouteHandlerCleanup:
    """Tests for unroute_all + try/finally guarantees."""

    @pytest.mark.asyncio
    async def test_unroute_all_called_before_context_close_on_success(self):
        """On happy path, page.unroute_all is called before context.close."""
        from app.services import scraper

        call_order = []
        mock_page = MagicMock()
        mock_page.unroute_all = AsyncMock(side_effect=lambda **kw: call_order.append("unroute_all"))
        mock_page.goto = AsyncMock()
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>" + "x" * 200 + "</body></html>")
        mock_page.url = "https://example.com/"
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()
        mock_page.wait_for_timeout = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_cookies = AsyncMock()
        mock_context.close = AsyncMock(side_effect=lambda: call_order.append("context.close"))

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock(side_effect=lambda: call_order.append("browser.close"))

        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch("playwright.async_api.async_playwright") as mock_pw:
            mock_pw.return_value.__aenter__.return_value = MagicMock()
            mock_pw.return_value.__aexit__ = AsyncMock()

            result = await scraper.scrape_html(
                "https://example.com", proxy="http://u:p@proxy:8000"
            )

        assert result is not None
        assert call_order.index("unroute_all") < call_order.index("context.close")

    @pytest.mark.asyncio
    async def test_browser_closed_on_mid_fetch_exception(self):
        """A mid-fetch exception still triggers context.close and browser.close (try/finally)."""
        from app.services import scraper

        closed = {"context": False, "browser": False}
        mock_page = MagicMock()
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()
        mock_page.goto = AsyncMock(side_effect=RuntimeError("synthetic mid-fetch error"))
        mock_page.unroute_all = AsyncMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.add_cookies = AsyncMock()
        async def close_ctx():
            closed["context"] = True
        mock_context.close = AsyncMock(side_effect=close_ctx)

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        async def close_br():
            closed["browser"] = True
        mock_browser.close = AsyncMock(side_effect=close_br)

        with patch.object(scraper, "_launch_browser", AsyncMock(return_value=(mock_browser, True))), \
             patch("playwright.async_api.async_playwright") as mock_pw:
            mock_pw.return_value.__aenter__.return_value = MagicMock()
            mock_pw.return_value.__aexit__ = AsyncMock()

            with pytest.raises(RuntimeError, match="synthetic mid-fetch error"):
                await scraper.scrape_html(
                    "https://example.com", proxy="http://u:p@proxy:8000"
                )

        assert closed["context"] is True
        assert closed["browser"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_scraper.py::TestBrowserSemaphoreEnv tests/test_scraper.py::TestRouteHandlerCleanup -v`

Expected: FAIL — semaphore is hardcoded `10`; unroute_all isn't called; try/finally isn't wrapping the lifecycle.

- [ ] **Step 3: Make BROWSER_SEMAPHORE_SIZE env-configurable**

In `apps-microservices/api-detection-langue-fr/app/services/scraper.py`, replace the hardcoded semaphore declaration (search for `_BROWSER_SEMAPHORE = asyncio.Semaphore(10)`):

```python
import os
# ... existing imports ...

# Sémaphore global limitant le nombre de navigateurs Playwright simultanés.
# Taille configurable via BROWSER_SEMAPHORE_SIZE env var (défaut: 10).
# Chaque Camoufox/Chromium consomme ~300-500 MB — ne pas dépasser la capacité du container.
_BROWSER_SEMAPHORE_SIZE = int(os.getenv("BROWSER_SEMAPHORE_SIZE", "10"))
_BROWSER_SEMAPHORE = asyncio.Semaphore(_BROWSER_SEMAPHORE_SIZE)
```

- [ ] **Step 4: Wrap browser lifecycle in `try/finally` + add `unroute_all` in `scrape_html`**

Find the main `async with _BROWSER_SEMAPHORE:` block in `scrape_html` (around line 295). The current structure uses `async with async_playwright() as p:` which handles its own cleanup, but the browser/context opened inside can leak on unexpected exceptions. Restructure the cleanup path:

Inside the `try:` block after `browser, is_camoufox = await _launch_browser(...)`, wrap everything that uses `context` / `page` in a nested `try/finally`:

```python
                async with _BROWSER_SEMAPHORE:
                    async with async_playwright() as p:
                        browser, is_camoufox = await _launch_browser(p, playwright_proxy)
                        context = None
                        page = None
                        try:
                            # ... existing context creation, page creation, navigation, extraction ...
                            context = await browser.new_context(**context_options)
                            await _inject_cookie_consent(context, url)
                            page = await context.new_page()
                            await _setup_resource_blocking(page)
                            # ... (all the navigation, challenge polling, content extraction logic
                            #      moves inside this try)
                            final_url = page.url
                            # Do NOT close here — finally block handles it
                            if content and len(content) > 100:
                                # ... existing success logging ...
                                return (content, final_url)
                            else:
                                logger.warning(f"Contenu trop court pour {url}")
                                return None
                        finally:
                            # Drain in-flight route callbacks before tearing down the page.
                            # Suppresses TargetClosedError flood from _route_handler firing
                            # on closed pages under concurrent load.
                            if page is not None:
                                try:
                                    await page.unroute_all(behavior='ignoreErrors')
                                except Exception as unroute_err:
                                    logger.debug(f"unroute_all failed for {url}: {unroute_err}")
                            if context is not None:
                                try:
                                    await context.close()
                                except Exception as ctx_err:
                                    logger.debug(f"context.close failed for {url}: {ctx_err}")
                            try:
                                await browser.close()
                            except Exception as br_err:
                                logger.debug(f"browser.close failed for {url}: {br_err}")
```

**Important:** the existing navigation-error branch that does `await context.close(); await browser.close(); raise` for `_PERMANENT_NAV_ERRORS` must be changed — remove the explicit closes there (the `finally` block will handle them), keep the `raise`:

```python
                except Exception as nav_e:
                    err_str = str(nav_e)
                    if any(err in err_str for err in _PERMANENT_NAV_ERRORS):
                        logger.error(f"Erreur navigation permanente pour {url}: {err_str.splitlines()[0]}")
                        raise  # finally block will close context + browser
                    logger.warning(f"Timeout/Erreur navigation pour {url} (extraction partielle tentée): {nav_e}")
```

- [ ] **Step 5: Apply the same pattern to `scrape_html_with_redirects`**

The second scraping function at the bottom of `scraper.py` (around line 400+) has the same structure and the same bug. Apply identical changes: `context = None; page = None`, nested `try/finally`, `unroute_all` before close.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_scraper.py::TestBrowserSemaphoreEnv tests/test_scraper.py::TestRouteHandlerCleanup -v`

Expected: PASS for all new tests.

Then run the full scraper test file to make sure no regression:

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_scraper.py -v`

Expected: All tests that previously passed still pass.

- [ ] **Step 7: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/api-detection-langue-fr/app/services/scraper.py \
        apps-microservices/api-detection-langue-fr/tests/test_scraper.py
git commit -m "$(cat <<'EOF'
fix(api-detection-langue-fr): drain route callbacks + guarantee browser cleanup

- Call page.unroute_all(behavior='ignoreErrors') before context.close()
  to eliminate the TargetClosedError flood observed under concurrent load
- Wrap browser lifecycle in try/finally so context.close()/browser.close()
  always run, even when navigation or extraction raises
- Make BROWSER_SEMAPHORE_SIZE env-configurable (default 10) so ops can
  tune browser concurrency without a redeploy

---

fix(api-detection-langue-fr): vide les callbacks de routes + garantit le nettoyage du navigateur

- Appelle page.unroute_all(behavior='ignoreErrors') avant context.close()
  pour eliminer le flot de TargetClosedError sous charge concurrente
- Encapsule le cycle de vie du navigateur dans un try/finally pour que
  context.close()/browser.close() s'executent toujours, meme en cas
  d'exception lors de la navigation ou de l'extraction
- Rend BROWSER_SEMAPHORE_SIZE configurable par env (defaut 10) pour
  permettre le tuning sans redeploiement
EOF
)"
```

---

### Task 2: Update api-detection-langue-fr CLAUDE.md

**Goal:** Fix the stale "Scraping: Playwright (Chromium)" statement to reflect the actual Camoufox-primary / Chromium-fallback architecture, and document the new `BROWSER_SEMAPHORE_SIZE` env var (the other new env vars are added later, but list them here for a single source of truth).

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/CLAUDE.md`

**Acceptance Criteria:**
- [ ] "Scraping" line correctly states Camoufox primary + Chromium fallback
- [ ] Build/Run section mentions `CAMOUFOX_ENABLED=false` as the fallback toggle
- [ ] A new "Concurrency & Admission Control" section lists the env vars introduced by this plan
- [ ] No content changes beyond documentation (no code edits)

**Verify:** `grep -E "Camoufox|BROWSER_SEMAPHORE_SIZE" apps-microservices/api-detection-langue-fr/CLAUDE.md` returns the updated text.

**Steps:**

- [ ] **Step 1: Update the Tech Stack section**

Replace the line in `apps-microservices/api-detection-langue-fr/CLAUDE.md` currently reading:
```
- **Scraping:** Playwright (Chromium) via Apify proxy (mandatory)
```

with:
```
- **Scraping:** Camoufox (stealth Firefox, default) via Playwright; Chromium fallback via `CAMOUFOX_ENABLED=false` or on Camoufox launch failure. Apify proxy mandatory for both.
```

- [ ] **Step 2: Update the Docker build line**

Replace:
```
- **Docker build:** installs Playwright + Chromium browser at build time
```

with:
```
- **Docker build:** installs Playwright + Chromium (fallback) and fetches the Camoufox binary at build time. Camoufox's ~200MB browser is stored in the image.
```

- [ ] **Step 3: Add a new "Concurrency & Admission Control" section**

Add this section after the existing "Conventions" section (before "Dependencies on Other Services"):

```markdown
## Concurrency & Admission Control

Under concurrent load the service applies three layers of protection:

1. **Admission middleware** rejects with `503 + Retry-After` when in-flight count reaches `ADMISSION_MAX_SLOTS` (default 12). `/detect-debug` has an isolated budget via `ADMISSION_DEBUG_SLOTS` (default 2).
2. **Inflight URL dedup** coalesces concurrent fetches of the same URL to a single browser launch. Bypassed when `force_refresh=True`.
3. **Browser semaphore** caps concurrent Camoufox/Chromium instances at `BROWSER_SEMAPHORE_SIZE` (default 10).

Prometheus metrics exposed at `/metrics` for all three layers.

### Env vars

| Variable | Default | Purpose |
|---|---|---|
| `BROWSER_SEMAPHORE_SIZE` | `10` | Max concurrent Camoufox/Chromium instances |
| `CAMOUFOX_ENABLED` | `true` | Use Camoufox; `false` falls back to Chromium |
| `ADMISSION_ENABLED` | `true` | Kill switch for admission middleware |
| `ADMISSION_MAX_SLOTS` | `12` | Production endpoint in-flight limit |
| `ADMISSION_DEBUG_SLOTS` | `2` | `/detect-debug` in-flight limit |
| `ADMISSION_RETRY_AFTER_SECONDS` | `30` | `Retry-After` header value in 503 responses |
| `INFLIGHT_DEDUP_ENABLED` | `true` | Kill switch for URL dedup |

Callers MUST use the shared contract: `libs/common-utils/src/common_utils/detection_client.py` (Python) or mirror its env vars (`DETECTION_MAX_CONCURRENCY`, `DETECTION_REQUEST_TIMEOUT_S`, `DETECTION_MAX_RETRIES`, `DETECTION_BACKOFF_BASE_S`) in other languages.
```

- [ ] **Step 4: Verify the diff reads sensibly**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git diff apps-microservices/api-detection-langue-fr/CLAUDE.md
```

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(api-detection-langue-fr): correct browser stack + document concurrency envs

- Fix stale Chromium-only statement (Camoufox is the default; Chromium
  is fallback via CAMOUFOX_ENABLED=false or launch failure)
- Add a Concurrency & Admission Control section listing env vars that
  the upcoming admission middleware, URL dedup, browser semaphore, and
  caller contract all read

---

docs(api-detection-langue-fr): corrige le stack navigateur + documente les envs de concurrence

- Corrige la mention obsolete uniquement Chromium (Camoufox est par
  defaut; Chromium est le fallback via CAMOUFOX_ENABLED=false ou echec
  de lancement)
- Ajoute une section Concurrence & Controle d'admission listant les env
  vars lues par le middleware d'admission, le dedup d'URL, le semaphore
  de navigateurs et le contrat cote appelant a venir
EOF
)"
```

---

## Phase 2 — Container + observability

### Task 3: Add Prometheus metrics module + instrument scraper + `/metrics` endpoint

**Goal:** Create the metrics module with all histograms/counters/gauges from the spec, expose `/metrics` on the FastAPI app, and instrument `scrape_html` to record browser launch duration.

**Files:**
- Create: `apps-microservices/api-detection-langue-fr/app/core/metrics.py`
- Create: `apps-microservices/api-detection-langue-fr/tests/test_metrics.py`
- Modify: `apps-microservices/api-detection-langue-fr/main.py` (mount `/metrics`)
- Modify: `apps-microservices/api-detection-langue-fr/app/services/scraper.py` (wrap `_launch_browser` timing)
- Modify: `apps-microservices/api-detection-langue-fr/requirements.txt` (add `prometheus-client`)

**Acceptance Criteria:**
- [ ] `prometheus-client>=0.19.0` added to requirements.txt
- [ ] `app/core/metrics.py` exports: `REQUEST_DURATION`, `BROWSER_LAUNCH_DURATION`, `ADMISSION_REJECTED`, `DEDUP_HITS`, `INFLIGHT_REQUESTS`, `BROWSER_SEMAPHORE_WAITERS`
- [ ] `GET /metrics` returns Prometheus text exposition format (`text/plain; version=0.0.4; charset=utf-8`)
- [ ] `scrape_html` records `BROWSER_LAUNCH_DURATION` with label `browser=camoufox|chromium`
- [ ] Unit tests verify each metric can be incremented/observed without errors

**Verify:**
```bash
cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_metrics.py -v
```
Expected: all tests pass.

**Steps:**

- [ ] **Step 1: Add prometheus-client to requirements.txt**

Append to `apps-microservices/api-detection-langue-fr/requirements.txt`:

```
prometheus-client>=0.19.0
```

- [ ] **Step 2: Write failing tests**

Create `apps-microservices/api-detection-langue-fr/tests/test_metrics.py`:

```python
"""Tests for the Prometheus metrics module."""
import pytest
from fastapi.testclient import TestClient


class TestMetricsDefinitions:
    """Each metric must be importable and have the expected type."""

    def test_request_duration_is_histogram(self):
        from app.core.metrics import REQUEST_DURATION
        from prometheus_client import Histogram
        assert isinstance(REQUEST_DURATION, Histogram)

    def test_browser_launch_duration_labeled(self):
        from app.core.metrics import BROWSER_LAUNCH_DURATION
        # Should accept a browser label
        BROWSER_LAUNCH_DURATION.labels(browser="camoufox").observe(0.5)
        BROWSER_LAUNCH_DURATION.labels(browser="chromium").observe(1.2)

    def test_admission_rejected_counter(self):
        from app.core.metrics import ADMISSION_REJECTED
        before = ADMISSION_REJECTED.labels(endpoint="/detect")._value.get()
        ADMISSION_REJECTED.labels(endpoint="/detect").inc()
        after = ADMISSION_REJECTED.labels(endpoint="/detect")._value.get()
        assert after == before + 1

    def test_dedup_hits_counter(self):
        from app.core.metrics import DEDUP_HITS
        before = DEDUP_HITS._value.get()
        DEDUP_HITS.inc()
        assert DEDUP_HITS._value.get() == before + 1

    def test_inflight_gauge(self):
        from app.core.metrics import INFLIGHT_REQUESTS
        before = INFLIGHT_REQUESTS._value.get()
        INFLIGHT_REQUESTS.inc()
        INFLIGHT_REQUESTS.dec()
        assert INFLIGHT_REQUESTS._value.get() == before


class TestMetricsEndpoint:
    """/metrics returns Prometheus exposition format."""

    def test_metrics_endpoint_returns_prometheus_format(self):
        from main import app
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        # Prometheus format markers
        body = response.text
        assert "# HELP" in body or "# TYPE" in body or body == ""  # allow empty if no metrics recorded yet
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_metrics.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.metrics'`.

- [ ] **Step 4: Create the metrics module**

Create `apps-microservices/api-detection-langue-fr/app/core/metrics.py`:

```python
"""Prometheus metrics for api-detection-langue-fr.

Exposed at /metrics. Used to drive the post-rollout decision on whether
the Approach 3 refactor (browser pool + queue) is needed (see spec).
"""
from prometheus_client import Counter, Gauge, Histogram

# End-to-end request duration distribution.
REQUEST_DURATION = Histogram(
    "detect_request_duration_seconds",
    "End-to-end request duration in seconds",
    labelnames=("endpoint", "status"),
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)

# Cost of browser cold-start. Drives the Approach 3 decision: if this
# dominates request duration, a warm browser pool would be a direct win.
BROWSER_LAUNCH_DURATION = Histogram(
    "detect_browser_launch_duration_seconds",
    "Time to launch a Camoufox or Chromium browser",
    labelnames=("browser",),
    buckets=(0.5, 1, 2, 5, 10, 20, 45),
)

# Count of 503s emitted by the admission middleware.
ADMISSION_REJECTED = Counter(
    "detect_admission_rejected_total",
    "Requests rejected by the admission middleware",
    labelnames=("endpoint",),
)

# Count of coalesced duplicate URL fetches.
DEDUP_HITS = Counter(
    "detect_dedup_hits_total",
    "Concurrent requests for the same URL that were coalesced",
)

# Current number of admitted in-flight requests.
INFLIGHT_REQUESTS = Gauge(
    "detect_inflight_requests",
    "Current concurrent admitted requests",
)

# Queue depth on the Playwright browser semaphore.
BROWSER_SEMAPHORE_WAITERS = Gauge(
    "detect_browser_semaphore_waiters",
    "Number of coroutines waiting on the browser semaphore",
)
```

- [ ] **Step 5: Wire `/metrics` endpoint into `main.py`**

In `apps-microservices/api-detection-langue-fr/main.py`, add imports and a route. Find the line `app.include_router(router, prefix="/api/v1")` and add before it:

```python
from fastapi import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
# Import to ensure metric objects are registered with the default registry.
from app.core import metrics  # noqa: F401


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    """Prometheus metrics exposition endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

- [ ] **Step 6: Instrument browser launch in `scraper.py`**

In `apps-microservices/api-detection-langue-fr/app/services/scraper.py`, modify `_launch_browser` to record the launch duration. Add at the top of the file:

```python
import time
from app.core.metrics import BROWSER_LAUNCH_DURATION
```

Wrap each browser-launch path:

```python
async def _launch_browser(playwright_instance, playwright_proxy: Optional[dict] = None):
    # ... existing docstring ...
    if settings.CAMOUFOX_ENABLED:
        try:
            from camoufox import AsyncNewBrowser
            t0 = time.monotonic()
            browser = await asyncio.wait_for(
                AsyncNewBrowser(
                    playwright_instance,
                    headless=True,
                    proxy=playwright_proxy,
                    geoip=True,
                ),
                timeout=45,
            )
            BROWSER_LAUNCH_DURATION.labels(browser="camoufox").observe(time.monotonic() - t0)
            logger.info("Navigateur Camoufox (stealth Firefox) lancé")
            return browser, True
        except ImportError:
            logger.warning("Package camoufox non installé, fallback vers Chromium")
        except asyncio.TimeoutError:
            logger.warning("Timeout lancement Camoufox (45s), fallback vers Chromium")
        except Exception as e:
            logger.warning(f"Erreur lancement Camoufox: {e}, fallback vers Chromium")

    t0 = time.monotonic()
    browser = await playwright_instance.chromium.launch(
        headless=True,
        proxy=playwright_proxy,
        args=[
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-gpu',
            '--disable-blink-features=AutomationControlled',
        ],
    )
    BROWSER_LAUNCH_DURATION.labels(browser="chromium").observe(time.monotonic() - t0)
    logger.info("Navigateur Playwright Chromium lancé (fallback)")
    return browser, False
```

- [ ] **Step 7: Install the new dep locally**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB/apps-microservices/api-detection-langue-fr
pip install prometheus-client
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_metrics.py -v`

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/api-detection-langue-fr/app/core/metrics.py \
        apps-microservices/api-detection-langue-fr/main.py \
        apps-microservices/api-detection-langue-fr/app/services/scraper.py \
        apps-microservices/api-detection-langue-fr/requirements.txt \
        apps-microservices/api-detection-langue-fr/tests/test_metrics.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): add Prometheus metrics and /metrics endpoint

- Histograms: request duration, browser launch duration (camoufox|chromium)
- Counters: admission rejections, dedup hits
- Gauges: inflight requests, browser semaphore waiters
- /metrics endpoint exposed on FastAPI app
- Browser launch timing instrumented in _launch_browser

Post-rollout these metrics drive the decision on whether the Approach 3
refactor (warm browser pool + queue) is needed — see spec.

---

feat(api-detection-langue-fr): ajoute les metriques Prometheus et l'endpoint /metrics

- Histogrammes : duree de requete, duree de lancement navigateur
  (camoufox|chromium)
- Compteurs : rejets d'admission, hits de dedup
- Jauges : requetes en vol, attenteurs du semaphore navigateur
- Endpoint /metrics expose sur l'app FastAPI
- Timing du lancement navigateur instrumente dans _launch_browser
EOF
)"
```

---

### Task 4: Docker resource limits + healthcheck + Uvicorn `--limit-concurrency`

**Goal:** Add memory/CPU ceilings, a functional healthcheck, and a hard Uvicorn connection ceiling as container-level safety nets.

**Files:**
- Modify: `docker-compose.yml` (the `api-detection-langue-fr-service` block)
- Modify: `apps-microservices/api-detection-langue-fr/Dockerfile` (CMD line)

**Acceptance Criteria:**
- [ ] `mem_limit: 4500m` and `cpus: 4` set on the service
- [ ] Healthcheck block uses `curl -fsS http://localhost:8999/api/v1/health`
- [ ] Dockerfile CMD includes `--limit-concurrency 50`
- [ ] `docker compose config` output parses cleanly (no YAML error)

**Verify:**
```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
docker compose config | grep -A 20 "api-detection-langue-fr-service:"
```
Expected: output shows the new `mem_limit`, `cpus`, and `healthcheck` keys.

**Steps:**

- [ ] **Step 1: Read current service block to preserve existing keys**

```bash
grep -A 30 "api-detection-langue-fr-service:" docker-compose.yml | head -40
```

Note the existing keys (image/build, volumes, ports, env, logging, network, init) — preserve them all.

- [ ] **Step 2: Add resource limits and healthcheck**

In `docker-compose.yml`, update the `api-detection-langue-fr-service` block by adding (or merging) these keys. Place them after the existing `environment:` block and before `logging:`:

```yaml
    mem_limit: 4500m
    cpus: 4
    healthcheck:
      test: ["CMD-SHELL", "curl -fsS http://localhost:8999/api/v1/health || exit 1"]
      interval: 30s
      timeout: 10s
      start_period: 30s
      retries: 3
```

- [ ] **Step 3: Update Dockerfile CMD to include `--limit-concurrency 50`**

In `apps-microservices/api-detection-langue-fr/Dockerfile`, replace the CMD line currently reading:

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8999", "--proxy-headers", "--timeout-keep-alive", "300"]
```

with:

```dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8999", \
     "--proxy-headers", "--timeout-keep-alive", "300", \
     "--limit-concurrency", "50"]
```

- [ ] **Step 4: Validate compose file parses**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
docker compose config --profile app | grep -A 20 "api-detection-langue-fr-service:"
```

Expected: shows the new keys. Confirms YAML is syntactically valid.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml apps-microservices/api-detection-langue-fr/Dockerfile
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): add Docker resource limits + healthcheck

- mem_limit 4500m: OOM-kills runaway memory usage, auto-restarts via
  existing restart policy
- cpus 4: forces browser semaphore to be the bottleneck, not CPU
  contention bleeding into other services
- Healthcheck on /api/v1/health: catches event-loop starvation (can't
  respond in 10s → unhealthy → restart after 3 consecutive failures)
- Uvicorn --limit-concurrency 50: hard ceiling above the admission
  middleware limit (12) as belt-and-braces if middleware ever fails open

---

feat(api-detection-langue-fr): ajoute les limites de ressources Docker + healthcheck

- mem_limit 4500m : tue par OOM la consommation memoire incontrolee,
  redemarre automatiquement via la restart policy existante
- cpus 4 : force le semaphore de navigateurs a etre le goulot, pas la
  contention CPU debordant sur les autres services
- Healthcheck sur /api/v1/health : detecte la famine de l'event loop
  (incapable de repondre en 10s -> unhealthy -> restart apres 3 echecs)
- Uvicorn --limit-concurrency 50 : plafond dur au-dessus de la limite
  du middleware d'admission (12) comme ceinture-et-bretelles si le
  middleware echoue en mode ouvert
EOF
)"
```

---

## Phase 3 — Admission control + inflight dedup

### Task 5: `AdmissionController` class with tests

**Goal:** Implement the atomic in-flight counter used by the admission middleware. Pure class, no FastAPI integration yet.

**Files:**
- Create: `apps-microservices/api-detection-langue-fr/app/core/admission.py`
- Create: `apps-microservices/api-detection-langue-fr/tests/test_admission.py`

**Acceptance Criteria:**
- [ ] `AdmissionController(max_slots: int)` class
- [ ] `async acquire() -> bool` — returns `True` and increments counter if `counter < max_slots`, else returns `False` without incrementing
- [ ] `async release() -> None` — decrements counter; no-op if counter already 0 (defensive)
- [ ] Thread-safe under `asyncio.gather`: 100 concurrent `acquire()` calls with `max=5` result in exactly 5 Trues and 95 Falses
- [ ] `inflight` property returns current counter value
- [ ] All tests pass

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_admission.py -v`

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `apps-microservices/api-detection-langue-fr/tests/test_admission.py`:

```python
"""Tests for the AdmissionController class."""
import asyncio
import pytest


class TestAdmissionController:
    """Core acquire/release logic."""

    @pytest.mark.asyncio
    async def test_acquire_returns_true_when_slot_available(self):
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=3)
        assert await ctrl.acquire() is True
        assert ctrl.inflight == 1

    @pytest.mark.asyncio
    async def test_acquire_returns_false_when_saturated(self):
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=2)
        assert await ctrl.acquire() is True
        assert await ctrl.acquire() is True
        # Third attempt: should be rejected
        assert await ctrl.acquire() is False
        assert ctrl.inflight == 2

    @pytest.mark.asyncio
    async def test_release_decrements_counter(self):
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=5)
        await ctrl.acquire()
        await ctrl.acquire()
        assert ctrl.inflight == 2
        await ctrl.release()
        assert ctrl.inflight == 1

    @pytest.mark.asyncio
    async def test_release_does_not_go_negative(self):
        """Defensive: double-release must not produce a negative counter."""
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=5)
        await ctrl.acquire()
        await ctrl.release()
        await ctrl.release()  # defensive no-op
        assert ctrl.inflight == 0

    @pytest.mark.asyncio
    async def test_atomic_under_concurrent_load(self):
        """100 concurrent acquires with max=5 → exactly 5 Trues."""
        from app.core.admission import AdmissionController
        ctrl = AdmissionController(max_slots=5)
        results = await asyncio.gather(*[ctrl.acquire() for _ in range(100)])
        assert sum(1 for r in results if r) == 5
        assert sum(1 for r in results if not r) == 95
        assert ctrl.inflight == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_admission.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `AdmissionController`**

Create `apps-microservices/api-detection-langue-fr/app/core/admission.py`:

```python
"""Admission control primitive.

Non-blocking counter: acquire() either succeeds immediately (slot
available) or returns False (saturated). Never queues. Callers see
fast-fail rather than latency, which is the point.
"""
import asyncio


class AdmissionController:
    """Atomic in-flight counter with a hard max.

    Not a semaphore: acquire() does NOT block when the counter is at
    max — it returns False so the caller can emit 503+Retry-After.
    """

    def __init__(self, max_slots: int) -> None:
        if max_slots < 1:
            raise ValueError("max_slots must be >= 1")
        self._max = max_slots
        self._counter = 0
        self._lock = asyncio.Lock()

    @property
    def inflight(self) -> int:
        """Current admitted in-flight count (unsynchronized read for observability)."""
        return self._counter

    @property
    def max_slots(self) -> int:
        return self._max

    async def acquire(self) -> bool:
        """Try to acquire a slot. Returns True on success, False if saturated."""
        async with self._lock:
            if self._counter >= self._max:
                return False
            self._counter += 1
            return True

    async def release(self) -> None:
        """Release a slot. Defensive: does not go below zero."""
        async with self._lock:
            if self._counter > 0:
                self._counter -= 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_admission.py -v`

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/core/admission.py \
        apps-microservices/api-detection-langue-fr/tests/test_admission.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): add AdmissionController with atomic counter

Non-blocking admission primitive: acquire() either succeeds immediately
(slot available) or returns False (saturated). Never queues.

---

feat(api-detection-langue-fr): ajoute AdmissionController avec compteur atomique

Primitive d'admission non-bloquante : acquire() reussit immediatement
(slot dispo) ou renvoie False (sature). Ne met jamais en file d'attente.
EOF
)"
```

---

### Task 6: Admission middleware + integration tests

**Goal:** Wrap incoming requests with path-based admission checks. Emit `503 + Retry-After` when saturated. Update metrics.

**Files:**
- Create: `apps-microservices/api-detection-langue-fr/app/middleware/__init__.py` (empty)
- Create: `apps-microservices/api-detection-langue-fr/app/middleware/admission.py`
- Create: `apps-microservices/api-detection-langue-fr/tests/test_admission_middleware.py`

**Acceptance Criteria:**
- [ ] Middleware picks controller by path: `/detect-debug` → debug controller; `/detect`, `/detect-batch`, `/check-url` → prod controller; other paths bypass
- [ ] Returns `503 Service Unavailable` with `Retry-After` header when saturated
- [ ] Increments `ADMISSION_REJECTED{endpoint=...}` counter on rejection
- [ ] Increments/decrements `INFLIGHT_REQUESTS` gauge on accept/release
- [ ] Respects `ADMISSION_ENABLED=false` (no-op)
- [ ] Integration tests cover: admit, reject, debug isolation, bypass paths, kill switch

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_admission_middleware.py -v`

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `apps-microservices/api-detection-langue-fr/tests/test_admission_middleware.py`:

```python
"""Integration tests for the admission middleware."""
import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app(max_prod=2, max_debug=1, enabled=True):
    """Build a minimal FastAPI app with the admission middleware attached."""
    from app.middleware.admission import AdmissionMiddleware
    from app.core.admission import AdmissionController

    app = FastAPI()
    prod_ctrl = AdmissionController(max_slots=max_prod)
    debug_ctrl = AdmissionController(max_slots=max_debug)
    app.add_middleware(
        AdmissionMiddleware,
        prod_controller=prod_ctrl,
        debug_controller=debug_ctrl,
        retry_after_seconds=10,
        enabled=enabled,
    )

    @app.get("/api/v1/detect")
    async def _detect():
        await asyncio.sleep(0.05)
        return {"ok": True}

    @app.get("/api/v1/detect-batch")
    async def _batch():
        await asyncio.sleep(0.05)
        return {"ok": True}

    @app.get("/api/v1/detect-debug")
    async def _debug():
        await asyncio.sleep(0.05)
        return {"ok": True}

    @app.get("/api/v1/health")
    async def _health():
        return {"status": "healthy"}

    @app.get("/metrics")
    async def _metrics():
        return {"metrics": "here"}

    return app, prod_ctrl, debug_ctrl


class TestAdmissionMiddleware:

    def test_accepts_request_when_slots_available(self):
        app, _, _ = _make_app(max_prod=2)
        client = TestClient(app)
        r = client.get("/api/v1/detect")
        assert r.status_code == 200

    def test_rejects_with_503_when_saturated(self):
        app, prod_ctrl, _ = _make_app(max_prod=1)
        # Fill the slot manually (simulate an in-flight request)
        asyncio.get_event_loop().run_until_complete(prod_ctrl.acquire())
        client = TestClient(app)
        r = client.get("/api/v1/detect")
        assert r.status_code == 503
        assert r.headers["retry-after"] == "10"
        assert "saturated" in r.text.lower() or "unavailable" in r.text.lower()

    def test_debug_has_independent_budget(self):
        """Saturating /detect does NOT affect /detect-debug."""
        app, prod_ctrl, _ = _make_app(max_prod=1, max_debug=1)
        asyncio.get_event_loop().run_until_complete(prod_ctrl.acquire())
        client = TestClient(app)
        assert client.get("/api/v1/detect").status_code == 503
        assert client.get("/api/v1/detect-debug").status_code == 200

    def test_health_bypasses_admission(self):
        """/health (and /metrics) must always respond, even when prod is saturated."""
        app, prod_ctrl, _ = _make_app(max_prod=1)
        asyncio.get_event_loop().run_until_complete(prod_ctrl.acquire())
        client = TestClient(app)
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/metrics").status_code == 200

    def test_kill_switch_disables_admission(self):
        """With enabled=False, middleware is a no-op."""
        app, prod_ctrl, _ = _make_app(max_prod=1, enabled=False)
        asyncio.get_event_loop().run_until_complete(prod_ctrl.acquire())
        client = TestClient(app)
        # With kill switch, request goes through even though counter is at max
        assert client.get("/api/v1/detect").status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_admission_middleware.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.middleware'`.

- [ ] **Step 3: Create the middleware package**

Create empty file `apps-microservices/api-detection-langue-fr/app/middleware/__init__.py`.

- [ ] **Step 4: Implement the middleware**

Create `apps-microservices/api-detection-langue-fr/app/middleware/admission.py`:

```python
"""FastAPI admission-control middleware.

Per-path routing to two AdmissionController instances:
- Production endpoints (/detect, /detect-batch, /check-url) share one pool
- /detect-debug has its own smaller pool so dev traffic can't starve prod
- Infrastructure endpoints (/health, /metrics, /, /docs, /openapi.json)
  bypass admission entirely

On rejection: 503 + Retry-After. On accept: counter++ until response
is built, then counter-- in finally.
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.admission import AdmissionController
from app.core.metrics import ADMISSION_REJECTED, INFLIGHT_REQUESTS

logger = logging.getLogger(__name__)

# Paths that use the production slot pool.
_PROD_PATHS = frozenset({
    "/api/v1/detect",
    "/api/v1/detect-batch",
    "/api/v1/check-url",
})

# Path using the isolated debug slot pool.
_DEBUG_PATH = "/api/v1/detect-debug"


class AdmissionMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        prod_controller: AdmissionController,
        debug_controller: AdmissionController,
        retry_after_seconds: int = 30,
        enabled: bool = True,
    ):
        super().__init__(app)
        self._prod = prod_controller
        self._debug = debug_controller
        self._retry_after = str(int(retry_after_seconds))
        self._enabled = enabled

    def _pick_controller(self, path: str):
        if path == _DEBUG_PATH:
            return self._debug, _DEBUG_PATH
        if path in _PROD_PATHS:
            return self._prod, path
        return None, None

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._enabled:
            return await call_next(request)

        controller, endpoint_label = self._pick_controller(request.url.path)
        if controller is None:
            # Not an admission-controlled path (health, metrics, docs, etc.)
            return await call_next(request)

        admitted = await controller.acquire()
        if not admitted:
            ADMISSION_REJECTED.labels(endpoint=endpoint_label).inc()
            logger.warning(
                f"Admission rejected for {endpoint_label}: "
                f"{controller.inflight}/{controller.max_slots} in flight"
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Service temporarily saturated",
                    "retry_after_seconds": int(self._retry_after),
                },
                headers={"Retry-After": self._retry_after},
            )

        INFLIGHT_REQUESTS.inc()
        try:
            return await call_next(request)
        finally:
            await controller.release()
            INFLIGHT_REQUESTS.dec()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_admission_middleware.py -v`

Expected: all 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/middleware/ \
        apps-microservices/api-detection-langue-fr/tests/test_admission_middleware.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): add admission middleware with path-scoped controllers

- /detect, /detect-batch, /check-url share the production slot pool
- /detect-debug has an isolated pool so dev traffic can't starve prod
- /health, /metrics and other infra paths bypass admission entirely
- On saturation: 503 + Retry-After header, ADMISSION_REJECTED counter++
- enabled=false kill switch for emergency rollback

---

feat(api-detection-langue-fr): ajoute le middleware d'admission avec controleurs par chemin

- /detect, /detect-batch, /check-url partagent le pool de slots prod
- /detect-debug a un pool isole pour que le dev n'affame pas la prod
- /health, /metrics et autres chemins infra contournent l'admission
- En saturation : 503 + header Retry-After, ADMISSION_REJECTED++
- Kill switch enabled=false pour un rollback d'urgence
EOF
)"
```

---

### Task 7: Wire admission middleware into `main.py`

**Goal:** Instantiate the two controllers from env vars and attach the middleware to the running app.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/main.py`

**Acceptance Criteria:**
- [ ] Two `AdmissionController` instances created from `ADMISSION_MAX_SLOTS` (default 12) and `ADMISSION_DEBUG_SLOTS` (default 2)
- [ ] `AdmissionMiddleware` attached with `retry_after_seconds` from `ADMISSION_RETRY_AFTER_SECONDS` (default 30)
- [ ] `ADMISSION_ENABLED` env var controls the `enabled` flag (default `true`)
- [ ] Manual smoke test: start the service locally, fill the pool by setting a small max, observe 503

**Verify:**
```bash
cd apps-microservices/api-detection-langue-fr
ADMISSION_MAX_SLOTS=1 python -c "
import asyncio, httpx
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
# hit /api/v1/health to confirm server starts
print('health:', client.get('/api/v1/health').status_code)
print('metrics content-type:', client.get('/metrics').headers.get('content-type'))
"
```
Expected: `health: 200`, `metrics content-type: text/plain; ...`

**Steps:**

- [ ] **Step 1: Modify `main.py` to instantiate controllers and attach middleware**

In `apps-microservices/api-detection-langue-fr/main.py`, add imports at the top (after existing imports):

```python
import os
from app.core.admission import AdmissionController
from app.middleware.admission import AdmissionMiddleware
```

After the `app = FastAPI(...)` declaration and before `app.include_router(router, prefix="/api/v1")`, add:

```python
# ─── Admission control ────────────────────────────────────────────────────────
_admission_enabled = os.getenv("ADMISSION_ENABLED", "true").lower() == "true"
_prod_admission = AdmissionController(
    max_slots=int(os.getenv("ADMISSION_MAX_SLOTS", "12"))
)
_debug_admission = AdmissionController(
    max_slots=int(os.getenv("ADMISSION_DEBUG_SLOTS", "2"))
)
app.add_middleware(
    AdmissionMiddleware,
    prod_controller=_prod_admission,
    debug_controller=_debug_admission,
    retry_after_seconds=int(os.getenv("ADMISSION_RETRY_AFTER_SECONDS", "30")),
    enabled=_admission_enabled,
)
logger = logging.getLogger(__name__)
logger.info(
    f"Admission middleware attached: enabled={_admission_enabled}, "
    f"prod={_prod_admission.max_slots}, debug={_debug_admission.max_slots}"
)
```

- [ ] **Step 2: Smoke-test locally**

```bash
cd apps-microservices/api-detection-langue-fr
ADMISSION_MAX_SLOTS=5 python -c "
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
assert client.get('/api/v1/health').status_code == 200
print('OK — health responds with admission middleware attached')
"
```

Expected: `OK — health responds with admission middleware attached`

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/main.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): wire admission middleware into main app

Instantiates the prod and debug AdmissionController instances from env
vars (ADMISSION_MAX_SLOTS, ADMISSION_DEBUG_SLOTS) and attaches the
AdmissionMiddleware. Controlled by ADMISSION_ENABLED (kill switch) and
ADMISSION_RETRY_AFTER_SECONDS.

---

feat(api-detection-langue-fr): cable le middleware d'admission dans l'app principale

Instancie les deux AdmissionController (prod et debug) depuis les env
(ADMISSION_MAX_SLOTS, ADMISSION_DEBUG_SLOTS) et attache le
AdmissionMiddleware. Controle par ADMISSION_ENABLED (kill switch) et
ADMISSION_RETRY_AFTER_SECONDS.
EOF
)"
```

---

### Task 8: `InflightDedup` class with tests

**Goal:** Implement the URL coalescing primitive. Concurrent requests for the same URL wait on a shared future instead of launching duplicate browsers.

**Files:**
- Create: `apps-microservices/api-detection-langue-fr/app/core/inflight_dedup.py`
- Create: `apps-microservices/api-detection-langue-fr/tests/test_inflight_dedup.py`

**Acceptance Criteria:**
- [ ] `InflightDedup` class with `async coalesce(key: str, factory: Callable[[], Awaitable[T]]) -> T`
- [ ] First caller for `key`: runs `factory()`, stores result, returns it
- [ ] Concurrent callers for same `key`: await the shared future, return same result
- [ ] Exception in `factory()`: propagates to all waiters; entry removed so next call retries
- [ ] Different keys: fully independent (no cross-talk)
- [ ] `dedup.hits` property counts how many coalesced calls were served
- [ ] All tests pass

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_inflight_dedup.py -v`

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `apps-microservices/api-detection-langue-fr/tests/test_inflight_dedup.py`:

```python
"""Tests for InflightDedup."""
import asyncio
import pytest


class TestInflightDedup:

    @pytest.mark.asyncio
    async def test_first_caller_runs_factory(self):
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()
        called = {"count": 0}

        async def factory():
            called["count"] += 1
            return "result"

        out = await dedup.coalesce("url1", factory)
        assert out == "result"
        assert called["count"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_callers_coalesce(self):
        """5 concurrent calls for same key → factory runs once, all get same value."""
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()
        calls = {"count": 0}

        async def factory():
            calls["count"] += 1
            await asyncio.sleep(0.05)  # give coalescing a chance to occur
            return "shared"

        results = await asyncio.gather(*[
            dedup.coalesce("url-same", factory) for _ in range(5)
        ])
        assert all(r == "shared" for r in results)
        assert calls["count"] == 1
        assert dedup.hits >= 4  # 4 coalesced, 1 original

    @pytest.mark.asyncio
    async def test_different_keys_independent(self):
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()

        async def factory_a():
            return "A"

        async def factory_b():
            return "B"

        a, b = await asyncio.gather(
            dedup.coalesce("url-a", factory_a),
            dedup.coalesce("url-b", factory_b),
        )
        assert a == "A"
        assert b == "B"

    @pytest.mark.asyncio
    async def test_exception_propagates_to_all_waiters(self):
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()

        async def failing_factory():
            await asyncio.sleep(0.05)
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            await asyncio.gather(*[
                dedup.coalesce("url-fail", failing_factory) for _ in range(3)
            ])

    @pytest.mark.asyncio
    async def test_entry_cleaned_up_after_exception(self):
        """After a failure, a subsequent call for same key retries."""
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()
        attempts = {"n": 0}

        async def flaky():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("first try fails")
            return "second try succeeds"

        with pytest.raises(RuntimeError):
            await dedup.coalesce("url-flaky", flaky)
        out = await dedup.coalesce("url-flaky", flaky)
        assert out == "second try succeeds"
        assert attempts["n"] == 2

    @pytest.mark.asyncio
    async def test_entry_cleaned_up_after_success(self):
        """After success, entry is removed so a later unrelated call is not served stale."""
        from app.core.inflight_dedup import InflightDedup
        dedup = InflightDedup()

        async def factory_v1():
            return "v1"

        async def factory_v2():
            return "v2"

        out1 = await dedup.coalesce("url-same", factory_v1)
        out2 = await dedup.coalesce("url-same", factory_v2)
        assert out1 == "v1"
        assert out2 == "v2"  # not "v1" — dedup only while in-flight
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_inflight_dedup.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `InflightDedup`**

Create `apps-microservices/api-detection-langue-fr/app/core/inflight_dedup.py`:

```python
"""In-process URL coalescing primitive.

NOT a cache — the entry only lives while the fetch is actually in
flight. After the factory resolves or raises, the entry is removed so
subsequent calls run a fresh factory.

Purpose: when N concurrent callers ask for the same URL at the same
time, run the expensive browser launch once and give them all the same
result. The existing Redis cache handles the "completed within last
30d/7d/6h" case; this handles the "completed 20ms ago but cache not
written yet" case.
"""
import asyncio
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class InflightDedup:
    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self._hits = 0

    @property
    def hits(self) -> int:
        """Number of coalesced calls served from a shared future."""
        return self._hits

    async def coalesce(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        """Run factory() at most once for concurrent callers with the same key.

        First caller for the key: registers a future, runs factory(), resolves
        the future, cleans up the entry.
        Concurrent callers: await the existing future and get the same result
        (or exception).

        The factory runs OUTSIDE the lock so unrelated coalesce() calls for
        different keys are not serialized.
        """
        async with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                self._hits += 1
                fut = existing
                is_owner = False
            else:
                fut = asyncio.get_event_loop().create_future()
                self._inflight[key] = fut
                is_owner = True

        if not is_owner:
            # Wait on someone else's future
            return await fut

        # We own the future: run factory, resolve future, clean up
        try:
            result = await factory()
        except BaseException as e:
            fut.set_exception(e)
            raise
        else:
            fut.set_result(result)
            return result
        finally:
            async with self._lock:
                self._inflight.pop(key, None)
```

**Implementation note:** the `is_owner` flag is set inside the lock, guaranteeing that exactly one caller per key becomes the owner and runs `factory()`. All other concurrent callers with the same key are non-owners and simply `await` the shared future.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps-microservices/api-detection-langue-fr && python -m pytest tests/test_inflight_dedup.py -v`

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/core/inflight_dedup.py \
        apps-microservices/api-detection-langue-fr/tests/test_inflight_dedup.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): add InflightDedup for URL coalescing

Concurrent fetches for the same URL share a single in-flight future:
one browser launch, N waiters. Entry only lives while the fetch is
actually in flight — not a cache. Complements the existing Redis
domain cache (which covers completed 30d/7d/6h results).

---

feat(api-detection-langue-fr): ajoute InflightDedup pour la coalescence d'URL

Les fetches concurrents d'une meme URL partagent un future unique : un
seul lancement de navigateur, N attenteurs. L'entree ne vit que le
temps du fetch en vol — pas un cache. Complete le cache Redis de
domaine existant (qui couvre les resultats termines a 30j/7j/6h).
EOF
)"
```

---

### Task 9: Wire inflight dedup into `routes.py _detect_single_url`

**Goal:** Replace the direct `fetch_html` call inside `_detect_single_url` with `dedup.coalesce(...)`, keyed by normalized URL. Respect `force_refresh` to bypass dedup.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py`

**Acceptance Criteria:**
- [ ] Module-level `_inflight_dedup = InflightDedup()` singleton
- [ ] `INFLIGHT_DEDUP_ENABLED` env var gates the behavior (default `true`)
- [ ] When enabled and `force_refresh=False`, `fetch_html(url, proxy_url)` is wrapped in `_inflight_dedup.coalesce(normalized_url, ...)`
- [ ] When disabled OR `force_refresh=True`, `fetch_html` runs directly (current behavior)
- [ ] Normalization: lowercase host + path (NOT just domain — different pages of same domain should not coalesce)
- [ ] `DEDUP_HITS` counter stays in sync with `InflightDedup.hits`
- [ ] Existing tests in `test_api.py` and `test_domain_fr.py` still pass (no regressions)

**Verify:**
```bash
cd apps-microservices/api-detection-langue-fr && python -m pytest tests/ -v --ignore=tests/test_api.py
```
(test_api.py has pre-existing import issues unrelated to this change.)

Expected: all non-broken tests pass.

**Steps:**

- [ ] **Step 1: Add imports and module-level dedup instance**

In `apps-microservices/api-detection-langue-fr/app/api/routes.py`, add near the top imports (after existing imports):

```python
import os
from urllib.parse import urlparse
from app.core.inflight_dedup import InflightDedup
from app.core.metrics import DEDUP_HITS

_inflight_dedup = InflightDedup()
_INFLIGHT_DEDUP_ENABLED = os.getenv("INFLIGHT_DEDUP_ENABLED", "true").lower() == "true"


def _normalize_url_for_dedup(url: str) -> str:
    """Normalize URL for dedup: lowercase scheme+host+path, strip trailing slash, drop fragment."""
    try:
        p = urlparse(url)
        scheme = (p.scheme or "https").lower()
        host = (p.hostname or "").lower()
        path = (p.path or "/").rstrip("/") or "/"
        q = f"?{p.query}" if p.query else ""
        return f"{scheme}://{host}{path}{q}"
    except Exception:
        return url
```

- [ ] **Step 2: Wrap the `fetch_html` call in `_detect_single_url`**

Find the block inside `_detect_single_url` (around line 74) that reads:

```python
        # Fetch HTML
        fetch_result = await fetch_html(url, proxy_url)
        if not fetch_result:
            return DetectionResponse(...)
```

Replace with:

```python
        # Fetch HTML (with inflight dedup unless force_refresh)
        if _INFLIGHT_DEDUP_ENABLED and not force_refresh:
            dedup_key = _normalize_url_for_dedup(url)
            prev_hits = _inflight_dedup.hits
            fetch_result = await _inflight_dedup.coalesce(
                dedup_key, lambda: fetch_html(url, proxy_url)
            )
            # Sync metric counter with dedup hit-count delta
            if _inflight_dedup.hits > prev_hits:
                DEDUP_HITS.inc(_inflight_dedup.hits - prev_hits)
        else:
            fetch_result = await fetch_html(url, proxy_url)

        if not fetch_result:
            return DetectionResponse(
                ok=False, url=url, method='fetch_failed',
                error='Impossible de récupérer le contenu HTML'
            )
```

- [ ] **Step 3: Run the existing test suite — no regressions**

```bash
cd apps-microservices/api-detection-langue-fr
python -m pytest tests/test_domain_fr.py tests/test_scraper.py tests/test_admission.py tests/test_admission_middleware.py tests/test_inflight_dedup.py tests/test_metrics.py -v
```

Expected: all tests pass. (test_api.py is known-broken from pre-existing issues; skip it.)

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/api/routes.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): coalesce duplicate concurrent URL fetches

Wraps fetch_html inside _detect_single_url with InflightDedup keyed by
normalized URL (scheme+host+path+query). N concurrent callers for the
same URL now share a single browser launch. force_refresh=True and the
INFLIGHT_DEDUP_ENABLED=false kill switch bypass dedup.

---

feat(api-detection-langue-fr): coalesce les fetches d'URL concurrents duplicates

Encapsule fetch_html dans _detect_single_url avec InflightDedup indexe
par URL normalisee (scheme+host+path+query). Les N appelants concurrents
d'une meme URL partagent maintenant un seul lancement de navigateur.
force_refresh=True et le kill switch INFLIGHT_DEDUP_ENABLED=false
contournent le dedup.
EOF
)"
```

---

## Phase 4 — Caller rollout

### Task 10: Create `common_utils.detection_client` Python helper

**Goal:** Ship the shared Python HTTP client wrapper that any Python caller of api-detection-langue-fr should use. Enforces the contract via env vars.

**Files:**
- Create: `libs/common-utils/src/common_utils/detection_client.py`
- Create: `libs/common-utils/tests/test_detection_client.py`

**Acceptance Criteria:**
- [ ] Class `DetectionClient` with methods `detect(url, mode, ...)`, `detect_batch(items, ...)`, `check_url(url)`
- [ ] Reads `DETECTION_MAX_CONCURRENCY` (default 5), `DETECTION_REQUEST_TIMEOUT_S` (default 180), `DETECTION_MAX_RETRIES` (default 2), `DETECTION_BACKOFF_BASE_S` (default 2)
- [ ] `asyncio.Semaphore` caps concurrency at `DETECTION_MAX_CONCURRENCY`
- [ ] On 503: waits based on precedence — server `Retry-After` header > exponential `backoff_base * 2**attempt`
- [ ] Retries up to `DETECTION_MAX_RETRIES` on 503 only; other status codes raise immediately
- [ ] All tests pass

**Verify:**
```bash
cd libs/common-utils && python -m pytest tests/test_detection_client.py -v
```

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `libs/common-utils/tests/test_detection_client.py`:

```python
"""Tests for common_utils.detection_client.DetectionClient."""
import asyncio
import os
import pytest
import httpx
import respx


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Reset contract env vars to known defaults so tests are hermetic."""
    for var in (
        "DETECTION_MAX_CONCURRENCY",
        "DETECTION_REQUEST_TIMEOUT_S",
        "DETECTION_MAX_RETRIES",
        "DETECTION_BACKOFF_BASE_S",
    ):
        monkeypatch.delenv(var, raising=False)


class TestDetectionClientBasic:

    @pytest.mark.asyncio
    @respx.mock
    async def test_detect_success(self):
        from common_utils.detection_client import DetectionClient
        respx.post("http://detect/api/v1/detect").mock(
            return_value=httpx.Response(200, json={"ok": True, "url": "https://x", "method": "langHtml"})
        )
        client = DetectionClient("http://detect")
        result = await client.detect("https://x", mode="simple")
        assert result["ok"] is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_on_503_honoring_retry_after(self):
        from common_utils.detection_client import DetectionClient
        # First response: 503 with Retry-After: 0 (for fast test)
        # Second response: 200
        route = respx.post("http://detect/api/v1/detect").mock(
            side_effect=[
                httpx.Response(503, headers={"Retry-After": "0"}),
                httpx.Response(200, json={"ok": True, "url": "https://x", "method": "m"}),
            ]
        )
        client = DetectionClient("http://detect")
        result = await client.detect("https://x")
        assert result["ok"] is True
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_exhausts_retries_and_raises(self, monkeypatch):
        from common_utils.detection_client import DetectionClient
        monkeypatch.setenv("DETECTION_MAX_RETRIES", "1")
        respx.post("http://detect/api/v1/detect").mock(
            return_value=httpx.Response(503, headers={"Retry-After": "0"})
        )
        client = DetectionClient("http://detect")
        with pytest.raises(httpx.HTTPStatusError):
            await client.detect("https://x")

    @pytest.mark.asyncio
    @respx.mock
    async def test_non_503_error_does_not_retry(self):
        from common_utils.detection_client import DetectionClient
        route = respx.post("http://detect/api/v1/detect").mock(
            return_value=httpx.Response(500, json={"detail": "boom"})
        )
        client = DetectionClient("http://detect")
        with pytest.raises(httpx.HTTPStatusError):
            await client.detect("https://x")
        assert route.call_count == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_concurrency_semaphore_caps_inflight(self, monkeypatch):
        """With DETECTION_MAX_CONCURRENCY=2, at most 2 requests are in flight at once."""
        from common_utils.detection_client import DetectionClient
        monkeypatch.setenv("DETECTION_MAX_CONCURRENCY", "2")

        in_flight = {"current": 0, "peak": 0}

        def _handler(request):
            in_flight["current"] += 1
            in_flight["peak"] = max(in_flight["peak"], in_flight["current"])
            # Simulate work
            import time; time.sleep(0.02)
            in_flight["current"] -= 1
            return httpx.Response(200, json={"ok": True, "url": "https://x", "method": "m"})

        respx.post("http://detect/api/v1/detect").mock(side_effect=_handler)
        client = DetectionClient("http://detect")
        await asyncio.gather(*[client.detect(f"https://x/{i}") for i in range(10)])
        assert in_flight["peak"] <= 2
```

- [ ] **Step 2: Ensure test deps available**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB/libs/common-utils
pip install httpx respx pytest pytest-asyncio
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd libs/common-utils && python -m pytest tests/test_detection_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'common_utils.detection_client'`.

- [ ] **Step 4: Implement the DetectionClient module**

Create `libs/common-utils/src/common_utils/detection_client.py`:

```python
"""Shared HTTP client enforcing the api-detection-langue-fr call contract.

Contract env vars (with defaults):
  DETECTION_MAX_CONCURRENCY=5     max concurrent /detect calls per client instance
  DETECTION_REQUEST_TIMEOUT_S=180 httpx total timeout
  DETECTION_MAX_RETRIES=2         retries on 503 (server overload)
  DETECTION_BACKOFF_BASE_S=2      exponential backoff base when Retry-After absent

Retry policy:
  - Retries ONLY on HTTP 503.
  - Wait precedence: server `Retry-After` header if present, else
    `backoff_base * 2**attempt` seconds.
"""
import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class DetectionClient:
    """HTTP client wrapper for api-detection-langue-fr enforcing the caller contract."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._sem = asyncio.Semaphore(int(os.getenv("DETECTION_MAX_CONCURRENCY", "5")))
        self._timeout = float(os.getenv("DETECTION_REQUEST_TIMEOUT_S", "180"))
        self._max_retries = int(os.getenv("DETECTION_MAX_RETRIES", "2"))
        self._backoff_base = float(os.getenv("DETECTION_BACKOFF_BASE_S", "2"))

    async def detect(self, url: str, mode: str = "complete", **kwargs: Any) -> dict:
        body = {"url": url, "mode": mode, **kwargs}
        return await self._request_with_retry("POST", "/api/v1/detect", json=body)

    async def detect_batch(self, items: list[dict], **kwargs: Any) -> dict:
        body = {"items": items, **kwargs}
        return await self._request_with_retry("POST", "/api/v1/detect-batch", json=body)

    async def check_url(self, url: str, track_redirect: bool = False) -> dict:
        params = {"url": url, "track_redirect": str(track_redirect).lower()}
        return await self._request_with_retry("GET", "/api/v1/check-url", params=params)

    async def _request_with_retry(self, method: str, path: str, **kwargs: Any) -> dict:
        full_url = f"{self._base_url}{path}"
        async with self._sem:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout, connect=10.0)) as client:
                for attempt in range(self._max_retries + 1):
                    response = await client.request(method, full_url, **kwargs)
                    if response.status_code != 503:
                        response.raise_for_status()
                        return response.json()

                    # 503: decide whether to retry
                    if attempt >= self._max_retries:
                        # No retries left — raise with context
                        response.raise_for_status()

                    # Precedence: server Retry-After > exponential backoff
                    retry_after = response.headers.get("Retry-After")
                    if retry_after is not None:
                        try:
                            wait_s = float(retry_after)
                        except ValueError:
                            wait_s = self._backoff_base * (2 ** attempt)
                    else:
                        wait_s = self._backoff_base * (2 ** attempt)

                    logger.warning(
                        f"DetectionClient got 503 for {method} {path} "
                        f"(attempt {attempt + 1}/{self._max_retries + 1}); "
                        f"waiting {wait_s}s before retry"
                    )
                    await asyncio.sleep(wait_s)

        # unreachable
        raise RuntimeError("DetectionClient retry loop exited without result")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd libs/common-utils && python -m pytest tests/test_detection_client.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 6: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add libs/common-utils/src/common_utils/detection_client.py \
        libs/common-utils/tests/test_detection_client.py
git commit -m "$(cat <<'EOF'
feat(common-utils): add DetectionClient enforcing the detection-langue-fr contract

Shared HTTP client wrapper for any Python service calling
api-detection-langue-fr. Enforces the caller-side contract:
- Per-instance asyncio.Semaphore caps concurrency at
  DETECTION_MAX_CONCURRENCY (default 5)
- httpx 180s timeout via DETECTION_REQUEST_TIMEOUT_S
- 503-only retry honoring Retry-After (server guidance) with
  exponential fallback DETECTION_BACKOFF_BASE_S * 2**attempt

---

feat(common-utils): ajoute DetectionClient applicant le contrat detection-langue-fr

Wrapper HTTP client partage pour tout service Python appelant
api-detection-langue-fr. Applique le contrat cote appelant :
- Semaphore asyncio par instance limitant la concurrence a
  DETECTION_MAX_CONCURRENCY (defaut 5)
- Timeout httpx de 180s via DETECTION_REQUEST_TIMEOUT_S
- Retry 503 uniquement en respectant Retry-After (directive serveur)
  avec fallback exponentiel DETECTION_BACKOFF_BASE_S * 2**attempt
EOF
)"
```

---

### Task 11: Gateway per-service timeout override (detection only)

**Goal:** Add a `DOWNSTREAM_TIMEOUTS_S` map to the api-gateway settings, apply it in `proxy()` so that detection calls get a 180s timeout while all other services keep the existing `timeout=None` behavior.

**Files:**
- Modify: `apps-microservices/api-gateway/app/core/settings.py`
- Modify: `apps-microservices/api-gateway/main.py`
- Create: `apps-microservices/api-gateway/tests/test_proxy_timeout.py`

**Acceptance Criteria:**
- [ ] `Configuration.DOWNSTREAM_TIMEOUTS_S: Dict[str, float]` with `{"api-detection-langue-fr-service": 180.0}`
- [ ] `proxy()` derives `timeout` from the map, falling back to `None` for unmapped services
- [ ] 503 pass-through with Retry-After header preserved (should already work — assert it does)
- [ ] Test: proxy call to an unmapped service has `timeout=None`; call to detection has `timeout=180`
- [ ] Existing gateway tests still pass

**Verify:**
```bash
cd apps-microservices/api-gateway && python -m pytest tests/test_proxy_timeout.py -v
```

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `apps-microservices/api-gateway/tests/test_proxy_timeout.py`:

```python
"""Tests for the per-service downstream timeout map."""
import pytest
import httpx
import respx


class TestDownstreamTimeouts:

    def test_detection_service_has_180s_timeout(self):
        from app.core.settings import settings
        assert settings.DOWNSTREAM_TIMEOUTS_S["api-detection-langue-fr-service"] == 180.0

    def test_unmapped_services_absent_from_map(self):
        from app.core.settings import settings
        # Other services are NOT in the map (preserves existing timeout=None behavior)
        assert "embedding-service" not in settings.DOWNSTREAM_TIMEOUTS_S
        assert "llm-service" not in settings.DOWNSTREAM_TIMEOUTS_S
```

And add a minimal integration test (requires the proxy to be testable — if complex, replace with the direct map test plus a manual smoke test). For now, the config-level test is sufficient to prove the wiring:

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps-microservices/api-gateway && python -m pytest tests/test_proxy_timeout.py -v
```

Expected: FAIL with `AttributeError: type object 'Configuration' has no attribute 'DOWNSTREAM_TIMEOUTS_S'`.

- [ ] **Step 3: Add `DOWNSTREAM_TIMEOUTS_S` to settings**

In `apps-microservices/api-gateway/app/core/settings.py`, add a new class attribute to `Configuration`. Insert after the `EXCLUDED_ROUTES_LIST` block:

```python
    # ─── Per-service downstream timeouts ───────────────────────────────────
    # Keys are service names (the <name> in /<name>-service path prefixes).
    # Services NOT listed here use timeout=None (current behavior preserved).
    # Add a service here only after understanding its request-duration profile.
    DOWNSTREAM_TIMEOUTS_S: Dict[str, float] = {
        "api-detection-langue-fr-service": 180.0,
    }
```

- [ ] **Step 4: Use the map in `proxy()`**

In `apps-microservices/api-gateway/main.py`, find the `async with httpx.AsyncClient() as client:` block (around line 188). Replace it:

```python
    # Per-service timeout: detection=180s, others=None (existing behavior)
    service_key = f"{service}-service" if not service.endswith("-service") else service
    timeout_s = settings.DOWNSTREAM_TIMEOUTS_S.get(service_key)
    timeout = httpx.Timeout(timeout_s, connect=10.0) if timeout_s else None

    start_time = time.monotonic()
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.request(
                request.method,
                target_url,
                headers=headers,
                content=body,
            )
        except httpx.TimeoutException as e:
            # Downstream took longer than its per-service budget
            logger.warning(f"Timeout calling {service} after {timeout_s}s: {e}")
            return JSONResponse(
                status_code=504,
                content={"detail": f"Le service '{service}' a depasse son timeout ({timeout_s}s)."},
            )
        except httpx.RequestError as e:
            logger.error(f"Impossible de contacter le service {service}: {e}")
            return JSONResponse(
                status_code=503,
                content={"detail": f"Le service '{service}' est indisponible."},
            )

    # Log 503 responses at WARNING (load-shedding signal, not bug)
    if response.status_code == 503:
        logger.warning(
            f"Service {service} returned 503 (retry-after={response.headers.get('retry-after', 'n/a')})"
        )
```

**Note:** remove the old `timeout=None` line since we're now setting it explicitly.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd apps-microservices/api-gateway && python -m pytest tests/test_proxy_timeout.py -v
```

Expected: both config tests pass.

- [ ] **Step 6: Manual smoke test — import check**

```bash
cd apps-microservices/api-gateway
python -c "from main import app; print('gateway import OK')"
```

Expected: `gateway import OK`.

- [ ] **Step 7: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/api-gateway/app/core/settings.py \
        apps-microservices/api-gateway/main.py \
        apps-microservices/api-gateway/tests/test_proxy_timeout.py
git commit -m "$(cat <<'EOF'
feat(api-gateway): add per-service downstream timeout map (detection=180s)

Replaces the blanket timeout=None with a per-service opt-in map.
Only api-detection-langue-fr-service is configured (180s total, 10s
connect). All other services keep timeout=None — current behavior
preserved so this change has zero blast radius on unrelated services.
503 responses from downstream are now logged at WARNING level.

---

feat(api-gateway): ajoute une map de timeouts par service downstream (detection=180s)

Remplace le timeout=None global par une map opt-in par service.
Seul api-detection-langue-fr-service est configure (180s total, 10s
connect). Tous les autres services conservent timeout=None — le
comportement actuel est preserve donc ce changement a zero impact sur
les services non-concernes. Les 503 en provenance des services
downstream sont desormais logues au niveau WARNING.
EOF
)"
```

---

### Task 12: Crawler `DetectionLangueClient.ts` — p-limit + 503 retry

**Goal:** Cap concurrent `/detect` calls per crawler instance, handle 503 responses by honoring `Retry-After` (fallback to exponential backoff), and bump the axios timeout to 180s.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/package.json` (add `p-limit`)
- Modify: `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts`

**Acceptance Criteria:**
- [ ] `p-limit: ^5.0.0` added to crawler/package.json dependencies
- [ ] `DetectionLangueClient` uses `pLimit(DETECTION_MAX_CONCURRENCY ?? 5)` to cap concurrent `/detect` calls
- [ ] 503 triggers retry up to `DETECTION_MAX_RETRIES` (default 2), honoring `Retry-After` header
- [ ] When `Retry-After` is absent, exponential backoff `DETECTION_BACKOFF_BASE_S * 2**attempt`
- [ ] Axios timeout bumped from 120000 to `DETECTION_REQUEST_TIMEOUT_S * 1000` (default 180000)
- [ ] `npm run build` succeeds (TypeScript compiles)
- [ ] Existing `checkUrl` and helper methods preserved

**Verify:**
```bash
cd apps-microservices/crawler-service/crawler
npm install
npm run build
```
Expected: no TypeScript errors; `dist/class/DetectionLangueClient.js` produced.

**Steps:**

- [ ] **Step 1: Check if p-limit is already transitively installed**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service/crawler
npm ls p-limit 2>&1 | head -10
```

If present via crawlee: note the version. If not: we add it as a direct dep.

Either way, adding it to the direct dependencies block of `package.json` is correct practice (makes the intent explicit and pins the API we rely on).

- [ ] **Step 2: Add `p-limit` to `package.json`**

Edit `apps-microservices/crawler-service/crawler/package.json`. In the `dependencies` object, add (keeping alphabetical order):

```json
    "dependencies": {
        "axios": "^1.7.2",
        "camoufox-js": "^0.9.3",
        "crawlee": "^3.0.0",
        "p-limit": "^5.0.0",
        "playwright": "1.56.1",
        "redis": "^4.6.10"
    },
```

- [ ] **Step 3: Update `DetectionLangueClient.ts`**

Edit `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts`. At the top, add the import:

```typescript
import axios, { AxiosInstance, AxiosError } from "axios";
import pLimit from "p-limit";
```

Replace the constructor with one that reads env-driven contract values and creates the limiter + retry state:

```typescript
export class DetectionLangueClient {
    private client: AxiosInstance;
    private limit: ReturnType<typeof pLimit>;
    private maxRetries: number;
    private backoffBaseS: number;

    constructor(baseUrl?: string) {
        const url =
            baseUrl ||
            process.env.DETECTION_LANGUE_API_URL ||
            "http://api-detection-langue-fr-service:8999";
        if (!baseUrl && !process.env.DETECTION_LANGUE_API_URL) {
            console.warn('DETECTION_LANGUE_API_URL not set, using default: http://api-detection-langue-fr-service:8999');
        }

        const timeoutMs = parseInt(process.env.DETECTION_REQUEST_TIMEOUT_S ?? "180") * 1000;
        const maxConcurrency = parseInt(process.env.DETECTION_MAX_CONCURRENCY ?? "5");
        this.maxRetries = parseInt(process.env.DETECTION_MAX_RETRIES ?? "2");
        this.backoffBaseS = parseFloat(process.env.DETECTION_BACKOFF_BASE_S ?? "2");

        this.client = axios.create({
            baseURL: `${url}/api/v1`,
            timeout: timeoutMs,
            // DO NOT use validateStatus — default is 2xx, we want 503 to throw so
            // our retry logic in catch() fires.
        });
        this.limit = pLimit(maxConcurrency);
    }
```

Replace the `detect` method body to use `this.limit(...)` and the retry wrapper:

```typescript
    async detect(
        url: string,
        htmlContent?: string,
        options?: DetectOptions
    ): Promise<DetectionResult> {
        return this.limit(() => this._detectWithRetry(url, htmlContent, options));
    }

    private async _detectWithRetry(
        url: string,
        htmlContent?: string,
        options?: DetectOptions
    ): Promise<DetectionResult> {
        for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
            try {
                const response = await this.client.post<DetectionResult>("/detect", {
                    url,
                    html_content: htmlContent || undefined,
                    mode: options?.mode ?? "complete",
                    forced_method: options?.forcedMethod ?? undefined,
                    use_nlp_detection: options?.useNlpDetection ?? true,
                    proxy_url: options?.proxyUrl ?? undefined,
                });
                return response.data;
            } catch (error: any) {
                const axiosErr = error as AxiosError;
                const status = axiosErr.response?.status;

                // Retry only on 503 (server overload) with budget remaining
                if (status === 503 && attempt < this.maxRetries) {
                    const retryAfterHeader = axiosErr.response?.headers?.["retry-after"];
                    // Precedence: server Retry-After > exponential backoff
                    const waitS = retryAfterHeader
                        ? parseFloat(String(retryAfterHeader))
                        : this.backoffBaseS * Math.pow(2, attempt);
                    console.warn(
                        `DetectionLangueClient got 503 for ${url} ` +
                        `(attempt ${attempt + 1}/${this.maxRetries + 1}); ` +
                        `waiting ${waitS}s before retry`
                    );
                    await new Promise((resolve) => setTimeout(resolve, waitS * 1000));
                    continue;
                }

                // Non-retryable or retry budget exhausted
                const message = axiosErr.response?.data?.detail || axiosErr.message || String(error);
                throw new Error(`Detection API error for ${url}: ${message}`);
            }
        }
        throw new Error(`Detection API retry loop exited without result for ${url}`);
    }
```

Replace the `checkUrl` method body to also use the limiter (smaller operation but still counts against the caller budget):

```typescript
    async checkUrl(
        url: string,
        trackRedirect: boolean = false
    ): Promise<CheckUrlResult> {
        return this.limit(async () => {
            try {
                const response = await this.client.get<CheckUrlResult>("/check-url", {
                    params: { url, track_redirect: trackRedirect },
                });
                return response.data;
            } catch (error: any) {
                const message = error?.response?.data?.detail || error?.message || String(error);
                throw new Error(`Detection API check-url error for ${url}: ${message}`);
            }
        });
    }
```

Keep all other existing methods (`extractPrimaryMethod`, etc.) unchanged.

- [ ] **Step 4: Install new dep and build**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB/apps-microservices/crawler-service/crawler
npm install
npm run build
```

Expected: install succeeds; `tsc` compiles without errors; `dist/class/DetectionLangueClient.js` exists.

- [ ] **Step 5: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/crawler/package.json \
        apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts
git commit -m "$(cat <<'EOF'
feat(crawler-service): apply detection-langue-fr caller contract

- p-limit(DETECTION_MAX_CONCURRENCY=5) caps concurrent /detect and
  /check-url calls per crawler instance
- 503 responses trigger retry with Retry-After precedence over
  exponential backoff (DETECTION_BACKOFF_BASE_S * 2**attempt)
- Retries up to DETECTION_MAX_RETRIES=2 on 503 only; other errors
  propagate immediately
- Axios timeout bumped to DETECTION_REQUEST_TIMEOUT_S * 1000 (default
  180s) to align with the contract

---

feat(crawler-service): applique le contrat appelant detection-langue-fr

- p-limit(DETECTION_MAX_CONCURRENCY=5) limite les appels concurrents a
  /detect et /check-url par instance crawler
- Les reponses 503 declenchent un retry avec Retry-After prioritaire
  sur le backoff exponentiel (DETECTION_BACKOFF_BASE_S * 2**attempt)
- Retries jusqu'a DETECTION_MAX_RETRIES=2 uniquement sur 503 ; les
  autres erreurs se propagent immediatement
- Timeout axios augmente a DETECTION_REQUEST_TIMEOUT_S * 1000 (defaut
  180s) pour s'aligner avec le contrat
EOF
)"
```

---

### Task 13: CLAUDE.md updates for api-gateway and crawler-service

**Goal:** Document the caller-contract integration in both downstream services' CLAUDE.md files so future contributors discover the convention.

**Files:**
- Modify: `apps-microservices/api-gateway/CLAUDE.md`
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] api-gateway CLAUDE.md documents `DOWNSTREAM_TIMEOUTS_S` convention and references the detection timeout
- [ ] crawler-service CLAUDE.md documents the DetectionLangueClient contract env vars and the 503 retry behavior
- [ ] No code changes

**Verify:**
```bash
grep -E "DOWNSTREAM_TIMEOUTS_S|DETECTION_MAX_CONCURRENCY" apps-microservices/api-gateway/CLAUDE.md apps-microservices/crawler-service/CLAUDE.md
```
Expected: both files contain the new references.

**Steps:**

- [ ] **Step 1: Add "Per-service downstream timeouts" section to api-gateway CLAUDE.md**

Append to `apps-microservices/api-gateway/CLAUDE.md` (at the end, before the final blank line):

```markdown
## Per-Service Downstream Timeouts

The gateway applies per-service HTTP timeouts via `Configuration.DOWNSTREAM_TIMEOUTS_S` in `app/core/settings.py`. Services NOT in the map use `timeout=None` (current behavior preserved — zero blast radius on unlisted services).

Currently configured:
- `api-detection-langue-fr-service`: 180s total, 10s connect

Add a service to the map only after understanding its request-duration profile. On timeout, the gateway returns `504` to the caller. Downstream `503` responses (typically from admission middleware load-shedding) are logged at WARNING and passed through with `Retry-After` intact.
```

- [ ] **Step 2: Add "api-detection-langue-fr caller contract" section to crawler-service CLAUDE.md**

Append to `apps-microservices/crawler-service/CLAUDE.md`:

```markdown
## api-detection-langue-fr Caller Contract

`DetectionLangueClient` (`crawler/src/class/DetectionLangueClient.ts`) enforces the shared caller contract for api-detection-langue-fr. Behavior controlled via env vars:

| Variable | Default | Effect |
|---|---|---|
| `DETECTION_MAX_CONCURRENCY` | `5` | `p-limit` cap on concurrent `/detect` + `/check-url` calls |
| `DETECTION_REQUEST_TIMEOUT_S` | `180` | Axios timeout (milliseconds × 1000) |
| `DETECTION_MAX_RETRIES` | `2` | Retries on HTTP 503 only (non-503 errors raise immediately) |
| `DETECTION_BACKOFF_BASE_S` | `2` | Exponential backoff base when server omits `Retry-After` |

On HTTP 503, precedence for the retry wait time is **server `Retry-After` header > exponential backoff (`backoffBase * 2**attempt`)**. Matches the Python `common_utils.detection_client.DetectionClient` behavior so both callers hit the detection service with identical semantics.

Spec: `docs/superpowers/specs/2026-04-20-detection-langue-fr-concurrency-defense-design.md`.
```

- [ ] **Step 3: Commit**

```bash
cd c:/Users/randr/Documents/Workspaces/RAG-HP-PUB
git add apps-microservices/api-gateway/CLAUDE.md \
        apps-microservices/crawler-service/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(api-gateway,crawler-service): document detection caller contract

- api-gateway: document Configuration.DOWNSTREAM_TIMEOUTS_S map with
  detection=180s and the zero-blast-radius opt-in policy for other
  services
- crawler-service: document the DetectionLangueClient env-var contract
  (DETECTION_MAX_CONCURRENCY, DETECTION_REQUEST_TIMEOUT_S,
  DETECTION_MAX_RETRIES, DETECTION_BACKOFF_BASE_S) and the 503-only
  retry policy with Retry-After precedence

---

docs(api-gateway,crawler-service): documente le contrat appelant detection

- api-gateway : documente la map Configuration.DOWNSTREAM_TIMEOUTS_S
  avec detection=180s et la politique opt-in zero-blast-radius pour
  les autres services
- crawler-service : documente le contrat env-var de DetectionLangueClient
  (DETECTION_MAX_CONCURRENCY, DETECTION_REQUEST_TIMEOUT_S,
  DETECTION_MAX_RETRIES, DETECTION_BACKOFF_BASE_S) et la politique de
  retry 503-uniquement avec priorite a Retry-After
EOF
)"
```

---

## Post-implementation validation

After all 13 tasks are merged, perform manual load verification:

1. **Smoke test:** Start the stack with `docker compose --profile app up api-detection-langue-fr-service`. Hit `/api/v1/health`, `/metrics`, `/api/v1/check-url?url=https://www.example.fr`. Confirm 200 responses and that `/metrics` returns Prometheus format.

2. **Saturation test:** With `ADMISSION_MAX_SLOTS=2` set in the environment, run the following in two terminals simultaneously:

   ```bash
   curl -X POST http://localhost:8999/api/v1/detect \
     -H "content-type: application/json" \
     -d '{"url": "https://www.example.com", "mode": "simple"}' &
   curl -X POST http://localhost:8999/api/v1/detect \
     -H "content-type: application/json" \
     -d '{"url": "https://www.example.org", "mode": "simple"}' &
   curl -v -X POST http://localhost:8999/api/v1/detect \
     -H "content-type: application/json" \
     -d '{"url": "https://www.example.net", "mode": "simple"}'
   ```
   Expected: the third curl returns `HTTP/1.1 503 Service Unavailable` with `Retry-After: 30`. Confirm `curl http://localhost:8999/metrics | grep detect_admission_rejected_total` shows the counter incremented.

3. **Health under pressure:** While sending the saturation load, `curl http://localhost:8999/api/v1/health` must respond < 1s and return `{"status":"healthy"}`. Proves the event loop isn't starved.

4. **Dedup visibility:** Hit `/api/v1/detect` with the same URL concurrently 5 times. `curl /metrics | grep detect_dedup_hits_total` should show ≥4 hits.

5. **Caller retry behavior:** With `ADMISSION_MAX_SLOTS=1`, run the crawler's detection call path (integration test or trigger a crawl). Crawler logs should show `DetectionLangueClient got 503 ... waiting Xs before retry`.

None of these are part of the task list (they require a running stack and are manual gates between the phases documented in the spec's rollout section).
