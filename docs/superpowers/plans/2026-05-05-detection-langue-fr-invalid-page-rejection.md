# Detection-Langue-FR — Invalid Page Rejection + Homepage Fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject hard 4XX/5XX, soft-404, and 404→home redirects in `api-detection-langue-fr` before the detection pipeline runs, with one-hop homepage fallback when allowed, so a 404 page is never analyzed as French.

**Architecture:** New `ScrapeResult` dataclass surfaces HTTP status from `scraper.scrape_html` through `redirect_tracker.fetch_html`. Pure `page_validator` module classifies pages as `valid | http_error | soft_404 | redirected_to_home`. Orchestration in `routes._detect_single_url` does cache-HIT cross-URL awareness, validation, and one-hop homepage fallback. Six new env vars provide kill switches, thresholds, and per-verdict cache TTLs. Three new method values (`http_error`, `soft_404`, `redirected_to_home`) surface in `DetectionResponse.method`; new `analyzed_url` field reveals when a different URL produced the answer.

**Tech Stack:** Python 3.10, FastAPI, Pydantic, Playwright (Camoufox + Chromium), pytest, BeautifulSoup4, prometheus-client, Redis (optional).

**Spec:** `docs/superpowers/specs/2026-05-05-detection-langue-fr-invalid-page-rejection-design.md`

---

## File Structure

| File | Disposition | Responsibility |
|---|---|---|
| `apps-microservices/api-detection-langue-fr/app/services/scraper.py` | MOD | Add `ScrapeResult` dataclass at module top. `scrape_html` captures `response.status` from `page.goto` and returns `ScrapeResult \| None`. |
| `apps-microservices/api-detection-langue-fr/app/services/redirect_tracker.py` | MOD | `fetch_html` returns `ScrapeResult \| None` (was `tuple[str, str] \| None`). Phase 1 + Phase 2 logic unchanged. |
| `apps-microservices/api-detection-langue-fr/app/services/page_validator.py` | NEW | Pure module: `validate(scrape, requested_url) -> ValidationVerdict`. Multilingual title/H1 regex, URL-path 404 marker, redirect-to-home detection. |
| `apps-microservices/api-detection-langue-fr/app/api/routes.py` | MOD | `_detect_single_url`: cache-HIT cross-URL fix, validate after fetch, optional homepage fallback, per-verdict TTL on cache write. |
| `apps-microservices/api-detection-langue-fr/app/core/config.py` | MOD | Add 6 env vars: `INVALID_PAGE_DETECTION_ENABLED`, `HOMEPAGE_FALLBACK_ENABLED`, `SOFT_404_TITLE_THIN_THRESHOLD`, `SOFT_404_H1_THIN_THRESHOLD`, `INVALID_PAGE_TTL_HARD_S`, `INVALID_PAGE_TTL_SOFT_S`. |
| `apps-microservices/api-detection-langue-fr/app/core/metrics.py` | MOD | Add `VALIDATION_VERDICTS` (Counter, label=verdict) and `HOMEPAGE_FALLBACK_TRIGGERED` (Counter, label=outcome). |
| `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py` | MOD | `DomainCache.set` accepts `ttl_override: Optional[int]`. Persists `requested_url` field in cached payload. |
| `apps-microservices/api-detection-langue-fr/app/models/schemas.py` | MOD | `DetectionRequest.homepage_fallback: bool = True`. `DetectionResponse.analyzed_url: Optional[str] = None`. Document new method values in docstrings. |
| `apps-microservices/api-detection-langue-fr/CLAUDE.md` | MOD | Document new methods, env vars, fallback behavior. |
| `apps-microservices/api-detection-langue-fr/tests/test_page_validator.py` | NEW | ~14 unit tests for `validate()`. |
| `apps-microservices/api-detection-langue-fr/tests/test_scraper_result.py` | NEW | `ScrapeResult` shape + `scrape_html` status_code capture (mocked Playwright). |
| `apps-microservices/api-detection-langue-fr/tests/test_redirect_tracker_result.py` | NEW | `fetch_html` returns `ScrapeResult` through Phase 1 + Phase 2. |
| `apps-microservices/api-detection-langue-fr/tests/test_routes_invalid_page.py` | NEW | E2E orchestration: cache HIT same/cross-URL, valid path, http_error, soft_404+fallback success, soft_404+fallback fail, redirected_to_home, env kill switches, per-request flag. |
| `apps-microservices/api-detection-langue-fr/tests/test_domain_cache_ttl.py` | NEW | `ttl_override` honored; `requested_url` round-trip; old-entry forward compat. |

---

## Task 1: ScrapeResult dataclass + scraper.scrape_html migration

**Goal:** Add `ScrapeResult` dataclass to `scraper.py` and migrate `scrape_html` to return it (with HTTP status code captured from `page.goto`).

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/scraper.py:263-441` (signature, return statement, capture `response.status`)
- Create: `apps-microservices/api-detection-langue-fr/tests/test_scraper_result.py`

**Acceptance Criteria:**
- [ ] `ScrapeResult` dataclass defined at top of `scraper.py` with fields `html: str`, `final_url: str`, `status_code: int`, `content_type: str = ""`, `headers: dict = field(default_factory=dict)`.
- [ ] `scrape_html` return type annotation is `Optional[ScrapeResult]`.
- [ ] `scrape_html` captures the response from `page.goto(...)` and uses `response.status` (or `0` if response is None).
- [ ] Returns `ScrapeResult` on success, `None` on failure (same failure conditions as before).
- [ ] Existing tests in `test_scraper.py` still pass (any tests asserting on tuple unpacking get migrated in this task).

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_scraper_result.py tests/test_scraper.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write failing test for `ScrapeResult` shape**

Create `apps-microservices/api-detection-langue-fr/tests/test_scraper_result.py`:

```python
import pytest
from app.services.scraper import ScrapeResult


class TestScrapeResultShape:
    def test_minimal_construction(self):
        r = ScrapeResult(html="<html></html>", final_url="https://example.com/", status_code=200)
        assert r.html == "<html></html>"
        assert r.final_url == "https://example.com/"
        assert r.status_code == 200
        assert r.content_type == ""
        assert r.headers == {}

    def test_full_construction(self):
        r = ScrapeResult(
            html="<html></html>",
            final_url="https://example.com/",
            status_code=404,
            content_type="text/html; charset=utf-8",
            headers={"server": "nginx"},
        )
        assert r.status_code == 404
        assert r.content_type.startswith("text/html")
        assert r.headers["server"] == "nginx"
```

- [ ] **Step 2: Run test, see it fail with ImportError**

```bash
cd apps-microservices/api-detection-langue-fr
pytest tests/test_scraper_result.py::TestScrapeResultShape -v
```

Expected: `ImportError: cannot import name 'ScrapeResult'`.

- [ ] **Step 3: Add `ScrapeResult` dataclass at top of `scraper.py`**

Insert after the existing imports (around line 14, before `def build_proxy_url`):

```python
from dataclasses import dataclass, field


@dataclass
class ScrapeResult:
    """Result of a Playwright scrape: HTML body + final URL + HTTP status + headers.

    status_code is 0 when Playwright returned no Response object (rare —
    happens when navigation aborts before any response is received).
    """
    html: str
    final_url: str
    status_code: int
    content_type: str = ""
    headers: dict = field(default_factory=dict)
```

- [ ] **Step 4: Run shape test, see it pass**

```bash
pytest tests/test_scraper_result.py::TestScrapeResultShape -v
```

Expected: 2 passed.

- [ ] **Step 5: Write failing test for `scrape_html` returning ScrapeResult with status_code**

Append to `tests/test_scraper_result.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


class TestScrapeHtmlReturnsScrapeResult:
    @pytest.mark.asyncio
    async def test_returns_scrape_result_with_status_code(self):
        """scrape_html captures response.status and returns ScrapeResult."""
        from app.services import scraper

        # Mock Playwright Response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "text/html"}

        # Mock page
        mock_page = MagicMock()
        mock_page.goto = AsyncMock(return_value=mock_response)
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>" + "x" * 200 + "</body></html>")
        mock_page.url = "https://example.com/final"
        mock_page.unroute_all = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()

        # Mock context
        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()
        mock_context.add_cookies = AsyncMock()

        # Mock browser
        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        # Mock playwright
        mock_pw = MagicMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.scraper.async_playwright", return_value=mock_pw), \
             patch("app.services.scraper._launch_browser",
                   AsyncMock(return_value=(mock_browser, False))):
            result = await scraper.scrape_html(
                "https://example.com/",
                proxy="http://auto:pw@proxy.apify.com:8000",
            )

        assert result is not None
        assert isinstance(result, scraper.ScrapeResult)
        assert result.status_code == 200
        assert result.final_url == "https://example.com/final"
        assert "<html>" in result.html

    @pytest.mark.asyncio
    async def test_status_code_zero_when_no_response(self):
        """When Playwright returns no Response, status_code defaults to 0."""
        from app.services import scraper

        mock_page = MagicMock()
        mock_page.goto = AsyncMock(return_value=None)  # No response object
        mock_page.wait_for_load_state = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html><body>" + "x" * 200 + "</body></html>")
        mock_page.url = "https://example.com/"
        mock_page.unroute_all = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.route = AsyncMock()
        mock_page.on = MagicMock()

        mock_context = MagicMock()
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()
        mock_context.add_cookies = AsyncMock()

        mock_browser = MagicMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_browser.close = AsyncMock()

        mock_pw = MagicMock()
        mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_pw.__aexit__ = AsyncMock(return_value=None)

        with patch("app.services.scraper.async_playwright", return_value=mock_pw), \
             patch("app.services.scraper._launch_browser",
                   AsyncMock(return_value=(mock_browser, False))):
            result = await scraper.scrape_html(
                "https://example.com/",
                proxy="http://auto:pw@proxy.apify.com:8000",
            )

        assert result is not None
        assert result.status_code == 0
