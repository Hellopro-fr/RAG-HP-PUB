# Design: Regional Path Exclusion for Duplicate Prevention

**Date:** 2026-04-06
**Services:** `crawler-service`, `api-detection-langue-fr`
**Status:** Approved

## Problem

Multilingual sites (e.g., `manitou.com`) expose multiple French regional paths: `/fr-FR/`, `/fr/`, `/fr-BE/`, `/fr-CA/`, etc. These regional variants share identical or near-identical content. The crawler treats them as separate URLs, crawls all of them, and produces duplicate data in the RAG pipeline.

**Root cause:** The crawler uses `same-domain` link enqueuing with exact-string deduplication. Language switcher links on pages (e.g., `/fr-FR/products` linking to `/fr-BE/products`) get discovered and enqueued as separate URLs. Each variant passes French detection individually because they all have `<html lang="fr">`.

**Example:** For `manitou.com` seeded at `/fr-FR`, the detection API returns:

```json
{
  "ok": true,
  "url": "https://www.manitou.com/fr-FR",
  "method": "langHtml+nlp_confirmed",
  "alternative_urls": [
    { "url": "https://www.manitou.com/fr-FR", "method": "hreflang", "region_priority": 0 },
    { "url": "https://www.manitou.com/fr/", "method": "hreflang", "region_priority": 1 },
    { "url": "https://www.manitou.com/fr-BE", "method": "hreflang", "region_priority": 2 },
    { "url": "https://www.manitou.com/fr-CA", "method": "hreflang", "region_priority": 2 }
  ]
}
```

The winner is `/fr-FR`. The alternatives (`/fr/`, `/fr-BE`, `/fr-CA`, ...) are duplicate French paths that should not be crawled.

## Solution: Exclude Alternative Regional Paths

Use the `alternative_urls` from the homepage detection response to build an exclusion list. Apply it at two levels:

1. **Standard mode:** Block discovered URLs in `transformRequestFunction` before they enter the request queue.
2. **Update mode:** Two-phase seeding — process the homepage first to determine excluded paths, then seed remaining URLs from the previous crawl with filtering.

## Architecture

### Standard mode — filter at discovery time

```
Homepage detection (routes.ts, isMainSite block)
    |
    |  detectResult.ok=true + alternative_urls present
    |  Extract path prefixes from alternatives
    |  Exclude the winner URL's path prefix
    |
    v
context.excludedRegionalPaths = ["/fr", "/fr-BE", "/fr-CA", ...]
    |
    |  Every discovered URL passes through:
    v
transformRequestFunction (routes.ts)
    |
    |  URL path starts with an excluded prefix? --> return false (blocked)
    |
    v
Enqueued or rejected
```

### Update mode — two-phase seeding

```
Phase 1: Seed homepage only
    |
    v
Crawler processes homepage --> detection returns alternatives
    --> context.excludedRegionalPaths populated
    --> resolve homepageReady promise
    |
    v
Phase 2: Seed remaining URLs from previous crawl
    |
    |  For each URL from UrlConsolidator:
    |  Path matches excluded prefix? --> skip (not seeded)
    |  Otherwise --> addRequest to queue
    |
    v
Crawler processes remaining URLs (no excluded paths in queue)
    + transformRequestFunction still blocks newly discovered regional links
```

**Why two-phase seeding is necessary:** In update mode, URLs from the previous crawl are injected directly into the request queue via `requestQueue.addRequest()`, bypassing `transformRequestFunction` entirely. Without two-phase seeding, previously crawled regional variants (e.g., `/fr-BE/products`) would be re-fetched, pass French detection, and produce duplicates again.

**Timing coordination:** The homepage must complete detection before Phase 2 begins. This is achieved via a Promise stored in context (`homepageReady`), resolved by the homepage handler in routes.ts, awaited by the seeding loop in main.ts.

## Changes

### 1. context.ts — New fields

Add to the global crawler context:

```typescript
excludedRegionalPaths: [] as string[],
homepageReady: null as { resolve: () => void; promise: Promise<void> } | null
```

- `excludedRegionalPaths`: Array of path prefixes to exclude (e.g., `["/fr", "/fr-BE", "/fr-CA"]`). Populated once during homepage detection, read synchronously on every `transformRequestFunction` call.
- `homepageReady`: Promise-based signal for update mode two-phase seeding. Created in main.ts before crawl start (update mode only). Resolved by the homepage handler in routes.ts after storing excluded paths. Awaited by the Phase 2 seeding loop in main.ts.

