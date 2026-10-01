# `validate_alternatives` Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-request `validate_alternatives` flag (default `true`) to `api-detection-langue-fr` that, when `false`, skips ALL HTTP/browser validation of alternative-language URLs (httpx Phase-1 + Phase-2 browser + Case-6 NLP-confirm), and have `crawler-service` opt out on its homepage detect call — eliminating browser opens / OOM on `html_content` (complete-mode) calls.

**Architecture:** The flag is carried as a `DomainFR` constructor field (mirroring `use_nlp_detection`). Two gates in `domain_fr.py` short-circuit the only two browser paths in COMPLETE mode (`_validate_alternative_urls` call → `scrape_html`; Case-6 loop → `fetch_html`). Alternatives are still parsed (hreflang stays `validated=true`, trusted, zero-HTTP), so the crawler's Regional Path Exclusion is unaffected. The flag is threaded through `/detect`, `/detect-batch`, the async worker (`BatchOpts`), and the crawler's `DetectionLangueClient`. Default `true` makes every existing caller (BO) behave exactly as today.

**Tech Stack:** Python 3.10 / FastAPI / Pydantic / pytest (service); Node.js / TypeScript / `node:test` (crawler).

**Spec:** `docs/superpowers/specs/2026-06-04-detection-langue-fr-validate-alternatives-flag-design.md` (adversarially verified against current code).

**Conventions:**
- Service test cwd: `apps-microservices/api-detection-langue-fr`. Crawler test cwd: `apps-microservices/crawler-service/crawler`.
- TDD order satisfies the repo's TDD-gate hook: write the co-located test before editing production code.
- Commit messages: bilingual EN + FR, Conventional Commits (see `.claude/rules/commit-messages.md`). Branch: `features/poc` (do not commit to `main`).
- Default-true ⇒ each task is backward-compatible on its own.

---

### Task 1: Add `validate_alternatives` to the 4 request/opts models

**Goal:** Declare the flag (default `True`) on `DetectionRequest`, `BatchDetectionRequest`, `AsyncBatchSubmitRequest`, and the `BatchOpts` dataclass — the contract foundation, mirroring the existing `homepage_fallback` field.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/models/schemas.py` (`:45-48`, `:153-156`, `:274`, `:294`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_validate_alternatives.py` (create)

**Acceptance Criteria:**
- [ ] All 4 models/dataclass expose `validate_alternatives`, default `True`.
- [ ] Each accepts an explicit `False`.
- [ ] No other field changed.

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_validate_alternatives.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test** — create `tests/test_validate_alternatives.py`:

```python
"""Tests for the validate_alternatives skip-all flag.
Spec: docs/superpowers/specs/2026-06-04-detection-langue-fr-validate-alternatives-flag-design.md
"""
import pytest

from app.models.schemas import (
    DetectionRequest,
    BatchDetectionRequest,
    AsyncBatchSubmitRequest,
    BatchItem,
    BatchOpts,
)


class TestValidateAlternativesSchema:
    def test_detection_request_default_true(self):
        assert DetectionRequest(url="https://example.com").validate_alternatives is True

    def test_detection_request_accepts_false(self):
        req = DetectionRequest(url="https://example.com", validate_alternatives=False)
        assert req.validate_alternatives is False

    def test_batch_request_default_true(self):
        req = BatchDetectionRequest(items=[BatchItem(url="https://example.com")])
        assert req.validate_alternatives is True

    def test_async_submit_request_default_true(self):
        req = AsyncBatchSubmitRequest(items=[BatchItem(url="https://example.com")])
        assert req.validate_alternatives is True

    def test_batch_opts_default_true_and_overridable(self):
        assert BatchOpts().validate_alternatives is True
        assert BatchOpts(validate_alternatives=False).validate_alternatives is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/api-detection-langue-fr && pytest tests/test_validate_alternatives.py -v`
Expected: FAIL — `TypeError`/`ValidationError` (no `validate_alternatives` field).

- [ ] **Step 3: Add the field to `DetectionRequest`** — after the `homepage_fallback` field (`schemas.py:45-48`):

