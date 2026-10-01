# Design — `validate_alternatives` flag: skip browser-based alternative-URL fetches in `api-detection-langue-fr`

- **Date:** 2026-06-04
- **Status:** APPROVED design (brainstorm complete). Next: implementation plan (writing-plans).
- **Repos / services:** `RAG-HP-PUB` → `api-detection-langue-fr` (service) + `crawler-service` (caller). No Marketplace BO change.
- **Investigation source:** `docs/superpowers/references/2026-06-02-detection-alt-url-browse-on-htmlcontent-investigation.md` (verified findings, Option A/B/C trade-offs, 5 open questions). This spec implements **Option B**.

---

## Problem (one paragraph)

In `mode="complete"`, even when the caller provides `html_content` (so the **initial** page is never fetched), the service still **opens a headless browser to fetch/validate alternative-language URLs** — both during alt validation (`_validate_single_url` Phase-2 `scrape_html`) and in the Case-6 NLP-confirmation loop (`fetch_html` per validated alt). `crawler-service` calls `/detect` for the homepage with `html_content` + `mode:"complete"`, so these alt-fetch browser launches run on the crawler's behalf, prolong per-call browser occupancy (minutes), and raise the odds of an OOM kill (`6 browsers × ~600MB + heap ≈ 4.1GB` vs `mem_limit: 4500m`). An OOM SIGKILL mid-request surfaces to the crawler as `socket hang up` (ECONNRESET); the crawler does not retry the homepage → the whole crawl aborts. This is the "it's browsing when it shouldn't" issue. **The async-job-API work (2026-06-01) is unrelated and exonerated.**

## Goal

Give callers a per-request flag to **opt out of all HTTP/browser validation of alternative URLs** while still receiving the parsed `alternative_urls` (hreflang prefixes) the crawler needs. Eliminate browser opens on `html_content` + `complete` calls. Backward-compatible: default behavior unchanged for every existing caller (BO).

## Non-goals (deferred — see § Out of scope)

- Lowering `BROWSER_SEMAPHORE_SIZE` (Option C) — kept as a reactive lever, not shipped.
- Crawler retry / `checkUrl` fallback on `socket hang up` (`routes.ts:575-578`) — separate resilience spec.
- Flagging the crawler's internal-page detect calls (`routes.ts:604,658`).

---

## Resolved decisions (the investigation's 5 open questions)

| # | Question | Decision |
|---|----------|----------|
| Q1 | Flag name + semantics: browser-only vs also httpx? | **`validate_alternatives`, skip-all.** `false` ⇒ skip httpx Phase-1 **and** Phase-2 browser **and** Case-6. Clean name↔behavior; lowest latency; zero alt-network. The kept-httpx alternative buys the only opt-in caller (crawler) nothing — it consumes hreflang prefixes only, which are trusted with zero HTTP under both options. |
| Q2 | Default | **`true`** everywhere. BO and all current callers keep full validation; only an explicit `false` changes behavior. |
| Q3 | Crawler side | Crawler threads `validateAlternatives: false` on the **homepage** detect call (`routes.ts:473`). Still receives usable (unvalidated) `alternative_urls` for Regional Path Exclusion. |
| Q4 | Endpoints scope | **Single + batch + async.** Flag on `DetectionRequest`, `BatchDetectionRequest`, `AsyncBatchSubmitRequest`, `BatchOpts`. |
| Q5 | Crawler `socket hang up` fallback | **Deferred** (out of scope). B removes the browser-driven hang-up for crawler calls, lowering urgency. |
| Q6 | Ship Option C alongside? | **No** — kept in pocket; documented lever only. |

---

## Architecture & data flow

```
DetectionRequest.validate_alternatives (default true)
        │  (also BatchDetectionRequest / AsyncBatchSubmitRequest → BatchOpts)
        ▼
routes._detect_single_url(..., validate_alternatives)
        │  passed into every DomainFR(...) construction
        ▼
DomainFR(validate_alternatives=<bool>)   # ctor field self.validate_alternatives
        ├─ detect_alternative_languages()  → if False: parse only, NO _validate_alternative_urls (no httpx, no browser)
        └─ check_page_if_french() Case 6   → if False: skip browser NLP-confirm loop (no fetch_html)
```

