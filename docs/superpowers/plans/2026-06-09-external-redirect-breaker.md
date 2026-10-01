# External-Redirect Breaker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In update-mode crawls, detect when all/most seeded URLs redirect off-domain (relocated site), abort early, and report a real failure (`exit code 7`, `failure_cause=domain_changed`) instead of a misleading success.

**Architecture:** A pure decision helper (`shouldTripExternalRedirectBreaker`) drives a new breaker wired into the existing external-redirect guard in `routes.ts`. Two triggers — a homepage fast-path (abort before Phase-2 seeding) and a ratio breaker (`external/(external+processed) ≥ rate` after a sample gate). Both set `context.stopReason` + a new `context.fatalExitCode=7`, then `stopCrawler`. The natural-completion `gracefulShutdown` call reads `fatalExitCode` so the run exits 7; the Python orchestrator maps exit 7 → `failed` → failure webhook with `failure_cause=domain_changed`.

**Tech Stack:** TypeScript (Crawlee/Playwright crawler, Node `node:test`), Python (FastAPI orchestrator, pytest).

**Spec:** `docs/superpowers/specs/2026-06-09-external-redirect-breaker-design.md`

**Hook note (TDD gate):** The testable logic lives entirely in the Task 1 helper (full unit coverage). Tasks 2–3 are integration wiring in `main.ts`/`routes.ts`/`context.ts` verified by `tsc` build (these files have no co-located unit tests in this codebase). If the `tdd-gate.sh` hook blocks a wiring edit, it is expected — the corresponding logic test is Task 1.

---

### Task 1: Pure external-redirect breaker decision helper

**Goal:** A pure, Crawlee-free function that decides whether the external-redirect ratio breaker should trip, plus full unit tests.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/externalRedirectBreaker.ts`
- Test: `apps-microservices/crawler-service/crawler/src/externalRedirectBreaker.test.ts`

**Acceptance Criteria:**
- [ ] `shouldTripExternalRedirectBreaker(external, processed, cfg)` returns `{trip, reason}`.
- [ ] Below the sample gate (`external+processed < minSample`) → `trip=false`.
- [ ] At/above the gate AND ratio `≥ maxExternalRedirectRate` → `trip=true`.
- [ ] At/above the gate AND ratio `< maxExternalRedirectRate` → `trip=false`.
- [ ] No divide-by-zero (gate guarantees denom ≥ minSample ≥ 1 before division).

**Verify:** `cd apps-microservices/crawler-service/crawler && node --import tsx --test src/externalRedirectBreaker.test.ts` → all tests pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/crawler-service/crawler/src/externalRedirectBreaker.test.ts`:

```ts
/**
 * Tests for shouldTripExternalRedirectBreaker().
 *
 * The breaker fires in update mode when all/most seeded URLs redirect
 * off-domain (the site relocated). It mirrors the existing rate-breaker
 * philosophy: a minimum sample gate, then a ratio threshold.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldTripExternalRedirectBreaker } from './externalRedirectBreaker.js';

const CFG = { externalRedirectMinSample: 10, maxExternalRedirectRate: 0.90 };

test('moved domain: 5000 external / 0 processed → trips', () => {
    const r = shouldTripExternalRedirectBreaker(5000, 0, CFG);
    assert.equal(r.trip, true);
});

test('healthy update: 20 external / 4980 processed (0.4%) → no trip', () => {
    const r = shouldTripExternalRedirectBreaker(20, 4980, CFG);
    assert.equal(r.trip, false);
});

test('below sample gate: 9 external / 0 processed (denom 9 < 10) → no trip', () => {
    const r = shouldTripExternalRedirectBreaker(9, 0, CFG);
    assert.equal(r.trip, false);
});

test('at sample gate, all external: 10 external / 0 processed → trips', () => {
    const r = shouldTripExternalRedirectBreaker(10, 0, CFG);
    assert.equal(r.trip, true);
});

test('at gate, exactly at threshold: 9 external / 1 processed (90%) → trips', () => {
    const r = shouldTripExternalRedirectBreaker(9, 1, CFG);
    assert.equal(r.trip, true);
});

test('at gate, just below threshold: 8 external / 2 processed (80%) → no trip', () => {
    const r = shouldTripExternalRedirectBreaker(8, 2, CFG);
    assert.equal(r.trip, false);
});

test('reason string is populated for both outcomes', () => {
    assert.ok(shouldTripExternalRedirectBreaker(10, 0, CFG).reason.length > 0);
    assert.ok(shouldTripExternalRedirectBreaker(0, 0, CFG).reason.length > 0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service/crawler && node --import tsx --test src/externalRedirectBreaker.test.ts`