```python
    homepage_fallback: bool = Field(
        default=True,
        description="Si la page demandée est invalide (404, soft-404, redirect-to-home), tenter une fois la page d'accueil du domaine. Désactiver pour avoir une réponse strictement URL-level."
    )
    validate_alternatives: bool = Field(
        default=True,
        description="Valider les URLs alternatives via HTTP/navigateur (httpx + fallback navigateur + confirmation NLP). false = parsing seul, aucune requête réseau sur les alternatives (réduit la charge navigateur/OOM). Les alternatives hreflang restent validated=true (déclaration de confiance)."
    )
```

- [ ] **Step 4: Add the field to `BatchDetectionRequest`** — after its `homepage_fallback` field (`schemas.py:153-156`):

```python
    homepage_fallback: bool = Field(
        default=True,
        description="Tenter un repli vers la page d'accueil si la page demandée est invalide (pour chaque item du lot)."
    )
    validate_alternatives: bool = Field(
        default=True,
        description="Valider les URLs alternatives via HTTP/navigateur (appliqué à chaque item). false = parsing seul, aucune requête réseau sur les alternatives."
    )
```

- [ ] **Step 5: Add the field to `AsyncBatchSubmitRequest`** — after its `homepage_fallback` field (`schemas.py:294`):

```python
    homepage_fallback: bool = Field(default=True)
    validate_alternatives: bool = Field(default=True)
    client_job_id: Optional[str] = Field(
        default=None,
        description="Caller idempotency key. A re-submit with the same key returns the existing job."
    )
```

- [ ] **Step 6: Add the field to the `BatchOpts` dataclass** — after its `homepage_fallback` field (`schemas.py:274`):

