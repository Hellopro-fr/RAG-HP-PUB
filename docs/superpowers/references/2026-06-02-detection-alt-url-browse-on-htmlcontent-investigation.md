# Investigation — `api-detection-langue-fr` opens a browser on `html_content` calls (alt-URL fetch) → crawler `socket hang up`

- **Date:** 2026-06-02
- **Status:** Investigation COMPLETE (evidence-verified). Awaiting brainstorm → spec → implementation.
- **Repos:** `RAG-HP-PUB` (service `api-detection-langue-fr` + `crawler-service`). Likely no Hellopro change.
- **Trigger:** crawler-service log: `Erreur API de détection pour le site principal https://www.leybold.com/fr-fr: ... socket hang up`. Operator suspected the recent async-job-API work broke the `html_content` bypass, and that an HTTP request from crawler appears in the detection log when it "shouldn't".

---

## TL;DR

1. **The async-job-API work did NOT break anything.** The `html_content` → no-slot / no-initial-fetch bypass is intact and untouched (verified by git diff/show/blame). `_detect_single_url` + `/detect` unchanged since March (`7d2f02e2e`).
2. **An HTTP request from crawler in the detection log is NORMAL** — crawler calls the `/detect` HTTP API. A log line ≠ a browser opened.
3. **BUT** `html_content` only guarantees the *initial page* isn't fetched. In **`mode="complete"`** (which crawler uses for the homepage), the service still **opens a browser to fetch/validate alternative-language URLs** (hreflang / data-lang / `/fr/`). This is pre-existing behavior in `domain_fr.py`. **This is the real "it's browsing when it shouldn't" issue** the operator sensed.
4. **`socket hang up` = the detection server died mid-request** (ECONNRESET), not a client timeout. Almost certainly an **OOM kill** (documented loop: `6 browsers × ~600MB + ~500MB heap ≈ 4.1GB` vs `mem_limit: 4500m`).
5. Browser launches are **CAPPED** at a single global semaphore (`BROWSER_SEMAPHORE_SIZE=6`); alt-fetches are **sequential** within a call. So OOM is a **headroom** problem, not unbounded alt-fetch concurrency — but alt-fetches **prolong** per-call browser occupancy (minutes), raising OOM odds.

**Recommended fix: Option B** (flag-gated skip of browser-based alternative-URL fetches), with **Option C** (semaphore/mem headroom) kept as a safety lever.

---

## Verified findings (with evidence)

### A. `html_content` bypass intact; async work didn't touch it — CONFIRMED
- `routes.py:143-146`: `html_was_provided = html_content is not None`; `if not html_was_provided:` gates the entire fetch+admission block. With `html_content` → **no `_fetch_with_admission` (no slot), no fetch, no browser** for the initial page.
- Async commits `344ddd1a` (refactor `_run_batch_core`) and `42ccb73d` (async endpoints) added only the `/detect-batch-async` routes + imports; `git diff 344ddd1a..42ccb73d` shows **zero changes** to `_detect_single_url` / `/detect`.
- `git blame` : the `if not html_was_provided:` gate is from `7d2f02e2e` (2026-03-26), stable since.

### B. `mode="complete"` + `html_content` STILL opens a browser for alternatives — CONFIRMED
- `domain_fr.py:1062`: `if mode == DetectionMode.COMPLETE:` → `detect_alternative_languages(content)` parses hreflang/data-lang/`<a>`/`<option>` from the provided HTML (no fetch).
- `domain_fr.py:464-519` `_validate_alternative_urls`: Phase 1 `httpx.AsyncClient` (HTTP GET, no browser); **Phase 2 fallback `scrape_html()` (`:433`) → launches a browser**. Candidates validated via `asyncio.gather` (up to 3, local `Semaphore(3)`).
- `domain_fr.py:1201-1283` (Case 6): **sequential** `for alt_candidate in reliable_alternatives:` → `await asyncio.wait_for(fetch_html(alt_candidate.url), timeout=120)` (`:1204`) → `redirect_tracker.py:227` → `scrape_html()` → **browser**. Loop breaks on first FR match.
- These alt-fetch browser launches **bypass route-level admission** (`_fetch_with_admission` is only in `routes.py`, used for the initial page) — but they DO acquire the global browser semaphore (see D).