### 2. routes.ts — Homepage detection (populate excluded paths)

When `detectResult.ok === true` and `detectResult.alternative_urls` has entries:

1. Parse the winning URL (`detectResult.url`) to extract its path prefix (first path segment).
2. For each entry in `alternative_urls`, extract its path prefix.
3. Store all prefixes **except the winner's** into `context.excludedRegionalPaths`.
4. Log the excluded paths for observability.

**Path prefix extraction:** Parse the URL, get the pathname, extract the first segment.
- `https://www.manitou.com/fr-FR` --> `/fr-FR`
- `https://www.manitou.com/fr/` --> `/fr`
- `https://www.manitou.com/fr-BE` --> `/fr-BE`

**Winner filtering:** The winner URL may appear in `alternative_urls` (as in the manitou.com example). It must be excluded from the exclusion list.

**Seed URL awareness:** Also compare against the seed URL path prefix. If the seed is `/fr-FR` and the winner is `/fr-FR`, both refer to the same allowed path.

### 3. routes.ts — transformRequestFunction (filter excluded paths)

Add a check after URL cleaning but before the dedup check. For each discovered URL:

1. Parse the URL pathname.
2. Check if the pathname starts with any excluded prefix followed by `/` or end-of-string.
3. If matched, log as `blocked: regional-variant` and return `false`.

**Matching rule:** A prefix `/fr-BE` matches `/fr-BE`, `/fr-BE/`, `/fr-BE/products/123`, but NOT `/fr-BEL/` or `/france/`. This is achieved by checking: `pathname === prefix || pathname.startsWith(prefix + "/")`.

**Performance:** Simple string comparison. The exclusion list is typically 5-20 entries. No regex, no async, no Redis.

**Critical constraint:** `transformRequestFunction` must be synchronous (Crawlee API contract). Path prefix matching is purely synchronous — no issue.

### 4. main.ts — Two-phase seeding for update mode

Restructure the update mode seeding (currently lines 622-641) into two phases:

**Before crawl start (update mode only):**
1. Create the `homepageReady` promise and store it in context.
2. Seed only the homepage URL into the request queue.
3. Start the crawler (it processes the homepage first).

**Phase 2 (runs concurrently with crawler, after homepage completes):**
1. `await context.homepageReady.promise` — blocks until homepage handler resolves it.
2. Iterate over all consolidated URLs from UrlConsolidator.
3. For each URL, extract its path prefix via `extractPathPrefix()`.
4. If the prefix matches any entry in `context.excludedRegionalPaths`, skip it (log as `skipped: regional-variant`).
5. Otherwise, add to the request queue as before (with source tracking and dedup).

**Standard mode:** No change. There is no pre-seeding — URLs are discovered during the crawl and filtered by `transformRequestFunction`.

**Safety:** If `homepageReady` is never resolved (e.g., homepage fails), add a timeout (e.g., 120s) after which Phase 2 proceeds without filtering. This prevents the crawl from stalling if the homepage encounters an error.

### 5. routes.ts — Resolve homepageReady after homepage detection

At the end of the homepage detection block (after storing `excludedRegionalPaths`), resolve the promise:

```typescript
if (context.homepageReady) {
    context.homepageReady.resolve();
}
```

This unblocks Phase 2 seeding in main.ts. The resolve must happen regardless of whether alternatives were found (an empty `excludedRegionalPaths` is valid — Phase 2 just seeds everything).

### 6. DetectionLangueClient.ts — Helper method

Add a static method to extract the first path segment from a URL:

```typescript
static extractPathPrefix(url: string): string | null
```

Returns the first path segment (e.g., `/fr-FR` from `https://example.com/fr-FR/page`), or `null` if the URL has no meaningful path (root `/`).

## Edge Cases