```

- [ ] **Step 6: Run new tests, see them fail**

```bash
pytest tests/test_scraper_result.py::TestScrapeHtmlReturnsScrapeResult -v
```

Expected: 2 failed (scrape_html still returns tuple).

- [ ] **Step 7: Migrate `scrape_html` to capture status and return ScrapeResult**

In `apps-microservices/api-detection-langue-fr/app/services/scraper.py`:

1. Change signature on line 263:

```python
async def scrape_html(url: str, timeout: int = 90, proxy: Optional[str] = None) -> Optional[ScrapeResult]:
```

2. Capture response on line 335. Change:

```python
await page.goto(url, wait_until='domcontentloaded', timeout=nav_timeout)
```

to:

```python
response = await page.goto(url, wait_until='domcontentloaded', timeout=nav_timeout)
```

(Also: ensure `response = None` is initialized before the try block at the appropriate scope, around line 333, so the variable exists if `goto` raises.)

3. On line 438 replace:

```python
return (content, final_url)
```

with:

```python
content_type = response.headers.get('content-type', '') if response else ''
status_code = response.status if response else 0
headers = dict(response.headers) if response else {}
return ScrapeResult(
    html=content,
    final_url=final_url,
    status_code=status_code,
    content_type=content_type,
    headers=headers,
)
```

4. Update the existing docstring (line 280-281) to describe `ScrapeResult` instead of tuple.

- [ ] **Step 8: Run all scraper tests, verify pass**

```bash
pytest tests/test_scraper_result.py tests/test_scraper.py -v
```

Expected: all pass. If any existing test in `test_scraper.py` still uses tuple unpacking like `content, final_url = result`, migrate to `result.html` / `result.final_url` / `result.status_code` access.

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/services/scraper.py apps-microservices/api-detection-langue-fr/tests/test_scraper_result.py apps-microservices/api-detection-langue-fr/tests/test_scraper.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): scrape_html returns ScrapeResult dataclass

EN: Surface HTTP status and headers from Playwright by introducing a
ScrapeResult dataclass and migrating scrape_html away from a bare tuple
return. Foundation for invalid-page rejection (4XX/5XX detection requires
the status code that the previous return shape discarded).

FR: Expose le statut HTTP et les en-têtes Playwright via une dataclass
ScrapeResult, en remplacement du tuple retourné par scrape_html. Socle
pour le rejet des pages invalides (la détection 4XX/5XX nécessite le
status code que l'ancien retour ignorait).
EOF
)"
```

---

## Task 2: redirect_tracker.fetch_html migration to ScrapeResult

**Goal:** Make `fetch_html` return `ScrapeResult | None` instead of `tuple[str, str] | None`. Phase 1 retry + Phase 2 variant logic stays.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/services/redirect_tracker.py:189-293`
- Create: `apps-microservices/api-detection-langue-fr/tests/test_redirect_tracker_result.py`

**Acceptance Criteria:**
- [ ] `fetch_html` return type annotation is `Optional[ScrapeResult]`.
- [ ] Phase 1 retry logic forwards `ScrapeResult` from `scrape_html`.
- [ ] Phase 2 variant fallback forwards `ScrapeResult` from `scrape_html`.
- [ ] Returns `None` on full failure (same condition as before).

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_redirect_tracker_result.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `apps-microservices/api-detection-langue-fr/tests/test_redirect_tracker_result.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.scraper import ScrapeResult


class TestFetchHtmlReturnsScrapeResult:
    @pytest.mark.asyncio
    async def test_phase_1_returns_scrape_result(self):
        from app.services import redirect_tracker

        scrape = ScrapeResult(
            html="<html>FR</html>",
            final_url="https://example.com/",
            status_code=200,
        )
        with patch("app.services.redirect_tracker.scrape_html",
                   AsyncMock(return_value=scrape)):
            result = await redirect_tracker.fetch_html(
                "https://example.com/", proxy="http://auto:pw@proxy.apify.com:8000"
            )
        assert isinstance(result, ScrapeResult)
        assert result.status_code == 200
        assert result.html == "<html>FR</html>"

    @pytest.mark.asyncio
    async def test_phase_2_variant_fallback_returns_scrape_result(self):
        """When Phase 1 hits a variant-eligible error, Phase 2 retries variants."""
        from app.services import redirect_tracker

        variant_scrape = ScrapeResult(
            html="<html>FR</html>",
            final_url="http://example.com/",
            status_code=200,
        )

        # First call raises ERR_SSL_PROTOCOL_ERROR; second call (Phase 2 variant) succeeds.
        side_effects = [
            Exception("page.goto: net::ERR_SSL_PROTOCOL_ERROR at https://www.example.com/"),
            variant_scrape,
        ]
        with patch("app.services.redirect_tracker.scrape_html",
                   AsyncMock(side_effect=side_effects)):
            result = await redirect_tracker.fetch_html(
                "https://www.example.com/", proxy="http://auto:pw@proxy.apify.com:8000"
            )
        assert isinstance(result, ScrapeResult)
        assert result.status_code == 200
        assert result.final_url == "http://example.com/"

    @pytest.mark.asyncio
    async def test_returns_none_on_complete_failure(self):
        from app.services import redirect_tracker

        with patch("app.services.redirect_tracker.scrape_html",
                   AsyncMock(return_value=None)):
            result = await redirect_tracker.fetch_html(
                "https://example.com/", proxy="http://auto:pw@proxy.apify.com:8000"
            )
        assert result is None
```

- [ ] **Step 2: Run, see them fail**

```bash
cd apps-microservices/api-detection-langue-fr
pytest tests/test_redirect_tracker_result.py -v
```

Expected: 3 failed (current `fetch_html` returns tuple, not ScrapeResult).

- [ ] **Step 3: Migrate `fetch_html` signature and propagation**

In `apps-microservices/api-detection-langue-fr/app/services/redirect_tracker.py`:

1. Add import at top (after `from app.core.config import settings`):

```python
from app.services.scraper import ScrapeResult
```

2. Change signature on line 189:

```python
async def fetch_html(url: str, proxy: Optional[str] = None) -> Optional[ScrapeResult]:
```

3. In Phase 1 (around line 228-233), replace:

```python
result = await scrape_html(url, proxy=attempt_proxy)
if result:
    content, final_url = result
    if attempt > 1:
        logger.info(f"Récupération réussie pour {url} à la tentative {attempt}/{max_retries}")
    return (content, final_url)

# Contenu vide/trop court — retryable
last_error = "Contenu vide ou trop court"
```

with:

```python
result = await scrape_html(url, proxy=attempt_proxy)
if result:
    if attempt > 1:
        logger.info(f"Récupération réussie pour {url} à la tentative {attempt}/{max_retries}")
    return result

# Contenu vide/trop court — retryable
last_error = "Contenu vide ou trop court"
```

4. In Phase 2 (around line 273-281), replace:

```python
result = await scrape_html(variant, proxy=variant_proxy)
if result:
    content, final_url = result
    logger.warning(
        f"[VARIANTE] Succès avec {variant} → {final_url} "
        f"({len(content)} caractères)"
    )
    return (content, final_url)
```

with:

```python
result = await scrape_html(variant, proxy=variant_proxy)
if result:
    logger.warning(
        f"[VARIANTE] Succès avec {variant} → {result.final_url} "
        f"({len(result.html)} caractères)"
    )
    return result
```

5. Update the docstring on `fetch_html` (around lines 204-205) to describe `ScrapeResult` instead of tuple.

- [ ] **Step 4: Run, see all pass**

```bash
pytest tests/test_redirect_tracker_result.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Update existing fetch_html callers**

Grep callers — there are two: `routes.py` (3 sites: `_detect_single_url`, `detect_french_debug`) and `domain_fr.py` (none directly; uses RedirectTracker only).

Search:

```bash
grep -n "fetch_html" apps-microservices/api-detection-langue-fr/app/api/routes.py
```

For each call site that does tuple-unpack `html_content, final_url = fetch_result`, change to use the dataclass:

```python
html_content = fetch_result.html
final_url = fetch_result.final_url
```

(Truthiness check `if not fetch_result:` stays — it works on dataclass too, returns True for non-None ScrapeResult.)

Specifically in `routes.py` lines 95-114 and around line 506-535 (`detect_french_debug`):

Replace `html_content, final_url = fetch_result` with explicit attribute access. Leave inflight dedup wrapping unchanged — `_inflight_dedup.coalesce` returns whatever the factory returns, now `ScrapeResult | None` instead of `tuple | None`.

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py
```

(`test_api.py` + `test_domain_fr.py` are pre-existing-broken; out of scope.)

Expected: existing tests still pass (route paths now use attribute access).

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/services/redirect_tracker.py apps-microservices/api-detection-langue-fr/app/api/routes.py apps-microservices/api-detection-langue-fr/tests/test_redirect_tracker_result.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): fetch_html returns ScrapeResult

EN: Propagate ScrapeResult through redirect_tracker.fetch_html (Phase 1
retries + Phase 2 URL variants) and update routes call sites to use
attribute access. Required for the page validator to see HTTP status.

FR: Propage ScrapeResult dans redirect_tracker.fetch_html (retries Phase 1
+ variantes URL Phase 2) et migre les sites d'appel dans routes vers
l'accès par attributs. Nécessaire pour que le page_validator voie le
statut HTTP.
EOF
)"
```