```python
@dataclass
class BatchOpts:
    """Per-call batch options, decoupled from the request model so the batch
    core can be driven by both the sync route and the async worker."""
    proxy_url: Optional[str] = None
    use_nlp_detection: bool = True
    force_refresh: bool = False
    max_concurrency: int = 10
    homepage_fallback: bool = True
    validate_alternatives: bool = True
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd apps-microservices/api-detection-langue-fr && pytest tests/test_validate_alternatives.py -v`
Expected: PASS (5 tests).

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/models/schemas.py apps-microservices/api-detection-langue-fr/tests/test_validate_alternatives.py
git commit -m "feat(detection-langue-fr): add validate_alternatives flag to request models" -m "EN: Declare validate_alternatives (default true) on DetectionRequest, BatchDetectionRequest, AsyncBatchSubmitRequest and BatchOpts, mirroring homepage_fallback. Contract only; no behavior change yet." -m "FR: Declare validate_alternatives (defaut true) sur DetectionRequest, BatchDetectionRequest, AsyncBatchSubmitRequest et BatchOpts, en miroir de homepage_fallback. Contrat seul ; aucun changement de comportement."
```

---

### Task 2: Gate the two browser paths in `DomainFR` + add skip metric

**Goal:** Add the `validate_alternatives` constructor field and use it to (a) skip the `_validate_alternative_urls` HTTP call in `detect_alternative_languages` (returning medium candidates unvalidated), and (b) skip the Case-6 browser NLP-confirm loop — so no browser opens when the flag is off. Add a `VALIDATION_SKIPPED` counter.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/core/metrics.py` (after `:62`)
- Modify: `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py` (imports; ctor `:167-179`; `:884-886`; `:1195-1196`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_domain_fr.py` (append a class)

**Acceptance Criteria:**
- [ ] `validate_alternatives=False` ⇒ `detect_alternative_languages` does NOT await `_validate_alternative_urls`; hreflang alts returned `validated=True`, medium candidates returned `validated=False, reliability='low'`.
- [ ] `validate_alternatives=False` ⇒ Case 6 never calls `fetch_html`.
- [ ] `validate_alternatives=True` (default) ⇒ `_validate_alternative_urls` IS awaited (regression).
- [ ] `detection_alt_validation_skipped_total` increments once when a skip occurs with ≥1 candidate.

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_domain_fr.py -v -k "ValidateAlternatives"` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test** — append to `tests/test_domain_fr.py`:

```python
class TestValidateAlternativesGating:
    """validate_alternatives=False must open no browser for alternatives."""

    # hreflang (trusted, validated=true, zero-HTTP) + a /fr/ <a> link (medium, needs validation)
    HTML_WITH_ALTS = (
        '<html lang="en"><head>'
        '<link rel="alternate" hreflang="fr-FR" href="https://example.com/fr-FR/">'
        '</head><body><a href="https://example.com/fr/page">Version FR</a>'
        '<p>Some English content here for the body.</p></body></html>'
    )

    @pytest.mark.asyncio
    async def test_skip_does_not_validate_and_marks_medium_unvalidated(self):
        from app.core import metrics
        before = metrics.VALIDATION_SKIPPED._value.get()
        detector = DomainFR("https://example.com", validate_alternatives=False)
        with patch.object(detector, "_validate_alternative_urls", new=AsyncMock()) as spy:
            alts = await detector.detect_alternative_languages(self.HTML_WITH_ALTS)
        spy.assert_not_awaited()
        hreflang = [a for a in alts if a.method == "hreflang"]
        medium = [a for a in alts if a.method != "hreflang"]
        assert hreflang and all(a.validated is True for a in hreflang)
        assert medium and all(a.validated is False and a.reliability == "low" for a in medium)
        assert metrics.VALIDATION_SKIPPED._value.get() == before + 1

    @pytest.mark.asyncio
    async def test_default_true_validates(self):
        detector = DomainFR("https://example.com", validate_alternatives=True)
        with patch.object(detector, "_validate_alternative_urls", new=AsyncMock(return_value=[])) as spy:
            await detector.detect_alternative_languages(self.HTML_WITH_ALTS)
        spy.assert_awaited()

    @pytest.mark.asyncio
    async def test_case6_skipped_no_browser_fetch(self):
        # Non-French homepage content + a validated hreflang FR alt → would hit Case 6.
        # With the flag off, Case 6 must be skipped and fetch_html never called.
        detector = DomainFR("https://example.com", validate_alternatives=False)
        with patch("app.core.domain_fr.fetch_html", new=AsyncMock()) as fetch_spy, \
             patch.object(detector.language_detector, "detect_from_text_content_fasttext",
                          return_value={"lang": "en", "confidence": 0.95, "method": "nlp_detection_fasttext"}), \
             patch.object(detector.language_detector, "detect_from_text_content",
                          return_value={"lang": "en", "confidence": 0.95}):
            result = await detector.check_page_if_french(self.HTML_WITH_ALTS, DetectionMode.COMPLETE)
        fetch_spy.assert_not_awaited()
        assert result.ok is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/api-detection-langue-fr && pytest tests/test_domain_fr.py -v -k "ValidateAlternatives"`
Expected: FAIL — `DomainFR.__init__` got an unexpected keyword `validate_alternatives`.

- [ ] **Step 3: Add the metric** — append to `app/core/metrics.py` after `HOMEPAGE_FALLBACK_TRIGGERED` (after `:62`):

```python
# Times alternative-URL validation was skipped because validate_alternatives=false.
VALIDATION_SKIPPED = Counter(
    "detection_alt_validation_skipped_total",
    "Times alternative-URL validation (httpx + browser + Case-6) was skipped because validate_alternatives=false",
)
```

- [ ] **Step 4: Add the metric import to `domain_fr.py`** — in the top import block, after the existing `from app.services.redirect_tracker import RedirectTracker, fetch_html` line (`:21`):

```python
from app.services.redirect_tracker import RedirectTracker, fetch_html
from app.core.metrics import VALIDATION_SKIPPED
```

- [ ] **Step 5: Add ctor param + field** — `DomainFR.__init__` (`:167-179`):

```python
    def __init__(
        self,
        homepage: str,
        forced_method: Optional[str] = None,
        use_nlp_detection: bool = True,
        original_homepage: Optional[str] = None,
        validate_alternatives: bool = True,
    ):
        self.homepage = homepage
        self.original_homepage = original_homepage or homepage
        self.forced_method = forced_method
        self.use_nlp_detection = use_nlp_detection
        self.validate_alternatives = validate_alternatives
        self.tracker = RedirectTracker()
        self.language_detector = LanguageDetector()
```

- [ ] **Step 6: Gate the validation call** — `detect_alternative_languages` (`:884-886`):

```python
        # Validate candidates via HTTP (parallel, max 3 concurrent) — only when enabled.
        if self.validate_alternatives:
            validated_results = await self._validate_alternative_urls(candidates_to_validate)
        else:
            # Skip-all: no httpx, no browser. Return medium candidates unvalidated.
            validated_results = [
                AlternativeUrl(
                    url=c['url'],
                    method=c['method'],
                    reliability='low',
                    validated=False,
                    region_priority=self._french_region_priority(c['url'], c.get('hreflang_value', '')),
                )
                for c in candidates_to_validate
            ]
            if candidates_to_validate:
                VALIDATION_SKIPPED.inc()
        all_alternatives.extend(validated_results)
```

- [ ] **Step 7: Gate Case 6** — `check_page_if_french` (`:1195-1196`):

```python
        reliable_alternatives = [a for a in alternatives if a.validated]
        if self.validate_alternatives and reliable_alternatives:
```

(The rest of the Case-6 block is unchanged; only the `if` condition gains `self.validate_alternatives and`.)

- [ ] **Step 8: Run test to verify it passes**

Run: `cd apps-microservices/api-detection-langue-fr && pytest tests/test_domain_fr.py -v -k "ValidateAlternatives"`
Expected: PASS (3 tests). Then run the full file to confirm no regression:
Run: `pytest tests/test_domain_fr.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/core/metrics.py apps-microservices/api-detection-langue-fr/app/core/domain_fr.py apps-microservices/api-detection-langue-fr/tests/test_domain_fr.py
git commit -m "feat(detection-langue-fr): skip alt-URL browser validation when validate_alternatives=false" -m "EN: DomainFR gains a validate_alternatives field. When false, detect_alternative_languages skips the _validate_alternative_urls HTTP/browser call (medium alts returned unvalidated) and Case 6 skips its fetch_html NLP-confirm loop. hreflang alts stay validated=true (trusted, zero HTTP). Adds detection_alt_validation_skipped_total." -m "FR: DomainFR gagne un champ validate_alternatives. Si false, detect_alternative_languages saute l'appel HTTP/navigateur _validate_alternative_urls (alternatives medium non validees) et le cas 6 saute sa boucle fetch_html de confirmation NLP. Les alternatives hreflang restent validated=true (confiance, zero HTTP). Ajoute detection_alt_validation_skipped_total."
```

---

### Task 3: Thread the flag through routes + the async worker

**Goal:** Pass `validate_alternatives` from every entry point into `DomainFR`: single `/detect`, `_run_batch_core`/`_process_item_core`, the sync `/detect-batch` `BatchOpts`, and the async worker's `BatchOpts` (`async_jobs.py`). `/detect-debug` deliberately keeps the default (always validates).

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/app/api/routes.py` (`:131-140`, `:258-263`, `:291-296`, `:339-348`, `:406-414`, `:652-658`)
- Modify: `apps-microservices/api-detection-langue-fr/app/core/async_jobs.py` (`:189-193`)
- Test: `apps-microservices/api-detection-langue-fr/tests/test_validate_alternatives.py` (append route + batch behavior tests)

**Acceptance Criteria:**
- [ ] `POST /detect` with `html_content` + `validate_alternatives:false` + hreflang in HTML ⇒ `alternative_urls` non-empty; neither `fetch_html` nor `scrape_html` called.
- [ ] `_run_batch_core` with `BatchOpts(validate_alternatives=False)` propagates the flag (no browser for an `html_content` item).
- [ ] Async submit threads `validate_alternatives` into `BatchOpts` (`async_jobs.py:189-193`).
- [ ] `/detect-debug` still validates (flag ignored).

**Verify:** `cd apps-microservices/api-detection-langue-fr && pytest tests/test_validate_alternatives.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test** — append to `tests/test_validate_alternatives.py`:

```python
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from main import app
from app.models.schemas import BatchItem, BatchOpts, DetectionMode
from app.api.routes import _run_batch_core

HTML_WITH_ALTS = (
    '<html lang="en"><head>'
    '<link rel="alternate" hreflang="fr-FR" href="https://example.com/fr-FR/">'
    '</head><body><a href="https://example.com/fr/page">Version FR</a>'
    '<p>English body content.</p></body></html>'
)


class TestValidateAlternativesRoute:
    def test_detect_flag_false_no_browser_alts_present(self):
        client = TestClient(app)
        with patch("app.core.domain_fr.fetch_html", new=AsyncMock()) as fetch_spy, \
             patch("app.services.scraper.scrape_html", new=AsyncMock()) as scrape_spy:
            r = client.post("/api/v1/detect", json={
                "url": "https://example.com",
                "html_content": HTML_WITH_ALTS,
                "mode": "complete",
                "validate_alternatives": False,
            })
        assert r.status_code == 200
        body = r.json()
        # hreflang alt was parsed and returned even though nothing was validated over HTTP.
        assert any(a["method"] == "hreflang" for a in body["alternative_urls"])
        fetch_spy.assert_not_awaited()
        scrape_spy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_batch_core_threads_flag(self):
        items = [BatchItem(url="https://example.com", html_content=HTML_WITH_ALTS)]
        opts = BatchOpts(validate_alternatives=False)
        with patch("app.core.domain_fr.fetch_html", new=AsyncMock()) as fetch_spy:
            results, _ = await _run_batch_core(items, DetectionMode.COMPLETE, opts)
        fetch_spy.assert_not_awaited()
        assert len(results) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/api-detection-langue-fr && pytest tests/test_validate_alternatives.py -v -k "Route or batch_core"`
Expected: FAIL — flag not threaded; `_validate_alternative_urls`/`fetch_html` may be reached (or the `DomainFR` call lacks the kwarg so the flag has no effect → `fetch_spy` awaited).

- [ ] **Step 3: Add the param to `_detect_single_url`** — signature (`:131-140`):

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
    validate_alternatives: bool = True,
) -> DetectionResponse:
```

- [ ] **Step 4: Thread into the homepage-fallback `DomainFR`** (`:258-263`):

```python
                    detector = DomainFR(
                        homepage=homepage,
                        forced_method=forced_method,
                        use_nlp_detection=use_nlp_detection,
                        original_homepage=url,
                        validate_alternatives=validate_alternatives,
                    )