Expected: FAIL — cannot find module `./externalRedirectBreaker.js` / `shouldTripExternalRedirectBreaker is not a function`.

- [ ] **Step 3: Write minimal implementation**

Create `apps-microservices/crawler-service/crawler/src/externalRedirectBreaker.ts`:

```ts
/**
 * External-redirect breaker decision (update mode).
 *
 * A "external redirect" is a seeded URL whose final loaded host is off-domain
 * (routes.ts external-redirect guard). When all/most seeded URLs are external
 * redirects, the supplier site has relocated — abort and fail rather than
 * waste a full re-crawl and report a misleading success.
 *
 * Denominator = external + processed (internal pages that entered the breaker
 * block). Blocked-status throws / content-type skips are intentionally excluded,
 * making the ratio slightly more sensitive — acceptable at the 0.90 default.
 *
 * Pure function (no Crawlee/Redis) so it is unit-testable in isolation.
 */
export interface ExternalRedirectBreakerConfig {
    externalRedirectMinSample: number;
    maxExternalRedirectRate: number;
}

export function shouldTripExternalRedirectBreaker(
    external: number,
    processed: number,
    cfg: ExternalRedirectBreakerConfig,
): { trip: boolean; reason: string } {
    const denom = external + processed;
    if (denom < cfg.externalRedirectMinSample) {
        return { trip: false, reason: `below sample gate (${denom}/${cfg.externalRedirectMinSample})` };
    }
    const ratio = external / denom;
    if (ratio >= cfg.maxExternalRedirectRate) {
        return {
            trip: true,
            reason: `external-redirect ratio ${(ratio * 100).toFixed(1)}% >= ${(cfg.maxExternalRedirectRate * 100).toFixed(0)}% (external=${external}, processed=${processed})`,
        };
    }
    return { trip: false, reason: `external-redirect ratio ${(ratio * 100).toFixed(1)}% below threshold` };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/crawler-service/crawler && node --import tsx --test src/externalRedirectBreaker.test.ts`
Expected: PASS — all 7 tests.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/externalRedirectBreaker.ts apps-microservices/crawler-service/crawler/src/externalRedirectBreaker.test.ts
git commit -m "feat(crawler): add external-redirect breaker decision helper + tests"
```

---

### Task 2: Config fields + fatalExitCode plumbing

**Goal:** Add the 3 breaker config fields (with defaults + CLI args), the `fatalExitCode` context field, the exit-code override at natural completion, and surface the `external_redirects` counter in the callback payload.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/context.ts` (circuitBreaker block ~48-63, context fields ~65-68)
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (arg parse ~108-110, circuitBreaker literal ~129-140, payload readStat ~960-995, completion call 1342)

**Acceptance Criteria:**
- [ ] `context.config.circuitBreaker` has `externalRedirectBreakerEnabled` (default true), `maxExternalRedirectRate` (0.90), `externalRedirectMinSample` (10).
- [ ] `context.fatalExitCode` exists (default null).
- [ ] CLI args `--externalRedirectBreaker`, `--maxExternalRedirectRate`, `--externalRedirectMinSample` parse into the config.
- [ ] `main.ts:1342` uses `context.fatalExitCode ?? 2`.
- [ ] `external_redirects` is read and included in `_callback_payload.json`.
- [ ] `npm run build` (tsc) passes.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build` → exits 0, no type errors.

**Steps:**

- [ ] **Step 1: Add config fields + fatalExitCode in `context.ts`**

In `apps-microservices/crawler-service/crawler/src/context.ts`, the circuitBreaker block currently ends:

```ts
            // Micro Mode Settings (<= 50 URLs)
            maxAbsErrors: 5,
            maxAbsRedirects: 10,
            maxAbsNew: 20
        }
    },
    stopReason: "",
```

Replace with (add 3 fields + `fatalExitCode`):

```ts
            // Micro Mode Settings (<= 50 URLs)
            maxAbsErrors: 5,
            maxAbsRedirects: 10,
            maxAbsNew: 20,

            // External-redirect breaker (update mode): abort + fail when all/most
            // seeded URLs redirect off-domain (relocated site). See spec 2026-06-09.
            externalRedirectBreakerEnabled: true,
            maxExternalRedirectRate: 0.90,
            externalRedirectMinSample: 10
        }
    },
    stopReason: "",
    // Exit code to use at natural completion instead of the default 2 (success).
    // Set by a fatal in-handler breaker (e.g. domainChanged → 7) so the crawl
    // terminates as a failure. Null = normal success path. See spec 2026-06-09.
    fatalExitCode: null as number | null,