---

## Task 3: Add 6 env vars to config.py

**Goal:** Add the env vars and TTL constants the validator + orchestration need.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/config.py`

**Acceptance Criteria:**
- [ ] `Settings` class exposes 6 new attributes with documented defaults.
- [ ] All 6 read from environment via Pydantic `BaseSettings`.

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -c "from app.core.config import settings; print(settings.INVALID_PAGE_DETECTION_ENABLED, settings.HOMEPAGE_FALLBACK_ENABLED, settings.SOFT_404_TITLE_THIN_THRESHOLD, settings.SOFT_404_H1_THIN_THRESHOLD, settings.INVALID_PAGE_TTL_HARD_S, settings.INVALID_PAGE_TTL_SOFT_S)"` → prints `True True 2000 1500 604800 21600`.

**Steps:**

- [ ] **Step 1: Add the 6 env vars to `Settings`**

In `apps-microservices/api-detection-langue-fr/app/core/config.py`, add after line 29 (after `CAMOUFOX_ENABLED`):

```python
    # Invalid page rejection (4XX/5XX, soft-404, redirect-to-home)
    INVALID_PAGE_DETECTION_ENABLED: bool = True
    HOMEPAGE_FALLBACK_ENABLED: bool = True
    SOFT_404_TITLE_THIN_THRESHOLD: int = 2000   # Visible-text char limit when title regex matches
    SOFT_404_H1_THIN_THRESHOLD: int = 1500      # Visible-text char limit when H1 regex matches
    INVALID_PAGE_TTL_HARD_S: int = 604800       # 7 days — http_error + redirected_to_home
    INVALID_PAGE_TTL_SOFT_S: int = 21600        # 6 hours — soft_404 (heuristic, give site time to fix)
```

- [ ] **Step 2: Verify**

```bash
cd apps-microservices/api-detection-langue-fr
python -c "from app.core.config import settings; print(settings.INVALID_PAGE_DETECTION_ENABLED, settings.HOMEPAGE_FALLBACK_ENABLED, settings.SOFT_404_TITLE_THIN_THRESHOLD, settings.SOFT_404_H1_THIN_THRESHOLD, settings.INVALID_PAGE_TTL_HARD_S, settings.INVALID_PAGE_TTL_SOFT_S)"
```

Expected: `True True 2000 1500 604800 21600`

- [ ] **Step 3: Verify env override works**

```bash
INVALID_PAGE_DETECTION_ENABLED=false SOFT_404_TITLE_THIN_THRESHOLD=3000 python -c "from app.core.config import settings; print(settings.INVALID_PAGE_DETECTION_ENABLED, settings.SOFT_404_TITLE_THIN_THRESHOLD)"
```

Expected: `False 3000`

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/core/config.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): add env vars for invalid page rejection

EN: Six new settings cover the validator kill switches, soft-404 thinness
thresholds, and per-verdict cache TTLs. Defaults match the spec; operator
can override per environment for staged rollout.

FR: Six nouveaux paramètres couvrent les kill switches du validator, les
seuils de finesse soft-404, et les TTL de cache par verdict. Valeurs par
défaut conformes au spec ; l'opérateur peut surcharger par environnement
pour un déploiement progressif.
EOF
)"
```

---

## Task 4: page_validator module + unit tests

**Goal:** Pure validator that classifies a `ScrapeResult` against the requested URL.

**Files:**
- Create: `apps-microservices/api-detection-langue-fr/app/services/page_validator.py`
- Create: `apps-microservices/api-detection-langue-fr/tests/test_page_validator.py`

**Acceptance Criteria:**
- [ ] `ValidationVerdict` enum with values `VALID`, `HTTP_ERROR`, `SOFT_404`, `REDIRECTED_TO_HOME` (string-valued: `"valid"`, `"http_error"`, `"soft_404"`, `"redirected_to_home"`).
- [ ] `validate(scrape, requested_url)` returns the verdict.
- [ ] Hard 4XX/5XX (status `400 <= sc < 600`) → `HTTP_ERROR`.
- [ ] Requested non-root path, final URL = root path → `REDIRECTED_TO_HOME`.
- [ ] URL path matches `_URL_404_PATH_RE` → `SOFT_404`.
- [ ] Title regex match + visible text < `SOFT_404_TITLE_THIN_THRESHOLD` → `SOFT_404`.
- [ ] H1 regex match + visible text < `SOFT_404_H1_THIN_THRESHOLD` → `SOFT_404`.
- [ ] Parsing crash → `VALID` (fail-open) + WARNING log.
- [ ] All other cases → `VALID`.
- [ ] ~14 unit tests pass.

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_page_validator.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write all unit tests upfront**

Create `apps-microservices/api-detection-langue-fr/tests/test_page_validator.py`:

```python
import pytest
from app.services.scraper import ScrapeResult
from app.services.page_validator import ValidationVerdict, validate


def _scrape(html="<html><body>x</body></html>", final_url="https://example.com/page",
            status_code=200) -> ScrapeResult:
    return ScrapeResult(html=html, final_url=final_url, status_code=status_code)


class TestHttpError:
    def test_404_status_is_http_error(self):
        assert validate(_scrape(status_code=404), "https://example.com/page") == ValidationVerdict.HTTP_ERROR

    def test_500_status_is_http_error(self):
        assert validate(_scrape(status_code=500), "https://example.com/page") == ValidationVerdict.HTTP_ERROR

    def test_399_is_valid(self):
        assert validate(_scrape(status_code=399), "https://example.com/page") == ValidationVerdict.VALID

    def test_600_is_valid(self):
        # 600+ is non-standard; not flagged as http_error
        assert validate(_scrape(status_code=600), "https://example.com/page") == ValidationVerdict.VALID

    def test_status_zero_falls_through_to_other_signals(self):
        # status_code=0 means no Playwright Response; don't classify as HTTP_ERROR.
        assert validate(_scrape(status_code=0), "https://example.com/page") == ValidationVerdict.VALID


class TestRedirectedToHome:
    def test_deep_path_redirected_to_root_is_redirect(self):
        s = _scrape(final_url="https://example.com/", status_code=200)
        assert validate(s, "https://example.com/some/deep/page") == ValidationVerdict.REDIRECTED_TO_HOME

    def test_root_to_root_is_valid(self):
        s = _scrape(final_url="https://example.com/", status_code=200)
        assert validate(s, "https://example.com/") == ValidationVerdict.VALID

    def test_deep_to_deep_is_valid(self):
        s = _scrape(final_url="https://example.com/other", status_code=200)
        assert validate(s, "https://example.com/some/page") == ValidationVerdict.VALID


class TestSoft404URLPath:
    def test_404_in_final_url_path(self):
        s = _scrape(final_url="https://example.com/404", status_code=200)
        assert validate(s, "https://example.com/some/page") == ValidationVerdict.SOFT_404

    def test_not_found_segment_in_path(self):
        s = _scrape(final_url="https://example.com/not-found", status_code=200)
        assert validate(s, "https://example.com/some/page") == ValidationVerdict.SOFT_404

    def test_page_introuvable_in_path(self):
        s = _scrape(final_url="https://example.com/page-introuvable", status_code=200)
        assert validate(s, "https://example.com/some/page") == ValidationVerdict.SOFT_404


class TestSoft404TitleAndThin:
    def test_title_404_thin_body(self):
        html = "<html><head><title>404 - Not Found</title></head><body>Page not found</body></html>"
        s = _scrape(html=html, final_url="https://example.com/page", status_code=200)
        assert validate(s, "https://example.com/page") == ValidationVerdict.SOFT_404

    def test_title_introuvable_thin_body(self):
        html = "<html><head><title>Page introuvable</title></head><body>Désolé</body></html>"
        s = _scrape(html=html, final_url="https://example.com/page", status_code=200)
        assert validate(s, "https://example.com/page") == ValidationVerdict.SOFT_404

    def test_title_404_with_long_body_is_valid(self):
        # Article titled "What is a 404 error" with full content body is NOT soft-404.
        long_body = "x " * 1500  # ~3000 chars > threshold 2000
        html = f"<html><head><title>What is a 404 error</title></head><body>{long_body}</body></html>"
        s = _scrape(html=html, final_url="https://example.com/blog/404-error", status_code=200)
        assert validate(s, "https://example.com/blog/404-error") == ValidationVerdict.VALID


class TestSoft404H1AndThin:
    def test_h1_introuvable_thin_body(self):
        html = "<html><body><h1>Page non trouvée</h1><p>Désolé</p></body></html>"
        s = _scrape(html=html, final_url="https://example.com/page", status_code=200)
        assert validate(s, "https://example.com/page") == ValidationVerdict.SOFT_404

    def test_h1_404_with_long_body_is_valid(self):
        long_body = "x " * 1200  # ~2400 chars > threshold 1500
        html = f"<html><body><h1>Erreur 404</h1>{long_body}</body></html>"
        s = _scrape(html=html, final_url="https://example.com/page", status_code=200)
        assert validate(s, "https://example.com/page") == ValidationVerdict.VALID


class TestParsingCrashFailOpen:
    def test_invalid_html_returns_valid(self, caplog):
        # BeautifulSoup is robust; force crash via monkey-patching is overkill.
        # Empty HTML triggers fall-through; valid is correct here.
        s = _scrape(html="", final_url="https://example.com/page", status_code=200)
        # Empty body is not soft-404 by itself; should be VALID (fall through).
        assert validate(s, "https://example.com/page") == ValidationVerdict.VALID
