# robots.txt Total Block Detection & Bypass — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect blanket robots.txt blocks (`Disallow: *`) at startup and transparently bypass them so crawls produce results instead of silently failing.

**Architecture:** After fetching robots.txt, probe 3 diverse URLs against `isAllowed()`. If all are blocked, set `robots = undefined` to disable filtering and persist a `robots_txt_bypassed` flag in the callback payload for observability. No Python-side changes needed.

**Tech Stack:** TypeScript / Crawlee / Node.js

**Spec:** `docs/superpowers/specs/2026-04-08-robots-txt-bypass-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `crawler/src/robotsTxtGuard.ts` | CREATE | Pure function: `isBlanketBlock(robots, siteUrl)` — multi-path probe logic |
| `crawler/src/tests/test_robotsTxtGuard.ts` | CREATE | Unit tests for all probe scenarios |
| `crawler/src/context.ts` | MODIFY | Add `robotsTxtBypassed: boolean` field |
| `crawler/src/main.ts` | MODIFY | Call guard after robots.txt fetch, set flag, include in callback payload |

---

### Task 1: Create the multi-path probe function

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/robotsTxtGuard.ts`

- [ ] **Step 1: Create `robotsTxtGuard.ts` with the `isBlanketBlock` function**

```typescript
// robotsTxtGuard.ts
import { RobotsFile } from 'crawlee';

const ROBOTS_USER_AGENT = 'Googlebot';

/**
 * Probes multiple diverse paths against robots.txt to detect a blanket block.
 * Returns true only if ALL probe URLs are disallowed — indicating Disallow: * or Disallow: /
 * A selective block (e.g., Disallow: /products/) will NOT trigger this.
 */
export function isBlanketBlock(robots: RobotsFile, siteUrl: string): boolean {
    const origin = new URL(siteUrl).origin;
    const probeUrls = [
        origin + '/',
        origin + '/a',
        origin + '/test/page',
    ];
    return probeUrls.every(url => !robots.isAllowed(url, ROBOTS_USER_AGENT));
}
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/robotsTxtGuard.ts
git commit -m "feat(crawler-service): add isBlanketBlock robots.txt probe function"
```

---

### Task 2: Write unit tests for the probe function

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/tests/test_robotsTxtGuard.ts`

- [ ] **Step 1: Create the test file**

This project uses manual test runners (no vitest/jest). Follow the existing pattern in `tests/test_domain_fr.ts`:

```typescript
// test_robotsTxtGuard.ts
import { isBlanketBlock } from '../robotsTxtGuard.js';
import { RobotsFile } from 'crawlee';

const log = (msg: string, success: boolean) => {
    if (success) console.log(`✅ ${msg}`);
    else {
        console.error(`❌ ${msg}`);
        process.exitCode = 1;
    }
};

async function runTests() {
    console.log('=== ROBOTS.TXT GUARD TESTS ===\n');

    // --- Test 1: Disallow: * (blanket block) ---
    console.log('--- Test 1: Disallow * ---');
    const blanketRobots = await RobotsFile.parse(
        'https://example.com/robots.txt',
        'User-agent: *\nDisallow: *\n'
    );
    log(
        'Disallow: * → isBlanketBlock should return true',
        isBlanketBlock(blanketRobots, 'https://example.com') === true
    );

    // --- Test 2: Disallow: / (path-based blanket block) ---
    console.log('\n--- Test 2: Disallow / ---');
    const slashRobots = await RobotsFile.parse(
        'https://example.com/robots.txt',
        'User-agent: *\nDisallow: /\n'
    );
    log(
        'Disallow: / → isBlanketBlock should return true',
        isBlanketBlock(slashRobots, 'https://example.com') === true
    );

    // --- Test 3: Selective block (Disallow: /products/) ---
    console.log('\n--- Test 3: Selective block ---');
    const selectiveRobots = await RobotsFile.parse(
        'https://example.com/robots.txt',
        'User-agent: *\nDisallow: /products/\n'
    );
    log(
        'Disallow: /products/ → isBlanketBlock should return false',
        isBlanketBlock(selectiveRobots, 'https://example.com') === false
    );

    // --- Test 4: Homepage-only block (Disallow: /$) ---
    console.log('\n--- Test 4: Homepage-only block ---');
    const homepageOnlyRobots = await RobotsFile.parse(
        'https://example.com/robots.txt',
        'User-agent: *\nDisallow: /$\n'
    );
    log(
        'Disallow: /$ → isBlanketBlock should return false',
        isBlanketBlock(homepageOnlyRobots, 'https://example.com') === false
    );

    // --- Test 5: Allow overrides Disallow ---
    console.log('\n--- Test 5: Allow overrides Disallow ---');
    const overrideRobots = await RobotsFile.parse(
        'https://example.com/robots.txt',
        'User-agent: *\nDisallow: *\nAllow: /\n'
    );
    log(
        'Disallow: * + Allow: / → isBlanketBlock should return false',
        isBlanketBlock(overrideRobots, 'https://example.com') === false
    );

    // --- Test 6: Empty robots.txt (no rules) ---
    console.log('\n--- Test 6: Empty robots.txt ---');
    const emptyRobots = await RobotsFile.parse(
        'https://example.com/robots.txt',
        ''
    );
    log(
        'Empty robots.txt → isBlanketBlock should return false',
        isBlanketBlock(emptyRobots, 'https://example.com') === false
    );

    // --- Test 7: Googlebot-specific blanket block ---
    console.log('\n--- Test 7: Googlebot-specific blanket block ---');
    const googlebotRobots = await RobotsFile.parse(
        'https://example.com/robots.txt',
        'User-agent: Googlebot\nDisallow: /\n'
    );
    log(
        'User-agent: Googlebot + Disallow: / → isBlanketBlock should return true',
        isBlanketBlock(googlebotRobots, 'https://example.com') === true
    );

    // --- Test 8: Different user-agent blocked, Googlebot allowed ---
    console.log('\n--- Test 8: Different user-agent blocked ---');
    const otherAgentRobots = await RobotsFile.parse(
        'https://example.com/robots.txt',
        'User-agent: BadBot\nDisallow: /\n\nUser-agent: Googlebot\nAllow: /\n'
    );
    log(
        'BadBot blocked, Googlebot allowed → isBlanketBlock should return false',
        isBlanketBlock(otherAgentRobots, 'https://example.com') === false
    );

    console.log('\n=== TESTS COMPLETE ===');
}

