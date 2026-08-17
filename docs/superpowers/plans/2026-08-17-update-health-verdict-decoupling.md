# Update Health Verdict Decoupling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop `PENDING_SAMPLE` from permanently barring every small-corpus domain from having its detected deletions and redirections applied, without opening the mass-redirect hole the sample gate was accidentally closing.

**Architecture:** Extract the update health verdict from `functions.ts` into a pure, unit-tested module (`updateHealthVerdict.ts`), mirroring the existing `externalRedirectBreaker.ts` precedent. Representativeness becomes a **disjunction** — an absolute sample OR relative coverage — measured by a new dataset-scoped `accounted` counter. The error signal gains a **materiality conjunct** so a bad rate over a tiny sample no longer fires. Separately, the BO gains a redirect cap mirroring its existing deletion caps, because removing the sample gate otherwise leaves redirections completely unbounded.

**Tech Stack:** TypeScript / Node 20 (`node:test` runner, no framework) in `crawler-service`; PHP 7.4 in the Marketplace BO (no test runner — syntax check only).

**Spec:** `docs/superpowers/specs/2026-08-17-update-health-verdict-decoupling-design.md` (revision 3). Read § Design and § BO changes before starting. Revisions 1 and 2 were each refuted by verification; § What earlier revisions got wrong lists the eight + eight dead claims so nobody re-proposes them.

**User decisions (already made):**
- "« Le crawl est-il représentatif ? »" — the crawler answers representativeness with a working instrument; the BO decides safety with its own caps.
- "Une seule formule, plus de mode" — no MICRO/STANDARD switch; the verdict is one path.
- "Réviser la spec en entier" — including the constraint that no run passing today may newly fail.
- "Plafond BO sur les redirections" — a BO-side cap mirroring the deletion pair, accepted as a deliberate tightening after seeing the 35-of-613 blast radius.

---

## Global Constraints

These bind every task. A reviewer may reject work on any one of them.

1. **Two repos, two branches, never mixed.** Crawler work is in `D:\DevHellopro\Workspaces\RAG-HP-PUB` (branch `features/poc`). BO work is in `D:\DevHellopro\Marketplace` (branch `master`). Never stage a file from one while committing in the other.
2. **Never `git add -A` or `git add .`** — both repos are shared with other sessions and both currently carry unrelated untracked files (`.graphify_v59_*` and `scripts/_gf_v59_*.py` in RAG-HP-PUB; `tools/`, `.claude/hooks/conventional-commits.py` in the BO). Stage named paths only.
3. **Never push, never deploy.** The user controls both. RAG-HP-PUB has a remote; the BO has none. End every task at a local commit.
4. **Never uncomment `main.ts:983`.** `isMicroMode` also feeds `routes.ts:456`, whose MICRO branch aborts crawls on absolute caps. Re-enabling it re-arms exactly what commit `db1ec194` deliberately removed. This plan never touches that line.
5. **Preserve the "zero means disabled" semantics.** A configured rate of `0` means the caller switched that signal off — the BO launcher sends `max_redirect_rate = 0` and `max_growth_rate = 0` on every update. An absolute floor must never resurrect a disabled signal.
6. **Minimal diff.** Every changed line must trace to this plan. Preserve unrelated lines character-for-character, including indentation. `functions.ts` uses 4 spaces; `UpdateChecker.ts` uses 4 spaces; the BO PHP file uses 4 spaces in this region — match the file you are in, do not reformat.
7. **Never remove a comment** unless this plan says the change makes it factually wrong (Task 2 does, once).
8. **Local verification only.** `npm test` for the crawler; `php -l` for the BO. Nothing else runs locally — there is no BO test runner, no local DB, no local crawler.

---

## File Structure

| File | Repo | Responsibility |
|---|---|---|
| `crawler/src/updateHealthVerdict.ts` | RAG | **NEW.** Pure decision: counters + config → verdict. Owns the rate arithmetic. Zero imports. |
| `crawler/src/updateHealthVerdict.test.ts` | RAG | **NEW.** `node:test` suite, including a positive control. |
| `crawler/src/class/UpdateChecker.ts` | RAG | Gains five `accounted` increments — one per dataset branch that establishes a state. |
| `crawler/src/context.ts` | RAG | Gains the `minCoverage` config key. |
| `crawler/src/functions.ts` | RAG | Verdict logic replaced by a call; report gains additive fields; one wrong comment corrected. |
| `script/chatgpt/script_process_update_crawling.php` | BO | Gains the redirect cap; stops blocking on `WARNING`. |

Deliberately **not** touched: `routes.ts` (the circuit breaker keeps June's configuration), `app/schemas/crawler.py` (no new API parameter), `shell.php` (the launcher's payload is unchanged), and the reconciliation coverage gate (withdrawn — see spec).

---

## Task 1: The pure verdict module

**Goal:** A dependency-free `decideUpdateHealth()` that produces today's verdict for every run that is healthy today, and the new verdict for the small-corpus case — with a test suite that pins both.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts`
- Create: `apps-microservices/crawler-service/crawler/src/updateHealthVerdict.test.ts`