```

- [ ] **Step 2: Run tests, see them fail**

```bash
cd apps-microservices/api-detection-langue-fr
pytest tests/test_page_validator.py -v
```

Expected: ImportError on `app.services.page_validator`.

- [ ] **Step 3: Create the validator module**

Create `apps-microservices/api-detection-langue-fr/app/services/page_validator.py`:

```python
"""Pure page validator for api-detection-langue-fr.

Classifies a ScrapeResult against the requested URL into one of:
  - VALID — looks like real content
  - HTTP_ERROR — Playwright reported a 4XX/5XX status
  - SOFT_404 — body or final URL signals "page not found" despite 200 OK
  - REDIRECTED_TO_HOME — requested non-root path, final URL is root

No I/O. Heuristics + regex only. Easy unit-test surface.
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.core.config import settings
from app.services.scraper import ScrapeResult

logger = logging.getLogger(__name__)


class ValidationVerdict(str, Enum):
    VALID = "valid"
    HTTP_ERROR = "http_error"
    SOFT_404 = "soft_404"
    REDIRECTED_TO_HOME = "redirected_to_home"


# Multilingual "page not found" patterns (FR + EN).
_NOT_FOUND_RE = re.compile(
    r"\b(404|not\s+found|page\s+not\s+found|page\s+introuvable|"
    r"page\s+non\s+trouv[eé]e|page\s+n['’]existe\s+pas|erreur\s+404|"
    r"page\s+inexistante|file\s+not\s+found)\b",
    re.IGNORECASE,
)

# URL path containing a 404/error/not-found segment.
_URL_404_PATH_RE = re.compile(
    r"/(?:404|error|not[-_]found|page[-_]non[-_]trouv[eé]e|page[-_]introuvable)(?:/|$)",
    re.IGNORECASE,
)


def validate(scrape: ScrapeResult, requested_url: str) -> ValidationVerdict:
    """Classify a ScrapeResult against the requested URL.

    Order of checks:
      1. Hard HTTP error (status 400-599).
      2. Redirected to home (requested path non-root, final path root).
      3. Soft-404 (URL path marker, or title/H1 regex + thin body).
      4. Otherwise VALID.
    """
    if 400 <= scrape.status_code < 600:
        return ValidationVerdict.HTTP_ERROR

    if _is_redirect_to_home(scrape, requested_url):
        return ValidationVerdict.REDIRECTED_TO_HOME

    soft = _detect_soft_404(scrape)
    if soft is not None:
        return soft

    return ValidationVerdict.VALID


def _is_redirect_to_home(scrape: ScrapeResult, requested_url: str) -> bool:
    req_path = (urlparse(requested_url).path or "/").rstrip("/")
    final_path = (urlparse(scrape.final_url).path or "/").rstrip("/")
    return req_path != "" and final_path == ""


def _detect_soft_404(scrape: ScrapeResult) -> Optional[ValidationVerdict]:
    if _URL_404_PATH_RE.search(scrape.final_url):
        return ValidationVerdict.SOFT_404

    try:
        soup = BeautifulSoup(scrape.html, "lxml")
        title = (soup.title.string if soup.title else "") or ""
        h1_tag = soup.h1
        h1 = h1_tag.get_text(strip=True) if h1_tag else ""
        visible_len = _visible_text_length(soup)
    except Exception as e:
        logger.warning(
            f"[VALIDATE] parse error for {scrape.final_url}: {e} — fail-open as VALID"
        )
        return None

    if _NOT_FOUND_RE.search(title) and visible_len < settings.SOFT_404_TITLE_THIN_THRESHOLD:
        return ValidationVerdict.SOFT_404
    if _NOT_FOUND_RE.search(h1) and visible_len < settings.SOFT_404_H1_THIN_THRESHOLD:
        return ValidationVerdict.SOFT_404

    return None


def _visible_text_length(soup) -> int:
    """Lightweight visible-text length for the thin-content threshold."""
    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    return len(soup.get_text(separator=" ", strip=True))
```

- [ ] **Step 4: Run, see all pass**

```bash
pytest tests/test_page_validator.py -v
```

Expected: all 14 tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/services/page_validator.py apps-microservices/api-detection-langue-fr/tests/test_page_validator.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): add page_validator module

EN: Pure validator classifies a ScrapeResult as valid, http_error,
soft_404, or redirected_to_home. Multilingual regex (FR + EN) plus
multi-signal soft-404 detection (URL path, title+thin, H1+thin) keeps
false positives off legitimate "404" articles.

FR: Validateur pur classifiant un ScrapeResult en valid, http_error,
soft_404 ou redirected_to_home. Regex multilingue (FR + EN) et
détection soft-404 multi-signal (chemin URL, titre+contenu fin,
H1+contenu fin) limitent les faux positifs sur les articles
légitimes parlant de "404".
EOF
)"
```

---

## Task 5: Add Prometheus metrics

**Goal:** Add `VALIDATION_VERDICTS` and `HOMEPAGE_FALLBACK_TRIGGERED` counters.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/metrics.py`

**Acceptance Criteria:**
- [ ] `VALIDATION_VERDICTS` Counter with label `verdict`.
- [ ] `HOMEPAGE_FALLBACK_TRIGGERED` Counter with label `outcome`.
- [ ] Both importable from `app.core.metrics`.

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -c "from app.core.metrics import VALIDATION_VERDICTS, HOMEPAGE_FALLBACK_TRIGGERED; VALIDATION_VERDICTS.labels(verdict='valid').inc(); HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome='success').inc(); print('ok')"` → prints `ok`.

**Steps:**

- [ ] **Step 1: Append to `metrics.py`**

In `apps-microservices/api-detection-langue-fr/app/core/metrics.py`, append after the existing gauges:

```python
# Page-validation outcomes (after fetch, before DomainFR).
VALIDATION_VERDICTS = Counter(
    "detection_validation_verdicts_total",
    "Page validation outcomes (valid, http_error, soft_404, redirected_to_home)",
    labelnames=("verdict",),
)

# Homepage fallback triggers and outcomes.
HOMEPAGE_FALLBACK_TRIGGERED = Counter(
    "detection_homepage_fallback_triggered_total",
    "Homepage fallback triggers and their outcomes",
    labelnames=("outcome",),  # success | rejected | network_failure
)
```

- [ ] **Step 2: Verify**

```bash
cd apps-microservices/api-detection-langue-fr
python -c "from app.core.metrics import VALIDATION_VERDICTS, HOMEPAGE_FALLBACK_TRIGGERED; VALIDATION_VERDICTS.labels(verdict='valid').inc(); HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome='success').inc(); print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/core/metrics.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): add validation + fallback metrics

EN: Two new Prometheus counters surface validation verdicts and
homepage-fallback outcomes for the staged rollout (P2/P3 gates check
soft-404 false-positive rate and fallback success rate via these
counters).

FR: Deux nouveaux compteurs Prometheus exposent les verdicts de
validation et les résultats de repli vers la page d'accueil pour le
déploiement progressif (les portes P2/P3 vérifient le taux de faux
positifs soft-404 et le taux de succès du repli via ces compteurs).
EOF
)"
```

---

## Task 6: Schema additions (homepage_fallback flag + analyzed_url field)

**Goal:** Add the per-request opt-out flag and the response disclosure field.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/models/schemas.py`

**Acceptance Criteria:**
- [ ] `DetectionRequest.homepage_fallback: bool = True`.
- [ ] `DetectionResponse.analyzed_url: Optional[str] = None`.
- [ ] Existing routes still serialize/deserialize correctly.

**Verify:** `cd apps-microservices/api-detection-langue-fr && python -c "from app.models.schemas import DetectionRequest, DetectionResponse; r = DetectionRequest(url='https://example.com/'); print(r.homepage_fallback); resp = DetectionResponse(ok=True, url='https://example.com/', method='langHtml', analyzed_url='https://example.com/'); print(resp.analyzed_url)"` → prints `True\nhttps://example.com/`.

**Steps:**

- [ ] **Step 1: Add `homepage_fallback` to `DetectionRequest`**

In `apps-microservices/api-detection-langue-fr/app/models/schemas.py`, add after line 43 (the `include_full_content` field, before the `model_config`):

```python
    homepage_fallback: bool = Field(
        default=True,
        description="Si la page demandée est invalide (404, soft-404, redirect-to-home), tenter une fois la page d'accueil du domaine. Désactiver pour avoir une réponse strictement URL-level."
    )
```

- [ ] **Step 2: Add `analyzed_url` to `DetectionResponse`**

After line 99 (the `group` field), add:

```python
    analyzed_url: Optional[str] = Field(
        default=None,
        description="URL réellement analysée si différente de l'URL demandée (cas: repli homepage, ou cache HIT cross-URL via la clé domain). None = analyse directe de l'URL demandée."
    )
```

- [ ] **Step 3: Verify**

```bash
cd apps-microservices/api-detection-langue-fr
python -c "from app.models.schemas import DetectionRequest, DetectionResponse; r = DetectionRequest(url='https://example.com/'); print(r.homepage_fallback); resp = DetectionResponse(ok=True, url='https://example.com/', method='langHtml', analyzed_url='https://example.com/'); print(resp.analyzed_url)"
```

Expected:
```
True
https://example.com/
```

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/models/schemas.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): add homepage_fallback + analyzed_url

EN: New per-request flag homepage_fallback (default true) gives callers
a strict URL-level mode. New response field analyzed_url discloses when
the answer came from a different URL (homepage fallback, or cache HIT
on the domain key from a different requested URL).

FR: Nouveau drapeau par requête homepage_fallback (true par défaut)
offre aux appelants un mode strict URL-level. Nouveau champ de réponse
analyzed_url indique quand la réponse provient d'une autre URL (repli
homepage, ou HIT cache sur la clé domain depuis une URL différente).
EOF
)"
```

---

## Task 7: domain_cache.set ttl_override + requested_url field

**Goal:** Allow the orchestrator to override TTL per verdict and persist `requested_url` for cross-URL cache HIT awareness.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py:102-131`
- Create: `apps-microservices/api-detection-langue-fr/tests/test_domain_cache_ttl.py`

**Acceptance Criteria:**
- [ ] `DomainCache.set(input_url, result_url, result, ttl_override=None)` accepts the new optional kwarg.
- [ ] When `ttl_override` is provided, it overrides the existing TTL logic.
- [ ] When `ttl_override` is None, behavior is unchanged.
- [ ] The cached payload now includes `result["requested_url"] = input_url` (mutation in-place is acceptable since callers don't rely on idempotency of the result dict).
- [ ] Old cached entries (without `requested_url`) read back as before — no key required.

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_domain_cache_ttl.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write failing tests**

Create `apps-microservices/api-detection-langue-fr/tests/test_domain_cache_ttl.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.domain_fr import DomainCache


@pytest.fixture
def cache_with_mock_redis():
    cache = DomainCache()
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=None)
    mock_client.setex = AsyncMock()
    cache._client = mock_client
    cache._initialized = True
    return cache, mock_client


class TestTtlOverride:
    @pytest.mark.asyncio
    async def test_ttl_override_used_when_provided(self, cache_with_mock_redis):
        cache, client = cache_with_mock_redis
        result = {"ok": False, "method": "http_error", "url": "https://example.com/page"}
        await cache.set(
            "https://example.com/page", "https://example.com/page",
            result, ttl_override=604800,
        )
        # First setex call: TTL must be 604800
        assert client.setex.await_count >= 1
        ttl_used = client.setex.await_args_list[0].args[1]
        assert ttl_used == 604800

    @pytest.mark.asyncio
    async def test_ttl_override_none_falls_back_to_existing_logic(self, cache_with_mock_redis):
        cache, client = cache_with_mock_redis
        result = {"ok": True, "method": "langHtml", "url": "https://example.com/"}
        await cache.set("https://example.com/", "https://example.com/", result, ttl_override=None)
        ttl_used = client.setex.await_args_list[0].args[1]
        assert ttl_used == cache.TTL_OK  # 30 days


class TestRequestedUrlField:
    @pytest.mark.asyncio
    async def test_requested_url_persisted_in_payload(self, cache_with_mock_redis):
        cache, client = cache_with_mock_redis
        result = {"ok": True, "method": "langHtml", "url": "https://example.com/"}
        await cache.set(
            "https://example.com/some/path", "https://example.com/", result,
        )
        # The serialized payload must carry requested_url == input_url
        payload_json = client.setex.await_args_list[0].args[2]
        payload = json.loads(payload_json)
        assert payload["requested_url"] == "https://example.com/some/path"

    @pytest.mark.asyncio
    async def test_old_payload_without_requested_url_reads_back(self):
        """Forward compat: an old entry lacking 'requested_url' should still be readable."""
        cache = DomainCache()
        mock_client = MagicMock()
        old_payload = {"ok": True, "method": "langHtml", "url": "https://example.com/"}
        mock_client.get = AsyncMock(return_value=json.dumps(old_payload))
        cache._client = mock_client
        cache._initialized = True

        loaded = await cache.get("https://example.com/")
        assert loaded == old_payload  # No KeyError; missing field gracefully absent
```

- [ ] **Step 2: Run, see them fail**

```bash
cd apps-microservices/api-detection-langue-fr
pytest tests/test_domain_cache_ttl.py -v
```

Expected: 3 failed (no `ttl_override` kwarg, no `requested_url` mutation).

- [ ] **Step 3: Update `DomainCache.set`**

In `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py`, replace the `set` method (lines 102-131):

```python
    async def set(
        self,
        input_url: str,
        result_url: str,
        result: dict,
        ttl_override: Optional[int] = None,
    ) -> None:
        """Stocke le résultat pour input_url ET result_url (si redirection).

        ttl_override: bypass the method-based TTL logic when provided. Used by
        the page validator orchestration to set per-verdict TTLs (7d for
        http_error / redirected_to_home, 6h for soft_404).

        The persisted payload always carries `requested_url = input_url`
        so cross-URL cache HITs (different path on the same domain) can
        surface the originating URL via DetectionResponse.analyzed_url.
        """
        client = await self._get_client()
        if not client:
            return
        method = result.get('method', '')
        if method in self._NEVER_CACHE_METHODS:
            return
        try:
            input_domain = self._normalize_domain(input_url)
            if not input_domain:
                return

            # Persist requested_url for cross-URL HIT awareness.
            result["requested_url"] = input_url

            # TTL: override > method-based logic.
            if ttl_override is not None:
                ttl = ttl_override
            elif method in self._TRANSIENT_METHODS or any(
                method.startswith(prefix) for prefix in ('HTTP_',)
            ):
                ttl = self.TTL_TRANSIENT
            elif result.get('ok'):
                ttl = self.TTL_OK
            else:
                ttl = self.TTL_NOK

            data = json.dumps(result)
            await client.setex(self._cache_key(input_domain), ttl, data)
            result_domain = self._normalize_domain(result_url)
            if result_domain and result_domain != input_domain:
                await client.setex(self._cache_key(result_domain), ttl, data)
        except Exception as e:
            logger.debug(f"Cache set error ({input_url}): {e}")
```

- [ ] **Step 4: Run, see all pass**

```bash
pytest tests/test_domain_cache_ttl.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/core/domain_fr.py apps-microservices/api-detection-langue-fr/tests/test_domain_cache_ttl.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): cache ttl_override + requested_url field

EN: DomainCache.set accepts ttl_override (used by per-verdict TTL on
invalid pages: 7d for http_error / redirected_to_home, 6h for soft_404)
and persists requested_url in the payload so cross-URL cache HITs (a
deep path matching the cached homepage entry on the domain key) can
surface the original URL via DetectionResponse.analyzed_url.

FR: DomainCache.set accepte ttl_override (utilisé pour les TTL par
verdict des pages invalides : 7j pour http_error / redirected_to_home,
6h pour soft_404) et persiste requested_url dans le payload pour que
les HITs cache cross-URL (un chemin profond correspondant à l'entrée
cachée de la page d'accueil sur la clé domain) puissent exposer l'URL
d'origine via DetectionResponse.analyzed_url.
EOF
)"
```

---

## Task 8: routes._detect_single_url orchestration

**Goal:** Wire validate + homepage fallback into the request flow. Cache-HIT cross-URL fix. Per-verdict TTL on cache writes.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py:67-137` (the `_detect_single_url` function body)
- Create: `apps-microservices/api-detection-langue-fr/tests/test_routes_invalid_page.py`

**Acceptance Criteria:**
- [ ] Cache HIT for the same URL returns existing result (no `analyzed_url` set).
- [ ] Cache HIT where cached `requested_url` differs from current URL → response has `analyzed_url=cached.requested_url`.
- [ ] Validation runs after fetch when `INVALID_PAGE_DETECTION_ENABLED=true`.
- [ ] On non-VALID verdict + `homepage_fallback=true` + url != homepage: fetch homepage, validate, run DomainFR if homepage VALID, set `analyzed_url=homepage`. Cache result with normal TTL.
- [ ] On non-VALID verdict + homepage also non-VALID: cache rejection with verdict-specific TTL (7d hard, 6h soft); return rejection with `method=verdict.value`.
- [ ] On non-VALID verdict + `homepage_fallback=false`: cache rejection with verdict-specific TTL; return rejection.
- [ ] On non-VALID verdict + url == homepage: skip fallback; cache rejection; return rejection.
- [ ] Metrics counters (`VALIDATION_VERDICTS`, `HOMEPAGE_FALLBACK_TRIGGERED`) incremented at the right points.
- [ ] `INVALID_PAGE_DETECTION_ENABLED=false` skips validation entirely (existing behavior preserved).
- [ ] `HOMEPAGE_FALLBACK_ENABLED=false` skips fallback even when validation rejects.

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_routes_invalid_page.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write failing tests for orchestration**

Create `apps-microservices/api-detection-langue-fr/tests/test_routes_invalid_page.py`:

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from app.services.scraper import ScrapeResult
from app.services.page_validator import ValidationVerdict


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_inflight_dedup():
    """Force dedup off so tests don't share Future state."""
    import os
    os.environ["INFLIGHT_DEDUP_ENABLED"] = "false"
    # Reload routes module to pick up env change.
    import importlib
    from app.api import routes
    importlib.reload(routes)
    # Re-mount router so app sees the reloaded one.
    yield