The flag is carried as a **`DomainFR` constructor field** (consistent with `use_nlp_detection`, `forced_method`), so both the validation method and Case 6 read `self.validate_alternatives` without touching the `check_page_if_french(content, mode)` signature.

### Alternatives still parsed (no behavior loss for Regional Path Exclusion)

`detect_alternative_languages` parsing is **pure** (BeautifulSoup). hreflang alts are added via `_add_trusted` with `validated=true` and **zero HTTP** (`domain_fr.py:704-716`, `:752`). Regional Path Exclusion (`crawler/src/class/DetectionLangueClient.ts:computeExcludedRegionalPaths`) consumes alt **path prefixes** and never gated on `validated`. Therefore the flag does **not** change Regional Path Exclusion (leybold-type multilingual sites keep working).

---

## Detailed design

### A. Schemas — `app/models/schemas.py`

Add, mirroring the existing `homepage_fallback` field exactly (default `True`):

- `DetectionRequest.validate_alternatives: bool = Field(default=True, description="Valider les URLs alternatives via HTTP/navigateur (Phase httpx + fallback navigateur + confirmation NLP). false = parsing seul, aucune requête réseau sur les alternatives (réduit la charge navigateur/OOM). Les alternatives hreflang restent validated=true (déclaration de confiance).")`
- `BatchDetectionRequest.validate_alternatives: bool = Field(default=True, …)` (applied to every item)
- `AsyncBatchSubmitRequest.validate_alternatives: bool = Field(default=True, …)`
- `BatchOpts.validate_alternatives: bool = True` (dataclass field)

### B. Detector — `app/core/domain_fr.py`

**B1. Constructor (`:167-179`)** — add param + field:
```python
def __init__(
    self,
    homepage: str,
    forced_method: Optional[str] = None,
    use_nlp_detection: bool = True,
    original_homepage: Optional[str] = None,
    validate_alternatives: bool = True,
):
    ...
    self.use_nlp_detection = use_nlp_detection
    self.validate_alternatives = validate_alternatives
    ...
```

**B2. `detect_alternative_languages` (`:884-886`)** — gate the HTTP validation call:
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
        VALIDATION_SKIPPED.inc()   # see § Metrics
all_alternatives.extend(validated_results)
```
hreflang alts in `all_alternatives` are untouched (`validated=true`, trusted).

**B3. Case 6 (`:1196`)** — gate the browser NLP-confirmation loop:
```python
reliable_alternatives = [a for a in alternatives if a.validated]
if self.validate_alternatives and reliable_alternatives:
    ... # existing fetch_html(alt) browser loop, unchanged