**Acceptance Criteria:**
- [ ] `updateHealthVerdict.ts` has **zero** `import` statements (grep returns nothing).
- [ ] `decideUpdateHealth()` returns `{ status, statusMessage, disabledSignals }`.
- [ ] `updateHealthRates()` is exported and is the single place the three rates are computed.
- [ ] A rate configured at `0` puts that signal's name in `disabledSignals` and makes its check unreachable regardless of the absolute floor.
- [ ] The suite includes a positive control that fails if the module returns `HEALTHY` unconditionally.
- [ ] `npm test` passes with no new failures.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm test` → all tests pass, including the 14 new ones from `updateHealthVerdict.test.ts`

**Steps:**

- [ ] **Step 1: Record the pre-existing test baseline**

Before writing anything, capture what already passes, so a pre-existing failure is never mistaken for one you caused.

```bash
cd apps-microservices/crawler-service/crawler
npm test 2>&1 | tail -20
```

Write the pass/fail counts into your task report. If anything already fails, name it — do not try to fix it, it is out of scope.

- [ ] **Step 2: Write the failing test file**

Create `apps-microservices/crawler-service/crawler/src/updateHealthVerdict.test.ts`. Note the `.js` extension in the import — that is this project's convention for TS sources (see `externalRedirectBreaker.test.ts`).

```typescript
/**
 * Tests for decideUpdateHealth().
 *
 * The verdict answers one question: was this crawl representative of the
 * previously known Dataset population? Two properties matter most and are
 * pinned here:
 *   1. No run that is HEALTHY under the pre-change code may become non-HEALTHY.
 *   2. A signal whose configured rate is 0 is OFF — its absolute floor must not
 *      resurrect it (the BO launcher disables redirects and growth this way).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decideUpdateHealth, updateHealthRates } from './updateHealthVerdict.js';

// Production configuration: the BO sends max_redirect_rate = 0 and
// max_growth_rate = 0 (shell.php), and does not send min_sample or the
// max_abs_* values, so those keep their context.ts defaults.
const PROD = {
    minSample: 50,
    minCoverage: 0.8,
    maxErrorRate: 0.15,
    maxRedirectRate: 0,
    maxGrowthRate: 0,
    maxAbsErrors: 5,
    maxAbsRedirects: 10,
    maxAbsNew: 20,
};

// All three signals enabled — used only to prove the disabled-signal logic is
// what silences redirects and growth in production, not the module itself.
const ALL_ON = { ...PROD, maxRedirectRate: 0.30, maxGrowthRate: 0.50 };

const S = (o: Partial<Parameters<typeof decideUpdateHealth>[0]>) => ({
    processed: 0, errors: 0, redirects: 0, newUrls: 0, accounted: 0, previousTotal: 0, ...o,
});

test('small site, fully accounted → HEALTHY (the defect being fixed)', () => {
    const r = decideUpdateHealth(S({ processed: 12, accounted: 12, previousTotal: 12 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('large partial crawl still passes on the absolute sample → HEALTHY (non-regression)', () => {
    // 60 >= minSample, coverage only 12% — today this passes, so it must keep passing.
    const r = decideUpdateHealth(S({ processed: 60, accounted: 60, previousTotal: 500 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('collapsed crawl: 17% accounted, no errors, under sample → PENDING_SAMPLE', () => {
    // Domain 884's shape: 41 of 243 previously-known URLs, zero errors.
    const r = decideUpdateHealth(S({ processed: 41, accounted: 41, previousTotal: 243 }), PROD);
    assert.equal(r.status, 'PENDING_SAMPLE');
});

test('mass deletion is judged on errors, not on coverage', () => {
    // Same low fetch coverage, but every previously-known URL is accounted for.
    const r = decideUpdateHealth(
        S({ processed: 10, errors: 30, accounted: 40, previousTotal: 40 }), PROD);
    assert.notEqual(r.status, 'PENDING_SAMPLE');
});

test('materiality conjunct: bad rate but only 2 errors → HEALTHY', () => {
    // 2/12 = 16.7% > 15%, but 2 < maxAbsErrors. This is the small-sample noise
    // that a rate-only test would have flagged.
    const r = decideUpdateHealth(
        S({ processed: 12, errors: 2, accounted: 12, previousTotal: 12 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('exactly maxAbsErrors with the rate above threshold → CRITICAL', () => {
    // 5/20 = 25% > 15% and errors >= 5. Pins >= on the count and > on the rate.
    const r = decideUpdateHealth(
        S({ processed: 20, errors: 5, accounted: 20, previousTotal: 20 }), PROD);
    assert.equal(r.status, 'CRITICAL');
});

test('grown site: many errors but a low rate → HEALTHY (killed the max() form)', () => {
    // previousTotal 100 < processed 200. A max(floor, rate x previousTotal) form
    // would have made this CRITICAL; the conjunction keeps today's answer.
    const r = decideUpdateHealth(
        S({ processed: 200, errors: 20, accounted: 100, previousTotal: 100 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('disabled error signal: rate 0 with errors above the floor → not CRITICAL', () => {
    // Operator force-resume (shell.php bypasscberrors). The floor must not resurrect it.
    const cfg = { ...PROD, maxErrorRate: 0 };
    const r = decideUpdateHealth(
        S({ processed: 100, errors: 90, accounted: 100, previousTotal: 100 }), cfg);
    assert.notEqual(r.status, 'CRITICAL');
    assert.ok(r.disabledSignals.includes('errors'));
});

test('production config silences redirects and growth', () => {
    // 30 redirects / 38 processed = 79%, 30 new / 40 previous = 75%: both far above
    // the default rates, both inert because the BO sends 0.
    const r = decideUpdateHealth(
        S({ processed: 38, redirects: 30, newUrls: 30, accounted: 40, previousTotal: 40 }), PROD);
    assert.equal(r.status, 'HEALTHY');
    assert.deepEqual(r.disabledSignals.sort(), ['growth', 'redirects']);
});

test('same shape with all signals enabled → CRITICAL on redirects', () => {
    const r = decideUpdateHealth(
        S({ processed: 38, redirects: 30, newUrls: 30, accounted: 40, previousTotal: 40 }), ALL_ON);
    assert.equal(r.status, 'CRITICAL');
});

test('previousTotal = 0: no coverage verdict, error test still applies', () => {
    const r = decideUpdateHealth(S({ processed: 40, errors: 20, accounted: 0, previousTotal: 0 }), PROD);
    assert.equal(r.status, 'CRITICAL');
});

test('SUSPECT overrides HEALTHY', () => {
    const r = decideUpdateHealth(
        S({ processed: 0, errors: 12, accounted: 12, previousTotal: 12 }), PROD);
    assert.equal(r.status, 'SUSPECT');
});

test('SUSPECT does NOT override CRITICAL', () => {
    // 60/100 errors: over the 50% corpus bound AND over the rate with 60 >= 5.
    const r = decideUpdateHealth(
        S({ processed: 100, errors: 60, accounted: 100, previousTotal: 100 }), PROD);
    assert.equal(r.status, 'CRITICAL');
});

test('positive control: a run that MUST NOT be HEALTHY', () => {
    // Without this, a module returning HEALTHY unconditionally passes every
    // assertion above that uses assert.equal(..., 'HEALTHY').
    const r = decideUpdateHealth(
        S({ processed: 100, errors: 50, accounted: 100, previousTotal: 100 }), PROD);
    assert.notEqual(r.status, 'HEALTHY');
});

test('updateHealthRates matches the pre-change definitions', () => {
    const rates = updateHealthRates(S({ processed: 200, errors: 20, redirects: 40, newUrls: 50, previousTotal: 100 }));
    assert.equal(rates.errorRate, 0.1);
    assert.equal(rates.redirectRate, 0.2);
    assert.equal(rates.growthRate, 0.5);
});

test('rates are 0 when their denominator is 0 (no NaN leaks into the report)', () => {
    const rates = updateHealthRates(S({ processed: 0, errors: 5, previousTotal: 0, newUrls: 3 }));
    assert.equal(rates.errorRate, 0);
    assert.equal(rates.redirectRate, 0);
    assert.equal(rates.growthRate, 0);
});
```

- [ ] **Step 3: Run the tests to verify they fail**

```bash
cd apps-microservices/crawler-service/crawler
npm test 2>&1 | grep -A3 updateHealthVerdict
```

Expected: failure resolving `./updateHealthVerdict.js` — the module does not exist yet.

- [ ] **Step 4: Write the module**

Create `apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts`:

```typescript
/**
 * Update-mode health verdict decision.
 *
 * Answers ONE question: was this crawl representative of the previously known
 * Dataset population? It is deliberately NOT a deletion-safety net — the BO owns
 * the deletion and redirect caps that bound the destructive actions.
 *
 * Two properties are load-bearing and must survive any edit:
 *
 *  - STRICT RELAXATION. Every condition below is today's condition plus an extra
 *    AND'd conjunct, so no run that reaches HEALTHY under the pre-change code can
 *    become non-HEALTHY. The sample gate is a DISJUNCTION (absolute sample OR
 *    coverage), not a replacement, for the same reason.
 *  - ZERO MEANS DISABLED. A configured rate of 0 means the caller switched that
 *    signal off; the BO launcher does exactly that for redirects and growth on
 *    every update. The absolute floor must never resurrect a disabled signal —
 *    hence the rate guard leads each conjunction.
 *
 * Pure function (no Crawlee, no Redis, no fs) so it is unit-testable in isolation,
 * mirroring externalRedirectBreaker.ts.
 *
 * Design: docs/superpowers/specs/2026-08-17-update-health-verdict-decoupling-design.md
 */