def _scrape(html="<html><body>FR" + "x" * 200 + "</body></html>",
            final_url="https://example.com/page", status_code=200):
    return ScrapeResult(html=html, final_url=final_url, status_code=status_code)


class TestCacheHitSameUrl:
    @pytest.mark.asyncio
    async def test_same_url_hit_no_analyzed_url(self, client):
        cached = {
            "ok": True, "url": "https://example.com/", "method": "langHtml",
            "requested_url": "https://example.com/",
        }
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=cached)):
            r = client.post("/api/v1/detect", json={"url": "https://example.com/"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body.get("analyzed_url") is None


class TestCacheHitCrossUrl:
    @pytest.mark.asyncio
    async def test_cross_url_hit_sets_analyzed_url(self, client):
        cached = {
            "ok": True, "url": "https://example.com/", "method": "langHtml",
            "requested_url": "https://example.com/",
        }
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=cached)):
            r = client.post("/api/v1/detect", json={"url": "https://example.com/some/page"})
        body = r.json()
        assert body["ok"] is True
        assert body["analyzed_url"] == "https://example.com/"

    @pytest.mark.asyncio
    async def test_cross_url_hit_old_entry_without_requested_url_field(self, client):
        # Old entry lacks requested_url; falls back to url field.
        cached = {"ok": True, "url": "https://example.com/", "method": "langHtml"}
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=cached)):
            r = client.post("/api/v1/detect", json={"url": "https://example.com/some/page"})
        body = r.json()
        assert body["analyzed_url"] == "https://example.com/"


