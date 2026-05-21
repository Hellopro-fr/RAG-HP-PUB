# Camoufox / Browser-Engine Kill-Pattern Widening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the infinite OOM_RELAUNCH loop on Camoufox-using crawls by widening the browser-process kill pattern at both crawler-service callsites (pre-flight orphan cleanup + Tier 2 Phase A recovery) and adding a 2-second kernel-reap delay after pre-flight kill.

**Architecture:** Single TypeScript file change in `apps-microservices/crawler-service/crawler/src/main.ts`. Introduces one exported constant (`BROWSER_KILL_PATTERN`) + one exported helper (`killBrowserProcesses`). Both pkill callsites are refactored to call the helper. Pre-flight callsite gains a `setTimeout(2000)` reap delay. One new test file under `crawler/src/tests/`.

**Tech Stack:** TypeScript 5, Node.js 22, `node:test` (built-in), `node:child_process` `execAsync`, `node:os`.

**Spec:** `docs/superpowers/specs/2026-05-21-camoufox-oom-restart-loop-design.md`.

---

## File Structure

```
apps-microservices/crawler-service/crawler/src/
├── main.ts                                  MODIFIED — add constant, helper, refactor 2 callsites
└── tests/
    └── killBrowserProcesses.test.ts         NEW — pattern composition tests (2 cases)
```

No other files touched. No Python, no docker-compose, no `.env`, no protos.

---

## Task 1: Add `BROWSER_KILL_PATTERN` constant, `killBrowserProcesses` helper, and unit test

**Goal:** Introduce the shared module-level surface (constant + helper) and lock in the pattern composition with two unit tests. Pre-flight and Tier 2 callsites remain unchanged in this task — purely additive.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (add constant + helper near existing imports/constants, do NOT touch pkill callsites yet)
- Create: `apps-microservices/crawler-service/crawler/src/tests/killBrowserProcesses.test.ts`

**Acceptance Criteria:**
- [ ] `BROWSER_KILL_PATTERN` exported and equals exactly `"chrome|chromium|firefox|camoufox|playwright|headless_shell"`.
- [ ] `killBrowserProcesses(timeoutMs?: number): Promise<void>` exported.
- [ ] Helper invokes `execAsync` with `pkill -9 -f "${BROWSER_KILL_PATTERN}" 2>/dev/null || true` and the given timeout (default 5000 ms).
- [ ] Helper swallows `ETIMEDOUT` / `SIGKILL` silently; other errors logged via `console.warn`.
- [ ] Test file passes via `npm test`.
- [ ] `npm run build` (tsc) passes.
- [ ] Existing pre-flight + Tier 2 callsites unchanged.

**Verify:**
```bash
cd apps-microservices/crawler-service/crawler && npm test && npm run build
```
Expected: tests pass (existing + 2 new), tsc emits no errors.

**Steps:**

- [ ] **Step 1: Write the failing test**

Create `apps-microservices/crawler-service/crawler/src/tests/killBrowserProcesses.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BROWSER_KILL_PATTERN } from '../main.js';

test('BROWSER_KILL_PATTERN contains all required engines', () => {
    const expected = ['chrome', 'chromium', 'firefox', 'camoufox', 'playwright', 'headless_shell'];
    const tokens = BROWSER_KILL_PATTERN.split('|');
    for (const token of expected) {
        assert.ok(
            tokens.includes(token),
            `Pattern missing engine "${token}". Got: "${BROWSER_KILL_PATTERN}"`,
        );
    }
});

test('BROWSER_KILL_PATTERN has no unintended tokens', () => {
    const allowed = new Set(['chrome', 'chromium', 'firefox', 'camoufox', 'playwright', 'headless_shell']);
    for (const token of BROWSER_KILL_PATTERN.split('|')) {
        assert.ok(
            allowed.has(token),
            `Unexpected token "${token}" in pattern — could kill non-browser processes`,
        );
    }
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps-microservices/crawler-service/crawler && npm test
```
Expected: FAIL with TypeScript / import error — `BROWSER_KILL_PATTERN` not exported from `../main.js`.