```

- [ ] **Step 5: Thread into the VALID-path `DomainFR`** (`:291-296`):

```python
    detector = DomainFR(
        homepage=effective_url,
        forced_method=forced_method,
        use_nlp_detection=use_nlp_detection,
        original_homepage=url if effective_url != url else None,
        validate_alternatives=validate_alternatives,
    )
```

- [ ] **Step 6: Pass it from `/detect`** (`:339-348`):

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
            validate_alternatives=request.validate_alternatives,
        )
```

- [ ] **Step 7: Pass it from `_process_item_core`** (`:406-414`):

```python
            result = await _detect_single_url(
                url=url,
                html_content=item.html_content,
                proxy_url=opts.proxy_url,
                mode=detection_mode,
                use_nlp_detection=opts.use_nlp_detection,
                force_refresh=opts.force_refresh,
                homepage_fallback=opts.homepage_fallback,
                validate_alternatives=opts.validate_alternatives,
            )
```

- [ ] **Step 8: Populate it in `detect_french_batch`'s `BatchOpts`** (`:652-658`):

```python
    opts = BatchOpts(
        proxy_url=request.proxy_url,
        use_nlp_detection=request.use_nlp_detection,
        force_refresh=request.force_refresh,
        max_concurrency=request.max_concurrency,
        homepage_fallback=request.homepage_fallback,
        validate_alternatives=request.validate_alternatives,
    )
```