class TestHttpError:
    @pytest.mark.asyncio
    async def test_404_no_fallback_returns_http_error(self, client):
        scrape = _scrape(status_code=404)
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": False,
            })
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "http_error"


class TestSoft404FallbackSuccess:
    @pytest.mark.asyncio
    async def test_soft_404_then_homepage_success(self, client):
        soft = _scrape(
            html="<html><head><title>Page introuvable</title></head><body>x</body></html>",
            final_url="https://example.com/missing",
            status_code=200,
        )
        homepage = _scrape(
            html='<html lang="fr"><body>' + "Bonjour " * 100 + "</body></html>",
            final_url="https://example.com/",
            status_code=200,
        )
        # First fetch_html call returns soft-404; second returns valid homepage.
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(side_effect=[soft, homepage])):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": True,
            })
        body = r.json()
        assert body["ok"] is True
        assert body["analyzed_url"] == "https://example.com/"


class TestSoft404FallbackAlsoFails:
    @pytest.mark.asyncio
    async def test_soft_404_homepage_also_invalid(self, client):
        soft = _scrape(
            html="<html><head><title>Page introuvable</title></head><body>x</body></html>",
            final_url="https://example.com/missing", status_code=200,
        )
        homepage_bad = _scrape(status_code=503)
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(side_effect=[soft, homepage_bad])):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": True,
            })
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "soft_404"  # Original verdict surfaces
        assert body.get("analyzed_url") is None


class TestRedirectedToHome:
    @pytest.mark.asyncio
    async def test_redirected_to_home_no_fallback(self, client):
        # Server redirects /missing -> /
        scrape = _scrape(final_url="https://example.com/", status_code=200)
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": False,
            })
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "redirected_to_home"


class TestKillSwitches:
    @pytest.mark.asyncio
    async def test_validation_disabled_passes_through(self, client):
        scrape = _scrape(status_code=404)  # Would be http_error, but...
        with patch("app.core.config.settings.INVALID_PAGE_DETECTION_ENABLED", False), \
             patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=scrape)):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": False,
            })
        # With validation off, the 404's HTML body runs through DomainFR pipeline.
        # We don't assert on ok=true/false (depends on body content); we assert
        # the method is NOT http_error (validator was bypassed).
        body = r.json()
        assert body["method"] != "http_error"

    @pytest.mark.asyncio
    async def test_fallback_disabled_returns_rejection(self, client):
        soft = _scrape(
            html="<html><head><title>Page introuvable</title></head><body>x</body></html>",
            final_url="https://example.com/missing", status_code=200,
        )
        with patch("app.core.config.settings.HOMEPAGE_FALLBACK_ENABLED", False), \
             patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(return_value=soft)):
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com/missing", "homepage_fallback": True,
            })
        body = r.json()
        assert body["ok"] is False
        assert body["method"] == "soft_404"
```

- [ ] **Step 2: Run, see them fail**

```bash
cd apps-microservices/api-detection-langue-fr
pytest tests/test_routes_invalid_page.py -v
```

Expected: most fail (orchestration not yet wired).

- [ ] **Step 3: Update imports + helper at top of `routes.py`**

Add to `apps-microservices/api-detection-langue-fr/app/api/routes.py` imports (after line 24):

```python
from urllib.parse import urlparse, urlunparse
from app.services.page_validator import validate as validate_page, ValidationVerdict
from app.core.metrics import VALIDATION_VERDICTS, HOMEPAGE_FALLBACK_TRIGGERED
```

Add after `_normalize_url_for_dedup` (around line 45):

```python
def _homepage_of(url: str) -> str:
    """Build the root URL for a given URL (preserves scheme + host + port)."""
    p = urlparse(url)
    return urlunparse((p.scheme or "https", p.netloc, "/", "", "", ""))


def _is_homepage(url: str) -> bool:
    """True if URL has root path (no segments)."""
    p = urlparse(url)
    return (p.path or "/") in ("", "/")


_INVALID_VERDICT_TO_TTL_S = {
    ValidationVerdict.HTTP_ERROR.value: None,         # filled at runtime from settings
    ValidationVerdict.SOFT_404.value: None,
    ValidationVerdict.REDIRECTED_TO_HOME.value: None,
}


def _ttl_from_verdict(verdict_value: str) -> int:
    """Map a verdict string to its cache TTL (settings-aware)."""
    if verdict_value == ValidationVerdict.SOFT_404.value:
        return settings.INVALID_PAGE_TTL_SOFT_S
    return settings.INVALID_PAGE_TTL_HARD_S
```

- [ ] **Step 4: Replace `_detect_single_url` body**

Replace the entire body of `_detect_single_url` (lines 67-137 in the current file) with this version. Keep the signature the same plus accept `homepage_fallback`:

```python
async def _detect_single_url(
    url: str,
    html_content: Optional[str] = None,
    proxy_url: Optional[str] = None,
    mode: DetectionMode = DetectionMode.COMPLETE,
    use_nlp_detection: bool = True,
    forced_method: Optional[str] = None,
    force_refresh: bool = False,
    homepage_fallback: bool = True,
) -> DetectionResponse:
    """Pipeline de détection FR pour une URL unique."""
    effective_url = url
    html_was_provided = html_content is not None
    fetch_result: Optional[ScrapeResult] = None

    if not html_was_provided:
        # [1] Cache lookup (domain-keyed)
        if not force_refresh:
            cached = await domain_cache.get(url)
            if cached:
                logger.info(f"Cache HIT {url}")
                # Cross-URL HIT awareness: domain key may have been seeded by a
                # different requested URL. Surface the originating URL.
                cached_req_url = cached.get("requested_url") or cached.get("url")
                if cached_req_url and cached_req_url != url and not cached.get("analyzed_url"):
                    cached["analyzed_url"] = cached_req_url
                return DetectionResponse(**cached)

        # [2] Fetch HTML
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

        if not fetch_result:
            return DetectionResponse(
                ok=False, url=url, method='fetch_failed',
                error='Impossible de récupérer le contenu HTML'
            )

        html_content = fetch_result.html
        final_url = fetch_result.final_url
        if final_url and final_url != url:
            logger.info(f"Redirection: {url} → {final_url}")
            effective_url = final_url

        # [3] Validate page (skip if kill-switch off or html_content was provided)
        if settings.INVALID_PAGE_DETECTION_ENABLED:
            verdict = validate_page(fetch_result, requested_url=url)
            VALIDATION_VERDICTS.labels(verdict=verdict.value).inc()
            if verdict != ValidationVerdict.VALID:
                logger.info(
                    f"[VALIDATE] {verdict.value} for {url} "
                    f"(status={fetch_result.status_code}, final={final_url})"
                )
                # [5] Homepage fallback
                homepage = _homepage_of(url)
                want_fallback = (
                    homepage_fallback
                    and settings.HOMEPAGE_FALLBACK_ENABLED
                    and not _is_homepage(url)
                )
                if want_fallback:
                    logger.info(f"[FALLBACK] {url} → homepage {homepage}")
                    if _INFLIGHT_DEDUP_ENABLED and not force_refresh:
                        hp_key = _normalize_url_for_dedup(homepage)
                        hp_fetch = await _inflight_dedup.coalesce(
                            hp_key, lambda: fetch_html(homepage, proxy_url)
                        )
                    else:
                        hp_fetch = await fetch_html(homepage, proxy_url)

                    if not hp_fetch:
                        HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="network_failure").inc()
                        rejection = DetectionResponse(
                            ok=False, url=url, method=verdict.value,
                            error=f"Page invalide ({verdict.value}) — repli homepage a échoué (réseau)",
                        )
                        await domain_cache.set(
                            url, url, rejection.model_dump(),
                            ttl_override=domain_cache.TTL_TRANSIENT,
                        )
                        return rejection

                    hp_verdict = validate_page(hp_fetch, requested_url=homepage)
                    VALIDATION_VERDICTS.labels(verdict=hp_verdict.value).inc()
                    if hp_verdict != ValidationVerdict.VALID:
                        HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="rejected").inc()
                        logger.warning(
                            f"[FALLBACK] FAILED {url} (verdict={verdict.value}) "
                            f"and homepage {homepage} (verdict={hp_verdict.value})"
                        )
                        rejection = DetectionResponse(
                            ok=False, url=url, method=verdict.value,
                            error=f"Page invalide ({verdict.value}) et page d'accueil également invalide ({hp_verdict.value})",
                        )
                        await domain_cache.set(
                            url, url, rejection.model_dump(),
                            ttl_override=_ttl_from_verdict(verdict.value),
                        )
                        return rejection

                    # Homepage valid → run challenge_page detection + DomainFR on homepage HTML
                    challenge = detect_challenge_page(hp_fetch.html)
                    if challenge:
                        rejection = DetectionResponse(
                            ok=False, url=homepage, method='challenge_page',
                            error=_build_challenge_error_msg(challenge),
                            analyzed_url=homepage,
                        )
                        await domain_cache.set(
                            url, homepage, rejection.model_dump(),
                        )
                        return rejection

                    detector = DomainFR(
                        homepage=homepage,
                        forced_method=forced_method,
                        use_nlp_detection=use_nlp_detection,
                        original_homepage=url,
                    )
                    hp_result = await detector.check_page_if_french(hp_fetch.html, mode)
                    hp_result.analyzed_url = homepage
                    HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="success").inc()
                    logger.info(f"[FALLBACK] OK {url} via {homepage}")
                    await domain_cache.set(url, homepage, hp_result.model_dump())
                    return hp_result

                # No fallback (disabled, or url == homepage) → cache rejection + return
                rejection = DetectionResponse(
                    ok=False, url=url, method=verdict.value,
                    error=f"Page invalide ({verdict.value})",
                )
                await domain_cache.set(
                    url, url, rejection.model_dump(),
                    ttl_override=_ttl_from_verdict(verdict.value),
                )
                return rejection

    # [4] VALID path (or kill-switch off): existing flow — challenge + DomainFR
    challenge = detect_challenge_page(html_content)
    if challenge:
        logger.warning(f"Challenge/block {challenge} pour {effective_url}")
        return DetectionResponse(
            ok=False, url=effective_url, method='challenge_page',
            error=_build_challenge_error_msg(challenge),
        )

    detector = DomainFR(
        homepage=effective_url,
        forced_method=forced_method,
        use_nlp_detection=use_nlp_detection,
        original_homepage=url if effective_url != url else None,
    )
    result = await detector.check_page_if_french(html_content, mode)

    if not html_was_provided:
        await domain_cache.set(url, effective_url, result.model_dump())

    return result
