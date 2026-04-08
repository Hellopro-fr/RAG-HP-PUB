# Design: robots.txt Total Block Detection & Bypass

**Date:** 2026-04-08 (revised 2026-04-09)
**Service:** crawler-service (Node.js crawler engine)
**Status:** Approved (v2 — multi-path detection)

## Problem

When a site's robots.txt contains a blanket block (`Disallow: *` for all user-agents), the crawler respects it and produces zero results. This manifests as a silent success (exit code 0, empty dataset) with no indication that the crawl was blocked. Since the crawler simulates `Googlebot` for robots.txt checks, any site blocking Googlebot triggers this.

**Important context:** The start URL itself is never checked against robots.txt — it is seeded directly into the request queue via `requestQueue.addRequest()`. Only child URLs discovered during link enumeration are filtered by `robots.isAllowed()` in `routes.ts:652-656`. This means even with `Disallow: *`, the start URL is fetched and processed, but no child URLs are enqueued.

## Decision

Detect the total block at startup (before crawling begins) using a **multi-path probe** and bypass robots.txt entirely for the crawl. The bypass is transparent to the caller — no webhook contract change, no manual intervention. A metadata flag (`robots_txt_bypassed: true`) is persisted for observability.

## Design

### Detection Logic

**Location:** `crawler/src/main.ts`, immediately after the existing `RobotsFile.find()` block (~line 454).

After robots.txt is fetched and parsed, probe multiple diverse paths to distinguish a blanket block from a selective one:

```
origin = new URL(startUrl).origin
probeUrls = [
    origin + "/",              // homepage
    origin + "/a",             // arbitrary top-level path
    origin + "/test/page",     // nested path
]

allBlocked = probeUrls.every(url => !robots.isAllowed(url, "Googlebot"))
```

- If `allBlocked === true`: blanket block detected (`Disallow: *` or `Disallow: /`)
  - Set `robots = undefined` — disables all subsequent `isAllowed()` checks
  - Set `robotsTxtBypassed = true` flag for metadata
  - Log: `"⚠️ robots.txt blanket block detected (all probe URLs blocked). Bypassing for this crawl."`
- If `allBlocked === false`: selective block — respect robots.txt normally (even if start URL is blocked)

### Why Multi-Path Probing

A single `isAllowed(startUrl)` check has a **false positive risk**: if the start URL is `/products/123` and robots.txt only blocks `/products/`, the check returns `false` even though the rest of the site is allowed. Probing diverse paths (`/`, `/a`, `/test/page`) ensures we only bypass when the block is truly blanket.

| robots.txt rule | `/` | `/a` | `/test/page` | `allBlocked` | Action |
|----------------|-----|------|--------------|-------------|--------|
| `Disallow: *` | blocked | blocked | blocked | `true` | Bypass |
| `Disallow: /` | blocked | blocked | blocked | `true` | Bypass |
| `Disallow: /products/` | allowed | allowed | allowed | `false` | Respect |
| `Disallow: /$` (homepage only) | blocked | allowed | allowed | `false` | Respect |
| `Allow: /` overriding `Disallow: *` | allowed | allowed | allowed | `false` | Respect |

### Why This Works

The existing URL filtering in `routes.ts:652-656` uses the pattern:
```typescript
if (robots && !robots.isAllowed(request.url, "Googlebot")) {
    // blocked
}
```

Setting `robots = undefined` makes this condition always `false` — blocked URLs are no longer filtered. No changes needed in `routes.ts`.

### Metadata Persistence

At crawl completion, include `robots_txt_bypassed: true` in `_callback_payload.json`. This field:
- Flows through the existing success webhook payload (additive — callers ignore unknown fields)
- Is visible via `GET /status/{crawl_id}` when reading the callback payload from disk
- Requires no Python-side changes

### Scope

**Modified files:**
- `crawler/src/main.ts` — bypass check after robots.txt fetch (~5 lines), flag in context
- `crawler/src/main.ts` or `crawler/src/functions.ts` — include flag in `_callback_payload.json`

**No changes to:**
- `routes.ts` — URL filtering naturally becomes a no-op
- Python orchestrator (`crawler_manager.py`, `router/crawler.py`) — no awareness needed
- Webhook contract — additive field only
- Circuit breaker, archiving, update mode — no interaction

### Edge Cases

| Case | Behavior |
|------|----------|
| robots.txt fetch fails (timeout/404) | `robots` is already `undefined` — bypass detection doesn't trigger. Crawl proceeds normally (existing behavior). |
| `Disallow: *` or `Disallow: /` (blanket block) | **Detected.** All probe URLs return `false` → bypass triggered. |
| `Disallow: /products/` (selective block) | **Not bypassed.** Probe URLs `/`, `/a`, `/test/page` return `true` → robots.txt respected normally. |
| `Disallow: /$` (homepage only) | **Not bypassed.** Only `/` is blocked; `/a` and `/test/page` return `true`. |
| `Disallow:` targeting specific user-agent only | **Detected** if it matches `Googlebot` (the user-agent we simulate) AND blocks all probe paths. |
| `Allow: /` overriding `Disallow: *` | **Not bypassed.** `isAllowed()` returns `true` for probe URLs. |
| Start URL blocked by selective rule (not blanket) | **Not bypassed.** Probe URLs reveal it's selective. Start URL is still fetched (no robots.txt check on seed). |
| robots.txt allows start URL but blocks child URLs | **Not detected.** This is a runtime pattern requiring a different approach (deferred to future extension). |

## Alternatives Considered

### B: Runtime detection (monitor blocked ratio during crawl)
- Track robots.txt-blocked URLs during crawling, disable if >90% blocked
- **Rejected:** Adds complexity (threshold tuning, mid-crawl state reset, re-enqueueing blocked URLs) for an edge case not currently experienced. Can be added later if needed.

### C: Both startup + runtime
- Combines A and B
- **Rejected:** Same reasoning as B — startup check covers the primary target (`Disallow: *`).

## Future Extensions

If the "gradual blocking" pattern (start URL allowed, most child URLs blocked) becomes a problem, add runtime detection:
- Track a `robots_blocked_count` in StatsManager
- After N processed URLs, check ratio of blocked vs. total discovered
- If ratio > threshold, disable robots.txt and re-enqueue blocked URLs
- This can be added independently without modifying the startup check