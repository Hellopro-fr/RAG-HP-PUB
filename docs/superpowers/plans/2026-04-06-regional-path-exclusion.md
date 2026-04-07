# Regional Path Exclusion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent the crawler from crawling duplicate French regional paths (e.g., `/fr-BE/`, `/fr-CA/`) when one French path (e.g., `/fr-FR/`) has already been selected as the winner by the detection API.

**Architecture:** On homepage detection, extract path prefixes from `alternative_urls` and store them in context as excluded paths. In standard mode, `transformRequestFunction` blocks discovered links matching excluded prefixes. In update mode, two-phase seeding processes the homepage first (to learn excluded paths), then seeds remaining URLs from the previous crawl with path filtering.

**Tech Stack:** Node.js 22, TypeScript, Crawlee 3

**Spec:** `docs/superpowers/specs/2026-04-06-regional-path-exclusion-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `crawler/src/class/DetectionLangueClient.ts` | MODIFY | Add `extractPathPrefix()` static helper |
| `crawler/src/context.ts` | MODIFY | Add `excludedRegionalPaths` and `homepageReady` fields |
| `crawler/src/routes.ts` | MODIFY | Populate excluded paths on homepage detection; filter in `transformRequestFunction`; resolve `homepageReady` |
| `crawler/src/main.ts` | MODIFY | Two-phase seeding for update mode |
| `crawler/src/tests/test_regional_exclusion.ts` | CREATE | Unit tests for `extractPathPrefix()` and path matching |
| `CLAUDE.md` | MODIFY | Document regional path filtering |

All paths relative to `apps-microservices/crawler-service/`.

---

### Task 1: Add `extractPathPrefix()` to DetectionLangueClient

**Files:**
- Modify: `crawler/src/class/DetectionLangueClient.ts:155` (before closing brace)
- Create: `crawler/src/tests/test_regional_exclusion.ts`

- [ ] **Step 1: Create the test file with failing tests**

Create `crawler/src/tests/test_regional_exclusion.ts`:

```typescript
import { DetectionLangueClient } from "../class/DetectionLangueClient.js";

// --- extractPathPrefix tests ---

