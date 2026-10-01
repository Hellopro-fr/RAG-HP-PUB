# Detection-Langue-FR — Invalid Page Rejection + Homepage Fallback — Design

**Date:** 2026-05-05
**Status:** Approved (pending implementation)
**Scope:** `apps-microservices/api-detection-langue-fr` (Python). No caller-side changes required.
**Related:** Independent of the FR-detection validation hardening series (`2026-04-29`, `2026-04-30`) — those addressed alternative-link/regional-prefix validation in the crawler. This spec addresses page-validity gating in the API.

---

## Problem

The service currently treats any HTTP response from Playwright as analyzable content. Symptoms:

1. A user submits `https://www.example.com/this-does-not-exist` (real HTTP 404).
2. `scrape_html` returns `(html, final_url)` — **HTTP status code is discarded**.
3. `_detect_single_url` runs `detect_challenge_page` (covers Cloudflare/DataDome/Squid/some HTTP error pages), then DomainFR pipeline.
4. `detect_challenge_page` only fires on narrow patterns: `<title>4XX — ...</title>` plus noindex/forbidden/etc. A modern custom 404 (full chrome — header, menu, footer, FR cookie banner) does **not** match.
5. NLP runs over the 404 body → detects French → returns `ok=true` → cached for 30 days under the domain key.

**Net result:** invalid pages get cached as definitive French detections.

User report: "I put a 404 page as a page to be detected and it was still analyzed. We shouldn't use a non-valid page as verification."

### Root causes