export interface UpdateHealthStats {
    processed: number;
    errors: number;
    redirects: number;
    newUrls: number;
    /** Previously-known URLs whose state this crawl ESTABLISHED. Dataset-scoped. */
    accounted: number;
    /** Size of the previous Dataset population (NOT the whole previous corpus). */
    previousTotal: number;
}

export interface UpdateHealthConfig {
    minSample: number;
    minCoverage: number;
    maxErrorRate: number;
    maxRedirectRate: number;
    maxGrowthRate: number;
    maxAbsErrors: number;
    maxAbsRedirects: number;
    maxAbsNew: number;
}

export interface UpdateHealthVerdict {
    status: string;
    statusMessage: string;
    /** Signals skipped because their configured rate was <= 0. */
    disabledSignals: string[];
}

/** Fraction of the previous corpus that this crawl explained (0 when unknown). */
export function updateHealthCoverage(stats: UpdateHealthStats): number {
    return stats.previousTotal > 0 ? stats.accounted / stats.previousTotal : 0;
}

/**
 * The three rates, with their pre-change definitions and denominators.
 * Single source of truth: the verdict and the published report both use this.
 */
export function updateHealthRates(stats: UpdateHealthStats): {
    errorRate: number;
    redirectRate: number;
    growthRate: number;
} {
    return {
        errorRate: stats.processed > 0 ? stats.errors / stats.processed : 0,
        redirectRate: stats.processed > 0 ? stats.redirects / stats.processed : 0,
        growthRate: stats.previousTotal > 0 ? stats.newUrls / stats.previousTotal : 0,
    };
}