- [ ] **Step 3: Add constant + helper to `main.ts`**

Locate the existing imports + top-level constants area in `apps-microservices/crawler-service/crawler/src/main.ts` (near the `execAsync` definition around `util.promisify(exec)`). Add the constant and helper **after** all imports but **before** the `// --- PRE-FLIGHT CHECKS ---` comment block (currently around line 176):

```ts
// --- Browser-engine kill pattern (Spec-A 2026-05-21) ---
// Matches against /proc/*/cmdline via pkill -f. Covers:
//   - chrome / chromium / headless_shell: Playwright Chromium variants
//   - firefox: standard Playwright Firefox AND Camoufox bundled binary
//   - camoufox: cache directory path component (defensive)
//   - playwright: internal helper processes (e.g., playwright-driver)
// Per-container kill — Docker default PID namespace prevents cross-replica reach.
export const BROWSER_KILL_PATTERN =
    "chrome|chromium|firefox|camoufox|playwright|headless_shell";

export async function killBrowserProcesses(timeoutMs = 5000): Promise<void> {
    try {
        await execAsync(
            `pkill -9 -f "${BROWSER_KILL_PATTERN}" 2>/dev/null || true`,
            { timeout: timeoutMs },
        );
    } catch (e: any) {
        if (e.code !== 'ETIMEDOUT' && e.signal !== 'SIGKILL') {
            console.warn('⚠️  killBrowserProcesses warning:', e.message);
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd apps-microservices/crawler-service/crawler && npm test
```
Expected: PASS for both new tests + all existing tests.

- [ ] **Step 5: Run typecheck**

```bash
cd apps-microservices/crawler-service/crawler && npm run build
```
Expected: tsc emits no errors. Output `dist/` populated.

- [ ] **Step 6: Commit**

Ask the user: "Which language for the commit message? (EN / FR / both)" — wait for response.

Use `.git/COMMIT_EDITMSG` via Write tool (Windows cp1252 hazard — never use heredoc), then:

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts \
        apps-microservices/crawler-service/crawler/src/tests/killBrowserProcesses.test.ts
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Suggested subject: `feat(crawler-service): add BROWSER_KILL_PATTERN constant + helper`

Body must explain: introducing module-level surface, no callsite changes yet, tests assert pattern composition. Bilingual EN/FR.

---

## Task 2: Refactor pre-flight callsite to use helper + add 2-second reap delay

**Goal:** Replace the existing two-call pre-flight pkill block (lines ~178-191 of `main.ts`) with a single `killBrowserProcesses()` call followed by a 2-second sleep before the cgroup memory read. Update log strings.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (pre-flight block — currently around lines 177-191)

**Acceptance Criteria:**
- [ ] Lines 178-191 (current pre-flight kill block) are replaced with: helper call + 2s sleep + new log line.
- [ ] No `pkill` strings remain in the pre-flight block — only the helper call.
- [ ] 2-second sleep is implemented as `await new Promise((r) => setTimeout(r, 2000));`.
- [ ] New log line includes the engine list for operator clarity.
- [ ] Tier 2 Phase A callsite (line ~333) remains unchanged in this task.
- [ ] `npm test` still green. `npm run build` still green.

**Verify:**
```bash
cd apps-microservices/crawler-service/crawler && \
    grep -n "pkill" src/main.ts && \
    npm test && npm run build
```
Expected:
- `grep` shows ONLY the Tier 2 Phase A pkill (line ~333) — the pre-flight pkills are gone. (Phase A is fixed in Task 3.)
- Tests pass. Build passes.

**Steps:**

- [ ] **Step 1: Locate the pre-flight block**

In `apps-microservices/crawler-service/crawler/src/main.ts`, find the block that currently reads (around lines 177-191):

