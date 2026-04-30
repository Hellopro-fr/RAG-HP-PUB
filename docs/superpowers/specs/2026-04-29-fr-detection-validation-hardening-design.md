# French Detection Validation Hardening — Design

**Date:** 2026-04-29
**Status:** Proposed
**Scope:** `crawler-service` (Node.js/TypeScript) + `api-detection-langue-fr` (Python)

## Problem

Two production incidents revealed structural weaknesses in the French detection pipeline.

### Case 1 — Non-FR URL contaminating main dataset (aera-sa.fr)

Crawl of `aera-sa.fr` (stored method: `langHtml`) produced main-dataset entry for `https://www.aera-sa.fr/de/2022/12/16/all4pack-2022/` whose HTML clearly declares `<html lang="de-DE">` (German content).

**Trace:**
1. Internal page validation in `routes.ts` calls `detectionClient.detect(url, content, { forcedMethod: "langHtml", useNlpDetection: false })`.
2. API correctly rejects: `lang="de-DE"` → `value="de"` ≠ `"fr"` → returns `ok=false, method="Check_nok_forced"`.
3. Crawler fallback at `routes.ts:573-581` calls `detectionClient.checkUrl(url)`.
4. `https://www.aera-sa.fr/de/...` has `.fr` TLD → `checkUrl` returns `ok=true, method="direct_match"`.
5. Crawler accepts the page (`isEnqueuingLinks = true`) → routed to main dataset.

**Root cause:** the URL fallback runs after a *clean* HTML rejection. Forced detect already analyzed the HTML lang attribute; the URL TLD signal is weaker evidence and cannot legitimately override it. The original purpose of the fallback was to recover from API technical failures — but those are already handled by the surrounding `try/catch`.

### Case 2 — Content paths excluded as regional FR variants (jaunin.com)

`storage/miscellaneous/jaunin.com/jaunin.com.json` contains:

```json
{
  "method": "langHtml",
  "excludedPaths": ["/nos-realisations", "/l-entreprise", "/nos-actualites"]
}
```

These are content-section paths, not language regions. Their presence in `excludedPaths` causes `transformRequestFunction` to filter out every URL under those sections — large amount of missing crawl data.

**Trace:**
1. Homepage detection in `routes.ts:419-440` populates `context.excludedRegionalPaths` from `detectResult.alternative_urls`.
2. The API's `detect_alternative_languages` (in `domain_fr.py`) trusts every `<link hreflang="fr*" href="X">` declaration regardless of the shape of `X` (lines 678-685).
3. jaunin.com's HTML contains malformed hreflang tags pointing to content sections (e.g., `<link hreflang="fr-FR" href="/nos-realisations">`).
4. API returns those paths as French alternatives → crawler extracts path prefixes blindly via `extractPathPrefix` → adds them to `excludedRegionalPaths` → persisted to disk.

**Root cause (two layers):**
- API: hreflang/data-lang declarations on same-host paths are accepted without validating that the path is language-shaped.
- Crawler: no validation that an extracted prefix actually represents a language region.

## Goals

- Prevent non-French pages from entering the main dataset on `.fr` (or any TLD/path/query-French) sites when the page's actual content is non-French.
- Prevent content sections from being mistakenly excluded as regional language variants.
- Preserve self-healing behavior in update mode — bogus URLs from previous crawls get rejected on re-validation and removed from the dataset over one update cycle.

## Non-Goals

- Pre-filter previously-discovered bogus URLs at update-mode seed time. Self-healing in one cycle is acceptable; static deny lists for non-FR language paths add maintenance cost and false-positive risk for sites whose `/en/` section is in fact French.
- Migrate existing on-disk `{domain}.json` files. Homepage detection runs every crawl and overwrites the file with current `context.excludedRegionalPaths` — files self-clean on next run.
- Change behavior for NLP-validated methods (already correct).

## Solution Overview

Three changes across the two services:

1. **Crawler — drop URL fallback after clean HTML rejection.** Forced detect verdict on HTML lang attribute is authoritative.
2. **API — validate hreflang/data-lang/option_tag target URLs.** Same-host targets must point to a language-shaped path; cross-host targets remain trusted.
3. **Crawler — validate alt path prefix shape before exclusion.** Belt-and-braces against future API regression and other consumers.

## Detailed Design

### Change 1 — Crawler: drop URL fallback (Case 1)

**File:** `apps-microservices/crawler-service/crawler/src/routes.ts`
**Lines:** 571-581

**Current:**
```typescript
if (detectResult.ok) {
    isEnqueuingLinks = true;
} else if (!needsNlp) {
    // Fallback: URL-only check (no method match required).
    const checkUrlResult = await detectionClient.checkUrl(url);
    if (checkUrlResult.ok) {
        isEnqueuingLinks = true;
    }
}
```