- [ ] **Step 9: Populate it in the async worker's `BatchOpts`** — `app/core/async_jobs.py:189-193` (local var is `req`):

```python
        opts = BatchOpts(
            proxy_url=req.proxy_url, use_nlp_detection=req.use_nlp_detection,
            force_refresh=req.force_refresh, max_concurrency=req.max_concurrency,
            homepage_fallback=req.homepage_fallback,
            validate_alternatives=req.validate_alternatives,
        )
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `cd apps-microservices/api-detection-langue-fr && pytest tests/test_validate_alternatives.py -v`
Expected: PASS (all). Then a quick regression on routes:
Run: `pytest tests/test_routes_invalid_page.py -v`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/app/api/routes.py apps-microservices/api-detection-langue-fr/app/core/async_jobs.py apps-microservices/api-detection-langue-fr/tests/test_validate_alternatives.py
git commit -m "feat(detection-langue-fr): thread validate_alternatives through routes and async worker" -m "EN: Pass validate_alternatives from /detect, /detect-batch (BatchOpts) and the async worker into both DomainFR constructions. /detect-debug keeps the default (always validates)." -m "FR: Propage validate_alternatives depuis /detect, /detect-batch (BatchOpts) et le worker async vers les deux constructions DomainFR. /detect-debug garde le defaut (valide toujours)."
```

---

### Task 4: Crawler — send `validate_alternatives:false` on the homepage detect call