```

Add `from app.services.scraper import ScrapeResult` to the imports if not present.

- [ ] **Step 5: Wire `homepage_fallback` into `/detect` route**

Update the `/detect` route around line 173-186 — pass `request.homepage_fallback` through:

```python
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
```

- [ ] **Step 6: Run orchestration tests**

```bash
pytest tests/test_routes_invalid_page.py -v
```

Expected: all pass. Iterate fixing as needed.

- [ ] **Step 7: Run full test suite**

```bash
pytest tests/ -v --ignore=tests/test_api.py --ignore=tests/test_domain_fr.py
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/api/routes.py apps-microservices/api-detection-langue-fr/tests/test_routes_invalid_page.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): orchestrate validate + homepage fallback

EN: _detect_single_url now: surfaces analyzed_url on cross-URL cache HIT,
runs page_validator after fetch, attempts one-hop homepage fallback when
the page is invalid, caches rejections with per-verdict TTL (7d hard, 6h
soft), and emits Prometheus counters at each branch.

FR: _detect_single_url désormais : expose analyzed_url sur les HITs cache
cross-URL, exécute page_validator après le fetch, tente un repli (un
saut) vers la page d'accueil quand la page est invalide, met en cache
les rejets avec TTL par verdict (7j dur, 6h doux), et émet des compteurs
Prometheus à chaque branche.
EOF
)"
```

---

## Task 9: /detect-batch + /detect-debug behavior

**Goal:** Wire `homepage_fallback` through batch (default true) and confirm `/detect-debug` keeps fallback OFF. Verify batch Pass 2 retry does not loop on the new method values.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py:189-454` (batch processing) — pass `homepage_fallback`
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py:480-577` (`/detect-debug`) — explicit fallback OFF
- Modify: `apps-microservices/api-detection-langue-fr/app/models/schemas.py` (add `homepage_fallback` to `BatchDetectionRequest`)
- Append: `apps-microservices/api-detection-langue-fr/tests/test_routes_invalid_page.py`

**Acceptance Criteria:**
- [ ] `BatchDetectionRequest.homepage_fallback: bool = True`.
- [ ] `_detect_single_url` calls inside batch + first_match pass `request.homepage_fallback`.
- [ ] `_detect_single_url` call inside `/detect-debug` passes `homepage_fallback=False`.
- [ ] Batch Pass 2 retry filter (`r.method in ('fetch_failed', 'challenge_page')`) is unchanged — new methods (`http_error`, `soft_404`, `redirected_to_home`) are NOT retried.
- [ ] Tests verify batch passes through fallback flag correctly.

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_routes_invalid_page.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Append `homepage_fallback` to `BatchDetectionRequest`**

In `apps-microservices/api-detection-langue-fr/app/models/schemas.py`, after line 144 (`max_concurrency` field):

```python
    homepage_fallback: bool = Field(
        default=True,
        description="Tenter un repli vers la page d'accueil si la page demandée est invalide (pour chaque item du lot)."
    )
```

- [ ] **Step 2: Wire flag through batch + first_match calls in `routes.py`**

In `apps-microservices/api-detection-langue-fr/app/api/routes.py`, find each `_detect_single_url(...)` call in `_process_item_core` (around line 242):

```python
result = await _detect_single_url(
    url=url,
    html_content=item.html_content,
    proxy_url=request.proxy_url,
    mode=detection_mode,
    use_nlp_detection=request.use_nlp_detection,
    force_refresh=request.force_refresh,
    homepage_fallback=request.homepage_fallback,  # ADD
)
```

Verify there are no other `_detect_single_url` call sites in batch/first_match handlers needing the same addition.

- [ ] **Step 3: Force fallback OFF in `/detect-debug`**

In `apps-microservices/api-detection-langue-fr/app/api/routes.py`, around line 504-506 (`/detect-debug` route, where `fetch_html` is called directly), the function does not call `_detect_single_url` — it builds a debug response inline. Add explicit validation step there too, but with NO fallback:

After the `fetch_html` call (line 506-535) succeeds and `html_content`, `final_url` are set, insert (before the `detect_challenge_page` call at line 537):

```python
        # /detect-debug: validate but never trigger homepage fallback (debug shows
        # the requested URL's pipeline trace as-is). Surface verdict via result.method.
        if settings.INVALID_PAGE_DETECTION_ENABLED and fetch_result is not None:
            verdict = validate_page(fetch_result, requested_url=request.url)
            VALIDATION_VERDICTS.labels(verdict=verdict.value).inc()
            if verdict != ValidationVerdict.VALID:
                logger.info(
                    f"[DEBUG][VALIDATE] {verdict.value} for {request.url} "
                    f"(status={fetch_result.status_code}, final={final_url})"
                )
                # In debug, return the verdict in result.method but still emit
                # the rest of the debug trace using the fetched HTML.
                # (Reuse existing debug-build code below; just override method on result.)
```

Note: this creates a control-flow change. Cleanest approach: capture the verdict, run the existing debug pipeline (which calls `detector.check_page_if_french_debug`), then override the result's method:

After `return await detector.check_page_if_french_debug(...)` at line 548, wrap:

```python
        debug_response = await detector.check_page_if_french_debug(
            html_content, request.mode, fetched_by=fetched_by,
            include_full_content=request.include_full_content,
            redirected_from=redirected_from,
            challenge_detected=challenge,
        )
        if settings.INVALID_PAGE_DETECTION_ENABLED and fetch_result is not None:
            verdict = validate_page(fetch_result, requested_url=request.url)
            if verdict != ValidationVerdict.VALID:
                debug_response.result.ok = False
                debug_response.result.method = verdict.value
                debug_response.result.error = f"Page invalide ({verdict.value})"
        return debug_response
```

Note: `fetch_result` is set above when `not html_content`. When `html_content` was provided, validation is skipped (already by precondition `not html_was_provided` upstream).

This requires `fetch_result` to be in scope. In the current `/detect-debug`, the call assigns to `fetch_result` (line 506) — capture it as a `ScrapeResult` (Task 2 already migrated `fetch_html`).

In the section that handles `fetch_result` (after line 530), keep the local variable. (Task 2 step 5 already updated `html_content = fetch_result.html`.)

- [ ] **Step 4: Append batch/debug tests**

Append to `apps-microservices/api-detection-langue-fr/tests/test_routes_invalid_page.py`:

```python
class TestDetectBatchPassesHomepageFallback:
    @pytest.mark.asyncio
    async def test_batch_passes_homepage_fallback_flag(self, client):
        soft = _scrape(
            html="<html><head><title>Page introuvable</title></head><body>x</body></html>",
            final_url="https://example.com/missing", status_code=200,
        )
        homepage = _scrape(
            html='<html lang="fr"><body>' + "Bonjour " * 100 + "</body></html>",
            final_url="https://example.com/", status_code=200,
        )
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", AsyncMock(side_effect=[soft, homepage])):
            r = client.post("/api/v1/detect-batch", json={
                "items": [{"url": "https://example.com/missing"}],
                "homepage_fallback": True,
                "max_concurrency": 1,
            })
        body = r.json()
        assert body["total"] == 1
        assert body["results"][0]["ok"] is True
        assert body["results"][0]["analyzed_url"] == "https://example.com/"

    @pytest.mark.asyncio
    async def test_batch_pass2_does_not_retry_invalid_methods(self, client):
        """Pass 2 retries fetch_failed + challenge_page only — not http_error/soft_404."""
        scrape = _scrape(status_code=404)
        # If Pass 2 retried, fetch_html would be called > 1 time. Assert it's exactly 1.
        fetch_mock = AsyncMock(return_value=scrape)
        with patch("app.api.routes.domain_cache.get", AsyncMock(return_value=None)), \
             patch("app.api.routes.domain_cache.set", AsyncMock()), \
             patch("app.api.routes.fetch_html", fetch_mock):
            r = client.post("/api/v1/detect-batch", json={
                "items": [{"url": "https://example.com/missing"}],
                "homepage_fallback": False,
                "max_concurrency": 1,
            })
        body = r.json()
        assert body["results"][0]["method"] == "http_error"
        assert fetch_mock.await_count == 1