### C. `socket hang up` = server death, not client timeout — CONFIRMED
- `DetectionLangueClient.ts:63`: axios `timeout = DETECTION_REQUEST_TIMEOUT_S (180) × 1000`. `socket hang up` = ECONNRESET (server closed connection), NOT a read timeout (which would be `ETIMEDOUT`/`timeout exceeded`).
- `docker-compose.yml` (api-detection-langue-fr-service): comment documents an OOM-kill loop → `BROWSER_SEMAPHORE_SIZE` reduced 10→6, `ADMISSION_MAX_SLOTS` 12→8; `mem_limit: 4500m`, `restart: unless-stopped`. OOM SIGKILL mid-request → client sees `socket hang up`.
- `main.py` lifespan + `JobStore`/`JobManager` init are lazy/synchronous (no Redis connect at startup) → **cannot** cause a startup crash-loop or per-request hang. Async work exonerated.
- No per-request server-side timeout on `/detect` (only per-item `timeout=300` in batch, and per-fetch `timeout` in scraper/Case-6).

### D. Browser launches are CAPPED (semaphore), alt-fetches sequential — CONFIRMED
- `scraper.py:97`: `_BROWSER_SEMAPHORE = asyncio.Semaphore(int(os.getenv("BROWSER_SEMAPHORE_SIZE","10")))` — **single module-global**; compose pins **6**.
- `scraper.py:320`: `async with _BROWSER_SEMAPHORE:` wraps the browser launch in `scrape_html()`. ALL browser paths funnel through it (initial fetch, alt Phase-2, Case-6 via `fetch_html`→`scrape_html`).
- Case-6 alt fetches are a **sequential `for` loop** (break on first match) — at most 1 alt browser at a time per call.
- **Implication:** concurrent browsers across the whole service ≤ 6 regardless of alt count. OOM is **headroom** (6×600MB+heap ≈ ceiling), not unbounded concurrency. Alt-fetches **prolong** browser occupancy per call → raise OOM probability under concurrent load (crawler `DETECTION_MAX_CONCURRENCY=5` + BO).

### E. Crawler depends on `alternative_urls` (don't naively drop complete mode) — CONFIRMED
- `crawler/src/routes.ts:473-476`: homepage → `detectionClient.detect(url, content, {mode:"complete"})` (sends crawled `content`).
- `routes.ts:503-528` (`ok=true`): **Regional Path Exclusion** — extracts hreflang variant path prefixes (`/fr-BE/`, `/fr-CA/`) from `alternative_urls` to EXCLUDE them from the crawl (avoid duplicate regional content). Documented feature (`crawler-service/CLAUDE.md` § Regional Path Exclusion). **Only needs the alt URL prefixes — NOT content-validated alts.**
- `routes.ts:531-573` (`ok=false`): uses `alternative_urls[0]` to report the French version; falls back to `checkUrl` (URL-only) only if NLP didn't reject.
- `routes.ts:575-578`: on detection error (incl. `socket hang up`) crawler **does NOT retry / no checkUrl fallback for the homepage** — swallows it, crawl aborts (no links enqueued). One hang up = whole-site crawl lost.

---

## Options & trade-offs

### Option A — crawler sends `mode:"simple"` for the homepage (1-line crawler change)
- **Gain:** no NLP, no alt-URL fetches → zero browser opens on the homepage detect → removes this OOM trigger. Tiny diff, crawler-only blast radius.
- **Lose:** NLP detection gone (content-only-French homepages → false-negative → crawl aborts); **Regional Path Exclusion breaks** (`alternative_urls` empty → crawls duplicate `/fr-BE//fr-CA/` variants); French-version discovery on non-French homepage lost. Bad for multilingual sites (= leybold).