**Goal:** Add `validateAlternatives?` to `DetectOptions`, forward it in the `/detect` POST body, and set `validateAlternatives: false` on the homepage detect call (`routes.ts:473`) — the crawler's only complete-mode call.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts` (`:28-33`, `:102-109`)
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts` (`:473-476`)
- Test: `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.test.ts` (create — also satisfies the TDD-gate's co-located test requirement for editing `DetectionLangueClient.ts`)

**Acceptance Criteria:**
- [ ] `detect(url, html, { validateAlternatives: false })` puts `validate_alternatives: false` in the POST body.
- [ ] Omitting the option ⇒ `validate_alternatives` absent from the body (server default `true`).
- [ ] Homepage detect call sends `validateAlternatives: false`.
- [ ] `npm run build` (tsc) passes.

**Verify:** `cd apps-microservices/crawler-service/crawler && node --import tsx --test src/class/DetectionLangueClient.test.ts` → 2 pass; `npm run build` → no type errors.

**Steps:**

- [ ] **Step 1: Write the failing test** — create `src/class/DetectionLangueClient.test.ts`:

```typescript
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DetectionLangueClient } from './DetectionLangueClient.js';

function clientWithCapture(): { client: DetectionLangueClient; getBody: () => any } {
    const c = new DetectionLangueClient('http://test');
    let captured: any = null;
    // Replace the internal axios instance with a stub that records the POST body.
    (c as any).client = {
        post: async (_path: string, body: any) => {
            captured = body;
            return { data: { ok: true, method: 'langHtml', url: 'http://x' } };
        },
    };
    return { client: c, getBody: () => captured };
}

test('detect() sends validate_alternatives:false when validateAlternatives=false', async () => {
    const { client, getBody } = clientWithCapture();
    await client.detect('http://x', '<html></html>', { mode: 'complete', validateAlternatives: false });
    assert.equal(getBody().validate_alternatives, false);
});