- `scraper.scrape_html` does not surface HTTP status to the detection pipeline.
- `detect_challenge_page` is a security/anti-bot guard, not a generic page-validity guard. It misses:
  - Hard 4XX/5XX whose body has full chrome (no telltale "you have been blocked" text).
  - Soft-404 (server returns 200 OK but body is a "page introuvable" placeholder).
  - 404→homepage redirects (server catches 404 and 302s to `/`; pipeline analyzes the homepage thinking it's the requested URL).

---

## Goals

- Reject pages that are clearly not the requested content **before** running the detection pipeline.
- When rejection fires, attempt a homepage fallback (one hop), preserving the user intent of "is this domain French?".
- Keep behavior fully kill-switchable via env vars during rollout.
- No caller (api-gateway, crawler-service, common-utils detection_client) needs to change beyond awareness of three new method values.

## Non-Goals

- Detect parked domains, "under construction", or generic thin pages. Distinct heuristics; high false-positive risk on legit thin sites. Defer.
- Fix `tests/test_api.py` broken `from app.main import app` import (pre-existing, separate task).
- Migrate existing cached entries. Stale `ok=True` results for past-404 URLs naturally expire by TTL (max 30 days). If urgent, targeted Redis flush per domain.
- Modify `scrape_html_with_redirects` (already returns dict with `status_code`; orthogonal).

---

## Solution Overview

Three-part change in the API service only:

1. **Surface HTTP status** through `scrape_html` → `fetch_html`. Switch return type from `tuple[str, str]` to `ScrapeResult` dataclass (`html`, `final_url`, `status_code`, `content_type`, `headers`).
2. **New `app/services/page_validator.py`** — pure validator. Input: `ScrapeResult` + requested URL. Output: `ValidationVerdict` ∈ `{valid, http_error, soft_404, redirected_to_home}`. Multi-signal heuristics, no I/O.
3. **Orchestrate fallback in `routes._detect_single_url`** — on rejection (and when allowed), retry once against the requested URL's homepage. If homepage also rejects, return the original verdict.

Design choices:

| Decision | Picked | Why |
|---|---|---|
| Scope of "non-valid" | Hard 4XX/5XX + soft-404 + redirected-to-home | Matches the three real-world failure modes; defers parked/thin detection (high FP risk). |
| Response shape | 3 new method values: `http_error`, `soft_404`, `redirected_to_home` + new field `analyzed_url` | Best for observability + correct per-case TTL; callers can branch. |
| Soft-404 strictness | Multi-signal (title regex + thin OR H1 regex + thin OR URL path 404 marker) | Title-only fires on legit "What is a 404 error" articles; combining with thinness avoids false positives. |
| `scrape_html` return type | `ScrapeResult` dataclass | Self-documenting; room for future fields without churn. |
| Layer placement | New `page_validator.py` (pure) + orchestration in `_detect_single_url` | Validator unit-testable in isolation; orchestration stays where state lives. |
| `/detect-debug` fallback | OFF | Debug must show the requested URL's actual pipeline state. |

---

## Architecture

```
api-detection-langue-fr/
  app/
    services/
      scraper.py              [MOD] scrape_html returns ScrapeResult
      page_validator.py       [NEW] validate(scrape, requested_url) -> ValidationVerdict
      redirect_tracker.py     [MOD] fetch_html returns ScrapeResult instead of (html, final_url)
    api/
      routes.py               [MOD] _detect_single_url orchestrates: fetch → validate → fallback
    core/
      config.py               [MOD] new env vars (kill switches, thresholds, TTLs)
      domain_fr.py            [MOD] domain_cache.set accepts ttl_override; stores requested_url field
    models/
      schemas.py              [MOD] DetectionRequest.homepage_fallback,
                                    DetectionResponse.analyzed_url, new method enum values
    core/
      metrics.py              [MOD] VALIDATION_VERDICTS, HOMEPAGE_FALLBACK_TRIGGERED
  tests/
    test_page_validator.py    [NEW] ~12-15 tests for the validator
    test_scraper.py           [MOD] ScrapeResult shape assertions
    test_redirect_tracker.py  [NEW or MOD] fetch_html ScrapeResult propagation
    test_routes.py / test_api.py [MOD] orchestration E2E (~10 tests)
    test_domain_cache.py      [NEW or MOD] TTL override + requested_url round-trip
```

### Module responsibilities

- **`page_validator.py`** — pure, no I/O. Heuristics + thresholds. Unit tests on hand-crafted ScrapeResult instances.
- **`routes._detect_single_url`** — owns the state machine: cache → fetch → validate → fallback decision → DomainFR.
- **`scraper.py`** — dumb fetch + status surfacing. No semantic interpretation.
- **`redirect_tracker.fetch_html`** — retry + URL variant logic preserved. Now returns ScrapeResult.

---

## Data Flow

### Per-request (`/detect`, single URL)

```
_detect_single_url(url, ..., homepage_fallback=True):

  [1] Cache lookup (domain-keyed, existing behavior)
      cached = domain_cache.get(url)
      if cached:
          # Caveat 1 fix: cross-URL HIT awareness
          cached_req_url = cached.get("requested_url") or cached.get("url")
          if cached_req_url != url:
              cached["analyzed_url"] = cached_req_url
          return DetectionResponse(**cached)

  [2] Fetch HTML
      scrape = await fetch_html(url, proxy)   # ScrapeResult | None
      if scrape is None:
          return DetectionResponse(ok=False, method='fetch_failed', ...)

  [3] Validate
      verdict = page_validator.validate(scrape, requested_url=url)
      VALIDATION_VERDICTS.labels(verdict=verdict.value).inc()

  [4] If verdict == VALID
      → existing flow: detect_challenge_page → DomainFR
      → cache.set(url, effective_url=scrape.final_url, result, ttl=normal)
      → return result

  [5] If verdict != VALID and homepage_fallback enabled and url != homepage:
      homepage = scheme + "://" + host + "/"
      hp_scrape = await fetch_html(homepage, proxy)
      if hp_scrape is None:
          HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="network_failure").inc()
          → cache.set(url, ttl=transient 6h)
          → return rejection (method=verdict.value, error="homepage fetch failed")
      hp_verdict = page_validator.validate(hp_scrape, requested_url=homepage)
      if hp_verdict != VALID:
          HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="rejected").inc()
          → cache.set(url, ttl=ttl_from_verdict(verdict))
          → return DetectionResponse(ok=False, method=verdict.value, analyzed_url=None)
      # Homepage valid → run challenge_page + DomainFR on homepage HTML
      result = DomainFR.check_page_if_french(hp_scrape.html, ...)
      result.analyzed_url = homepage
      HOMEPAGE_FALLBACK_TRIGGERED.labels(outcome="success").inc()
      → cache.set(url, effective_url=homepage, result, ttl=normal)  # 30d if ok
      → return result

  [6] If verdict != VALID and (no fallback or url == homepage):
      → cache.set(url, ttl=ttl_from_verdict(verdict))
      → return DetectionResponse(ok=False, method=verdict.value, ...)
```

### Cache write contract

`domain_cache.set(url, effective_url, result, ttl_override=None)`:

- New optional `ttl_override` int. If `None`, existing logic (30d ok, 7d nok-definitive, 6h transient).
- Stores new field `requested_url=url` in cached payload.
- New verdicts map to TTL via `ttl_from_verdict()`:

| Verdict | TTL | Env var |
|---|---|---|
| `http_error` | 7d | `INVALID_PAGE_TTL_HARD_S` |
| `redirected_to_home` | 7d | `INVALID_PAGE_TTL_HARD_S` |
| `soft_404` | 6h | `INVALID_PAGE_TTL_SOFT_S` |

### Inflight dedup interaction

Existing `_inflight_dedup.coalesce(dedup_key, factory)` wraps `fetch_html(url)`. Homepage fallback adds a second `fetch_html(homepage)` call inside the same request. The second call has its own dedup key (the homepage URL) and coalesces with concurrent homepage requests from other callers.

---

## Components

### 3.1 `ScrapeResult` dataclass (in `scraper.py`)

```python
from dataclasses import dataclass, field

@dataclass
class ScrapeResult:
    html: str
    final_url: str
    status_code: int                    # 0 if Playwright returned no response
    content_type: str = ""
    headers: dict = field(default_factory=dict)
```

### 3.2 `page_validator.py`

```python
from enum import Enum
from typing import Optional
from urllib.parse import urlparse
import re
from bs4 import BeautifulSoup

from app.services.scraper import ScrapeResult
from app.core.config import settings

class ValidationVerdict(str, Enum):
    VALID = "valid"
    HTTP_ERROR = "http_error"
    SOFT_404 = "soft_404"
    REDIRECTED_TO_HOME = "redirected_to_home"

_NOT_FOUND_RE = re.compile(
    r"\b(404|not\s+found|page\s+not\s+found|page\s+introuvable|"
    r"page\s+non\s+trouv[eé]e|page\s+n['’]existe\s+pas|erreur\s+404|"
    r"page\s+inexistante|file\s+not\s+found)\b",
    re.IGNORECASE,
)
_URL_404_PATH_RE = re.compile(
    r"/(?:404|error|not[-_]found|page[-_]non[-_]trouv[eé]e|page[-_]introuvable)(?:/|$)",
    re.IGNORECASE,
)


def validate(scrape: ScrapeResult, requested_url: str) -> ValidationVerdict:
    # 1. Hard HTTP error
    if 400 <= scrape.status_code < 600:
        return ValidationVerdict.HTTP_ERROR

    # 2. Redirected-to-home
    req_path = (urlparse(requested_url).path or "/").rstrip("/")
    final_path = (urlparse(scrape.final_url).path or "/").rstrip("/")
    if req_path != "" and final_path == "":
        return ValidationVerdict.REDIRECTED_TO_HOME

    # 3. Soft-404 multi-signal
    soft = _detect_soft_404(scrape)
    if soft is not None:
        return soft

    return ValidationVerdict.VALID


def _detect_soft_404(scrape: ScrapeResult) -> Optional[ValidationVerdict]:
    if _URL_404_PATH_RE.search(scrape.final_url):
        return ValidationVerdict.SOFT_404

    try:
        soup = BeautifulSoup(scrape.html, "lxml")
        title = (soup.title.string if soup.title else "") or ""
        h1 = (soup.h1.get_text(strip=True) if soup.h1 else "") or ""
        visible_len = _visible_text_length(soup)
    except Exception:
        # Fail-open: if validator can't parse, let downstream pipeline judge.
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

### 3.3 Schema additions (`models/schemas.py`)

```python
# Existing method strings: 'langHtml', 'nlp_only', 'fetch_failed', 'challenge_page',
# 'error', 'Check_nok_forced', etc.

# New constants used in DetectionResponse.method:
HTTP_ERROR_METHOD = "http_error"
SOFT_404_METHOD = "soft_404"
REDIRECTED_TO_HOME_METHOD = "redirected_to_home"

class DetectionRequest(BaseModel):
    # ... existing fields
    homepage_fallback: bool = True       # NEW

class DetectionResponse(BaseModel):
    # ... existing fields
    analyzed_url: Optional[str] = None   # NEW: set when fallback fired or cross-URL cache HIT
```

### 3.4 `routes._detect_single_url` orchestration

Replaces the body of the existing function (lines 67-137). Adds two new branches: cache-HIT cross-URL detection (caveat 1 fix) and post-fetch validation + fallback hop. The exception envelope at the route level (lines 173-186 for `/detect`, 258-264 for batch items, 555-577 for debug) stays unchanged.

### 3.5 `domain_cache.set` signature

```python
async def set(
    self,
    url: str,
    effective_url: str,
    result: dict,
    ttl_override: Optional[int] = None,
) -> None:
    # If ttl_override provided, use it; else existing logic by result.ok / method.
    # Persist new field 'requested_url' = url in cached payload.
```

Cache value JSON gains `requested_url`. Old entries lack it; readers fall back to `effective_url` for the cross-URL HIT detection.

### 3.6 `scraper.scrape_html` migration

Currently returns `(html, final_url)` (or None). Capture `response.status` (already accessible at lines 525-554 area), wrap into `ScrapeResult`. Inner control flow + cleanup unchanged.

### 3.7 `redirect_tracker.fetch_html` migration

Return type `ScrapeResult | None`. Phase 1 retry + Phase 2 variant logic unchanged. All callers updated to use `.html` / `.final_url` instead of tuple unpacking.

### 3.8 Per-endpoint behavior

| Endpoint | Validate? | Homepage fallback? | New methods? |
|---|---|---|---|
| `/detect` | Yes | Yes (default ON, opt-out via `homepage_fallback=false`) | Yes |
| `/detect-batch` (mode=simple/complete) | Yes | Yes | Yes |
| `/detect-batch` (mode=first_match) | Yes | Per-item Yes | Yes |
| `/detect-debug` | Yes (in result, warning logged) | **OFF** | Yes |
| `/check-url` | N/A (no fetch) | N/A | N/A |

`/detect-batch` Pass 2 retry: `fetch_failed` + `challenge_page` retry as today. New methods (`http_error`, `soft_404`, `redirected_to_home`) **NOT retried** — definitive failures.

---

## Configuration

New env vars (in `app/core/config.py`):

| Variable | Default | Purpose |
|---|---|---|
| `INVALID_PAGE_DETECTION_ENABLED` | `true` | Master kill switch for validator |
| `HOMEPAGE_FALLBACK_ENABLED` | `true` | Master kill switch for homepage fallback |
| `SOFT_404_TITLE_THIN_THRESHOLD` | `2000` | Visible-text char limit when title regex matches |
| `SOFT_404_H1_THIN_THRESHOLD` | `1500` | Visible-text char limit when H1 regex matches |
| `INVALID_PAGE_TTL_HARD_S` | `604800` (7d) | Cache TTL for `http_error` + `redirected_to_home` |
| `INVALID_PAGE_TTL_SOFT_S` | `21600` (6h) | Cache TTL for `soft_404` |

Per-request flag on `DetectionRequest`:

- `homepage_fallback: bool = True` — caller-side opt-out per call.

---

## Error Handling

| Boundary | Behavior |
|---|---|
| `scrape_html` network/protocol error | Existing: returns None. ScrapeResult with `status_code=0` if Playwright returns no response. Validator treats `0` as unknown — falls through to soft-404 / redirect heuristics, does not trigger `http_error`. |
| `page_validator.validate` parsing crash | Try/except around BeautifulSoup ops. On error: log WARNING, return `VALID` (fail-open). Downstream pipeline retains its own safety nets. |
| `_detect_single_url` orchestration exception | Caught by existing route-level `try/except` → `method='error'`. Preserved. |
| Homepage fetch raises | Logged WARNING. Cache rejection with original verdict + 6h transient TTL. Return rejection. |
| `domain_cache.set` failure | Existing graceful degradation (Redis optional). TTL override doesn't change this. |

### Backward compat on cached entries

Old entries lack `requested_url`. Cross-URL HIT logic uses `cached.get("requested_url") or cached.get("url")` → safe degradation. New writes include the field. No migration / no Redis flush required.

### Logging

| Event | Level | Message |
|---|---|---|
| Validator returns non-`valid` | INFO | `[VALIDATE] {verdict} for {url} (status={code}, final={final_url})` |
| Homepage fallback fires | INFO | `[FALLBACK] {url} → homepage {homepage}` |
| Homepage fallback success | INFO | `[FALLBACK] OK {url} via {homepage}` |
| Homepage fallback also invalid | WARNING | `[FALLBACK] FAILED {url} (verdict={v}) and homepage {homepage} (verdict={hv})` |
| Cache HIT cross-URL | DEBUG | `[CACHE] HIT cross-URL {url} → analyzed_url={cached_url}` |
| Validator parse crash | WARNING | `[VALIDATE] parse error for {url}: {e} — fail-open as VALID` |

### Metrics (Prometheus, in `app/core/metrics.py`)

```python
VALIDATION_VERDICTS = Counter(
    "detection_validation_verdicts_total",
    "Page validation outcomes",
    ["verdict"],  # valid | http_error | soft_404 | redirected_to_home
)
HOMEPAGE_FALLBACK_TRIGGERED = Counter(
    "detection_homepage_fallback_triggered_total",
    "Homepage fallback fired",
    ["outcome"],  # success | rejected | network_failure
)
```

Exposed via existing `/metrics` endpoint. No new endpoint.

---

## Testing Strategy

### Unit + integration tests

| File | Coverage | Notes |
|---|---|---|
| `tests/test_page_validator.py` (NEW) | Pure validator. ~12-15 tests: hard 4XX/5XX boundaries; soft-404 by title+thin; soft-404 by H1+thin; soft-404 by URL path; redirect-to-home; valid pages near thresholds; parsing crash fail-open; multilingual title patterns (FR + EN). | Hand-crafted `ScrapeResult` instances. No I/O. |
| `tests/test_scraper.py` (MOD) | `scrape_html` returns ScrapeResult with status_code populated. ~2-3 new asserts; existing tests migrate from tuple unpacking. | TestRouteHandlerCleanup stays. |
| `tests/test_redirect_tracker.py` (NEW or MOD) | `fetch_html` ScrapeResult propagation through Phase 1 retry + Phase 2 variants. | Mock scraper. |
| `tests/test_routes.py` / `test_api.py` (MOD) | E2E: cache HIT same-URL, cache HIT cross-URL (analyzed_url set), valid path, http_error path, soft_404 + fallback success, soft_404 + fallback also invalid, redirected_to_home, homepage_fallback=False per-request, env kill switches. ~10 tests. | Mock fetch_html. |
| `tests/test_domain_cache.py` (NEW or MOD) | `ttl_override` honored; `requested_url` round-trip; old-entry forward compat. | Mock Redis. |

Total: ~30-35 new/modified tests.

TDD per task: red → green → refactor.

### Manual verification (post-deploy)

```
# Real 404 — fallback success
curl -X POST .../detect -d '{"url":"https://www.usinage-cn.fr/this-does-not-exist-xyz123"}'
# Expect: ok=true, analyzed_url="https://www.usinage-cn.fr/"

# Real 404 — fallback off
curl -X POST .../detect -d '{"url":"https://www.usinage-cn.fr/nope","homepage_fallback":false}'
# Expect: ok=false, method="http_error" or "soft_404"

# Soft-404 (Next.js default 404 page on a known site)
curl -X POST .../detect -d '{"url":"https://<known-nextjs-site>/random-bad-path"}'
# Expect: never ok=true on the original URL
```

Verify metrics:

```
curl /metrics | grep detection_validation_verdicts
curl /metrics | grep detection_homepage_fallback
```

---

## Rollout

| Phase | Action | Gate to next phase |
|---|---|---|
| **P1** | Land code with `INVALID_PAGE_DETECTION_ENABLED=false` + `HOMEPAGE_FALLBACK_ENABLED=false`. All existing behavior preserved. Tests green. | Merge to `features/poc`. |
| **P2** | Enable validation only (`INVALID_PAGE_DETECTION_ENABLED=true`, fallback still off). Observe 48h. Watch `validation_verdicts{verdict="soft_404"}` for false-positive spikes vs baseline `is_french=false` rate. | If soft-404 rate < 2% of total requests, proceed. |
| **P3** | Enable fallback (`HOMEPAGE_FALLBACK_ENABLED=true`). Observe `homepage_fallback_triggered{outcome="success"}` rate. | If success rate ≥ 30% of triggered, keep on. |
| **P4** | Lock defaults at `true` in `config.py`. Optionally drop kill-switch logic. | Done. |

Kill switch ensures rollback is env-only (no redeploy).

### Cache invalidation

No flush required. Stale `ok=True` entries for past-404 URLs naturally expire by TTL (max 30d). If urgent, targeted Redis flush per affected domain.

---

## Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Soft-404 heuristic rejects legit thin pages (bio pages, contact-only sites) | Medium | Multi-signal gate (title/H1 regex AND thin content). URL-segment signal alone is reliable (`/404` etc.). Threshold tunable via env. P2 phase observes FP rate before P3. |
| `<title>` matches "404" on legit articles (e.g., "What is a 404 error") | Low | Title alone never fires; needs title+thin (< 2000 chars) or H1+thin (< 1500 chars). Long-form articles exceed thresholds. |
| Homepage fallback masks data quality issues for callers expecting URL-level answers | Low | New `analyzed_url` field exposes the substitution. Per-request `homepage_fallback=false` gives strict mode. |
| Homepage fetch doubles latency per rejected URL | Medium | Inflight dedup coalesces concurrent homepage fetches. Domain cache absorbs subsequent calls (already domain-keyed). Net: amortized over batches. |
| Existing cached false positives (past 404s as ok=true) | High (existing) | Self-heal on TTL expiry (max 30d). Targeted flush available if a specific domain is reported. |
| `/detect-batch` first_match: per-item fallback could mask "no FR in group" semantics | Low | Per-item fallback to that item's homepage is per-URL, not per-group. Stop-at-first-FR semantic preserved. |
| ScrapeResult migration breaks any unknown caller of `scrape_html` | Low | Single-service file; only `fetch_html` calls it (verified by grep). Tests cover both call paths. |

---

## Open Questions

None.

---

## Appendix — Caveat 1 Fix Detail

Current cache HIT path (`routes.py` line 89-92) returns the cached payload as-is. With domain-keyed cache, a HIT for `/some/deep/path` may actually be the homepage's cached result (because earlier call seeded the key under the domain). Caller cannot tell.

Fix: when cached `requested_url` (or fallback `url` field) differs from the current call's URL, set `analyzed_url` on the response to the cached requested_url. Caller sees: "this answer came from a different URL on the same domain."

Pseudocode:

```python
cached = await domain_cache.get(url)
if cached:
    cached_req_url = cached.get("requested_url") or cached.get("url")
    if cached_req_url and cached_req_url != url:
        cached["analyzed_url"] = cached_req_url
    return DetectionResponse(**cached)
```