### Option B — service-side: skip BROWSER-based alternative fetches (RECOMMENDED)
- **Shape:** request flag (e.g. `fetch_alternatives:false` / `validate_alternatives:false`), default = current behavior; crawler passes it. Skip the Phase-2 `scrape_html` fallback (`domain_fr.py:433`) + the Case-6 `fetch_html` loop (`domain_fr.py:1201-1283`). Optionally KEEP the cheap httpx Phase-1 validation (no browser). Still return hreflang-parsed `alternative_urls` (just `validated=false`).
- **Gain:** keeps NLP + returns `alternative_urls` → crawler's Regional Path Exclusion + alt-discovery still work (needs only prefixes). Eliminates browser opens on `html_content` calls → fixes the design issue AND removes the biggest per-call OOM-pressure source (long sequential browser occupancy).
- **Lose:** alternatives become unvalidated (a dead/non-FR hreflang isn't caught → crawler could exclude a path or report a 404'd French URL). Service-side change touches all `/detect` complete callers unless flag-gated (flag contains it). Bigger diff + own test/review.
- **Not guaranteed to fully eliminate OOM:** the 6-browser cap can still OOM under ≥6 concurrent *initial-page* fetches alone. Pair with C if it persists.

### Option C — OOM headroom tuning (compose env only)
- **Shape:** lower `BROWSER_SEMAPHORE_SIZE` 6→4, and/or raise `mem_limit` 4500m→6000m.
- **Gain:** direct lever on the cap-vs-memory headroom → fewer OOM kills across ALL load. Zero code, instant, reversible. The only **guaranteed** OOM control.
- **Lose:** lower semaphore → less browser concurrency → slower throughput. Higher mem_limit → needs host RAM headroom (else host-level OOM/swap hits neighbors). Treats symptom, not the "shouldn't browse" design issue.

---

## Recommendation
- **Primary: Option B**, flag-gated (crawler opts out; BO `/detect` complete keeps current validated behavior by default). It's both the design-correct fix ("don't browse when html_content provided") and the largest single OOM-pressure reducer.
- **Safety: keep Option C in pocket** — if `socket hang up` persists under concurrent load after B, drop `BROWSER_SEMAPHORE_SIZE` to 4. That's the hard headroom guarantee.
- **Reject Option A** — the Regional-Path-Exclusion regression on multilingual sites (leybold) is a real documented loss.

---

## Open questions for the brainstorm
1. **Flag name + semantics:** `fetch_alternatives` vs `validate_alternatives`? Does it skip ONLY browser fetches (Phase-2 + Case-6) or ALSO the cheap httpx Phase-1? Recommendation: skip browser parts only; keep httpx Phase-1 optional.
2. **Default:** flag defaults to current behavior (validated) so BO / other `/detect` callers are unaffected; crawler explicitly opts out. Confirm BO detect-batch should keep validation.
3. **Crawler side:** crawler passes the new flag on the homepage `detect()` call (`routes.ts:473`). `DetectionLangueClient` must thread it into the POST body. Confirm crawler still gets usable `alternative_urls` (unvalidated) for Regional Path Exclusion — it only uses prefixes, so yes.
4. **Should crawler also gain a retry/`checkUrl` fallback on `socket hang up`** for the homepage (`routes.ts:575-578` currently aborts the crawl)? Separate resilience improvement; decide if in-scope.
5. **Does Option C ship alongside** (semaphore 6→4) as a belt-and-braces, or only if B proves insufficient?

## Implementation anchors (for the spec/plan)
- Service: `apps-microservices/api-detection-langue-fr/`
  - `app/models/schemas.py` — `DetectionRequest` (+ `BatchItem`/`BatchDetectionRequest` if batch parity wanted): add the flag.
  - `app/api/routes.py` — `_detect_single_url(...)` signature + thread the flag into the detector call. `/detect` route passes `request.<flag>`.
  - `app/core/domain_fr.py` — `check_page_if_french` / `detect_alternative_languages` / `_validate_alternative_urls` (`:433` Phase-2) / Case 6 (`:1201-1283`, `:1204`): gate the browser fetches on the flag.
  - Tests: `tests/test_domain_fr.py` / `tests/test_routes_invalid_page.py` — flag on → no browser fetch path taken; alternatives still parsed.
- Crawler: `apps-microservices/crawler-service/crawler/src/`
  - `class/DetectionLangueClient.ts` — add the flag to the `detect()` POST body.
  - `routes.ts:473` — pass the flag on the homepage detect call.
- (Optional C) `docker-compose.yml` — `BROWSER_SEMAPHORE_SIZE`.

## Note
This is an investigation/handoff doc, NOT an approved design. Brainstorm first (the flag semantics + crawler-fallback scope are genuine decisions). The async-job-API work (2026-06-01) is unrelated and exonerated.