runTests().catch(console.error);
```

- [ ] **Step 2: Run tests to verify they work**

Run from the crawler directory:
```bash
cd apps-microservices/crawler-service/crawler
npx tsx src/tests/test_robotsTxtGuard.ts
```

Expected: All 8 tests pass with ✅. If `RobotsFile.parse` is not available in Crawlee's API, check for an alternative factory method — the `robots-parser` package (a Crawlee dependency) may expose `robotsParser(url, content)` instead.

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/tests/test_robotsTxtGuard.ts
git commit -m "test(crawler-service): add unit tests for robots.txt blanket block detection"
```

---

### Task 3: Add `robotsTxtBypassed` flag to context

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/context.ts:52`

- [ ] **Step 1: Add the flag after `stopReason`**

In `context.ts`, add `robotsTxtBypassed: false` after line 52 (`stopReason: ""`):

```typescript
    stopReason: "",
    robotsTxtBypassed: false,
    crawlErrorMessage: "",
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/context.ts
git commit -m "feat(crawler-service): add robotsTxtBypassed flag to crawler context"
```

---

### Task 4: Integrate guard into main.ts startup

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:37` (imports)
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:454` (after robots.txt fetch)

- [ ] **Step 1: Add import**

At line 37 in `main.ts`, next to the existing `context` import, add:

```typescript
import { isBlanketBlock } from "./robotsTxtGuard.js";
```

- [ ] **Step 2: Add bypass check after robots.txt fetch**

Immediately after line 454 (after the `catch` block that handles robots.txt fetch failures), add:

```typescript
// Detect blanket robots.txt block (Disallow: * or Disallow: /)
if (robots && isBlanketBlock(robots, site)) {
    console.warn(`⚠️ robots.txt blanket block detected (all probe URLs blocked). Bypassing robots.txt for this crawl.`);
    robots = undefined;
    context.robotsTxtBypassed = true;
}
```

- [ ] **Step 3: Verify the integration point**

The code should read like this after the change:

```typescript
} catch (e: any) {
    console.warn(`⚠️ Warning: Failed to retrieve robots.txt ...`);
}

// Detect blanket robots.txt block (Disallow: * or Disallow: /)
if (robots && isBlanketBlock(robots, site)) {
    console.warn(`⚠️ robots.txt blanket block detected (all probe URLs blocked). Bypassing robots.txt for this crawl.`);
    robots = undefined;
    context.robotsTxtBypassed = true;
}

// Declare the Glob of URL to include
const siteParts = getPathAfterDomain(site);
```

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "feat(crawler-service): integrate robots.txt blanket block detection at startup"
```

---

### Task 5: Include flag in callback payload

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts:836-844` (payload construction)

- [ ] **Step 1: Add `robots_txt_bypassed` to the payload object**

In the `payload` object constructed around line 836, add the field:

```typescript
    const payload = {
        id_domaine: id,
        success: finalStats?.requestsFinished || 0,
        failed: finalStats?.requestsFailed || 0,
        isFinished: isFinished,
        method: method,
        isError: isError,
        storagePath: storagePath,
        message_erreur_crawling: messageErreurCrawling || null,
        robots_txt_bypassed: context.robotsTxtBypassed
    };
```

This ensures the flag is written to `_callback_payload.json` (line 851) and flows through to the Python orchestrator's success webhook without any Python-side changes.

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "feat(crawler-service): include robots_txt_bypassed in callback payload"
```

---

### Task 6: Update CLAUDE.md

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md`

- [ ] **Step 1: Add robots.txt bypass section**

Add a section in the service's CLAUDE.md after the existing "Archiving — GCS Fallback" section:

```markdown
## robots.txt Blanket Block Bypass

At startup, after fetching robots.txt, the crawler checks if the site has a blanket block (`Disallow: *` or `Disallow: /`) using a multi-path probe (`isBlanketBlock` in `robotsTxtGuard.ts`). Three diverse URLs are tested against `isAllowed()` — if all are blocked, `robots` is set to `undefined`, disabling all robots.txt filtering for the crawl.

- Detection is at startup only (not runtime)
- Bypass is transparent to the caller — no webhook contract change
- `robots_txt_bypassed: true` is included in `_callback_payload.json` for observability
- Selective blocks (e.g., `Disallow: /products/`) are NOT bypassed
```

- [ ] **Step 2: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler-service): document robots.txt blanket block bypass feature"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| Multi-path probe detection logic | Task 1 (`isBlanketBlock`) |
| Set `robots = undefined` on blanket block | Task 4 (main.ts integration) |
| Set `robotsTxtBypassed` flag | Task 3 (context) + Task 4 (main.ts) |
| Log warning on bypass | Task 4 (console.warn) |
| Include in `_callback_payload.json` | Task 5 |
| No changes to `routes.ts` | Confirmed — no task touches it |
| No Python-side changes | Confirmed — no task touches Python files |
| Edge cases (fetch failure, selective block, Allow override) | Task 2 (8 unit tests) |