test('detect() omits validate_alternatives when option not provided', async () => {
    const { client, getBody } = clientWithCapture();
    await client.detect('http://x', '<html></html>', { mode: 'complete' });
    assert.equal(getBody().validate_alternatives, undefined);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service/crawler && node --import tsx --test src/class/DetectionLangueClient.test.ts`
Expected: FAIL — first test: `validate_alternatives` is `undefined` (not in body) / type error on `validateAlternatives`.

- [ ] **Step 3: Add `validateAlternatives` to `DetectOptions`** (`:28-33`):

```typescript
export interface DetectOptions {
    mode?: "simple" | "complete";
    forcedMethod?: string;
    useNlpDetection?: boolean;
    proxyUrl?: string;
    validateAlternatives?: boolean;
}
```

- [ ] **Step 4: Forward it in the POST body** — `_detectWithRetry` (`:102-109`):

```typescript
                const response = await this.client.post<DetectionResult>("/detect", {
                    url,
                    html_content: htmlContent || undefined,
                    mode: options?.mode ?? "complete",
                    forced_method: options?.forcedMethod ?? undefined,
                    use_nlp_detection: options?.useNlpDetection ?? true,
                    proxy_url: options?.proxyUrl ?? undefined,
                    validate_alternatives: options?.validateAlternatives ?? undefined,
                });
```

- [ ] **Step 5: Set the flag on the homepage detect call** — `routes.ts:473-476`:

```typescript
                    const detectResult = await detectionClient.detect(url, content, {
                        mode: "complete",
                        proxyUrl: proxyUrl ?? undefined,
                        validateAlternatives: false,
                    });
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd apps-microservices/crawler-service/crawler && node --import tsx --test src/class/DetectionLangueClient.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 7: Type-check the build**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: tsc completes with no errors.

- [ ] **Step 8: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.test.ts apps-microservices/crawler-service/crawler/src/routes.ts
git commit -m "feat(crawler): opt out of alt-URL validation on homepage detect" -m "EN: DetectionLangueClient forwards a validateAlternatives option as validate_alternatives in the /detect body; the homepage detect call (its only complete-mode call) sends false to stop the detection service from opening a browser to validate alternatives (OOM / socket-hang-up source)." -m "FR: DetectionLangueClient transmet une option validateAlternatives en tant que validate_alternatives dans le corps /detect ; l'appel de detection de la page d'accueil (son seul appel en mode complete) envoie false pour empecher le service de detection d'ouvrir un navigateur afin de valider les alternatives (source d'OOM / socket-hang-up)."
```

---

### Task 5: Documentation (both `CLAUDE.md`)

**Goal:** Document the flag in `api-detection-langue-fr/CLAUDE.md` (per-request flags, endpoint table, Case-6 behavior note, metric) and note the crawler opt-out in `crawler-service/CLAUDE.md`.

**Files:**
- Modify: `apps-microservices/api-detection-langue-fr/CLAUDE.md`
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

**Acceptance Criteria:**
- [ ] `api-detection-langue-fr/CLAUDE.md` documents `validate_alternatives` (semantics, default true, skip-all, metric, debug ignores it, Case-6 verdict change).
- [ ] `crawler-service/CLAUDE.md` documents that the homepage detect sends `validate_alternatives=false` and why.

**Verify:** `git diff --stat` shows both files changed; manual read confirms the flag is described accurately.

**Steps:**

- [ ] **Step 1: Update `api-detection-langue-fr/CLAUDE.md`** — under the "Invalid Page Rejection & Homepage Fallback" → "Per-request flag" area, add a sibling subsection:

```markdown
## Alternative-URL Validation Skip (`validate_alternatives`)

`validate_alternatives: bool = true` on `DetectionRequest`, `BatchDetectionRequest`, and `AsyncBatchSubmitRequest` (threaded via `BatchOpts`). When **false**, COMPLETE-mode detection still **parses** alternatives from the HTML but performs **zero HTTP/browser work** on them:

- skips the httpx Phase-1 + Phase-2 browser validation (`_validate_alternative_urls` → `scrape_html`),
- skips the Case-6 browser NLP-confirmation loop (`fetch_html` per validated alt).

Returned alts: hreflang → `validated:true` (trusted declaration, unchanged); medium (`data-lang`/`link`/`option`) → `validated:false, reliability:'low'`. Default **true** ⇒ existing callers (BO) keep full validation.

**Why:** `crawler-service` sends `html_content` for the homepage in `complete` mode; the alt-validation browser opens (not the initial page) were the residual OOM / `socket hang up` source. Setting `validate_alternatives=false` removes them while preserving the hreflang prefixes the crawler's Regional Path Exclusion consumes.

**Deliberate behavior change (flagged calls only):** a site whose provided homepage content is not NLP-confirmed French but exposes an NLP-confirmable French alternative previously returned `ok=true` via Case 6; with the flag off it returns `ok=false` (falls through to Case 7/9). `/detect-debug` **ignores** the flag (always validates, to show the full pipeline).

Metric: `detection_alt_validation_skipped_total` (no labels) — increments once per flagged skip with ≥1 candidate.
```

- [ ] **Step 2: Update `crawler-service/CLAUDE.md`** — under "api-detection-langue-fr Caller Contract", append:

```markdown
**Alternative-URL validation opt-out:** the homepage detect call (`routes.ts:473`, the crawler's only `mode:"complete"` call) sends `validateAlternatives: false` → POST body `validate_alternatives: false`. This stops the detection service from opening a browser to fetch/validate alternative-language URLs on the crawler's `html_content` calls (the OOM / `socket hang up` source). The crawler still receives parsed `alternative_urls` (hreflang prefixes) for Regional Path Exclusion. Internal-page detect calls use `mode:"simple"` and never trigger alt validation, so they need no flag.
```

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/api-detection-langue-fr/CLAUDE.md apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(detection-langue-fr,crawler): document validate_alternatives flag" -m "EN: Document the validate_alternatives skip-all flag (service) and the crawler homepage opt-out." -m "FR: Documente le flag skip-all validate_alternatives (service) et l'opt-out de la page d'accueil cote crawler."
```

---

## Out of scope (per spec)

- Option C (`BROWSER_SEMAPHORE_SIZE` 6→4) — reactive lever only, not shipped.
- Crawler retry / `checkUrl` fallback on `socket hang up` (`routes.ts:575-578`) — separate spec.
- `/detect-debug` honoring the flag — intentionally always validates.

## Rollout (post-merge, operator)

1. Deploy `api-detection-langue-fr` (new flag, default true → no-op for existing traffic).
2. Deploy `crawler-service` (homepage call now sends `validate_alternatives=false`).
3. Watch `detection_alt_validation_skipped_total` rise + `socket hang up` / OOM-restart count fall.
4. If hang-ups persist under load → apply Option C (`BROWSER_SEMAPHORE_SIZE=4`, compose env, no code).