function testExtractPathPrefix() {
    const cases: [string, string | null, string][] = [
        ["https://www.manitou.com/fr-FR", "/fr-FR", "regional path"],
        ["https://www.manitou.com/fr-FR/", "/fr-FR", "regional path with trailing slash"],
        ["https://www.manitou.com/fr-FR/products/123", "/fr-FR", "deep path"],
        ["https://www.manitou.com/fr/", "/fr", "generic french path"],
        ["https://www.manitou.com/fr-BE", "/fr-BE", "other region"],
        ["https://www.manitou.com/", null, "root path"],
        ["https://www.manitou.com", null, "no path"],
        ["not-a-url", null, "invalid URL"],
    ];

    let passed = 0;
    let failed = 0;

    for (const [url, expected, label] of cases) {
        const result = DetectionLangueClient.extractPathPrefix(url);
        if (result === expected) {
            passed++;
        } else {
            console.error(`FAIL [${label}]: extractPathPrefix("${url}") = "${result}", expected "${expected}"`);
            failed++;
        }
    }

    console.log(`\nextractPathPrefix: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

testExtractPathPrefix();
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && npx tsx crawler/src/tests/test_regional_exclusion.ts`

Expected: FAIL with `DetectionLangueClient.extractPathPrefix is not a function`

- [ ] **Step 3: Implement `extractPathPrefix()`**

Add to `crawler/src/class/DetectionLangueClient.ts` before the closing `}` of the class (line 155):

```typescript
    /**
     * Extract the first path segment from a URL.
     * Used to identify regional path prefixes for exclusion filtering.
     *
     * e.g. "https://www.manitou.com/fr-FR/products" -> "/fr-FR"
     *      "https://www.manitou.com/fr/"             -> "/fr"
     *      "https://www.manitou.com/"                -> null (root)
     */
    static extractPathPrefix(url: string): string | null {
        try {
            const pathname = new URL(url).pathname;
            // Remove trailing slash, then extract first segment
            const cleaned = pathname.replace(/\/+$/, "");
            if (!cleaned || cleaned === "") return null;
            const firstSegment = cleaned.split("/").filter(Boolean)[0];
            return firstSegment ? `/${firstSegment}` : null;
        } catch {
            return null;
        }
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/crawler-service && npx tsx crawler/src/tests/test_regional_exclusion.ts`

Expected: `extractPathPrefix: 8 passed, 0 failed`

- [ ] **Step 5: Commit**

```bash
git add crawler/src/class/DetectionLangueClient.ts crawler/src/tests/test_regional_exclusion.ts
git commit -m "feat(crawler): add extractPathPrefix() helper for regional path exclusion"
```

---

### Task 2: Add `isExcludedRegionalPath()` helper and tests

**Files:**
- Modify: `crawler/src/class/DetectionLangueClient.ts`
- Modify: `crawler/src/tests/test_regional_exclusion.ts`

- [ ] **Step 1: Add path matching tests to test file**

Append to `crawler/src/tests/test_regional_exclusion.ts` before the final call:

```typescript
// --- isExcludedRegionalPath tests ---

function testIsExcludedRegionalPath() {
    const excluded = ["/fr", "/fr-BE", "/fr-CA"];

    const cases: [string, boolean, string][] = [
        ["https://www.manitou.com/fr-BE/products", true, "excluded prefix with subpath"],
        ["https://www.manitou.com/fr-BE", true, "excluded prefix exact"],
        ["https://www.manitou.com/fr-BE/", true, "excluded prefix with trailing slash"],
        ["https://www.manitou.com/fr/home", true, "excluded generic /fr/"],
        ["https://www.manitou.com/fr-FR/products", false, "allowed path (not excluded)"],
        ["https://www.manitou.com/france/products", false, "partial match must not trigger"],
        ["https://www.manitou.com/fr-BEL/products", false, "/fr-BEL != /fr-BE"],
        ["https://www.manitou.com/", false, "root path"],
        ["https://www.manitou.com/products", false, "unrelated path"],
    ];

    // Empty exclusion list should never match
    const emptyExcluded: string[] = [];

    let passed = 0;
    let failed = 0;

    for (const [url, expected, label] of cases) {
        const result = DetectionLangueClient.isExcludedRegionalPath(url, excluded);
        if (result === expected) {
            passed++;
        } else {
            console.error(`FAIL [${label}]: isExcludedRegionalPath("${url}") = ${result}, expected ${expected}`);
            failed++;
        }
    }

    // Empty list test
    const emptyResult = DetectionLangueClient.isExcludedRegionalPath("https://www.manitou.com/fr-BE/x", emptyExcluded);
    if (emptyResult === false) {
        passed++;
    } else {
        console.error("FAIL [empty list]: should return false with empty exclusion list");
        failed++;
    }

    console.log(`isExcludedRegionalPath: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
}

testIsExcludedRegionalPath();
```

Remove the old single `testExtractPathPrefix();` call at the bottom and replace with both:

```typescript
testExtractPathPrefix();
testIsExcludedRegionalPath();
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && npx tsx crawler/src/tests/test_regional_exclusion.ts`

Expected: FAIL with `DetectionLangueClient.isExcludedRegionalPath is not a function`

- [ ] **Step 3: Implement `isExcludedRegionalPath()`**

Add to `DetectionLangueClient.ts` after `extractPathPrefix()`:

```typescript
    /**
     * Check if a URL's path starts with any excluded regional prefix.
     * Matching rule: prefix must match exactly or be followed by "/".
     * e.g. prefix "/fr-BE" matches "/fr-BE", "/fr-BE/", "/fr-BE/products"
     *      but NOT "/fr-BEL/" or "/france/".
     */
    static isExcludedRegionalPath(url: string, excludedPrefixes: string[]): boolean {
        if (excludedPrefixes.length === 0) return false;
        try {
            const pathname = new URL(url).pathname;
            return excludedPrefixes.some(
                prefix => pathname === prefix || pathname.startsWith(prefix + "/")
            );
        } catch {
            return false;
        }
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/crawler-service && npx tsx crawler/src/tests/test_regional_exclusion.ts`

Expected: Both test suites pass.

- [ ] **Step 5: Commit**

```bash
git add crawler/src/class/DetectionLangueClient.ts crawler/src/tests/test_regional_exclusion.ts
git commit -m "feat(crawler): add isExcludedRegionalPath() for regional URL filtering"
```

---

### Task 3: Add context fields

**Files:**
- Modify: `crawler/src/context.ts`

- [ ] **Step 1: Add `excludedRegionalPaths` and `homepageReady` to context**

In `crawler/src/context.ts`, add two new fields before the closing `};` (after line 60, after `languageQueryParam`):

```typescript
    // Regional path prefixes to exclude (e.g., ["/fr", "/fr-BE", "/fr-CA"]).
    // Populated from alternative_urls during homepage detection.
    // Read by transformRequestFunction to block discovered regional variant links.
    excludedRegionalPaths: [] as string[],
    // Promise-based signal for update mode two-phase seeding.
    // Created in main.ts (update mode only). Resolved by homepage handler in routes.ts
    // after storing excludedRegionalPaths. Awaited by Phase 2 seeding in main.ts.
    homepageReady: null as { resolve: () => void; promise: Promise<void> } | null
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd apps-microservices/crawler-service/crawler && npx tsc --noEmit`

Expected: No errors (or only pre-existing errors unrelated to context.ts).

- [ ] **Step 3: Commit**

```bash
git add crawler/src/context.ts
git commit -m "feat(crawler): add excludedRegionalPaths and homepageReady context fields"
```

---

### Task 4: Populate excluded paths during homepage detection

**Files:**
- Modify: `crawler/src/routes.ts:394-414` (homepage detection success block)
- Modify: `crawler/src/routes.ts:451-455` (end of homepage block — resolve homepageReady)

- [ ] **Step 1: Add excluded path extraction after homepage detection succeeds**

In `crawler/src/routes.ts`, after line 413 (`isEnqueuingLinks = true;`) and before the closing `}` of the `if (detectResult.ok)` block, add:

```typescript
                            // Regional path exclusion: extract alternative paths to exclude
                            if (detectResult.alternative_urls && detectResult.alternative_urls.length > 0) {
                                const winnerPrefix = DetectionLangueClient.extractPathPrefix(detectResult.url || url);
                                const seedPrefix = DetectionLangueClient.extractPathPrefix(site);

                                const excluded: string[] = [];
                                for (const alt of detectResult.alternative_urls) {
                                    const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
                                    if (altPrefix && altPrefix !== winnerPrefix && altPrefix !== seedPrefix) {
                                        if (!excluded.includes(altPrefix)) {
                                            excluded.push(altPrefix);
                                        }
                                    }
                                }

                                if (excluded.length > 0) {
                                    context.excludedRegionalPaths = excluded;
                                    log.info(`[REGIONAL_EXCLUSION] Excluded ${excluded.length} regional paths: ${excluded.join(", ")}`);
                                }
                            }