| Scenario | Behavior |
|---|---|
| Seed is `/fr-FR`, alternatives found | Exclude `/fr/`, `/fr-BE`, etc. Only `/fr-FR/**` is crawled |
| Seed is `/`, alternatives found | Same exclusion. Homepage links to `/fr-BE/` are blocked |
| No alternatives returned | `excludedRegionalPaths` stays empty. No filtering (current behavior) |
| Winner URL appears in `alternative_urls` | Filtered out when building exclusion list |
| URL like `/france/products` | Not matched by `/fr` prefix (requires `/fr/` or `/fr` at end) |
| Site with no regional paths | No alternatives detected, no exclusion, no change |
| Alternative on a different domain | Path extraction uses same-domain check; cross-domain alternatives are ignored |
| `detectResult.ok=false` with alternatives | Currently logged as error. Exclusion logic only fires on `ok=true` |
| Update mode, previous crawl has regional variants | Two-phase seeding filters them out before queue insertion |
| Update mode, homepage fails | `homepageReady` times out after 120s; Phase 2 seeds all URLs unfiltered (graceful degradation) |
| First crawl (no previous data) | Standard mode; no seeding; `transformRequestFunction` handles discovery filtering |

## Interaction with Other Features

- **Stored method (`langHtml`):** Orthogonal. The stored method validates language (via forced_method on internal pages). Regional exclusion validates path. Both operate independently.
- **DedupManager:** Unaffected. Regional URLs that slip through (if any) would still be deduplicated by exact URL match. The exclusion prevents them from being enqueued in the first place.
- **Update mode (UpdateChecker):** Handled via two-phase seeding. URLs from the previous crawl matching excluded paths are never seeded into the queue, so UpdateChecker never sees them. They silently disappear from the dataset — which is the correct behavior (they were duplicates). The `consolidationCounts.dataset` total (used for circuit breaker rate calculations) still reflects the previous crawl's full count, but this is acceptable since the circuit breaker uses it as a baseline denominator.
- **Session-based i18n (`languageQueryParam`):** Orthogonal. Query param propagation applies to URLs that pass the exclusion filter.
- **Circuit breaker:** Excluded URLs never enter the queue, so they don't increment any metrics. The `previousTotal` denominator may include excluded URLs from the previous crawl, making rate calculations slightly conservative (lower rates than actual). This is safe — it reduces false circuit breaker triggers, not increases them.

## Files to Modify

| File | Action | Description |
|---|---|---|
| `crawler-service/crawler/src/context.ts` | UPDATE | Add `excludedRegionalPaths` and `homepageReady` fields |
| `crawler-service/crawler/src/routes.ts` | UPDATE | Populate excluded paths on homepage detection; filter in transformRequestFunction; resolve `homepageReady` |
| `crawler-service/crawler/src/main.ts` | UPDATE | Two-phase seeding for update mode (create `homepageReady` promise, Phase 2 filtering loop) |
| `crawler-service/crawler/src/class/DetectionLangueClient.ts` | UPDATE | Add `extractPathPrefix()` static helper |
| `crawler-service/CLAUDE.md` | UPDATE | Document regional path filtering and two-phase update mode seeding |

## Known Limitations (Deferred)

### Query-based regional variants

Some sites use query parameters for regional targeting (e.g., `?lang=fr-FR` vs `?lang=fr-BE`) instead of path prefixes. The detection API can return these as alternatives (via `link_pattern`, `data_lang`, and `option_tag` methods). Path-prefix exclusion does not catch them because the path is identical — only the query differs.

**Why deferred:**
- Path-based is the dominant i18n URL pattern (WordPress WPML, Shopify, most CMS).
- Query-based regional variants (as opposed to a single `?lang=fr`) are rare in practice.
- The crawler's session-based i18n feature (`languageQueryParam`) already propagates a single `?lang=fr` to all discovered URLs, making multi-regional query params unlikely during a crawl.
- Adding query-param exclusion would require parsing query strings, matching specific parameter values, and handling parameter ordering — significant complexity for a rare case.

**When to address:** If a real-world crawl produces query-based regional duplicates, revisit. The fix would extend the exclusion matching to compare query parameters (e.g., strip `lang=fr-BE` variants when `lang=fr-FR` is the winner).

### Subdomain and TLD-based alternatives

Alternatives on different hostnames (e.g., `fr.example.com`, `example.fr`) are already blocked by the crawler's `same-domain` enqueue strategy. No action needed.

## Testing Strategy

- Unit test for `extractPathPrefix()` — various URL patterns
- Integration test: mock homepage detection with alternatives, verify excluded paths are populated
- Integration test: verify `transformRequestFunction` blocks URLs matching excluded prefixes
- Integration test: verify Phase 2 seeding skips URLs matching excluded prefixes (update mode)
- Integration test: verify `homepageReady` timeout triggers graceful degradation
- Manual verification: run a crawl on a site with known regional variants, confirm only the winner path is crawled