**New:**
```typescript
if (detectResult.ok) {
    isEnqueuingLinks = true;
}
// No URL fallback. The forced HTML detect already analyzed the lang attribute;
// URL TLD/path signals cannot override a clean rejection. API technical
// failures are handled by the surrounding try/catch.
```

**Effect:**
- Pages that fail forced HTML detect go to `nfr-{domain}` dataset (existing branch at routes.ts ~666).
- API technical failures (network, 5xx after retries) raise → caught by `catch (apiError)` at line 582 → `isEnqueuingLinks` remains `false` → same as before.

### Change 2 — API: validate hreflang/data-lang target URLs (Case 2)

**File:** `apps-microservices/api-detection-langue-fr/app/core/domain_fr.py`

#### 2a. Add helper `_is_valid_language_alternative`

Insert as a `@staticmethod` on `DomainFR`, near the existing `_check_base_domain` helper:

```python
@staticmethod
def _is_valid_language_alternative(homepage_host: str, target_url: str) -> bool:
    """
    Validate that an hreflang/data-lang target URL looks like a language alternative.

    Cross-host targets (different hostname than homepage) are trusted unconditionally —
    webmasters legitimately declare external French sites via hreflang.

    Same-host targets must have a language-shaped first path segment, e.g.:
      /fr, /fr-be, /fr_ca, /french, /francais, /français, /france
    Anything else (e.g. /nos-realisations, /l-entreprise) is rejected as a webmaster
    error or non-language declaration.

    Returns:
        True if target should be accepted as a French alternative candidate.
    """
    try:
        parsed = urlparse(target_url)
        target_host = (parsed.hostname or '').lower()
        if target_host and target_host != homepage_host:
            return True
        segments = [s for s in parsed.path.split('/') if s]
        if not segments:
            return False
        first = segments[0].lower()
        return bool(re.match(
            r'^(fr|fr-[a-z]{2}|fr_[a-z]{2}|french|francais|français|france)$',
            first
        ))
    except Exception:
        return False
```

#### 2b. Apply gate on hreflang detection

**Lines:** 678-685 (Method 1: hreflang)

**Before `_add_trusted` call:**
```python
for regex in [re.compile(r'^fr', re.IGNORECASE), re.compile(r'fr', re.IGNORECASE)]:
    for link in soup.find_all(attrs={'hreflang': regex}):
        href = link.get('href')
        hreflang_val = link.get('hreflang', '')
        if href and href != '#':
            resolved = self.resolve_url(self.homepage, href)
            if resolved and not self._is_self_url(resolved):
                if not self._is_valid_language_alternative(homepage_host, resolved):
                    continue  # Skip same-host non-language-shaped paths
                _add_trusted(resolved, 'hreflang', hreflang_value=hreflang_val)
```

#### 2c. Apply gate on data-lang/data-gt-lang detection

**Lines:** 687-697 (Method 2: data-lang attributes)

**Before `_queue_candidate` call:**
```python
for attr_name in ['data-lang', 'data-gt-lang']:
    method_name = attr_name.replace('-', '_')
    for regex in [re.compile(r'^fr', re.IGNORECASE), re.compile(r'fr', re.IGNORECASE)]:
        for elem in soup.find_all(attrs={attr_name: regex}):
            href = elem.get('href')
            lang_val = elem.get(attr_name, '')
            if href and href != '#':
                resolved = _resolve_and_check(href)
                if resolved:
                    if not self._is_valid_language_alternative(homepage_host, resolved):
                        continue
                    _queue_candidate(resolved, href, method_name, hreflang_value=lang_val)
```

#### 2d. NOT applied to `link_pattern` (lines 700-708)

The `link_pattern` method already requires a path-shape match via the regex `r'/(fr|fr-fr|fr_fr)(/|$)|lang=fr'`. It cannot produce false positives like jaunin.com's content paths. Leaving as-is preserves existing coverage for sites without explicit hreflang declarations.

#### 2e. NOT applied to `option_tag` and Methods 5/6 (cross-domain `.fr` and FR subdomain)

These already perform shape/domain validation by construction. Adding the gate is redundant.

### Change 3 — Crawler: validate alt prefix shape (Case 2 belt-and-braces)

**File:** `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts`

**Add static helper:**
```typescript
/**
 * Returns true if path prefix looks like a French regional variant.
 * Accepted shapes: /fr, /fr-XX, /fr_XX, /french, /francais, /français, /france
 * Used to validate that prefixes added to excludedRegionalPaths are actual
 * language regions, not content sections (e.g. /nos-realisations).
 */
static isFrenchRegionalPathPrefix(prefix: string): boolean {
    if (!prefix || !prefix.startsWith("/")) return false;
    const segment = prefix.slice(1).toLowerCase();
    return /^(fr|fr-[a-z]{2}|fr_[a-z]{2}|french|francais|français|france)$/.test(segment);
}
```