```
With the flag off, `reliable_alternatives` still contains hreflang alts (`validated=true` trusted), so the `self.validate_alternatives` guard is **required** to prevent browser-fetching them. Skipping Case 6 falls through to Case 7/8/9.

> **Deliberate behavior change (flagged calls only):** a site whose *provided* homepage content is **not** NLP-confirmed French but exposes an NLP-confirmable French alternative previously returned `ok=true` via Case 6. With the flag off it now returns `ok=false` (Case 7/9). Accepted per the investigation. The crawler seeds French homepages (resolved via Case 1/2 on the provided content), so it rarely reaches Case 6; and on `ok=false` the crawler does not auto-switch to the alt regardless.

### C. Routes — `app/api/routes.py`

**C1. `_detect_single_url`** — add param `validate_alternatives: bool = True`; thread into **both** `DomainFR(...)` constructions:
- homepage-fallback detector (`:258-263`)
- VALID-path detector (`:291-296`)

**C2. `/detect`** (`:339-348`) — pass `validate_alternatives=request.validate_alternatives`.

**C3. `_run_batch_core` / `_process_item_core`** (`:406-414`) — pass `validate_alternatives=opts.validate_alternatives` into `_detect_single_url`.

**C4. `detect_french_batch`** (`:652-658`) — populate `BatchOpts(validate_alternatives=request.validate_alternatives, …)`.

**C5. Async worker** — `app/core/async_jobs.py:189-193` (`JobManager.submit`) is the **single** site converting `AsyncBatchSubmitRequest` → `BatchOpts` (then passed to `_batch_runner` → `_run_batch_core`). Add `validate_alternatives=req.validate_alternatives,` after the `homepage_fallback=req.homepage_fallback,` line (note: the local var is `req`, not `request`).

**C6. `/detect-debug`** (`:757-762`) — **flag ignored**: construct `DomainFR` with the default (`validate_alternatives=True`) so debug always validates and shows the full pipeline. Same deliberate divergence as debug already forcing `homepage_fallback` OFF. Documented in the endpoint table.

### D. Crawler — `crawler/src/class/DetectionLangueClient.ts` + `routes.ts`

**D1. `DetectOptions`** (`:28-33`) — add `validateAlternatives?: boolean;`.

**D2. `_detectWithRetry` POST body** (`:102-109`) — add:
```ts
validate_alternatives: options?.validateAlternatives ?? undefined,
```
(`undefined` ⇒ axios omits the field ⇒ server default `true`.)

**D3. Homepage detect call `routes.ts:473`** — add `validateAlternatives: false`:
```ts
const detectResult = await detectionClient.detect(url, content, {
    mode: "complete",
    proxyUrl: proxyUrl ?? undefined,
    validateAlternatives: false,
});
```

No other crawler call sites change in this scope.

### E. Metrics — `app/core/metrics.py`

Add a no-label counter:
```python
VALIDATION_SKIPPED = Counter(
    "detection_alt_validation_skipped_total",
    "Times alternative-URL validation (httpx + browser + Case-6) was skipped because validate_alternatives=false",
)
```
Incremented once in `detect_alternative_languages` when the flag causes a skip with ≥1 candidate (see B2). Confirms crawler adoption post-deploy. Import where needed in `domain_fr.py`.

---

## Out of scope / follow-ups

1. **Option C** (`BROWSER_SEMAPHORE_SIZE` 6→4 / `mem_limit` raise) — reactive lever only. If `socket hang up` persists under concurrent load after B ships, drop the semaphore to 4 (compose env, zero code). The 6-browser cap can still OOM under ≥6 concurrent *initial-page* fetches alone — B does not change that.
2. **Crawler `socket hang up` resilience** (`routes.ts:575-578`) — add retry + `checkUrl` fallback for the homepage so one hang-up does not abort the crawl. Separate spec.
3. **Internal-page detect calls** (`routes.ts:604,658`) — both use `mode:"simple"` (verified), so `detect_alternative_languages` (COMPLETE-only, `domain_fr.py:1061`) never runs → they never validate alternatives and never open a browser for alts. **No flag needed.** The homepage call (`routes.ts:473`) is the crawler's *only* `complete`-mode call and thus the sole source of alt-fetch browser opens.
4. **`/detect-debug` honoring the flag** — intentionally not done; revisit only if operators need to reproduce a crawler call's exact (skip) path through debug.

## BO (Marketplace) — explicitly no change

`fonctions_scrapping.php::detectBatchUrls` and all BO `/detect` / `/detect-batch` callers never send `validate_alternatives` → server default `true` → full validation preserved. No PHP edit.

---

## Testing plan

### Service (pytest)
- `tests/test_domain_fr.py`
  - `validate_alternatives=False`: spy/assert `_validate_alternative_urls` is **not awaited**; hreflang alts present with `validated=True`; medium candidates present with `validated=False, reliability='low'`; `region_priority` populated.
  - `validate_alternatives=False` + content with a `validated` hreflang alt + non-French homepage text: mock `fetch_html`; assert it is **not called** (Case 6 skipped); result `ok=False` (falls through to Case 7/9).
  - `validate_alternatives=True` (default): existing behavior unchanged (regression) — `_validate_alternative_urls` called, Case 6 may fetch.
  - `VALIDATION_SKIPPED` increments once when skip occurs with ≥1 candidate; not incremented when validating or when no medium candidates.
- new `tests/test_validate_alternatives.py` (routes)
  - `POST /detect` `{html_content, mode:"complete", validate_alternatives:false}` with hreflang in HTML ⇒ `alternative_urls` non-empty, no browser path exercised (patch `scrape_html`/`fetch_html`, assert not called).
  - `POST /detect-batch` with `validate_alternatives:false` ⇒ per-item parity.
  - `POST /detect-batch-async` submit with `validate_alternatives:false` ⇒ propagated into `BatchOpts` (assert via worker path or a unit check on the submit→opts mapping).
  - Default (`validate_alternatives` omitted) ⇒ true ⇒ validation path taken.

### Crawler (TS)
- `DetectionLangueClient` test: `detect(url, html, { validateAlternatives: false })` puts `validate_alternatives: false` in the POST body; omitted option ⇒ field absent.

---

## Blast radius

- **Files:** service `schemas.py`, `domain_fr.py`, `routes.py`, `async_jobs.py` (one construction site), `metrics.py`, `CLAUDE.md`, tests; crawler `DetectionLangueClient.ts`, `routes.ts`, `CLAUDE.md`, tests.
- **No shared libs, no proto regen, no `docker-compose.yml`** change (Option C deferred).
- **Backward compatibility:** default `true` ⇒ every current caller (BO, any other `/detect` consumer) behaves exactly as today. Only `validate_alternatives=false` callers (crawler homepage) change.
- **Deploy order is free:** server is additive (new optional field, default = old behavior); crawler sending the field to an older server is harmless (server ignores unknown field via Pydantic default) — though for the OOM relief to take effect the **server** must be deployed. Recommended: deploy service first, then crawler.

## Rollout

1. Deploy `api-detection-langue-fr` (new flag, default true → no-op for existing traffic).
2. Deploy `crawler-service` (homepage call now sends `validate_alternatives=false`).
3. Watch `detection_alt_validation_skipped_total` rising (crawler adoption) and `socket hang up` / OOM-restart count on the detection service falling.
4. If `socket hang up` persists under load → apply Option C (`BROWSER_SEMAPHORE_SIZE=4`, compose env) — no code change.

## Documentation

- `apps-microservices/api-detection-langue-fr/CLAUDE.md`: add `validate_alternatives` to the per-request flags + env/endpoint tables; note the Case-6 verdict change for flagged calls; debug ignores the flag.
- `apps-microservices/crawler-service/CLAUDE.md`: note the homepage detect now sends `validate_alternatives=false` and why (avoid browser opens / OOM on `html_content` calls).

---

## Verification (provenance)

This spec was adversarially verified against the current code via a 5-agent fan-out (read-only) before approval-to-plan:

- **Anchors:** every cited `file:line` confirmed accurate against current code.
- **Parity:** `homepage_fallback` confirmed to live in exactly the 4 targets we mirror (`DetectionRequest:45-48`, `BatchDetectionRequest:153-156`, `BatchOpts:274`, `AsyncBatchSubmitRequest:294`); `AlternativeUrl` (`schemas.py:63-81`) has the 5 fields the B2 skip-branch constructs; `metrics.py` already imports `Counter` and defines sibling counters (`VALIDATION_VERDICTS`, `HOMEPAGE_FALLBACK_TRIGGERED`).
- **Async site pinned:** `async_jobs.py:189-193` (`JobManager.submit`) is the only `AsyncBatchSubmitRequest → BatchOpts` conversion (C5).
- **Browser-path completeness (adversarial):** the only two browser paths in COMPLETE mode are `scrape_html` (`domain_fr.py:433`, inside `_validate_alternative_urls`) and `fetch_html` (`:1204`, Case 6). No third path exists, so B2 (skip the `_validate_alternative_urls` call) + B3 (gate Case 6) is sufficient to guarantee zero browser opens when the flag is off.
- **Claims B & C confirmed:** Regional Path Exclusion (`computeExcludedRegionalPaths`) reads only `alt.url` prefixes, never `validated`; hreflang alts are `validated=true` via `_add_trusted` with zero HTTP.
- **Crawler scope confirmed:** internal-page detect calls (`routes.ts:604,658`) are `mode:"simple"` → never validate alternatives; only the homepage call (`:473`) is `complete`.