export function decideUpdateHealth(
    stats: UpdateHealthStats,
    cfg: UpdateHealthConfig,
): UpdateHealthVerdict {
    const { processed, errors, redirects, newUrls, accounted, previousTotal } = stats;
    const { errorRate, redirectRate, growthRate } = updateHealthRates(stats);
    const coverage = updateHealthCoverage(stats);

    const disabledSignals: string[] = [];
    if (!(cfg.maxErrorRate > 0)) disabledSignals.push("errors");
    if (!(cfg.maxRedirectRate > 0)) disabledSignals.push("redirects");
    if (!(cfg.maxGrowthRate > 0)) disabledSignals.push("growth");

    let status = "HEALTHY";
    let statusMessage = "Update progressing normally.";

    if (previousTotal > 0 && processed < cfg.minSample && coverage < cfg.minCoverage) {
        status = "PENDING_SAMPLE";
        statusMessage = `Crawl accounted for ${accounted}/${previousTotal} of the previous Dataset `
            + `(${(coverage * 100).toFixed(1)}%) with only ${processed} processed`;
    } else if (cfg.maxErrorRate > 0 && errorRate > cfg.maxErrorRate && errors >= cfg.maxAbsErrors) {
        status = "CRITICAL";
        statusMessage = `Error rate too high (${(errorRate * 100).toFixed(1)}%, ${errors} errors)`;
    } else if (cfg.maxRedirectRate > 0 && redirectRate > cfg.maxRedirectRate && redirects >= cfg.maxAbsRedirects) {
        status = "CRITICAL";
        statusMessage = `Redirect rate too high (${(redirectRate * 100).toFixed(1)}%, ${redirects} redirects)`;
    } else if (cfg.maxGrowthRate > 0 && growthRate > cfg.maxGrowthRate && newUrls >= cfg.maxAbsNew) {
        status = "WARNING";
        statusMessage = `Site growth high (${(growthRate * 100).toFixed(1)}%, ${newUrls} new URLs)`;
    }

    // Mass-deletion guard, moved verbatim from functions.ts. Only HEALTHY and
    // PENDING_SAMPLE are overridden: WARNING and CRITICAL already block and carry
    // a more specific reason. Do NOT widen this.
    if (previousTotal > 0 && errors / previousTotal > 0.5
        && (status === "HEALTHY" || status === "PENDING_SAMPLE")) {
        status = "SUSPECT";
        statusMessage = `Deleted/error volume (${errors}) exceeds 50% of previous corpus (${previousTotal})`;
    }

    return { status, statusMessage, disabledSignals };
}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd apps-microservices/crawler-service/crawler
npm test 2>&1 | tail -20
```

Expected: PASS, with the same pre-existing failures (if any) as Step 1 and no new ones.

- [ ] **Step 6: Commit**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/crawler/src/updateHealthVerdict.ts \
        apps-microservices/crawler-service/crawler/src/updateHealthVerdict.test.ts
git commit -m "feat(crawler): pure update-health-verdict module with disjunctive sample gate"
```

---

## Task 2: The `accounted` counter

**Goal:** A dataset-scoped counter incremented exactly once per previously-known URL whose state the crawl actually established — excluding the branch that explicitly declines to reach a verdict.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts` (five insertions)
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts:1449-1452` (one comment corrected)

**Acceptance Criteria:**
- [ ] `increment("accounted")` appears exactly **five** times in `UpdateChecker.ts`.
- [ ] It does **not** appear in the `unverified_http_error_*` branch.
- [ ] It does **not** appear in any `else` branch handling non-dataset URLs.
- [ ] The comment at `functions.ts:1449-1452` no longer claims that CASE 3 errors bypass `processed`.
- [ ] `npm test` still passes.

**Verify:** `cd apps-microservices/crawler-service/crawler && grep -c 'increment("accounted")' src/class/UpdateChecker.ts` → `5`, then `npm test` → passes

**Steps:**

- [ ] **Step 1: Understand why one branch is excluded**

Read `UpdateChecker.ts:173-197`. The `isHttpError` + `isFromDataset` path splits in two:

- `404`/`410` → a server verdict that the resource is **gone** → `action: 'deleted'`. This **is** an established state.
- anything else (`401/403/407/429/5xx/0`) → `action: 'ignored'`, `reason: unverified_http_error_*`. The comment at `:176-181` says the page **may be alive** — a 403 from an anti-bot wall is not a deletion. This is **not** an established state.

Counting the second one as accounted would make a rate-limited or firewalled crawl read as fully explained, therefore `HEALTHY`, therefore free to delete. `routes.ts:1269-1298` already guards the same hazard from the other side by refusing to call `checkUrl` at all when no verdict is possible. Follow that convention.

- [ ] **Step 2: Insert the five increments**

Each one goes immediately before its branch's `return`, next to the existing `statsManager` calls so the grouping stays readable.

**2a — Case 1, confirmed deleted (`404`/`410`).** After the `writeJsonl` on the line that currently reads `await this.writeJsonl(UpdateChecker.DELETED_FILE, result);` inside the `if (httpStatus === 404 || httpStatus === 410)` block:

```typescript
                    await this.writeJsonl(UpdateChecker.DELETED_FILE, result);
                    await this.statsManager.increment("accounted");
                    return result;
```

**2b — Case 2a, redirect onto another Dataset URL.** Before the `return { action: 'confirmed', url: originalUrl, source, reason: 'redirect_to_existing' };`:

```typescript
                    await this.statsManager.increment("accounted");
                    return { action: 'confirmed', url: originalUrl, source, reason: 'redirect_to_existing' };
```

**2c — Case 2b, redirect off the Dataset.** After the `writeJsonl(UpdateChecker.REDIRECTED_FILE, result)` inside the `else` of `destInDataset` (still inside `if (isFromDataset)`):

```typescript
                    await this.writeJsonl(UpdateChecker.REDIRECTED_FILE, result);
                    await this.statsManager.increment("accounted");
                    return result;
```