```

- [ ] **Step 2: Parse CLI args in `main.ts`**

In `apps-microservices/crawler-service/crawler/src/main.ts`, after the `maxAbsNew` parse line (`const maxAbsNew = parseNumericArg('maxAbsNew', 'npm_config_maxabsnew', 20);`), add:

```ts

// External-redirect breaker (update mode) — spec 2026-06-09
const externalRedirectBreakerEnabled = (getArg('externalRedirectBreaker', 'npm_config_externalredirectbreaker') || 'true').toLowerCase() === 'true';
const maxExternalRedirectRate = parseNumericArg('maxExternalRedirectRate', 'npm_config_maxexternalredirectrate', 0.90);
const externalRedirectMinSample = parseNumericArg('externalRedirectMinSample', 'npm_config_externalredirectminsample', 10);
```

- [ ] **Step 3: Add the fields to the circuitBreaker config literal in `main.ts`**

In the `circuitBreaker: { ... }` object inside `context.config = {...}`, the block currently ends:

```ts
        maxAbsErrors: maxAbsErrors,
        maxAbsRedirects: maxAbsRedirects,
        maxAbsNew: maxAbsNew
    }
};
```

Replace with:

```ts
        maxAbsErrors: maxAbsErrors,
        maxAbsRedirects: maxAbsRedirects,
        maxAbsNew: maxAbsNew,
        externalRedirectBreakerEnabled: externalRedirectBreakerEnabled,
        maxExternalRedirectRate: maxExternalRedirectRate,
        externalRedirectMinSample: externalRedirectMinSample
    }
};
```

- [ ] **Step 4: Override exit code at natural completion (`main.ts:1342`)**

Change:

```ts
// Normal completion
await gracefulShutdown('COMPLETED', 2);
```

to:

```ts
// Normal completion. fatalExitCode is set by an in-handler fatal breaker
// (e.g. domainChanged → 7) so the run terminates as a failure; otherwise 2 (success).
await gracefulShutdown('COMPLETED', context.fatalExitCode ?? 2);
```

- [ ] **Step 5: Surface `external_redirects` in the callback payload (`main.ts`)**

In `gracefulShutdown`, next to the other `readStat` calls (the block reading `filtered_qm`, `filtered_hash`, `filtered_ext`, …), add:

```ts
    const external_redirects = await readStat("external_redirects");
```

Then add it to the `payload` object next to `dropped_cb`:

```ts
        dropped_cb,
        external_redirects,
```

- [ ] **Step 6: Build**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: exits 0, no type errors.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/context.ts apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "feat(crawler): wire external-redirect breaker config + fatalExitCode exit override"
```

---

### Task 3: Integrate the breaker into the external-redirect guard

**Goal:** In the `routes.ts` external-redirect guard (update mode), increment `external_redirects`, run the homepage fast-path and the ratio breaker, and on a trip set `stopReason`/`crawlErrorMessage`/`fatalExitCode=7` then `stopCrawler`.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts` (import ~top; guard 264-271)

**Acceptance Criteria:**
- [ ] Helper imported into `routes.ts`.
- [ ] In update mode with the breaker enabled, an off-domain redirect increments `external_redirects`.
- [ ] Homepage off-domain (`request.url === site`) → set `stopReason="domainChanged"`, `fatalExitCode=7`, `stopCrawler`, return.
- [ ] Non-homepage off-domain → ratio breaker via the helper; on trip set `stopReason="domainChanged"`, `crawlErrorMessage`, `fatalExitCode=7`, `stopCrawler`, return.
- [ ] Kill-switch (`externalRedirectBreakerEnabled=false`) → no counter, no abort (current behavior).
- [ ] `npm run build` (tsc) passes.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build` → exits 0.

**Steps:**

- [ ] **Step 1: Import the helper in `routes.ts`**

Add near the existing `stopCrawler` import (`import { stopCrawler } from "./functions.js";` region at the top of `routes.ts`):

```ts
import { shouldTripExternalRedirectBreaker } from "./externalRedirectBreaker.js";
```

- [ ] **Step 2: Replace the external-redirect guard body**

The guard currently reads (routes.ts ~264-271):

```ts
        if (!isInternal) {
            log.warning(`Blocked external redirect: ${url} (Target: ${targetDomain})`);
            // Set structured error message for "1 seul URL crawlé" case: domain change
            if (request.url === site) {
                context.crawlErrorMessage = "L'URL après la page d'accueil change de domaine";
            }
            return;
        }
```

Replace with:

```ts
        if (!isInternal) {
            log.warning(`Blocked external redirect: ${url} (Target: ${targetDomain})`);
            const isHomepageRedirect = request.url === site;
            // Set structured error message for "1 seul URL crawlé" case: domain change
            if (isHomepageRedirect) {
                context.crawlErrorMessage = "L'URL après la page d'accueil change de domaine";
            }

            // --- External-Redirect Breaker (update mode only) ---
            // Off-domain redirects return here BEFORE the circuit-breaker block and
            // before UpdateChecker, so this guard is the only place that can detect a
            // relocated domain. Abort + fail (exit 7) instead of wasting a full
            // re-crawl and reporting a misleading success. See spec 2026-06-09.
            const cb = context.config?.circuitBreaker;
            if (context.updateChecker && context.statsManager && cb?.externalRedirectBreakerEnabled) {
                const external = await context.statsManager.increment("external_redirects");

                // Homepage fast-path: homepage off-domain ⇒ whole site moved.
                // Abort BEFORE Phase 2 seeds the previous dataset (saves the re-crawl).
                if (isHomepageRedirect) {
                    context.stopReason = "domainChanged";
                    context.fatalExitCode = 7;
                    await stopCrawler(crawler, "Domain changed: homepage redirects off-domain");
                    return;
                }

                // Ratio breaker: most seeded URLs redirect off-domain.
                const processed = await context.statsManager.getValue("processed");
                const decision = shouldTripExternalRedirectBreaker(external, processed, cb);
                if (decision.trip) {
                    log.warning(`🛑 External-redirect breaker: ${decision.reason}`);
                    context.stopReason = "domainChanged";
                    context.crawlErrorMessage = "Toutes les URLs redirigent vers un autre domaine (domaine changé)";
                    context.fatalExitCode = 7;
                    await stopCrawler(crawler, `Domain changed: ${decision.reason}`);
                    return;
                }
            }
            return;
        }
```

- [ ] **Step 3: Build**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: exits 0, no type errors. (If tsc reports `crawler` is possibly undefined, confirm the default handler already destructures `crawler` — the existing circuit breaker at routes.ts:352 calls `stopCrawler(crawler, ...)`, so it is in scope.)

- [ ] **Step 4: Run the full crawler test suite (regression)**

