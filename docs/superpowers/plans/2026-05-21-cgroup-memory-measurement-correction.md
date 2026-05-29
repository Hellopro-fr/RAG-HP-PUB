# Cgroup Memory Measurement Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace raw `memory.current` reads in the crawler-service pre-flight + watchdog with a corrected formula that subtracts page-cache bytes, so the threshold check reflects memory pressure rather than total occupancy. Eliminates the second half of the OOM_RELAUNCH loop (the first half — Camoufox kill-pattern — was fixed in Spec-A).

**Architecture:** New side-effect-free module `cgroupMemory.ts` exporting `parseMemoryStat()` (pure parser) and `readUsableMemory()` (composition: cgroup v2 → v1 → host fallback). `main.ts` pre-flight + `readContainerMemory` watchdog both delegate to it. Tier 1 + Tier 2 handler log lines get a `% usable` suffix. Dual log format surfaces usable + raw + page cache for operator diagnostics.

**Tech Stack:** TypeScript 5, Node.js 22, `node:test`, `node:fs/promises`, `node:os`.

**Spec:** `docs/superpowers/specs/2026-05-21-cgroup-memory-measurement-correction-design.md`.

---

## File Structure

```
apps-microservices/crawler-service/crawler/src/
├── cgroupMemory.ts                  NEW — parseMemoryStat + readUsableMemory (~80 LOC)
├── main.ts                          MODIFIED — pre-flight (189-231) + readContainerMemory (239-270) + Tier 1/2 handler log strings (278+, 315+)
└── tests/
    └── cgroupMemory.test.ts         NEW — 4 parser fixture tests (~50 LOC)
```

No other files touched. No Python, no docker-compose, no `.env`, no protos.

---

## Task 1: Add `cgroupMemory.ts` module with `parseMemoryStat` + `readUsableMemory`, plus 4 parser fixture tests

**Goal:** Introduce the side-effect-free helper module and lock in the parser's behaviour with 4 unit tests. `main.ts` callsites stay unchanged in this task — purely additive.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/cgroupMemory.ts`
- Create: `apps-microservices/crawler-service/crawler/src/tests/cgroupMemory.test.ts`

**Acceptance Criteria:**
- [ ] `parseMemoryStat(content: string): { file: number }` exported. Reads `file` key (cgroup v2). Falls back to `cache` key (cgroup v1). Returns `{ file: 0 }` if neither present. Skips malformed lines silently.
- [ ] `readUsableMemory(): Promise<UsableMemory | null>` exported. Returns `{ usableUsed, totalMem, rawCurrent, pageCache }` per spec § 4.1.
- [ ] `UsableMemory` interface exported per spec § 4.1.
- [ ] Lookup order per spec § 4.2 (cgroup v2 → v1 → host fallback → null).
- [ ] Host fallback path returns `pageCache: 0`, `usableUsed = rawCurrent` (no visibility from `os.*` APIs).
- [ ] 4 unit tests pass: v2 format, v1 format, missing key, malformed lines.
- [ ] `npm test` green (58 tests = 54 existing + 4 new).
- [ ] `npm run build` clean.
- [ ] `main.ts` callsites unchanged (verify via grep: `readUsableMemory` only in `cgroupMemory.ts` + test file; pre-flight still reads `memory.current` directly).

**Verify:**
```bash
cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -10 && npm run build 2>&1 | tail -3
```
Expected: 58 tests pass / 0 fail; tsc clean.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `apps-microservices/crawler-service/crawler/src/tests/cgroupMemory.test.ts`:

```ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseMemoryStat } from '../cgroupMemory.js';

test('parseMemoryStat extracts file key from cgroup v2 format', () => {
    const content = [
        'anon 500000000',
        'file 5800000000',
        'kernel_stack 1024',
        'slab 2000000',
        'sock 50000',
        'inactive_file 3400000000',
        'active_file 2400000000',
    ].join('\n') + '\n';
    assert.equal(parseMemoryStat(content).file, 5800000000);
});

test('parseMemoryStat extracts cache key from cgroup v1 format', () => {
    const content = [
        'cache 5800000000',
        'rss 500000000',
        'rss_huge 0',
        'mapped_file 200000',
        'swap 0',
    ].join('\n') + '\n';
    assert.equal(parseMemoryStat(content).file, 5800000000);
});

test('parseMemoryStat returns file: 0 when neither key present', () => {
    const content = [
        'anon 500000000',
        'kernel_stack 1024',
        'slab 2000000',
    ].join('\n') + '\n';
    assert.equal(parseMemoryStat(content).file, 0);
});

test('parseMemoryStat skips malformed lines without throwing', () => {
    const content = [
        '',
        '   ',
        'not_a_keyvalue_line',
        'file abcdef',           // non-numeric value
        'file 5800000000',       // valid — should win
        'kernel_stack 1024',
        '   garbage with spaces',
    ].join('\n') + '\n';
    assert.equal(parseMemoryStat(content).file, 5800000000);
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -20
```
Expected: FAIL with import error — `parseMemoryStat` not exported from `../cgroupMemory.js` (module does not exist yet).

- [ ] **Step 3: Create `cgroupMemory.ts`**

Create `apps-microservices/crawler-service/crawler/src/cgroupMemory.ts`:

```ts
// Cgroup memory reader with page-cache subtraction (Spec-B 2026-05-21).
//
// `memory.current` (v2) and `memory.usage_in_bytes` (v1) include page cache
// (reclaimable filesystem cache). Linux reclaims that on demand before invoking
// the OOM-killer. Treating it as "used" inflates the percentage when prior I/O
// loaded the cache — observed at 99.7% on shop.monlabofermier.fr crawl 6334.
//
// Fix: subtract the `file` (v2) / `cache` (v1) bytes from memory.current to get
// the "usable used" view (anon + slab + kernel + sock — non-reclaimable).
//
// Module is side-effect-free so it can be unit-tested in isolation (main.ts has
// top-level execution that fires on import, breaking direct test imports —
// same constraint that drove browserKill.ts extraction in Spec-A).

import fsPromises from "node:fs/promises";
import os from "node:os";

export interface UsableMemory {
    /** memory.current - file (v2) or memory.usage_in_bytes - cache (v1). */
    usableUsed: number;
    /** memory.max (v2) or memory.limit_in_bytes (v1) or os.totalmem() (host fallback). */
    totalMem: number;
    /** memory.current (v2) or memory.usage_in_bytes (v1) or os.totalmem()-os.freemem() (host fallback). */
    rawCurrent: number;
    /** file (v2) or cache (v1); 0 on host fallback (no cgroup visibility). */
    pageCache: number;
}

/**
 * Parses a cgroup memory.stat file content and returns the page-cache bytes.
 * v2 uses the `file` key; v1 uses the `cache` key. Returns { file: 0 } when
 * neither key is present. Malformed lines (blank, missing value, non-numeric)
 * are skipped silently.
 */
export function parseMemoryStat(content: string): { file: number } {
    let file = 0;
    for (const line of content.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const parts = trimmed.split(/\s+/);
        if (parts.length < 2) continue;
        const [key, rawValue] = parts;
        if (key !== "file" && key !== "cache") continue;
        const value = parseInt(rawValue, 10);
        if (!Number.isFinite(value) || Number.isNaN(value)) continue;
        file = value;
        // Don't break — last valid line wins (defensive against malformed content).
    }
    return { file };
}

async function readFileOrNull(path: string): Promise<string | null> {
    try {
        return await fsPromises.readFile(path, "utf-8");
    } catch {
        return null;
    }
}

/**
 * Reads cgroup memory.{max,current,stat} (v2 first, v1 fallback, host last)
 * and returns the usable-used view. Returns null only when all three fallback
 * paths fail (true I/O failure — never expected in a Linux Docker container).
 */
export async function readUsableMemory(): Promise<UsableMemory | null> {
    // cgroup v2
    const v2Max = await readFileOrNull("/sys/fs/cgroup/memory.max");
    const v2Current = await readFileOrNull("/sys/fs/cgroup/memory.current");
    const v2Stat = await readFileOrNull("/sys/fs/cgroup/memory.stat");
    if (v2Max && v2Current && v2Stat && v2Max.trim() !== "max") {
        const totalMem = parseInt(v2Max.trim(), 10);
        const rawCurrent = parseInt(v2Current.trim(), 10);
        const { file: pageCache } = parseMemoryStat(v2Stat);
        return { usableUsed: rawCurrent - pageCache, totalMem, rawCurrent, pageCache };
    }

    // cgroup v1
    const v1Limit = await readFileOrNull("/sys/fs/cgroup/memory/memory.limit_in_bytes");
    const v1Usage = await readFileOrNull("/sys/fs/cgroup/memory/memory.usage_in_bytes");
    const v1Stat = await readFileOrNull("/sys/fs/cgroup/memory/memory.stat");
    if (v1Limit && v1Usage && v1Stat) {
        const totalMem = parseInt(v1Limit.trim(), 10);
        const rawCurrent = parseInt(v1Usage.trim(), 10);
        const { file: pageCache } = parseMemoryStat(v1Stat);
        return { usableUsed: rawCurrent - pageCache, totalMem, rawCurrent, pageCache };
    }

    // Host fallback (no cgroup, e.g., local dev outside Docker)
    try {
        const totalMem = os.totalmem();
        const rawCurrent = totalMem - os.freemem();
        return { usableUsed: rawCurrent, totalMem, rawCurrent, pageCache: 0 };
    } catch {
        return null;
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -10
```
Expected: 58 tests pass / 0 fail. The 4 new parseMemoryStat tests appear in the output.

