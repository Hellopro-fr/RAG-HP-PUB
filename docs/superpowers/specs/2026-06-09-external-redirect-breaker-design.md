# External-Redirect Breaker — Design

**Date:** 2026-06-09
**Service:** `crawler-service` (Node/TS crawler + Python orchestrator)
**Scope:** crawler-service only (`features/poc`). No Marketplace BO code change required.
**Status:** Approved (design)

## Problem

In **update mode**, a domain that has fully relocated (every URL `301`/`302`-redirects to a
*different* registrable domain) is crawled completely with no early-out, and is reported to BO
as a **successful** update that changed nothing.

### Current behavior (traced 2026-06-09)

For an update crawl (`crawlMode=update`, `previousCrawlId=N`) where all URLs redirect off-domain:

1. Phase 1 seeds the homepage; Phase 2 seeds all previous-dataset URLs
   (`main.ts:708-711`, `main.ts:1136-1184`).
2. Each seeded URL: Playwright/Camoufox auto-follows the redirect → `request.loadedUrl` lands on
   the new domain. The handler's external-redirect guard (`routes.ts:248-263`) computes
   `isInternal = hostname.includes(targetDomain) || hostname.includes(siteHostname)` = `false`,
   logs `"Blocked external redirect"`, and `return`s at `routes.ts:270`.
3. That `return` is **before** the `processed++` increment (`routes.ts:313`), **before** the
   circuit-breaker block (`routes.ts:317-354`), and **before** any `UpdateChecker.checkUrl`
   call (`routes.ts:688`, `routes.ts:920`). So:
   - `processed`, `redirects`, `errors` stay **0** → no rate breaker, no absolute breaker
     (`maxAbsRedirects=10`) can ever fire (the counters never move).
   - `UpdateChecker` never runs → empty diff (0 confirmed / 0 deleted / 0 redirected / 0 new).
4. Queue drains → `gracefulShutdown('COMPLETED', 2)` (`main.ts:1342`) → `process.exit(2)`.
5. Python: `is_success = (exit_code in (0, 2))` = `true` (`crawler_manager.py:1146`) →
   `final_status='finished'` (`crawler_manager.py:1200`) → **success webhook**, carrying only the
   advisory message `message_erreur_crawling = "L'URL après la page d'accueil change de domaine"`
   (set for the homepage at `routes.ts:268`).

### Two consequences

- **Wasted work:** a previous dataset of e.g. 5000 URLs ⇒ ~5001 full Camoufox navigations + ~5001
  paid Apify-proxy requests + ~50 min wall-clock (`perminute=100`), all discarded. No mechanism
  aborts early — the circuit breaker is *structurally blind* to external redirects because they
  return before any counter increments (even a non-zero `maxRedirectRate` would not help:
  `redirectRate = redirects(0)/processed(0)`).
- **Misleading success:** the relocated supplier site is reported `finished` (success). BO gets no
  failure signal; the only breadcrumb is a message string.

The catalog is *not* wiped by the crawler (empty diff is non-destructive), but the success signal
is misleading and the waste is real.

## Goal

In update mode, detect "all/most URLs redirect off-domain", **abort early**, and report a real
**failure** (`failure_cause='domain_changed'`) so BO can surface the moved supplier. Stop wasting
calls — ideally before seeding the previous dataset at all.

## Decisions (locked)