```

- [ ] **Step 2: Resolve `homepageReady` at the end of the homepage block**

In `crawler/src/routes.ts`, find the end of the `try { ... } catch (apiError)` block that wraps the homepage detection (after the catch at line 454). Add right after this catch block, before the `} else {` that starts the internal page logic (line 456):

```typescript
                // Signal that homepage detection is complete (for update mode two-phase seeding)
                if (context.homepageReady) {
                    context.homepageReady.resolve();
                }
```

This must execute regardless of whether detection succeeded or failed, so it goes after the try/catch, not inside the success branch.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd apps-microservices/crawler-service/crawler && npx tsc --noEmit`

Expected: No errors related to the changes.

- [ ] **Step 4: Commit**

```bash
git add crawler/src/routes.ts
git commit -m "feat(crawler): populate excludedRegionalPaths from homepage alternative_urls"
```

---

### Task 5: Filter excluded paths in `transformRequestFunction`

**Files:**
- Modify: `crawler/src/routes.ts:710-717` (after external domain check, before dedup check)

- [ ] **Step 1: Add regional path filtering in transformRequestFunction**

In `crawler/src/routes.ts`, inside the `transformRequestFunction`, after the external domain check block (after line 717 `return false;` / `}`) and before the pre-crawl dedup check (line 724 `if (knownUrlsOnPage.has(request.url))`), add:

```typescript
                            // Regional variant exclusion: block links to excluded regional paths
                            if (context.excludedRegionalPaths.length > 0 &&
                                DetectionLangueClient.isExcludedRegionalPath(request.url, context.excludedRegionalPaths)) {
                                logBlocked('regional-variant', request.url);
                                return false;
                            }
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd apps-microservices/crawler-service/crawler && npx tsc --noEmit`

Expected: No errors related to the changes.

- [ ] **Step 3: Commit**

```bash
git add crawler/src/routes.ts
git commit -m "feat(crawler): filter excluded regional paths in transformRequestFunction"
```

---

### Task 6: Two-phase seeding for update mode

**Files:**
- Modify: `crawler/src/main.ts:587-665` (update mode seeding block)

- [ ] **Step 1: Create `homepageReady` promise and split seeding into two phases**

In `crawler/src/main.ts`, replace the seeding block (lines 622-641) with two-phase seeding. The key changes:

1. Before crawl start, create the `homepageReady` promise.
2. Seed only the homepage URL first.
3. Start the crawler.
4. After the crawler starts, await `homepageReady` (with timeout), then seed remaining URLs with filtering.

Find the current seeding block starting at line 622 (`// Seed the request queue with ALL consolidated URLs`). Replace lines 622-641 with:

```typescript
    // --- TWO-PHASE SEEDING (Regional Path Exclusion) ---
    // Phase 1: Seed only the homepage so it gets processed first.
    // The homepage handler populates context.excludedRegionalPaths from alternative_urls.
    // Phase 2: After homepage completes, seed remaining URLs with path filtering.

    // Create the homepageReady signal (resolved by homepage handler in routes.ts)
    let resolveHomepage: () => void;
    const homepagePromise = new Promise<void>((resolve) => { resolveHomepage = resolve; });
    context.homepageReady = { resolve: resolveHomepage!, promise: homepagePromise };

    // Phase 1: Seed only the homepage
    await requestQueue.addRequest({
        url: site,
        userData: { source: 'seed' }
    });
    if (context.dedupManager) {
        await context.dedupManager.addUrl(site);
    }

    // Collect remaining URLs for Phase 2 (all consolidated URLs except the homepage)
    const remainingUrls: { url: string; source: string }[] = [];
    for await (const { url: consolidatedUrl, source } of allUrls) {
        if (consolidatedUrl === site) continue; // Already seeded as homepage
        remainingUrls.push({ url: consolidatedUrl, source });
    }

    // Phase 2 runs AFTER the crawler starts (see below).
    // The crawler processes the homepage, which resolves homepageReady,
    // then we seed remaining URLs with regional path filtering.
```

Then, find where the crawler is started (search for `await crawler.run()` or the crawler start call). The Phase 2 seeding should run concurrently with the crawler. Add this logic right BEFORE `await crawler.run()`:

```typescript
    // Phase 2: Seed remaining URLs after homepage completes (runs concurrently with crawler)
    const seedPhase2 = async () => {
        // Wait for homepage detection to complete (with 120s safety timeout)
        const HOMEPAGE_TIMEOUT_MS = 120_000;
        const timeout = new Promise<void>((resolve) => setTimeout(resolve, HOMEPAGE_TIMEOUT_MS));
        await Promise.race([context.homepageReady!.promise, timeout]);

        const excluded = context.excludedRegionalPaths;
        if (excluded.length > 0) {
            console.log(`[PHASE 2] Homepage detected ${excluded.length} excluded regional paths: ${excluded.join(", ")}`);
        } else {
            console.log(`[PHASE 2] No regional paths to exclude. Seeding all URLs.`);
        }

        let seedCount = 0;
        let skippedCount = 0;
        for (const { url, source } of remainingUrls) {
            // Filter out excluded regional paths
            if (excluded.length > 0 && DetectionLangueClient.isExcludedRegionalPath(url, excluded)) {
                skippedCount++;
                continue;
            }

            if (context.dedupManager) {
                await context.dedupManager.addUrl(url);
            }
            await requestQueue.addRequest({
                url: url,
                userData: { source: source }
            });
            seedCount++;
            if (seedCount % 1000 === 0) {
                console.log(`[PHASE 2] Seeded ${seedCount} URLs...`);
            }
        }
        console.log(`[PHASE 2] Finished seeding ${seedCount} URLs (${skippedCount} excluded as regional variants).`);
    };

    // Launch Phase 2 concurrently (don't await — it runs alongside the crawler)
    seedPhase2().catch(err => console.error(`[PHASE 2] Error during seeding: ${err.message}`));
```

Also update the `seedCount` variable and the logging/safety check after the old seeding loop. The safety check (`if (seedCount === 0)`) needs adjustment — it should check `remainingUrls.length + 1` (homepage) instead, since Phase 2 hasn't completed yet at this point:

Replace lines 642-648 with:

```typescript
    const totalConsolidated = remainingUrls.length + 1; // +1 for homepage
    console.log(`Consolidated ${totalConsolidated} URLs from ${consolidationCounts.dataset} Dataset + ${consolidationCounts.requestQueue} RQ + ${consolidationCounts.requestUrl} RU.`);

    if (totalConsolidated === 0) {
        console.error(`❌ Update mode produced 0 URLs from previous crawl '${previousCrawlId}'. No data to compare against. Aborting.`);
        process.exit(4);
    }
```

- [ ] **Step 2: Add import for `DetectionLangueClient` in main.ts**

At the top of `main.ts`, add (if not already imported):

```typescript
import { DetectionLangueClient } from "./class/DetectionLangueClient.js";
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd apps-microservices/crawler-service/crawler && npx tsc --noEmit`

Expected: No errors related to the changes.

- [ ] **Step 4: Commit**

```bash
git add crawler/src/main.ts
git commit -m "feat(crawler): two-phase seeding for update mode regional path exclusion"
```

---

### Task 7: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (crawler-service root)

- [ ] **Step 1: Add regional path exclusion documentation**

In `apps-microservices/crawler-service/CLAUDE.md`, add a new section after "Update Mode" and before "Archiving — GCS Fallback":

```markdown
## Regional Path Exclusion

Prevents crawling duplicate French regional variants (e.g., `/fr-BE/`, `/fr-CA/`) when one French path (e.g., `/fr-FR/`) has been selected.

**How it works:**
1. Homepage detection (mode `"complete"`) returns `alternative_urls` with all French regional variants found via hreflang tags.
2. The crawler extracts path prefixes from alternatives, excludes the winner's prefix, and stores the rest in `context.excludedRegionalPaths`.
3. In **standard mode**, `transformRequestFunction` blocks discovered links matching excluded prefixes.
4. In **update mode**, two-phase seeding processes the homepage first, then seeds remaining URLs from the previous crawl with path filtering.

**Key files:** `context.ts` (fields), `routes.ts` (population + filtering), `main.ts` (two-phase seeding), `DetectionLangueClient.ts` (helpers).

**Limitation:** Only path-based regional variants are filtered. Query-based variants (`?lang=fr-BE`) are not handled (deferred — see spec).
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(crawler): document regional path exclusion feature"
```

---

### Task 8: Run full test suite and final verification

- [ ] **Step 1: Run all regional exclusion tests**

Run: `cd apps-microservices/crawler-service && npx tsx crawler/src/tests/test_regional_exclusion.ts`

Expected: All tests pass.

- [ ] **Step 2: Run TypeScript compilation check**

Run: `cd apps-microservices/crawler-service/crawler && npx tsc --noEmit`

Expected: No errors introduced by the changes.

- [ ] **Step 3: Build the crawler**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`

Expected: Build succeeds.

- [ ] **Step 4: Final commit with all changes verified**

If any uncommitted fixes were needed, commit them:

```bash
git add -A
git commit -m "chore(crawler): final verification for regional path exclusion"
```