- [ ] **Step 5: Run typecheck**

```bash
cd apps-microservices/crawler-service/crawler && npm run build 2>&1 | tail -3
```
Expected: tsc emits no errors. `dist/` populated.

- [ ] **Step 6: Confirm main.ts untouched**

```bash
cd apps-microservices/crawler-service/crawler && grep -nE "readUsableMemory|parseMemoryStat" src/main.ts
```
Expected: no matches (main.ts will be wired up in T2).

- [ ] **Step 7: Commit**

Ask: "Which language for the commit message? (EN / FR / both)" — user session preference: Both. Do NOT re-ask.

Use Write tool for `.git/COMMIT_EDITMSG` (UTF-8 — Windows cp1252 hazard). Read first; may have stale content. Then:

```bash
git add apps-microservices/crawler-service/crawler/src/cgroupMemory.ts \
        apps-microservices/crawler-service/crawler/src/tests/cgroupMemory.test.ts && \
    git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Suggested subject: `feat(crawler-service): add cgroupMemory module (parseMemoryStat + readUsableMemory)`

Body must explain: introduces side-effect-free module mirroring Spec-A's browserKill.ts extraction; parser handles cgroup v2 (`file`) + v1 (`cache`); composition tries v2 → v1 → host fallback → null; 4 unit tests lock parser behaviour; callsites unchanged in this task (T2 wires them). Bilingual EN+FR.

---

## Task 2: Refactor `main.ts` pre-flight + `readContainerMemory` to use `readUsableMemory()`; dual log format

**Goal:** Replace the inline cgroup-reading block in pre-flight (lines 189-231) and the `readContainerMemory` body (lines 239-270) with calls to `readUsableMemory()`. Pre-flight log line switches to dual format (usable + raw + page cache). Watchdog uses an adapter so Tier 1/2 handlers' return shape stays unchanged.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts`

**Acceptance Criteria:**
- [ ] New import `import { readUsableMemory } from "./cgroupMemory.js";` added near other relative imports.
- [ ] Pre-flight block (lines 189-231): old inline cgroup-reading + threshold + log replaced with `readUsableMemory()` call + null check (warn-and-skip path) + dual-format log + threshold on `usableUsed/totalMem`.
- [ ] `readContainerMemory` body (lines 239-270): replaced with adapter that returns `{ usedMem: mem.usableUsed, totalMem: mem.totalMem }` (or null when `readUsableMemory()` returns null).
- [ ] Dual log format: `💾 Memory status: ${gb(usableUsed)}GB usable / ${gb(rawCurrent)}GB raw / ${gb(totalMem)}GB limit (${usablePercent.toFixed(1)}% usable, ${rawPercent.toFixed(1)}% raw, ${gb(pageCache)}GB page cache).`
- [ ] Local `gb()` lambda or const defined once near the pre-flight block (DRY — old code repeated the `/ 1024 / 1024 / 1024` arithmetic at lines 222, 226).
- [ ] `containerMemoryMb` constant at line 237 still computed from `totalMem` (semantics unchanged).
- [ ] Threshold check: `if (usablePercent > 80) { … process.exit(3); }`.
- [ ] Tier 1/2 handler log strings unchanged in this task — T3 target.
- [ ] `npm test` green (58 tests). `npm run build` clean.