**2d — Case 3a, confirmed alive and eligible.** Before the `return { action: 'confirmed', url: originalUrl, source };`:

```typescript
                await this.statsManager.increment("accounted");
                return { action: 'confirmed', url: originalUrl, source };
```

**2e — Case 3b, alive but no longer eligible.** After the `writeJsonl(UpdateChecker.DELETED_FILE, result)` in the `not_eligible` branch:

```typescript
                await this.writeJsonl(UpdateChecker.DELETED_FILE, result);
                await this.statsManager.increment("accounted");
                return result;
```

Two of these `writeJsonl` calls target `DELETED_FILE` (2a and 2e) — make sure you edit **both** occurrences and not the same one twice. After editing, the grep in **Verify** must return exactly `5`.

- [ ] **Step 3: Correct the wrong comment in `functions.ts`**

The comment currently at `:1449-1452` states that errors do not count toward `processed`, citing "UpdateChecker CASE 1/3". Verification established that this is true for CASE 1 only: CASE 3's `not_eligible` branch runs *after* `routes.ts:444` has already incremented `processed`. Replace those four comment lines with:

```typescript
        // Mass-deletion guard: 'errors' ≈ deleted candidates (UpdateChecker CASE 1/3).
        // CASE 1 (permanent HTTP status) throws in routes.ts before 'processed' is
        // incremented, so a mass-404 restructure never reaches min_sample. CASE 3
        // ('not_eligible') does NOT share that property — it runs after the increment,
        // so those URLs are in both counters. Either way this guard is corpus-relative
        // and independent of 'processed', which is why it still holds
        // (incident 636-389-1783326914).
```

This is the one comment this plan is allowed to rewrite: the change makes the old wording factually wrong.

- [ ] **Step 4: Verify the count and run the tests**

```bash
cd apps-microservices/crawler-service/crawler
grep -c 'increment("accounted")' src/class/UpdateChecker.ts
grep -n 'unverified_http_error' -A1 -B4 src/class/UpdateChecker.ts | grep -c accounted
npm test 2>&1 | tail -20
```

Expected: `5`, then `0` (no `accounted` near the unverified branch), then tests pass.

- [ ] **Step 5: Commit**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/crawler/src/class/UpdateChecker.ts \
        apps-microservices/crawler-service/crawler/src/functions.ts
git commit -m "feat(crawler): dataset-scoped 'accounted' counter for update coverage"
```

---

## Task 3: Wire the module into the report

**Goal:** `generateUpdateReport` delegates the verdict to the module, keeps its `ABORTED` override, and publishes the new fields additively.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/context.ts` (add `minCoverage`)
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (add `minCoverage` to the startup config rebuild)
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts:1430-1457` (replace) and `:1464-1491` (extend)

**Acceptance Criteria:**
- [ ] `functions.ts` imports `decideUpdateHealth` and `updateHealthRates` from `./updateHealthVerdict.js`.
- [ ] The `if (context.stopReason)` / `ABORTED` block still exists in `generateUpdateReport`, **after** the module call.
- [ ] `minCoverage: 0.8` exists in `context.ts`'s `circuitBreaker` object and in `main.ts`'s rebuild.
- [ ] The report publishes `metrics.accounted`, `rates.coverage`, `thresholds.min_coverage`, `thresholds.max_abs_new`, `thresholds.disabled_signals`.
- [ ] `health`, `message`, and every existing `metrics.*` / `rates.*` key keep their names and meaning.
- [ ] `npm test` passes; `npx tsc --noEmit` reports no new errors.

**Verify:** `cd apps-microservices/crawler-service/crawler && npx tsc --noEmit && npm test` → no type errors, tests pass

**Steps:**

- [ ] **Step 1: Add the config key in both places**

`context.ts` — inside the `circuitBreaker` object, next to `minSample`:

```typescript
            minSample: 50,
            minCoverage: 0.8,
```

`main.ts` — the startup rebuild carries its own copy of these defaults (there is an `isMicroMode: false` there around line 160). Add `minCoverage: 0.8` alongside its `minSample` in that same object. If the rebuild does not list `minSample`, add nothing there and record that in your report.

> **Why 0.8:** borrowed from the BO's `UPDATE_RECONCILIATION_COVERAGE_MIN` so the two coverage notions in the system agree on one figure. It is not independently calibrated — and because the sample gate is a disjunction, a wrong value here cannot block a run that passes today.

- [ ] **Step 2: Add the import**

At the top of `functions.ts`, with the other local imports:

```typescript
import { decideUpdateHealth, updateHealthRates, updateHealthCoverage } from './updateHealthVerdict.js';
```

- [ ] **Step 3: Replace the verdict logic**

Read `generateUpdateReport` from its `const processed = await context.statsManager.getValue("processed");` down to the closing brace of the mass-deletion guard. Keep the four `getValue` reads, add a fifth, and replace everything from `let status = "HEALTHY";` through the end of the `SUSPECT` block with the call.

**The replaced range ends at the `SUSPECT` block's closing brace — NOT at the `ABORTED` block.** `if (context.stopReason) { status = "ABORTED"; ... }` stays exactly where it is, after the module call. Deleting it would let a crawl stopped by the queue cap, the circuit breaker, a blocked proxy (exit 8) or a dead domain (exit 9) be judged on partial counters: with `previousTotal = 6000` and a 5000-entry cap, 40 errors is a 0.7 % rate, no `SUSPECT`, verdict `HEALTHY` — deletions applied on a crawl that saw 83 % of the corpus.

```typescript
        const processed = await context.statsManager.getValue("processed");
        const errors = await context.statsManager.getValue("errors");
        const redirects = await context.statsManager.getValue("redirects");
        const newUrls = await context.statsManager.getValue("new_urls");
        const accounted = await context.statsManager.getValue("accounted");

        const cb = context.config.circuitBreaker;

        const healthStats = { processed, errors, redirects, newUrls, accounted, previousTotal: cb.previousTotal };
        const { errorRate, redirectRate, growthRate } = updateHealthRates(healthStats);
        const verdict = decideUpdateHealth(healthStats, cb);

        let status = verdict.status;
        let statusMessage = verdict.statusMessage;

        if (context.stopReason) {
            status = "ABORTED";
            statusMessage = `Crawler stopped: ${context.stopReason}`;
        }