| Axis | Decision |
|---|---|
| Trigger shape | **Ratio + sample gate** — `external / (external + processed) ≥ rate`, after a min sample. |
| On trip | **Failure webhook** with `failure_cause='domain_changed'` (new exit code 7). |
| Scope | **Update mode only** (the breaker is already update-only — `main.ts:738`). |
| Homepage fast-path | **Yes** — homepage off-domain (request #1) aborts *before* Phase-2 seeding. |

## Mechanism

New **exit code 7** = "domain changed / all external redirects". The trigger lives entirely in the
`routes.ts:264` external-redirect guard, gated on update mode (`context.updateChecker`) **and** a
kill-switch (`circuitBreaker.externalRedirectBreakerEnabled`, default `true`). Two paths, one
terminal flow:

```
routes.ts guard  (!isInternal, update mode, breaker enabled)
   ├─ homepage fast-path:  request.url === site            → trip immediately
   └─ ratio breaker:       denom ≥ minSample AND
                           external/denom ≥ rate            → trip
        ↓ (trip)
   context.stopReason     = "domainChanged"
   context.crawlErrorMessage = (homepage path) "L'URL après la page d'accueil change de domaine"  [already set at routes.ts:268]
                             | (ratio path)    "Toutes les URLs redirigent vers un autre domaine (domaine changé)"
   context.fatalExitCode  = 7                    ← NEW context field
   await stopCrawler(crawler, ...)  → autoscaledPool.abort()
        ↓
   crawler.run() resolves → main.ts:1342
   await gracefulShutdown('COMPLETED', context.fatalExitCode ?? 2)   ← ONLY change at 1342
        ↓
   process.exit(7)
        ↓ (Python orchestrator)
   is_success = (7 in (0,2)) = false → final_status = 'failed'   (crawler_manager.py:1146,1200)
   _classify_exit_code(7) → ("Le domaine a changé …", "domain_changed")
        ↓
   FAILURE webhook to BO   (failure_cause = "domain_changed")
```

**Why `fatalExitCode` and not `gracefulShutdown` from routes.ts:** `gracefulShutdown` is a local
function in `main.ts`, not importable into `routes.ts`. The existing circuit breaker already aborts
from inside the handler via `stopReason` + `stopCrawler` and lands at `main.ts:1342` — but that path
hardcodes exit `2` (success). Adding `context.fatalExitCode` and reading it at `main.ts:1342`
(`?? 2`) lets a domain-change abort become a real failure while every other `stopCrawler` path
(`limitCrawl`, the existing `circuitBreaker` reasons, qm/diez limits) keeps exit 2 unchanged. This
reuses the proven in-handler `stopCrawler` flow — no new coupling.

### Trigger 1 — homepage fast-path

The homepage is seeded first (Phase 1) and its handler runs within seconds. When it lands
off-domain (`request.url === site` at `routes.ts:267`), trip immediately. Phase-2 seeding
(`seedPhase2`, fire-and-forget) is parked in its 120s `homepageReady` wait (`main.ts:1143-1145`)
and never resolves because the `homepageReady.resolve()` at `routes.ts:944` is *after* the line-270
return — so the process exits (code 7) long before the 120s timeout fires. **0 of N URLs seeded.**

### Trigger 2 — ratio breaker

For the rarer case where the homepage stays on-domain but the deep dataset URLs have moved:

- **numerator:** `external_redirects` — new StatsManager counter, incremented in the guard
  (update mode).
- **denominator:** `external_redirects + processed`.
- **sample gate:** `denom ≥ externalRedirectMinSample` (default **10**).
- **trip:** `external_redirects / denom ≥ maxExternalRedirectRate` (default **0.90**).

Result: ~10–50 URLs wasted instead of ~5000.

Its own small sample gate (10) — not the breaker's `minSample=50` — so it fires in both micro and
standard mode. Small relocated sites are anyway caught by the fast-path.

**Denominator note:** blocked-status throws (`routes.ts:305`) and content-type skips
(`routes.ts:283`) bypass both counters, so they are excluded from the denominator. This makes the
ratio slightly *more* sensitive, which is acceptable at a 0.90 threshold — a healthy update has
`processed ≫ external_redirects`, keeping the ratio near 0.

### Decision helper (testability)

The trip decision is a **pure function** so it can be unit-tested without Crawlee:

```ts
// crawler/src/externalRedirectBreaker.ts
export function shouldTripExternalRedirectBreaker(
    external: number,
    processed: number,
    cfg: { externalRedirectMinSample: number; maxExternalRedirectRate: number },
): { trip: boolean; reason: string }
```

The homepage fast-path is a separate, explicit `request.url === site` check in the guard (not part
of this function).

## Configuration

3 new fields on `context.config.circuitBreaker` (default in `context.ts`, built in
`main.ts:113-141`, parsed via `parseNumericArg` / boolean arg):

| Field | Default | CLI arg |
|---|---|---|
| `externalRedirectBreakerEnabled` | `true` | `--externalRedirectBreaker` |
| `maxExternalRedirectRate` | `0.90` | `--maxExternalRedirectRate` |
| `externalRedirectMinSample` | `10` | `--externalRedirectMinSample` |

BO does not pass these → `parseNumericArg` defaults apply. **Backward-compatible.** BO may pass them
later to tune per-domain. The kill-switch `externalRedirectBreakerEnabled=false` disables both
triggers (homepage fast-path + ratio breaker) if it ever misfires.

## Exit-code & failure_cause contract (additive)

| Exit code | `failure_cause` | Meaning |
|---|---|---|
| **7** (new) | `domain_changed` | Update crawl aborted: all/most URLs redirect off-domain. |

Python `_classify_exit_code` (`crawler_manager.py:309-331`):
- add `elif exit_code == 7: return ("Le domaine a changé : toutes les URLs redirigent vers un autre domaine", "domain_changed")`
- add `7` to the catch-all exclusion set (`crawler_manager.py:328`,
  `(0, 2, 3, 4, 5, 6, 7, -1, 137)`) so it is not mislabeled `unknown`.

`is_success = (exit_code in (0, 2))` stays unchanged ⇒ exit 7 routes to the **failure** webhook with
`failure_cause='domain_changed'` (informational; no BO code change — BO records the cause string and
could later branch on it to notify the supplier).

## Files touched

**Crawler (TypeScript):**
- `crawler/src/context.ts` — +3 `circuitBreaker` config fields, +`fatalExitCode` context field.
- `crawler/src/main.ts` — parse 3 CLI args + add to `circuitBreaker` config (`~113-141`); change
  `main.ts:1342` from `gracefulShutdown('COMPLETED', 2)` to
  `gracefulShutdown('COMPLETED', context.fatalExitCode ?? 2)`.
- `crawler/src/routes.ts` — in the `!isInternal` guard (`264-270`, update mode): increment
  `external_redirects`; homepage fast-path; ratio-breaker trip → set
  `stopReason`/`crawlErrorMessage`/`fatalExitCode=7` + `stopCrawler`.
- `crawler/src/externalRedirectBreaker.ts` (new) — pure `shouldTripExternalRedirectBreaker`.
- `crawler/src/externalRedirectBreaker.test.ts` (new) — unit tests.
- (optional) surface `external_redirects` in the callback payload via `readStat` (`main.ts:960-995`)
  for observability.

**Python:**
- `app/core/crawler_manager.py` — `_classify_exit_code` exit-7 branch + add 7 to the L328 set.
- test for `_classify_exit_code(7)`.

**Docs:**
- `apps-microservices/crawler-service/CLAUDE.md` — exit-code table + `failure_cause` vocabulary
  (7 / `domain_changed`).

## Testing

- **TS unit (`externalRedirectBreaker.test.ts`):** trip table — `(5000,0)`→trip, `(20,4980)`→no-trip
  (0.4%), `(9,1)`→no-trip (below sample gate 10), `(9,1)` at sample 10 with rate→boundary,
  `(90,10)`→trip (90%). Verify gate and rate boundaries.
- **Python (pytest):** `_classify_exit_code(7) == ("…", "domain_changed")`; 7 produces
  `is_success=False`.
- **Remote-only constraint:** no live crawl locally — verify with `npm run build` (tsc) for TS and
  `python -m pytest` + lint for Python.

## Risks / trade-offs

- **Homepage false-positive:** homepage redirects to a genuinely different registrable domain while
  product pages remain on-domain (rare; `isInternal` already tolerates `www`/apex variants). A false
  trip = false `failed`, but the catalog is preserved (failure ⇒ BO skips the empty diff).
  Mitigation: `externalRedirectBreakerEnabled=false` kill-switch.
- **Denominator caveat:** see above — conservative (more sensitive), acceptable at 0.90.
- **Scope:** initial-mode crawls unchanged. Initial-mode `external_redirects` observability is a
  deferred nice-to-have.

## Out of scope

- BO-side branching on `failure_cause='domain_changed'` (e.g. supplier-moved notification).
- The pre-existing error-rate breaker denominator quirk (blocked-status pages excluded from
  `processed`) — not introduced here, not fixed here.
- Initial (non-update) crawl coverage.