**Verify:**
```bash
cd apps-microservices/crawler-service/crawler && \
    grep -nE "/sys/fs/cgroup/memory\\.(max|current|stat)|fsPromises\\.readFile.*memory" src/main.ts ; \
    npm test 2>&1 | tail -5 && npm run build 2>&1 | tail -3
```
Expected:
- `grep` returns no matches (all cgroup file reads moved to `cgroupMemory.ts`).
- 58 tests pass. tsc clean.

**Steps:**

- [ ] **Step 1: Add the import**

Locate the existing import block near top of `apps-microservices/crawler-service/crawler/src/main.ts` (currently around line 43 contains `import { killBrowserProcesses } from "./browserKill.js";`). Add immediately below:

```ts
import { readUsableMemory } from "./cgroupMemory.js";
```

- [ ] **Step 2: Replace the pre-flight block**

Locate the current pre-flight cgroup block (lines 187-231 — starts with `// 2. Check available memory` comment, ends with `console.log('✅ Pre-flight checks passed. Starting crawler...');`). Currently:

```ts
// 2. Check available memory (Docker container limits, not host VM)
let totalMem: number;
let freeMem: number;

try {
    // Try to read Docker container memory limit from cgroups v2
    const cgroupMemMax = await fsPromises.readFile('/sys/fs/cgroup/memory.max', 'utf-8').catch(() => null);
    const cgroupMemCurrent = await fsPromises.readFile('/sys/fs/cgroup/memory.current', 'utf-8').catch(() => null);

    if (cgroupMemMax && cgroupMemCurrent && cgroupMemMax.trim() !== 'max') {
        totalMem = parseInt(cgroupMemMax.trim());
        const usedMem = parseInt(cgroupMemCurrent.trim());
        freeMem = totalMem - usedMem;
    } else {
        // Try cgroups v1 (older Docker versions)
        const cgroupMemLimitV1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'utf-8').catch(() => null);
        const cgroupMemUsageV1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'utf-8').catch(() => null);

        if (cgroupMemLimitV1 && cgroupMemUsageV1) {
            totalMem = parseInt(cgroupMemLimitV1.trim());
            const usedMem = parseInt(cgroupMemUsageV1.trim());
            freeMem = totalMem - usedMem;
        } else {
            // Fallback to host memory (not in Docker or cgroups not available)
            totalMem = os.totalmem();
            freeMem = os.freemem();
        }
    }
} catch (e) {
    // Fallback to host memory if cgroup reading fails
    totalMem = os.totalmem();
    freeMem = os.freemem();
}

const usedMem = totalMem - freeMem;
const memPercent = (usedMem / totalMem) * 100;

console.log(`💾 Memory status: ${(usedMem / 1024 / 1024 / 1024).toFixed(2)}GB / ${(totalMem / 1024 / 1024 / 1024).toFixed(2)}GB (${memPercent.toFixed(1)}% used)`);

if (memPercent > 80) {
    console.error(`❌ Memory critically low: ${memPercent.toFixed(1)}% used. Aborting to prevent OOM.`);
    console.error(`   Free memory: ${(freeMem / 1024 / 1024 / 1024).toFixed(2)}GB`);
    console.error(`🔄 Pre-flight OOM: exiting with code 3 (OOM_RELAUNCH) to trigger Python-side auto-restart.`);
    process.exit(3); // OOM_RELAUNCH: trigger Python-side auto-restart
}

console.log('✅ Pre-flight checks passed. Starting crawler...');
```

Replace with:

```ts
// 2. Check available memory (Docker container limits, not host VM)
// Page cache is subtracted from used because Linux reclaims it on demand
// before invoking the OOM-killer (Spec-B 2026-05-21).
const gb = (n: number) => (n / 1024 / 1024 / 1024).toFixed(2);
let totalMem: number;

const mem = await readUsableMemory();
if (!mem) {
    // Cannot measure memory. Skip pre-flight — assume OK rather than block startup.
    console.warn('⚠️  Pre-flight: readUsableMemory() returned null. Skipping threshold check.');
    totalMem = os.totalmem();
} else {
    totalMem = mem.totalMem;
    const usablePercent = (mem.usableUsed / mem.totalMem) * 100;
    const rawPercent = (mem.rawCurrent / mem.totalMem) * 100;
    console.log(
        `💾 Memory status: ${gb(mem.usableUsed)}GB usable / ${gb(mem.rawCurrent)}GB raw / ` +
        `${gb(mem.totalMem)}GB limit ` +
        `(${usablePercent.toFixed(1)}% usable, ${rawPercent.toFixed(1)}% raw, ${gb(mem.pageCache)}GB page cache).`
    );
    if (usablePercent > 80) {
        console.error(`❌ Memory critically low: ${usablePercent.toFixed(1)}% usable used. Aborting to prevent OOM.`);
        console.error(`🔄 Pre-flight OOM: exiting with code 3 (OOM_RELAUNCH) to trigger Python-side auto-restart.`);
        process.exit(3);
    }
}

console.log('✅ Pre-flight checks passed. Starting crawler...');
```

Notes:
- `totalMem` is preserved outside the `if/else` because line ~237 reads it: `const containerMemoryMb = Math.floor(totalMem / 1024 / 1024);`. On null path it falls back to `os.totalmem()` matching old behaviour.
- The `freeMem` local from the old code is no longer needed — old log "Free memory:" line is removed because the dual format already shows raw+limit which makes free derivable.
- The `gb()` lambda inlines the `/ 1024 / 1024 / 1024` arithmetic that the old code repeated.

- [ ] **Step 3: Replace `readContainerMemory` body**

Locate the current `readContainerMemory` function (around lines 239-270). Currently:

```ts
const readContainerMemory = async (): Promise<{ usedMem: number; totalMem: number } | null> => {
    try {
        const cgroupMemMax = await fsPromises.readFile('/sys/fs/cgroup/memory.max', 'utf-8').catch(() => null);
        const cgroupMemCurrent = await fsPromises.readFile('/sys/fs/cgroup/memory.current', 'utf-8').catch(() => null);

        if (cgroupMemMax && cgroupMemCurrent && cgroupMemMax.trim() !== 'max') {
            return {
                totalMem: parseInt(cgroupMemMax.trim()),
                usedMem: parseInt(cgroupMemCurrent.trim())
            };
        }

        // Fallback to cgroups v1
        const cgroupMemLimitV1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'utf-8').catch(() => null);
        const cgroupMemUsageV1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'utf-8').catch(() => null);

        if (cgroupMemLimitV1 && cgroupMemUsageV1) {
            return {
                totalMem: parseInt(cgroupMemLimitV1.trim()),
                usedMem: parseInt(cgroupMemUsageV1.trim())
            };
        }

        // Fallback to OS-level
        return {
            totalMem: os.totalmem(),
            usedMem: os.totalmem() - os.freemem()
        };
    } catch (e) {
        return null;
    }
};
```

Replace with:

```ts
// Adapter over readUsableMemory(): preserves the {usedMem, totalMem} shape
// expected by Tier 1/2 handlers while shifting `usedMem` semantics from raw
// memory.current to usable used (= memory.current - page cache).
const readContainerMemory = async (): Promise<{ usedMem: number; totalMem: number } | null> => {
    const mem = await readUsableMemory();
    if (!mem) return null;
    return { usedMem: mem.usableUsed, totalMem: mem.totalMem };
};
```

- [ ] **Step 4: Verify no cgroup file paths remain in main.ts**

```bash
cd apps-microservices/crawler-service/crawler && grep -nE "/sys/fs/cgroup" src/main.ts
```
Expected: zero matches (grep exits 1).