**File:** `apps-microservices/crawler-service/crawler/src/routes.ts`
**Lines:** 423-431

**Current:**
```typescript
const excluded: string[] = [];
for (const alt of detectResult.alternative_urls) {
    const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
    if (altPrefix && altPrefix !== winnerPrefix && altPrefix !== seedPrefix) {
        if (!excluded.includes(altPrefix)) {
            excluded.push(altPrefix);
        }
    }
}
```

**New:**
```typescript
const excluded: string[] = [];
for (const alt of detectResult.alternative_urls) {
    const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
    if (altPrefix
        && altPrefix !== winnerPrefix
        && altPrefix !== seedPrefix
        && DetectionLangueClient.isFrenchRegionalPathPrefix(altPrefix)) {
        if (!excluded.includes(altPrefix)) {
            excluded.push(altPrefix);
        }
    }
}
```

## Tests

### API tests (`tests/test_domain_fr.py`)

Add unit tests for `_is_valid_language_alternative`:

| Input (homepage_host, target_url) | Expected |
|---|---|
| `("example.com", "https://example.com/fr/products")` | True |
| `("example.com", "https://example.com/fr-BE/products")` | True |
| `("example.com", "https://example.com/fr_CA/products")` | True |
| `("example.com", "https://example.fr/products")` | True (cross-host) |
| `("example.com", "https://fr.example.com/products")` | True (cross-host) |
| `("example.com", "https://example.com/nos-realisations")` | False |
| `("example.com", "https://example.com/products")` | False |
| `("example.com", "https://example.com/")` | False |
| `("example.com", "https://example.com/de/products")` | False |
| `("example.com", "not-a-url")` | False |

Add integration test: HTML containing `<link rel="alternate" hreflang="fr-FR" href="/nos-realisations">` produces empty `alternative_urls`.

### Crawler tests (`crawler/src/tests/test_detection_langue_client.ts`)

Add unit tests for `isFrenchRegionalPathPrefix`:

| Input | Expected |
|---|---|
| `/fr` | True |
| `/fr-BE` | True |
| `/fr_CA` | True |
| `/french` | True |
| `/francais` | True |
| `/nos-realisations` | False |
| `/de` | False |
| `/products` | False |
| `fr` (no leading slash) | False |
| `` | False |
| `/` | False |

### Crawler integration test (deferred)

End-to-end test of `routes.ts` internal-page validation requires mocking the detection client and Playwright page. Tracked separately; the unit-test coverage above and the existing API test for `/de/` rejection cover the critical path.

## Migration

None required.

- `{domain}.json` files: overwritten on every homepage detection (`functions.ts:1843` writes). After deployment, the next crawl of any affected domain produces a clean file.
- Update mode: `copyPreviousFrenchDetectionMethod` (`functions.ts:1145`) loads the previous file briefly, but homepage detection runs in Phase 1 (before Phase 2 seeding) and overwrites `context.excludedRegionalPaths` with the new clean state. Self-healing within a single update cycle.
- Bogus URLs in previous crawl datasets (e.g., `/de/...` for aera-sa.fr): re-seeded once in update mode, fetched, rejected by Change 1, marked as deleted by `UpdateChecker`, removed from dataset. Self-healing within one update cycle. Wasted bandwidth is bounded by the count of bogus URLs in the previous crawl — acceptable trade-off vs. the maintenance cost of a non-FR language deny list.

## Rollout

1. Deploy API change (Change 2) first. No callers depend on bogus alternative URLs being returned; the contract narrows safely.
2. Deploy crawler changes (Changes 1 and 3) in the same release. They're independent of each other but both depend on the API delivering correct alternatives for full effect.
3. No feature flag needed — both fixes are bug-correcting and low-risk.

## Risks and Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Change 1 rejects pages that were correctly French but had broken HTML lang attr | Low | The same forced-detect logic was already running; we're only removing the URL fallback that masked rejections. If it was rejecting before, it was rejecting wrongly. |
| Change 2 rejects legitimate same-host hreflang declarations whose href has unusual shape | Very low | Webmasters who declare `hreflang="fr-FR"` on a same-host page conventionally use a language-shaped path (`/fr/`). Sites with non-standard layouts can still be detected via NLP / HTML lang / cross-host hreflang / `link_pattern`. |
| Change 3 prevents storing legitimate FR regional prefix that doesn't fit the regex | Low | Regex covers `fr`, `fr-XX`, `fr_XX`, `french`, `francais`, `français`, `france` — all known shapes. New shapes can be added later if discovered. |

## Open Questions

None.