```ts
// --- PRE-FLIGHT CHECKS ---
// 1. Kill orphan processes from previous runs
console.log('🧹 Checking for orphan browser processes...');
try {
    // Kill Chrome/Chromium processes (ignore errors if no processes found)
    await execAsync('pkill -9 -f "chrome|chromium" 2>/dev/null || true', { timeout: 5000 });
    await execAsync('pkill -9 -f "playwright" 2>/dev/null || true', { timeout: 5000 });
    console.log('✅ Orphan processes cleaned.');
} catch (e: any) {
    // Ignore expected errors (no processes found, timeout, SIGKILL)
    if (e.code !== 'ETIMEDOUT' && e.signal !== 'SIGKILL') {
        console.warn('⚠️  Could not clean orphan processes:', e.message);
    } else {
        console.log('✅ No orphan processes found.');
    }
}
```

- [ ] **Step 2: Replace with helper call + reap delay**

Replace the entire block above (lines 177-191, from `// --- PRE-FLIGHT CHECKS ---` comment through the closing `}` of the try/catch) with:

```ts
// --- PRE-FLIGHT CHECKS ---
// 1. Kill orphan browser processes from previous runs
console.log('🧹 Checking for orphan browser processes...');
await killBrowserProcesses();
// Reap delay: kernel reclaims anon pages from killed children asynchronously.
// 2s is empirically sufficient on Linux 5.x+ to flush the post-kill cgroup
// state before the threshold check below reads /sys/fs/cgroup/memory.current.
await new Promise((r) => setTimeout(r, 2000));
console.log('✅ Orphan browser processes cleaned (engines: chrome/chromium/firefox/camoufox/playwright/headless_shell).');
```

- [ ] **Step 3: Verify no pre-flight pkill remains**

```bash
cd apps-microservices/crawler-service/crawler && grep -nE 'pkill.*chrome|pkill.*playwright' src/main.ts
```
Expected: zero or one match (the Tier 2 Phase A pkill at line ~333 — that's Task 3's target).

- [ ] **Step 4: Run tests + typecheck**

```bash
cd apps-microservices/crawler-service/crawler && npm test && npm run build
```
Expected: PASS, no compile errors.

- [ ] **Step 5: Commit**

Ask the user: "Which language for the commit message? (EN / FR / both)" — wait for response.

Use `.git/COMMIT_EDITMSG` via Write tool, then:

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Suggested subject: `fix(crawler-service): widen pre-flight kill + 2s reap delay`

Body must explain: pre-flight now uses the shared helper; pattern catches Camoufox/Firefox; 2s sleep absorbs cgroup-accounting lag after pkill so the threshold check sees the post-kill state. Bilingual EN/FR.

---

## Task 3: Refactor Tier 2 Phase A callsite to use helper

**Goal:** Replace the inline pkill in `handleCriticalMemory` (line ~333) with a call to `killBrowserProcesses()`. Update log string. No reap delay added (Phase A `return`s and waits for next watchdog tick — built-in delay).

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (`handleCriticalMemory` function — currently around lines 324-358, specifically lines 330-334)

**Acceptance Criteria:**
- [ ] Line ~333's inline `pkill -9 -f "chrome|chromium" 2>/dev/null || true` is replaced with `await killBrowserProcesses();`.
- [ ] The surrounding `try { ... } catch (e) { /* ignore */ }` wrapper is removed — the helper handles its own errors.
- [ ] Log string changes from `[Phase A] Killing all Chrome/Playwright processes` to `[Phase A] Killing all browser processes`.
- [ ] No `pkill` strings remain anywhere in `main.ts`.
- [ ] `npm test` green. `npm run build` green.

**Verify:**
```bash
cd apps-microservices/crawler-service/crawler && \
    grep -n "pkill" src/main.ts ; \
    npm test && npm run build
```
Expected:
- `grep` returns no matches (or exit code 1).
- Tests pass. Build passes.