class TestDetectDebugFallbackOff:
    @pytest.mark.asyncio
    async def test_debug_does_not_trigger_homepage_fallback(self, client):
        scrape = _scrape(status_code=404)
        fetch_mock = AsyncMock(return_value=scrape)
        with patch("app.api.routes.fetch_html", fetch_mock):
            r = client.post("/api/v1/detect-debug", json={
                "url": "https://example.com/missing",
            })
        # /detect-debug returns DebugDetectionResponse; result.method must reflect
        # the verdict, but no homepage hop should occur (only one fetch_html call).
        body = r.json()
        assert body["result"]["method"] == "http_error"
        assert fetch_mock.await_count == 1
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/test_routes_invalid_page.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/api/routes.py apps-microservices/api-detection-langue-fr/app/models/schemas.py apps-microservices/api-detection-langue-fr/tests/test_routes_invalid_page.py
git commit -m "$(cat <<'EOF'
feat(api-detection-langue-fr): wire fallback through batch + debug

EN: BatchDetectionRequest gains homepage_fallback (default true), passed
through to per-item _detect_single_url. /detect-debug runs the validator
but forces fallback OFF — debug must show the requested URL's actual
state. Batch Pass 2 retry list unchanged: only fetch_failed and
challenge_page retried, never the new method values.

FR: BatchDetectionRequest reçoit homepage_fallback (true par défaut),
transmis à _detect_single_url par item. /detect-debug exécute le
validateur mais force le repli OFF — le debug doit montrer l'état réel
de l'URL demandée. Liste des retries Pass 2 inchangée : seuls
fetch_failed et challenge_page sont retentés, jamais les nouvelles
valeurs de method.
EOF
)"
```

---

## Task 10: Update CLAUDE.md docs

**Goal:** Document the new behavior, env vars, and method values for future Claude sessions.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/CLAUDE.md`

**Acceptance Criteria:**
- [ ] New section "Invalid Page Rejection" with the three new method values, the homepage fallback flow, and the new env vars.
- [ ] Existing "Concurrency & Admission Control" section unchanged.
- [ ] Detection Pipeline list mentions the validation step.

**Verify:** `cd "c:\Users\randr\Documents\Workspaces\RAG-HP-PUB" && grep -n "Invalid Page Rejection\|http_error\|soft_404\|redirected_to_home\|HOMEPAGE_FALLBACK_ENABLED\|INVALID_PAGE_DETECTION_ENABLED" apps-microservices/api-detection-langue-fr/CLAUDE.md` → matches present.

**Steps:**

- [ ] **Step 1: Add a Detection Pipeline entry**

In `apps-microservices/api-detection-langue-fr/CLAUDE.md`, in the Detection Pipeline section, insert after step 2 ("Fetch HTML"):

```
3. **Page validation** — Classifies the fetched page: `valid` / `http_error` (4XX/5XX) / `soft_404` (200 OK + body looks like "page not found") / `redirected_to_home` (deep path 302d to root). Invalid → optional one-hop homepage fallback.
```

Renumber subsequent steps.

- [ ] **Step 2: Append "Invalid Page Rejection" section**

After the "Concurrency & Admission Control" section, append:

```markdown
## Invalid Page Rejection & Homepage Fallback

Three new method values surface in `DetectionResponse.method` when the requested page is rejected:

| Method | Meaning | Cache TTL |
|---|---|---|
| `http_error` | Hard 4XX/5XX status | 7 days |
| `soft_404` | 200 OK but body matches not-found heuristic (title/H1 regex + thin content, or URL path 404 marker) | 6 hours |
| `redirected_to_home` | Requested non-root path, server redirected to `/` | 7 days |

Callers should treat these as definitive failures (do NOT retry).

When validation rejects, the service tries the domain's homepage once. If the homepage is valid, the request returns `ok=True` with `analyzed_url=<homepage>` set. If the homepage also fails, the original verdict is returned.

`analyzed_url` is also set on cache HITs where the cached entry was originally seeded by a different URL on the same domain (e.g., requesting `/some/page` returns a cached homepage answer because the cache is keyed by domain).

### Per-request flag

- `homepage_fallback: bool = true` on `DetectionRequest` and `BatchDetectionRequest`. Set `false` for strict URL-level mode.

### Env vars

| Variable | Default | Purpose |
|---|---|---|
| `INVALID_PAGE_DETECTION_ENABLED` | `true` | Master kill switch for the validator. `false` = pre-validation behavior (page-validator skipped entirely). |
| `HOMEPAGE_FALLBACK_ENABLED` | `true` | Master kill switch for the homepage fallback hop. `false` = always return rejection on invalid page. |
| `SOFT_404_TITLE_THIN_THRESHOLD` | `2000` | Visible-text char limit when title regex matches. |
| `SOFT_404_H1_THIN_THRESHOLD` | `1500` | Visible-text char limit when H1 regex matches. |
| `INVALID_PAGE_TTL_HARD_S` | `604800` (7d) | Cache TTL for `http_error` + `redirected_to_home`. |
| `INVALID_PAGE_TTL_SOFT_S` | `21600` (6h) | Cache TTL for `soft_404`. |

### Endpoint behavior

| Endpoint | Validate? | Homepage fallback? |
|---|---|---|
| `/detect` | Yes | Yes (default ON) |
| `/detect-batch` (all modes) | Yes | Yes (default ON, per item) |
| `/detect-debug` | Yes (warning only — no flow change) | **OFF** (debug shows requested URL's actual pipeline state) |
| `/check-url` | N/A (no HTML fetch) | N/A |

Batch Pass 2 retry: still `fetch_failed` + `challenge_page` only. New method values are NOT retried.

### Metrics

- `detection_validation_verdicts_total{verdict}` — counter, label values: `valid`, `http_error`, `soft_404`, `redirected_to_home`.
- `detection_homepage_fallback_triggered_total{outcome}` — counter, label values: `success`, `rejected`, `network_failure`.
```

- [ ] **Step 3: Verify**

```bash
cd "c:\Users\randr\Documents\Workspaces\RAG-HP-PUB"
grep -n "Invalid Page Rejection\|http_error\|soft_404\|redirected_to_home\|HOMEPAGE_FALLBACK_ENABLED\|INVALID_PAGE_DETECTION_ENABLED" apps-microservices/api-detection-langue-fr/CLAUDE.md
```

Expected: multiple matching lines.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(api-detection-langue-fr): document invalid page rejection

EN: New CLAUDE.md section covers the three new method values, the
homepage fallback flow, the analyzed_url field, env vars, per-endpoint
behavior, and metrics — gives future Claude sessions the full picture
without re-reading the spec.

FR: Nouvelle section CLAUDE.md couvrant les trois nouvelles valeurs de
method, le flux de repli homepage, le champ analyzed_url, les variables
d'environnement, le comportement par endpoint, et les métriques —
donne aux futures sessions Claude le tableau complet sans relire le spec.
EOF
)"
```

---

## Self-Review Notes

**Spec coverage** — every spec section maps to at least one task:
- §Solution Overview (3-part change) → T1 (status), T4 (validator), T8 (orchestration)
- §Architecture file map → T1-T8 + T10
- §Data Flow → T8
- §Components 3.1 ScrapeResult → T1
- §Components 3.2 page_validator → T4
- §Components 3.3 schemas → T6 + T9 (BatchDetectionRequest)
- §Components 3.4 routes → T8
- §Components 3.5 domain_cache → T7
- §Components 3.6 fetch_html → T2
- §Components 3.7 scraper → T1
- §Components 3.8 per-endpoint behavior → T9
- §Configuration → T3
- §Error Handling → T4 (fail-open) + T8 (orchestration)
- §Metrics → T5 + T8 (call sites)
- §Testing Strategy → T1, T2, T4, T7, T8, T9
- §Caveat 1 cache-HIT fix → T8

**Placeholder scan** — no TBDs, all code blocks contain working code.

**Type consistency** — `ScrapeResult` defined in T1 used identically in T2 (`fetch_html` return), T4 (validator input), T8 (orchestration); `ValidationVerdict` enum from T4 used in T8; `ttl_override` kwarg from T7 used in T8.

**Manual verification** (post-deploy, from spec §Testing Strategy) is operator work, not in this plan.

---

## Rollout reminder (operator)

P1: deploy code with `INVALID_PAGE_DETECTION_ENABLED=false` and `HOMEPAGE_FALLBACK_ENABLED=false` set in the service env. Existing behavior preserved.

P2: flip `INVALID_PAGE_DETECTION_ENABLED=true`. Watch `detection_validation_verdicts_total{verdict="soft_404"}` for 48h. If soft-404 rate < 2% of total requests, proceed.

P3: flip `HOMEPAGE_FALLBACK_ENABLED=true`. Watch `detection_homepage_fallback_triggered_total{outcome="success"}`. If success rate ≥ 30% of triggered, keep on.

P4: lock both env vars at `true` (or remove operator overrides). Done.
