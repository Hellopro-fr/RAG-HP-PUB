# FR Implicit Winner When Homepage Is at Root — Design

**Date:** 2026-04-30
**Status:** Approved (pending implementation)
**Scope:** `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts`
**Related:** Follow-up to the FR detection validation hardening series (commits `e9f4df29` → `6d184e31`)

## Problem

When the homepage URL is at the site root (no locale prefix in the path), the current `computeExcludedRegionalPaths` logic treats every locale-shaped `alternative_url` returned by the detection API as a non-winning regional alternate and adds its path prefix to `excludedRegionalPaths`. The crawler then blocks every link under those prefixes at enqueue time.

For sites that serve their canonical French content under `/fr/`, this is a fatal misclassification:

- The homepage at `/` is just a landing page (often serving the same content as `/fr/`), but every other navigable URL on the site lives under `/fr/`.
- Hreflang on the homepage declares `<link hreflang="fr" href="/fr/">` to advertise the French variant.
- The detection API returns `/fr` as an alternative URL.
- `winnerPrefix = extractPathPrefix(homepageUrl)` evaluates to `null` (root has no first segment).
- `seedPrefix = extractPathPrefix(seedUrl)` is also `null`.
- `computeExcludedRegionalPaths` adds `/fr` to `excludedRegionalPaths` because it differs from both `winnerPrefix` and `seedPrefix`.
- Every `/fr/*` link gets dropped at `transformRequestFunction` as a "regional variant".
- The crawler discovers the homepage and nothing else.

### Concrete production case

`https://www.multimattp.com/` (crawl id 6066, 2026-04-30):

```
[REGIONAL_EXCLUSION] Excluded 1 regional paths: /fr
🚫 [regional-variant] https://www.multimattp.com/fr/119407-societe
🚫 [regional-variant] https://www.multimattp.com/fr/119428-occasions
... (all 16 internal links blocked)
```

Manual verification of the site:

- `/` and `/fr` serve the same content (French is the default locale).
- All non-homepage URLs require the `/fr/` prefix; without it they redirect back to `/`.
- The site also exposes other locales under `/de/`, `/en/`, etc.

The crawl returned only the homepage. No content was indexed.

## Design

### New rule

In `DetectionLangueClient.computeExcludedRegionalPaths`, when `winnerPrefix === null` AND `seedPrefix === null`:

1. Scan `alternativeUrls` for the first FR-shaped path prefix (`/^\/fr([-_][a-z]{2,4})?\/?$/i`).
2. Among FR-shaped candidates, prefer the one with the lowest `region_priority`. The contract is:
   - `0` = France (`fr-FR`)
   - `1` = generic (`/fr`)
   - `2` = other region (`fr-CA`, `fr-BE`, etc.)
   - undefined → treated as the worst priority (sorted last).
3. Treat that alternative's path prefix as the **implicit winner**.
4. Iterate all alternatives normally:
   - Skip if the alt's prefix equals the implicit winner's prefix (the new "winnerPrefix-like" gate).
   - Skip if the alt's prefix equals the original `seedPrefix` (already null here, no-op).
   - Reject prefixes that fail `isLocalePathPrefix` (existing belt-and-braces gate).
   - Add to `excluded` if not already present.
5. If no FR-shaped alternative is found → fall back to the existing logic (no implicit winner; every alt is processed against the original `winnerPrefix`/`seedPrefix`).

### When `winnerPrefix` or `seedPrefix` is non-null

Behavior is **unchanged**. The implicit-winner logic only activates when both are null.

### Signature

Unchanged. Caller-side code in `routes.ts` is not touched.

```ts
static computeExcludedRegionalPaths(
    alternativeUrls: AlternativeUrl[],
    winnerPrefix: string | null,
    seedPrefix: string | null,
): { excluded: string[]; rejected: { prefix: string; sourceUrl: string }[] }
```

### Logging

When the implicit-winner branch fires, emit a single `console.log` (or matching log style) noting the implicit winner and the source URL. This gives operators a paper trail when a crawl ends up with `excludedRegionalPaths=[]` despite alternatives being present.

The `rejected` field semantics (alts that failed the shape gate) are unchanged.

## Test matrix

| # | winnerPrefix | seedPrefix | alts (url, region_priority) | expected `excluded` | expected note |
|---|---|---|---|---|---|
| A | null | null | `[/fr]` (priority undef) | `[]` | implicit winner = `/fr` (multimattp.com case) |
| B | null | null | `[/fr, /de, /en]` (all undef) | `[/de, /en]` | implicit winner = `/fr` |
| C | null | null | `[/fr (1), /fr-FR (0), /fr-CA (2)]` | `[/fr, /fr-CA]` | priority 0 wins (`/fr-FR`) |
| D | null | null | `[/fr, /fr-CA]` (both undef) | `[/fr-CA]` | first FR wins when no priority data |
| E | null | null | `[/de, /en]` (no FR alt) | `[/de, /en]` | no implicit winner; current behavior |
| F | `/fr-FR` | null | `[/fr, /de]` | `[/fr, /de]` | unchanged when winnerPrefix non-null |
| G | null | null | `[]` | `[]` | empty alts, nothing to do |

The 9 existing cases for `computeExcludedRegionalPaths` must still pass.

## Out of scope

- Verifying that the API (`domain_fr.py::detect_alternative_languages`) returns non-FR locales (`/de`, `/en`, …) as `alternative_urls`. If the API filters to FR-only, non-FR variant URLs reach the crawler through normal navigation and are routed to `nfr-{domain}` per-page via the existing detection pipeline. That is functionally correct but wasteful; a future spec may broaden the API contract if production logs justify it.
- Migrating existing on-disk `{domain}.json` state. As before, the homepage handler overwrites `excludedRegionalPaths` on every crawl, so on-disk pollution self-heals on the next run.
- Changes to `routes.ts`, `main.ts`, or any other file. The fix is fully contained in `DetectionLangueClient.computeExcludedRegionalPaths`.

## Acceptance criteria

- multimattp.com crawl no longer drops `/fr/*` URLs.
- All 7 new test cases (A through G) pass.
- All 9 existing `computeExcludedRegionalPaths` cases still pass.
- Build clean (`npm run build`).
- No callers of `computeExcludedRegionalPaths` need to change.