**Steps:**

- [ ] **Step 1: Locate Tier 2 Phase A kill block**

In `apps-microservices/crawler-service/crawler/src/main.ts`, find the block that currently reads (around lines 330-334, inside `handleCriticalMemory`):

```ts
        // 1. Kill Chrome processes (Forcefully release external memory)
        try {
            console.log("   -> [Phase A] Killing all Chrome/Playwright processes");
            await execAsync('pkill -9 -f "chrome|chromium" 2>/dev/null || true');
        } catch (e) { /* ignore */ }
```

- [ ] **Step 2: Replace with helper call**

Replace the entire block above with:

```ts
        // 1. Kill all browser processes (forcefully release external memory)
        console.log("   -> [Phase A] Killing all browser processes");
        await killBrowserProcesses();
```

The helper handles its own error suppression (mirrors the original `/* ignore */` intent), so the surrounding try/catch is no longer needed.

- [ ] **Step 3: Verify no pkill remains**

```bash
cd apps-microservices/crawler-service/crawler && grep -n "pkill" src/main.ts
```
Expected: no matches (grep exits 1).

- [ ] **Step 4: Run tests + typecheck**

```bash
cd apps-microservices/crawler-service/crawler && npm test && npm run build
```
Expected: PASS, no compile errors.

- [ ] **Step 5: Operator smoke prerequisite**

Note for the executing agent: at this point, **no further code changes** are needed for Spec-A. Operator smoke (per spec §5.2) is post-deploy:

1. Deploy `features/poc` to one dev/staging replica.
2. Start the historically OOM-prone crawl (e.g., `shop.monlabofermier.fr` or equivalent Camoufox-using shop crawl).
3. Wait for first OOM_RELAUNCH cycle.
4. Inspect `crawler.log` — expect pre-flight memory percentage to **drop below 80%** between successive cycles (today it stays at 99.7%). Expect the new log line `Orphan browser processes cleaned (engines: ...)` to appear.
5. Confirm crawl resumes after restart rather than infinitely looping.

This is operator-driven verification, not a coded step.

- [ ] **Step 6: Commit**

Ask the user: "Which language for the commit message? (EN / FR / both)" — wait for response.

Use `.git/COMMIT_EDITMSG` via Write tool, then:

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts
git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Suggested subject: `fix(crawler-service): widen Tier 2 Phase A kill via shared helper`

Body must explain: Phase A now uses the shared helper to catch Camoufox/Firefox; closes the second of the two callsites identified in Spec-A; Phase A keeps its existing `return` → next watchdog tick pattern for reap delay (no explicit sleep needed). Bilingual EN/FR.

---

## Self-Review

**Spec coverage:**
- §2 goal "widen kill pattern" → Task 1 (constant) + Task 2 (pre-flight) + Task 3 (Phase A)
- §2 goal "centralise kill logic" → Task 1 (helper)
- §2 goal "2-second reap delay after pre-flight" → Task 2
- §2 goal "unit test locking in pattern composition" → Task 1
- §4.2 pattern composition → Task 1 constant
- §4.3 helper signature + error suppression → Task 1
- §4.4 pre-flight log strings + sleep → Task 2
- §4.5 Phase A log string + helper call (no sleep) → Task 3
- §5.1 unit test → Task 1
- §5.2 operator smoke → Task 3 Step 5

**Placeholder scan:** No "TBD" / "TODO" / vague guidance. Every code block is the actual content to paste. Every command is runnable. Every expected output stated.

**Type consistency:** `BROWSER_KILL_PATTERN: string`, `killBrowserProcesses(timeoutMs?: number): Promise<void>` — used consistently across Task 1 (definition) and Tasks 2 + 3 (callsites). No method-rename pitfalls.

**Verify commands:** All use `cd apps-microservices/crawler-service/crawler && ...` since `npm test` and `npm run build` run from the `crawler/` subdirectory (where `package.json` lives).