- [ ] **Step 5: Run tests + typecheck**

```bash
cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -8 && npm run build 2>&1 | tail -3
```
Expected: 58 pass / 0 fail. tsc clean.

- [ ] **Step 6: Commit**

Ask: "Which language for the commit message? (EN / FR / both)" — user session preference: Both. Do NOT re-ask.

Use Write tool for `.git/COMMIT_EDITMSG`. Read first; stale. Then:

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts && \
    git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Suggested subject: `fix(crawler-service): subtract page cache from memory threshold`

Body must explain: pre-flight + watchdog now call `readUsableMemory()`; `usedMem` semantics shift from raw memory.current to `current - file` (page cache reclaimable on demand by Linux); thresholds unchanged numerically (80/85/92) — more tolerant under heavy I/O without losing real anon/slab pressure detection; pre-flight log line switches to dual format showing usable + raw + page cache for operator diagnostics. Bilingual EN+FR.

---

## Task 3: Update Tier 1 + Tier 2 handler log strings to "% usable" suffix

**Goal:** After T2, the `memPercent` value passed to `handleWarningMemory` (Tier 1) and `handleCriticalMemory` (Tier 2) reflects usable %, not raw %. Update the log strings in those handlers (and the Phase B re-check) so operators see the metric they're actually reading.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts`

**Acceptance Criteria:**
- [ ] Tier 1 entry log changes from `⚠️  [Tier 1] Memory Warning (${memPercent.toFixed(1)}%). executing proactive recovery...` to `⚠️  [Tier 1] Memory Warning (${memPercent.toFixed(1)}% usable). executing proactive recovery...`.
- [ ] Tier 2 entry log changes from `❌ [Tier 2] Memory CRITICAL (${memPercent.toFixed(1)}%). Initiating Phase A Recovery...` to `❌ [Tier 2] Memory CRITICAL (${memPercent.toFixed(1)}% usable). Initiating Phase A Recovery...`.
- [ ] Tier 2 Phase B retry log changes from `❌ [Tier 2] Memory STILL CRITICAL (${memPercent.toFixed(1)}%) after recovery. Initiating Phase B: Auto-Relaunch...` to `❌ [Tier 2] Memory STILL CRITICAL (${memPercent.toFixed(1)}% usable) after recovery. Initiating Phase B: Auto-Relaunch...`.
- [ ] No other handler behaviour changes. Phase A recovery flow (kill browsers, emergency persist, double GC, return) unchanged.
- [ ] `npm test` green. `npm run build` clean.

**Verify:**
```bash
cd apps-microservices/crawler-service/crawler && \
    grep -nE "% usable\\)" src/main.ts ; \
    npm test 2>&1 | tail -5 && npm run build 2>&1 | tail -3
```
Expected:
- `grep` returns 3 matches (Tier 1, Tier 2, Phase B retry).
- 58 tests pass. tsc clean.

**Steps:**

- [ ] **Step 1: Update Tier 1 entry log**

In `apps-microservices/crawler-service/crawler/src/main.ts`, locate the Tier 1 handler `handleWarningMemory` (around line 278). The current entry log line (around line 283):

```ts
    console.warn(`⚠️  [Tier 1] Memory Warning (${memPercent.toFixed(1)}%). executing proactive recovery...`);
```

Change to:

```ts
    console.warn(`⚠️  [Tier 1] Memory Warning (${memPercent.toFixed(1)}% usable). executing proactive recovery...`);
```

- [ ] **Step 2: Update Tier 2 entry log**

Locate `handleCriticalMemory` (around line 315). The current Phase A entry log (around line 320):

```ts
        console.error(`❌ [Tier 2] Memory CRITICAL (${memPercent.toFixed(1)}%). Initiating Phase A Recovery...`);
```

Change to:

```ts
        console.error(`❌ [Tier 2] Memory CRITICAL (${memPercent.toFixed(1)}% usable). Initiating Phase A Recovery...`);
```

- [ ] **Step 3: Update Tier 2 Phase B retry log**