```

Delete the three now-duplicated rate computations that sat above `let status` — `updateHealthRates` replaces them, and having two copies of those formulas is how they drift apart.

- [ ] **Step 4: Extend the report object**

In the `const report = {` literal, make these edits and no others:

```typescript
            mode: "GRADUATED",
            health: status,
            message: statusMessage,
            metrics: {
                processed,
                errors,
                redirects,
                new_urls: newUrls,
                accounted,
                previous_total: cb.previousTotal
            },
            rates: {
                error_rate: parseFloat(errorRate.toFixed(4)),
                redirect_rate: parseFloat(redirectRate.toFixed(4)),
                growth_rate: parseFloat(growthRate.toFixed(4)),
                coverage: parseFloat(updateHealthCoverage(healthStats).toFixed(4))
            },
            thresholds: {
                min_sample: cb.minSample,
                min_coverage: cb.minCoverage,
                max_error_rate: cb.maxErrorRate,
                max_redirect_rate: cb.maxRedirectRate,
                max_growth_rate: cb.maxGrowthRate,
                max_abs_errors: cb.maxAbsErrors,
                max_abs_redirects: cb.maxAbsRedirects,
                max_abs_new: cb.maxAbsNew,
                disabled_signals: verdict.disabledSignals
            },
```

`mode` becomes the literal `"GRADUATED"` — there is no longer a mode to report, and the BO never reads this key. Rounding to four decimals is for **publication only**; the verdict already compared the unrounded values inside the module. Never feed `report.rates` back into a decision.

- [ ] **Step 5: Typecheck and test**

```bash
cd apps-microservices/crawler-service/crawler
npx tsc --noEmit
npm test 2>&1 | tail -20
```

Expected: no new type errors (a pre-existing error elsewhere is out of scope — name it in your report); tests pass.

- [ ] **Step 6: Commit**

```bash
cd D:/DevHellopro/Workspaces/RAG-HP-PUB
git add apps-microservices/crawler-service/crawler/src/functions.ts \
        apps-microservices/crawler-service/crawler/src/context.ts \
        apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "refactor(crawler): delegate the update health verdict to the pure module"
```

---

## Task 4: The BO redirect cap

**Goal:** Bound the redirect action the way deletions are already bounded, so removing the sample gate does not leave mass redirect archiving unguarded.

**Files:**
- Modify: `BO/script/chatgpt/script_process_update_crawling.php` — constants near `:37-45`, guard block at `:635-654`

**Acceptance Criteria:**
- [ ] `UPDATE_REDIRECTED_CAP_ABS` (100) and `UPDATE_REDIRECTED_CAP_PCT` (0.5) are defined with the same `if (!defined(...))` idiom as their deletion siblings.
- [ ] Both caps read `count($tab_urls_redirections)` — **never** `$metrics_update["redirects"]`.
- [ ] The percentage cap sits inside the `else` of the `health === "HEALTHY"` test; the absolute cap sits after the block, guarded by `$appliquer_actions_destructives &&`. Same shape as the deletion pair.
- [ ] `$raison_blocage_destructif` names redirections, so the health mail states its own cause.
- [ ] `php -l` clean.

**Verify:** `php -l BO/script/chatgpt/script_process_update_crawling.php` → `No syntax errors detected`

**Steps:**

- [ ] **Step 1: Read the BO repo's own rules first**

`D:\DevHellopro\Marketplace\CLAUDE.md` and `D:\DevHellopro\Marketplace\.claude\rules\` are **not** loaded automatically when the session was launched from the other repo. Read `CLAUDE.md` and `.claude/rules/code-modification.md` before editing.

- [ ] **Step 2: Understand why `metrics.redirects` must not be used**

`UpdateChecker.ts:205-219` writes the `REDIRECTED` row for a dataset URL redirecting onto another dataset URL but deliberately does **not** increment the `redirects` counter — its comment says *"that counter feeds the circuit breaker"*. The BO reads the file with **no filter** on `reason` (`:552-556`). So a site whose 40 URLs all redirect to canonical variants reports `redirects = 0` and `redirect_rate = 0.0` while the BO archives 40 sources. A cap built on the counter is inert for exactly the population it must protect.

`$tab_urls_redirections` is loaded at `:552-556`, well before the guard block at `:635`, so it is available. Use it.

- [ ] **Step 3: Add the two constants**

Next to the existing deletion caps near the top of the file, following the surrounding idiom exactly:

```php
// Plafonds redirections — miroir des plafonds de suppression. Les redirections
// n'avaient AUCUNE borne : les plafonds de suppression comptent
// $tab_urls_supprime_list, detecter_et_marquer_maintenance() rend null tant que
// MAINTENANCE_DETECT_ENABLED est éteint, et le breaker redirection-externe du
// crawler ne compte que le hors-domaine — une refonte INTERNE ne le déclenche
// jamais. Mesure du 17/08 sur 613 MAJ terminées : 33 runs ont appliqué plus de
// 100 redirections, un seul 2335.
// On compte count($tab_urls_redirections) et JAMAIS metrics.redirects : ce
// compteur saute volontairement la branche dataset→dataset (UpdateChecker CASE 2a)
// alors que le BO lit le fichier sans filtrer.
if (!defined('UPDATE_REDIRECTED_CAP_ABS')) define('UPDATE_REDIRECTED_CAP_ABS', 100);
if (!defined('UPDATE_REDIRECTED_CAP_PCT')) define('UPDATE_REDIRECTED_CAP_PCT', 0.5);
```

- [ ] **Step 4: Add the percentage cap inside the healthy branch**

In the `else` of `if ($health_update !== "HEALTHY")`, after the existing deletion percentage check, add a second `if` at the same nesting level:

```php
            # Gardé par $appliquer_actions_destructives comme les deux caps absolus :
            # sans cette garde, une co-brèche % écraserait la raison déjà posée par le
            # cap suppressions et le mail n'annoncerait que les redirections.
            if ($appliquer_actions_destructives && $previous_total_update > 0
                && (count($tab_urls_redirections) / $previous_total_update) > UPDATE_REDIRECTED_CAP_PCT) {
                $appliquer_actions_destructives = false;
                $raison_blocage_destructif = "redirections " . count($tab_urls_redirections)
                    . " > " . (UPDATE_REDIRECTED_CAP_PCT * 100) . "% du corpus précédent ({$previous_total_update})";
            }
```

> **Amended after Task 4's review.** The first draft of this step omitted the
> `$appliquer_actions_destructives &&` guard, copying the deletion sibling without noticing that
> the second check would then **overwrite** the reason string the first had set. A run breaching
> both percentage caps would have reported only the redirect breach, dropping the deletion one
> from the operator-facing mail — while the absolute pair, being guarded, blamed deletions
> instead. Two destructive families sharing one reason string with no ordering discipline.
> The guard makes attribution consistent. Making a co-breach report **both** causes is deferred:
> `$raison_blocage_destructif` has four writers, two of them pre-existing, and the health-guard
> mail reads it.

- [ ] **Step 5: Add the absolute cap after the block**

Immediately after the existing absolute deletion cap, mirroring it:

```php
    # Cap absolu redirections — s'applique aussi quand le rapport est absent.
    if ($appliquer_actions_destructives && count($tab_urls_redirections) > UPDATE_REDIRECTED_CAP_ABS) {
        $appliquer_actions_destructives = false;
        $raison_blocage_destructif = "redirections " . count($tab_urls_redirections) . " > cap absolu " . UPDATE_REDIRECTED_CAP_ABS;
    }
```

- [ ] **Step 6: Syntax check**

```bash
cd D:/DevHellopro/Marketplace
php -l BO/script/chatgpt/script_process_update_crawling.php
```

Expected: `No syntax errors detected`. Use the **local** `php`, not `wsl php`.

- [ ] **Step 7: Commit (BO repo)**

```bash
cd D:/DevHellopro/Marketplace
git add BO/script/chatgpt/script_process_update_crawling.php
git commit -m "feat(garde-sante): plafonds de redirections, miroir des plafonds de suppression"
```

---

## Task 5: `WARNING` stops blocking

**Goal:** A growth warning no longer bars deletions it does not describe.

**Files:**
- Modify: `BO/script/chatgpt/script_process_update_crawling.php` — the health test at `:636-639`

**Acceptance Criteria:**
- [ ] `WARNING` no longer sets `$appliquer_actions_destructives = false`.
- [ ] `CRITICAL`, `SUSPECT`, `PENDING_SAMPLE`, `ABORTED` and any unknown value still block.
- [ ] The deletion and redirect percentage caps still apply on a `WARNING` run — the whitelist must **not** bypass the `else` that contains them.
- [ ] `php -l` clean.

**Verify:** `php -l BO/script/chatgpt/script_process_update_crawling.php` → `No syntax errors detected`

**Steps:**

- [ ] **Step 1: Replace the condition**

The current test is `if ($health_update !== "HEALTHY")`. Widen the accepted set rather than adding an early bypass — an early `return`/`continue` would skip the caps in the `else`, which is the opposite of what this task wants.

```php
    if (is_array($sante_update)) {
        $health_update = $sante_update["health"] ?? "";
        # WARNING ne bloque plus : c'est le seul verdict que le signal de croissance
        # peut produire, et la croissance d'un site ne qualifie pas la sûreté d'une
        # SUPPRESSION. Les plafonds ci-dessous restent appliqués sur un run WARNING —
        # d'où l'élargissement de la liste acceptée plutôt qu'un court-circuit.
        # ⚠ Corollaire assumé : après ce changement, réactiver max_growth_rate côté
        # referentiel_seuils_cb n'aurait plus aucun effet sur cette garde. Si la
        # croissance doit redevenir observable, la router vers la trace ou le mail,
        # pas vers ce test.
        if (!in_array($health_update, ["HEALTHY", "WARNING"], true)) {
            $appliquer_actions_destructives = false;
            $raison_blocage_destructif = "health={$health_update} (" . ($sante_update["message"] ?? "") . ")";
        } else {
```

The `else` body — the deletion cap, and the redirect cap added in Task 4 — is unchanged.

- [ ] **Step 2: Confirm an empty verdict still blocks**

`$health_update` defaults to `""` when the report is absent. `in_array("", ["HEALTHY","WARNING"], true)` is `false`, so a missing report still blocks. The strict third argument matters: without it, `in_array(0, ["HEALTHY","WARNING"])` would be true in PHP 7.4. Keep `true`.

- [ ] **Step 3: Syntax check and commit**

```bash
cd D:/DevHellopro/Marketplace
php -l BO/script/chatgpt/script_process_update_crawling.php
git add BO/script/chatgpt/script_process_update_crawling.php
git commit -m "feat(garde-sante): WARNING ne bloque plus les actions destructives"
```

---

## Task 6: The BO deployment package

**Goal:** One MEP package for the BO half, with a description that carries the hard ordering constraint.

**Files:**
- Create: `BO/repertoire_test/MISE_EN_PRODUCTION/17-08-2026/ticket_verdict_sante_redirect_cap_SCRIPT/` (suffix `_2`, `_3`… if a folder of that name was already sent **today**; the suffix restarts inside each date folder)

**Acceptance Criteria:**
- [ ] The package contains only `script/chatgpt/script_process_update_crawling.php`, at its deployed-relative path.
- [ ] `description.txt` states the ordering constraint: **the crawler service must be deployed first**.
- [ ] The description explains that the redirect cap is a deliberate tightening, with the 35-of-613 figure.
- [ ] No file from the RAG repo is in the package.

**Verify:** `powershell -File tools/verify_mep_package.ps1 -Package "<full path to the package folder>"` → no errors

**Steps:**

- [ ] **Step 1: Build the package with the build-mep skill**

Use the project's MEP tooling rather than copying by hand. Routing is by the second path segment: `BO/script/**` → vhost `script.hellopro.fr`, domainId **3**, package suffix `_SCRIPT`. `tests/` directories are never packaged.

- [ ] **Step 2: Write `description.txt`**

It must state, in this order: what changes, why the redirect cap exists (the refonte shape that reaches `HEALTHY` with no bound), the measured blast radius (33 runs above the absolute cap, 3 above the percentage, 35 of 613), and the ordering constraint in a form nobody can miss:

```
⚠ ORDRE DE DEPLOIEMENT DUR : ce paquet part APRES le deploiement du crawler-service
qui publie metrics.accounted. Depose avant, le BO lit accounted absent — le repli sur
processed le rend inoffensif, mais le verdict PENDING_SAMPLE reste celui de l ancien
service et la MEP n a aucun effet.
```

- [ ] **Step 3: Verify the package**

```bash
powershell -File tools/verify_mep_package.ps1 -Package "D:/DevHellopro/Marketplace/BO/repertoire_test/MISE_EN_PRODUCTION/17-08-2026/ticket_verdict_sante_redirect_cap_SCRIPT"
```

`-Package` needs the **full** path. Never rewrite a package folder that has already been sent — create a `_2` suffix instead.

- [ ] **Step 4: Report, do not deploy**

Deployment is the user's. Report the package path and the ordering constraint, and stop.

---

## Deployment gate (not a task — the user's call)

The crawler side ends at three local commits on `features/poc`. It reaches production through the repo's own CI/CD once the user pushes; this plan never pushes.

**Order: crawler service first, BO second.** The service produces the verdict the BO interprets, and the BO changes are additive.

This ordering is **not** "strictly safe", and the earlier draft that said so was wrong. The service deployment is where the behaviour change lands: the moment it ships, small-corpus runs stop returning `PENDING_SAMPLE` and the *unchanged* BO gate begins applying their deletions and redirections. That is the intended outcome and it is bounded by the BO's existing deletion caps — but the redirect cap does **not** exist until the BO package is deployed. Between the two deployments, mass internal-redirect archiving on a small site is possible.

Two ways to close that window, for the user to choose at deploy time: deploy the BO package first (harmless — `metrics.accounted` is absent, the fallback keeps today's behaviour, and the redirect cap becomes active immediately), or deploy both in the same session. Deploying the service first and the BO days later is the one sequence to avoid.

---

## Self-review

**Spec coverage.** § A pure decision module → Task 1. § A sound coverage numerator → Task 2. § Representativeness / § Thresholds / § Evaluation order → Task 1. § Report shape → Task 3. § BO changes 1 (redirect cap) → Task 4. § BO changes 2 (`WARNING`) → Task 5. § Deployment order → the gate section. § Testing → Task 1 Step 2. Withdrawn from scope by the spec itself: the reconciliation numerator, `crawler-service/CLAUDE.md`, persisting `previous_total`, re-deriving the 80 rows.

**One spec item deliberately not implemented:** the spec's § Testing lists "the refonte shape → `HEALTHY`, asserted deliberately". It is in Task 1 as *"production config silences redirects and growth"* — same numbers, and its sibling test with `ALL_ON` shows what would fire if the rates were enabled. The pairing is the point: it documents that the crawler does not catch this case and that Task 4 is what must.

**Type consistency.** `UpdateHealthStats` / `UpdateHealthConfig` / `UpdateHealthVerdict` are defined in Task 1 and used unchanged in Task 3. `decideUpdateHealth`, `updateHealthRates`, `updateHealthCoverage` keep their names throughout. `cb` is passed directly as the config because `circuitBreaker` is a structural superset of `UpdateHealthConfig` once Task 3 Step 1 adds `minCoverage` — that ordering dependency is why Task 3 does the config edit before the wiring.

**Residual risk, stated rather than hidden.** `minCoverage = 0.8` is borrowed, not calibrated. The disjunction bounds the damage: a wrong value cannot block a run that passes today. And the BO half has no unit test — that repo has no runner, so its verification is `php -l` plus the package review plus the measured blast radius.