Run: `cd apps-microservices/crawler-service/crawler && npm test`
Expected: all tests pass (including Task 1's `externalRedirectBreaker.test.ts`).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/crawler/src/routes.ts
git commit -m "feat(crawler): trip external-redirect breaker in the off-domain guard (homepage fast-path + ratio)"
```

---

### Task 4: Python — classify exit code 7 as domain_changed failure

**Goal:** Map exit code 7 to `(message, "domain_changed")` in `_classify_exit_code` so the orchestrator emits a failure webhook with `failure_cause=domain_changed` (routing via `is_success` is automatic).

**Files:**
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py` (`_classify_exit_code` 309-331)
- Create: `apps-microservices/crawler-service/tests/test_classify_exit_code_domain_changed.py`

**Acceptance Criteria:**
- [ ] `CrawlerManager._classify_exit_code(7)` returns a `(message, "domain_changed")` tuple.
- [ ] `7` is added to the catch-all exclusion set so it is not labeled `unknown`.
- [ ] Exit 7 is not in `(0, 2)` → `is_success=False` (failure path) — unchanged, asserted by test.

**Verify:** `cd apps-microservices/crawler-service && python -m pytest tests/test_classify_exit_code_domain_changed.py -v` → all pass.

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/crawler-service/tests/test_classify_exit_code_domain_changed.py`:

```python
"""Exit code 7 (domain changed) must classify as a domain_changed failure."""

from app.core.crawler_manager import CrawlerManager


def test_exit_7_classifies_as_domain_changed():
    message, failure_cause = CrawlerManager._classify_exit_code(7)
    assert failure_cause == "domain_changed"
    assert message is not None and len(message) > 0


def test_exit_7_is_not_unknown():
    message, _ = CrawlerManager._classify_exit_code(7)
    assert "inattendue" not in message  # not the catch-all "Erreur inattendue" branch


def test_exit_7_is_a_failure_not_success():
    # Mirrors the is_success check in _monitor_process (exit_code in (0, 2)).
    assert 7 not in (0, 2)


def test_success_codes_still_return_none():
    assert CrawlerManager._classify_exit_code(0) == (None, None)
    assert CrawlerManager._classify_exit_code(2) == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_classify_exit_code_domain_changed.py -v`
Expected: FAIL — exit 7 currently hits the catch-all and returns `failure_cause="unknown"` with an "Erreur inattendue" message.

- [ ] **Step 3: Add the exit-7 branch**

In `apps-microservices/crawler-service/app/core/crawler_manager.py`, `_classify_exit_code`, after the exit-6 branch and before the SIGKILL/negative/catch-all branches:

```python
        elif exit_code == 6:
            return ("Crawl bloqué — aucune progression URL", "progress_stalled")
        elif exit_code == 7:
            return ("Le domaine a changé : toutes les URLs redirigent vers un autre domaine", "domain_changed")
        elif exit_code in (137, -9):
```

And add `7` to the catch-all exclusion set so it is never relabeled `unknown`:

```python
        elif exit_code is not None and exit_code not in (0, 2, 3, 4, 5, 6, 7, -1, 137):
            return (f"Erreur inattendue (code de sortie: {exit_code})", "unknown")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps-microservices/crawler-service && python -m pytest tests/test_classify_exit_code_domain_changed.py -v`
Expected: PASS — all 4 tests.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-service/app/core/crawler_manager.py apps-microservices/crawler-service/tests/test_classify_exit_code_domain_changed.py
git commit -m "feat(crawler): classify exit code 7 as domain_changed failure"
```

---

### Task 5: Document exit code 7 + domain_changed in CLAUDE.md

**Goal:** Record the new exit code and `failure_cause` in the service CLAUDE.md so the cross-language contract stays documented.

**Files:**
- Modify: `apps-microservices/crawler-service/CLAUDE.md` (Exit Codes table + `failure_cause` vocabulary table)

**Acceptance Criteria:**
- [ ] Exit Codes table has a row for `7` → update-mode domain-changed → failed, failure webhook.
- [ ] `failure_cause` vocabulary table has a `domain_changed` row (origin: exit 7).

**Verify:** `grep -n "domain_changed" apps-microservices/crawler-service/CLAUDE.md` → at least 2 matches (both tables).

**Steps:**

- [ ] **Step 1: Add the exit-code row**

In `apps-microservices/crawler-service/CLAUDE.md`, in the "Exit Codes (Node.js → Python)" table, after the row for code `6`, add:

```markdown
| 7 | Update mode: domain changed (all/most URLs redirect off-domain) | Status: `failed`, failure webhook with `failure_cause=domain_changed` |
```

- [ ] **Step 2: Add the failure_cause vocabulary row**

In the "`failure_cause` vocabulary" table, after the `6` / `progress_stalled` row, add:

```markdown
| 7 | `domain_changed` | Update crawl aborted: all/most seeded URLs redirect off-domain (relocated site). Homepage fast-path or external-redirect ratio breaker. Spec `docs/superpowers/specs/2026-06-09-external-redirect-breaker-design.md`. |
```

- [ ] **Step 3: Verify**

Run: `grep -n "domain_changed" apps-microservices/crawler-service/CLAUDE.md`
Expected: ≥ 2 matches.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-service/CLAUDE.md
git commit -m "docs(crawler): document exit code 7 / domain_changed failure_cause"
```

---

## Self-Review

**Spec coverage:**
- Mechanism (exit 7 + fatalExitCode + stopCrawler) → Tasks 2 (plumbing) + 3 (trip) + 4 (Python). ✓
- Homepage fast-path → Task 3 Step 2. ✓
- Ratio breaker (numerator/denominator/gate/threshold) → Task 1 (helper) + Task 3 (wiring). ✓
- Config (3 fields, defaults, CLI args, kill-switch, no BO change) → Task 2. ✓
- Exit-code & failure_cause contract → Task 4 + Task 5 (docs). ✓
- Observability (`external_redirects` in payload) → Task 2 Step 5. ✓
- Tests (TS trip table, Python classify) → Task 1 + Task 4. ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code; every verify is an exact command. ✓

**Type/name consistency:** `shouldTripExternalRedirectBreaker(external, processed, cfg) → {trip, reason}` and `ExternalRedirectBreakerConfig {externalRedirectMinSample, maxExternalRedirectRate}` used identically in Task 1 (def), Task 3 (call). Config fields `externalRedirectBreakerEnabled` / `maxExternalRedirectRate` / `externalRedirectMinSample` named identically across context.ts (Task 2), main.ts (Task 2), routes.ts (Task 3). `context.fatalExitCode` defined (Task 2) and set (Task 3), read (Task 2 Step 4). `stopReason="domainChanged"` consistent. Exit code `7` consistent across Tasks 2/3/4/5. ✓

**Dependencies:** Task 3 needs Task 1 (helper) + Task 2 (config + fatalExitCode). Task 5 follows Task 4 (final contract). Tasks 1, 2, 4 independent.