Still in `handleCriticalMemory`. The Phase B re-check log (around line 357 — line numbers shift due to T2 changes; search for `STILL CRITICAL`):

```ts
    console.error(`❌ [Tier 2] Memory STILL CRITICAL (${memPercent.toFixed(1)}%) after recovery. Initiating Phase B: Auto-Relaunch...`);
```

Change to:

```ts
    console.error(`❌ [Tier 2] Memory STILL CRITICAL (${memPercent.toFixed(1)}% usable) after recovery. Initiating Phase B: Auto-Relaunch...`);
```

- [ ] **Step 4: Verify exactly 3 occurrences**

```bash
cd apps-microservices/crawler-service/crawler && grep -nE "% usable\\)" src/main.ts
```
Expected output: 3 matches — Tier 1, Tier 2 entry, Phase B retry (in that order, line numbers around 283, 320, 357 ± shift from T2).

- [ ] **Step 5: Run tests + typecheck**

```bash
cd apps-microservices/crawler-service/crawler && npm test 2>&1 | tail -5 && npm run build 2>&1 | tail -3
```
Expected: 58 tests pass / 0 fail. tsc clean.

- [ ] **Step 6: Operator smoke prerequisite (note for executing agent)**

No further code changes for Spec-B. Operator smoke per spec § 5.2 happens post-deploy:

1. Deploy `features/poc` to one dev/staging replica.
2. Inspect `crawler.log` of any newly-started crawl. New dual-format log line should show two percentages.
3. Cross-check `pageCache` value against `cat /sys/fs/cgroup/memory.stat | grep ^file` inside the container.
4. On a replica that historically hit the OOM_RELAUNCH loop (`shop.monlabofermier.fr`), confirm pre-flight passes with `usablePercent < 80%` even when raw is high.

This is operator-driven verification, not a coded step.

- [ ] **Step 7: Commit**

Ask: "Which language for the commit message? (EN / FR / both)" — user session preference: Both. Do NOT re-ask.

Use Write tool for `.git/COMMIT_EDITMSG`. Read first; stale. Then:

```bash
git add apps-microservices/crawler-service/crawler/src/main.ts && \
    git -c commit.encoding=utf-8 commit -F .git/COMMIT_EDITMSG
```

Suggested subject: `fix(crawler-service): label Tier 1/2 watchdog logs as % usable`

Body must explain: after T2 the watchdog's `memPercent` reflects usable% (page cache subtracted); update the three log strings (Tier 1 entry, Tier 2 entry, Phase B retry) so operators know which metric they're seeing. Closes Spec-B. Bilingual EN+FR.

---

## Self-Review

**Spec coverage:**
- § 2 goal "subtract page cache" → T1 (parser + composition) + T2 (callsite refactor)
- § 2 goal "centralise in side-effect-free module" → T1 module creation
- § 2 goal "surface page-cache delta in operator logs" → T2 dual-format log + T3 % usable labels
- § 2 goal "keep thresholds 80/85/92 numerically" → preserved across T2 + T3
- § 4.1 module interface → T1
- § 4.2 lookup order → T1 Step 3 code block
- § 4.3 pre-flight refactor → T2 Step 2
- § 4.4 watchdog adapter → T2 Step 3
- § 4.5 Tier 1/2 handler log strings → T3
- § 4.6 data flow → covered by T1+T2+T3 composition
- § 4.7 backward compat → § 7 risks, no migration needed
- § 5.1 unit tests (4 parser fixtures) → T1
- § 5.2 operator smoke → T3 Step 6

**Placeholder scan:** No "TBD" / "TODO" / vague guidance. Every code block is the actual content. Every command is runnable.

**Type consistency:** `UsableMemory` interface defined in T1, used implicitly by T2 (callers pull `usableUsed`, `totalMem`, `rawCurrent`, `pageCache`). `readUsableMemory` signature consistent (T1 definition matches T2 + T3 callsites). `readContainerMemory` return shape unchanged (`{usedMem, totalMem}`) — Tier 1/2 handlers don't need updates beyond log strings.

**Verify commands:** All use `cd apps-microservices/crawler-service/crawler && ...` since `npm test` and `npm run build` run from the crawler subdirectory.
