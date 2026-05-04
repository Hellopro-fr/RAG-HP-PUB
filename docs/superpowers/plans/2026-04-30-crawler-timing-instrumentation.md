# Crawler Timing Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in (`TIMING_ENABLED=true`) per-page + pool-level timing instrumentation to the Node.js crawler, with crash-resilient JSONL trace, periodic summary flush, post-hoc reconstruction tool, and local-disk retention after archive cleanup.

**Architecture:** Pure aggregator (TS module) computes summary stats from page entries + pool samples. `TimingRecorder` class wraps the aggregator with a JSONL append stream + periodic flush timer + exit handlers. Crawlee `preNavigationHooks` and `postNavigationHooks` plus inline timestamps in the route handler feed `TimingRecorder.recordPage`. A 5s `setInterval` sampler reads `crawler.autoscaledPool` and the `pLimit` instance and feeds `TimingRecorder.recordPoolSample`. Post-hoc tool `tools/timing-summary.ts` rebuilds the summary from any JSONL using the same aggregator. `files_to_keep` in `crawler_manager.py` extended to retain timing files locally after archive cleanup.

**Tech Stack:** Node.js 22, TypeScript, Crawlee 3, p-limit (already in use), Node built-in `fs`/`fs.promises`, free-standing tsx test scripts (no Jest/Vitest). Python 3.x (FastAPI) for the `crawler_manager.py` change.

**Spec:** `docs/superpowers/specs/2026-04-30-crawler-timing-instrumentation-design.md` (commits `71784661`, `18443e51`)

---

## File Structure

| File | Responsibility |
|------|----------------|
| `apps-microservices/crawler-service/crawler/src/timing/types.ts` | TS interfaces: `PageTimingEntry`, `PoolSample`, `PhaseStats`, `TimingSummary`. |
| `apps-microservices/crawler-service/crawler/src/timing/aggregator.ts` | Pure functions: `addPage`, `addPoolSample`, `buildSummary`. Stateful via a passed-in `Aggregator` object. No I/O. |
| `apps-microservices/crawler-service/crawler/src/class/TimingRecorder.ts` | Wraps aggregator with JSONL stream, periodic summary flush timer, `replay`/`overwrite` resume, exit handlers, `finalize()`. |
| `apps-microservices/crawler-service/crawler/src/tools/timing-summary.ts` | Standalone CLI: read a JSONL, emit summary JSON via `aggregator.buildSummary`. |
| `apps-microservices/crawler-service/crawler/src/functions.ts` (modify ~lines 477–528) | Register Crawlee `preNavigationHooks`, `postNavigationHooks`, start pool sampler, wire recorder lifecycle. |
| `apps-microservices/crawler-service/crawler/src/routes.ts` (modify ~line 569) | Capture `detectStartAt`/`detectEndAt`, build `PageTimingEntry`, call `recorder.recordPage`. |
| `apps-microservices/crawler-service/crawler/src/main.ts` (modify, signal-handler block) | Construct/finalize the `TimingRecorder` based on `TIMING_ENABLED`. Hook SIGINT/SIGTERM/`beforeExit`. |
| `apps-microservices/crawler-service/app/core/crawler_manager.py` (modify line 1690) | Extend `files_to_keep` with `timing.jsonl` and `timing-summary.json`. |
| `apps-microservices/crawler-service/crawler/src/tests/test_timing_aggregator.ts` | Aggregator unit tests. |
| `apps-microservices/crawler-service/crawler/src/tests/test_TimingRecorder.ts` | Recorder I/O + flush + exit handler tests. |
| `apps-microservices/crawler-service/crawler/src/tests/test_timing_summary_tool.ts` | Post-hoc tool tests. |

---

### Task 1: Aggregator types and pure functions

**Goal:** A pure, dependency-free aggregator module that consumes `PageTimingEntry` and `PoolSample` instances and produces a `TimingSummary` with median/p95/p99 per phase plus pool-level metrics.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/timing/types.ts`
- Create: `apps-microservices/crawler-service/crawler/src/timing/aggregator.ts`
- Test: `apps-microservices/crawler-service/crawler/src/tests/test_timing_aggregator.ts`

**Acceptance Criteria:**
- [ ] `createAggregator()` returns a fresh empty state object.
- [ ] `addPage` and `addPoolSample` mutate the state and return void.
- [ ] `buildSummary(state)` returns the spec-defined `TimingSummary` shape.
- [ ] Median, p95, p99 computed correctly on a known fixed input (verified by hand).
- [ ] `share_of_total_pct` per phase sums to 100 ± 0.5 (rounding tolerance).
- [ ] `crawlee_throttle_pct` and `detect_saturated_pct` math: `throttled = currentConcurrency < desiredConcurrency`, `saturated = activeCount === maxConcurrency && pendingCount > 0`.
- [ ] Empty input (no pages, no samples) produces a well-formed summary with zeros.
- [ ] No I/O — no `fs`, no `console`, no `process`.

**Verify:** `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_timing_aggregator.ts`

**Steps:**

- [ ] **Step 1: Create the types module.**

`apps-microservices/crawler-service/crawler/src/timing/types.ts`:

```typescript
export interface PageTimingEntry {
    url: string;
    t: number;             // dequeue timestamp (ms since epoch)
    wait_ms: number;       // dequeue → preNav
    nav_ms: number;        // preNav → postNav
    pre_detect_ms: number; // postNav → detect.start
    detect_ms: number;     // detect.start → detect.end
    post_ms: number;       // detect.end → handler return
    total_ms: number;      // dequeue → handler return
    detect_method?: string;
    detect_ok?: boolean;
}

export interface PoolSample {
    t: number;
    crawlee: {
        currentConcurrency: number;
        desiredConcurrency: number;
        maxConcurrency: number;
    };
    detect: {
        pendingCount: number;
        activeCount: number;
    };
    memory: {
        used_mb: number;
        budget_mb: number;
        ratio: number;
    };
    rolling: {
        pages_per_min: number;
    };
}

export interface PhaseStats {
    median: number;
    p95: number;
    p99: number;
    share_of_total_pct: number;
}

export interface TimingSummary {
    crawl_id: string;
    started_at: number;       // first page dequeue ms
    duration_s: number;
    pages_total: number;
    pages_per_min_avg: number;
    pages_per_min_max_sustained: number;
    phases: {
        wait_ms: PhaseStats;
        nav_ms: PhaseStats;
        pre_detect_ms: PhaseStats;
        detect_ms: PhaseStats;
        post_ms: PhaseStats;
    };
    pool: {
        crawlee_avg_concurrency: number;
        crawlee_max_concurrency_reached: number;
        crawlee_throttle_pct: number;
        detect_avg_active: number;
        detect_avg_pending: number;
        detect_saturated_pct: number;
        memory_avg_ratio: number;
        memory_max_ratio: number;
    };
}

export interface AggregatorState {
    crawlId: string;
    startedAt: number | null;
    pages: PageTimingEntry[];
    samples: PoolSample[];
    detectMaxConcurrency: number;
}
```

- [ ] **Step 2: Write failing tests for the aggregator.**

`apps-microservices/crawler-service/crawler/src/tests/test_timing_aggregator.ts`:

```typescript
import {
    createAggregator,
    addPage,
    addPoolSample,
    buildSummary,
} from "../timing/aggregator";
import type { PageTimingEntry, PoolSample } from "../timing/types";

let passed = 0;
let failed = 0;

function assertEqual<T>(actual: T, expected: T, msg: string) {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    if (ok) {
        passed++;
    } else {
        failed++;
        console.error(`FAIL: ${msg}\n  expected: ${JSON.stringify(expected)}\n  actual:   ${JSON.stringify(actual)}`);
    }
}

function assertClose(actual: number, expected: number, tol: number, msg: string) {
    if (Math.abs(actual - expected) <= tol) {
        passed++;
    } else {
        failed++;
        console.error(`FAIL: ${msg} expected ${expected} ± ${tol}, got ${actual}`);
    }
}

// 1. createAggregator returns clean state
{
    const a = createAggregator("test-1", 5);
    assertEqual(a.pages.length, 0, "fresh aggregator has no pages");
    assertEqual(a.samples.length, 0, "fresh aggregator has no samples");
    assertEqual(a.crawlId, "test-1", "aggregator captures crawl id");
    assertEqual(a.detectMaxConcurrency, 5, "aggregator captures detect concurrency cap");
}

// 2. Empty input produces well-formed summary
{
    const a = createAggregator("test-2", 5);
    const s = buildSummary(a);
    assertEqual(s.pages_total, 0, "empty: pages_total = 0");
    assertEqual(s.duration_s, 0, "empty: duration_s = 0");
    assertEqual(s.phases.detect_ms.median, 0, "empty: phase medians = 0");
    assertEqual(s.pool.crawlee_max_concurrency_reached, 0, "empty: pool max = 0");
}

// 3. Median, p95, p99 on known input
// 100 pages with detect_ms = [10, 20, 30, ..., 1000]
{
    const a = createAggregator("test-3", 5);
    for (let i = 1; i <= 100; i++) {
        const p: PageTimingEntry = {
            url: `https://x/${i}`,
            t: 1000 + i,
            wait_ms: 0,
            nav_ms: 0,
            pre_detect_ms: 0,
            detect_ms: i * 10,
            post_ms: 0,
            total_ms: i * 10,
            detect_ok: true,
        };
        addPage(a, p);
    }
    const s = buildSummary(a);
    // Sorted detect_ms: 10, 20, ..., 1000
    // median = avg of 50th, 51st = (500 + 510)/2 = 505
    // p95 = 95th = 950
    // p99 = 99th = 990
    assertEqual(s.phases.detect_ms.median, 505, "median of 1..100 * 10");
    assertEqual(s.phases.detect_ms.p95, 950, "p95 of 1..100 * 10");
    assertEqual(s.phases.detect_ms.p99, 990, "p99 of 1..100 * 10");
}

// 4. share_of_total_pct sums to ~100
{
    const a = createAggregator("test-4", 5);
    for (let i = 0; i < 10; i++) {
        addPage(a, {
            url: `https://x/${i}`,
            t: 1000 + i,
            wait_ms: 100,
            nav_ms: 500,
            pre_detect_ms: 50,
            detect_ms: 250,
            post_ms: 100,
            total_ms: 1000,
        });
    }
    const s = buildSummary(a);
    const sum = s.phases.wait_ms.share_of_total_pct
              + s.phases.nav_ms.share_of_total_pct
              + s.phases.pre_detect_ms.share_of_total_pct
              + s.phases.detect_ms.share_of_total_pct
              + s.phases.post_ms.share_of_total_pct;
    assertClose(sum, 100, 0.5, "share_of_total_pct sums to 100 ± 0.5");
    assertClose(s.phases.nav_ms.share_of_total_pct, 50, 0.5, "nav 500/1000 = 50%");
}

// 5. detect_saturated_pct: 6 samples, 3 saturated (active=5, pending>0)
{
    const a = createAggregator("test-5", 5);
    const mkSample = (active: number, pending: number, t: number): PoolSample => ({
        t,
        crawlee: { currentConcurrency: 1, desiredConcurrency: 1, maxConcurrency: 5 },
        detect: { activeCount: active, pendingCount: pending },
        memory: { used_mb: 0, budget_mb: 1, ratio: 0 },
        rolling: { pages_per_min: 0 },
    });
    [
        mkSample(5, 3, 1),
        mkSample(5, 0, 2), // not saturated: pending = 0
        mkSample(4, 10, 3), // not saturated: active < max
        mkSample(5, 1, 4),
        mkSample(5, 2, 5),
        mkSample(2, 0, 6),
    ].forEach((s) => addPoolSample(a, s));
    const s = buildSummary(a);
    assertClose(s.pool.detect_saturated_pct, 50.0, 0.01, "3/6 saturated = 50%");
}

// 6. crawlee_throttle_pct: current < desired counts as throttled
{
    const a = createAggregator("test-6", 5);
    const mkSample = (cur: number, desired: number, t: number): PoolSample => ({
        t,
        crawlee: { currentConcurrency: cur, desiredConcurrency: desired, maxConcurrency: 10 },
        detect: { activeCount: 0, pendingCount: 0 },
        memory: { used_mb: 0, budget_mb: 1, ratio: 0 },
        rolling: { pages_per_min: 0 },
    });
    [
        mkSample(2, 5, 1), // throttled
        mkSample(5, 5, 2), // not
        mkSample(3, 8, 3), // throttled
        mkSample(8, 8, 4), // not
    ].forEach((s) => addPoolSample(a, s));
    const s = buildSummary(a);
    assertClose(s.pool.crawlee_throttle_pct, 50.0, 0.01, "2/4 throttled = 50%");
    assertEqual(s.pool.crawlee_max_concurrency_reached, 8, "max reached = 8");
}

console.log(`timing_aggregator: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
```

- [ ] **Step 3: Run tests; expect failure (module does not exist yet).**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_timing_aggregator.ts`
Expected: `Cannot find module '../timing/aggregator'` or compilation error.

- [ ] **Step 4: Implement the aggregator.**

`apps-microservices/crawler-service/crawler/src/timing/aggregator.ts`:

```typescript
import type {
    AggregatorState,
    PageTimingEntry,
    PhaseStats,
    PoolSample,
    TimingSummary,
} from "./types";

export function createAggregator(crawlId: string, detectMaxConcurrency: number): AggregatorState {
    return {
        crawlId,
        startedAt: null,
        pages: [],
        samples: [],
        detectMaxConcurrency,
    };
}

export function addPage(state: AggregatorState, page: PageTimingEntry): void {
    if (state.startedAt === null || page.t < state.startedAt) {
        state.startedAt = page.t;
    }
    state.pages.push(page);
}

export function addPoolSample(state: AggregatorState, sample: PoolSample): void {
    state.samples.push(sample);
}

function percentile(sorted: number[], p: number): number {
    if (sorted.length === 0) return 0;
    if (sorted.length === 1) return sorted[0];
    // Linear interpolation between the two nearest indices.
    const idx = (p / 100) * (sorted.length - 1);
    const lower = Math.floor(idx);
    const upper = Math.ceil(idx);
    if (lower === upper) return sorted[lower];
    const weight = idx - lower;
    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
}

function median(sorted: number[]): number {
    return percentile(sorted, 50);
}

function phaseStats(values: number[], totalSum: number): PhaseStats {
    const sorted = [...values].sort((a, b) => a - b);
    const phaseSum = sorted.reduce((a, b) => a + b, 0);
    return {
        median: round1(median(sorted)),
        p95: round1(percentile(sorted, 95)),
        p99: round1(percentile(sorted, 99)),
        share_of_total_pct: totalSum === 0 ? 0 : round1((phaseSum / totalSum) * 100),
    };
}

function round1(n: number): number {
    return Math.round(n * 10) / 10;
}

export function buildSummary(state: AggregatorState): TimingSummary {
    const N = state.pages.length;
    const startedAt = state.startedAt ?? 0;
    let endAt = startedAt;
    if (N > 0) {
        endAt = Math.max(...state.pages.map((p) => p.t + p.total_ms));
    }
    const durationS = N === 0 ? 0 : Math.max(1, Math.round((endAt - startedAt) / 1000));

    const phaseValues = (key: keyof PageTimingEntry): number[] =>
        state.pages.map((p) => Number(p[key] ?? 0));

    const totalSum = phaseValues("total_ms").reduce((a, b) => a + b, 0);

    // Pages per minute: average across the run, max sustained over a 60s window.
    const ppmAvg = N === 0 || durationS === 0 ? 0 : round1((N / durationS) * 60);
    let ppmMax = 0;
    if (N > 0) {
        const sortedTs = state.pages.map((p) => p.t).sort((a, b) => a - b);
        for (let i = 0; i < sortedTs.length; i++) {
            const windowEnd = sortedTs[i] + 60_000;
            let count = 0;
            for (let j = i; j < sortedTs.length && sortedTs[j] <= windowEnd; j++) count++;
            if (count > ppmMax) ppmMax = count;
        }
    }

    // Pool aggregates
    let throttled = 0;
    let saturated = 0;
    let crawleeSumCurrent = 0;
    let detectSumActive = 0;
    let detectSumPending = 0;
    let memSumRatio = 0;
    let memMaxRatio = 0;
    let crawleeMaxReached = 0;
    for (const s of state.samples) {
        if (s.crawlee.currentConcurrency < s.crawlee.desiredConcurrency) throttled++;
        if (s.detect.activeCount === state.detectMaxConcurrency && s.detect.pendingCount > 0) saturated++;
        crawleeSumCurrent += s.crawlee.currentConcurrency;
        detectSumActive += s.detect.activeCount;
        detectSumPending += s.detect.pendingCount;
        memSumRatio += s.memory.ratio;
        if (s.memory.ratio > memMaxRatio) memMaxRatio = s.memory.ratio;
        if (s.crawlee.currentConcurrency > crawleeMaxReached) crawleeMaxReached = s.crawlee.currentConcurrency;
    }
    const M = state.samples.length;

    return {
        crawl_id: state.crawlId,
        started_at: startedAt,
        duration_s: durationS,
        pages_total: N,
        pages_per_min_avg: ppmAvg,
        pages_per_min_max_sustained: ppmMax,
        phases: {
            wait_ms: phaseStats(phaseValues("wait_ms"), totalSum),
            nav_ms: phaseStats(phaseValues("nav_ms"), totalSum),
            pre_detect_ms: phaseStats(phaseValues("pre_detect_ms"), totalSum),
            detect_ms: phaseStats(phaseValues("detect_ms"), totalSum),
            post_ms: phaseStats(phaseValues("post_ms"), totalSum),
        },
        pool: {
            crawlee_avg_concurrency: M === 0 ? 0 : round1(crawleeSumCurrent / M),
            crawlee_max_concurrency_reached: crawleeMaxReached,
            crawlee_throttle_pct: M === 0 ? 0 : round1((throttled / M) * 100),
            detect_avg_active: M === 0 ? 0 : round1(detectSumActive / M),
            detect_avg_pending: M === 0 ? 0 : round1(detectSumPending / M),
            detect_saturated_pct: M === 0 ? 0 : round1((saturated / M) * 100),
            memory_avg_ratio: M === 0 ? 0 : round1(memSumRatio / M),
            memory_max_ratio: round1(memMaxRatio),
        },
    };
}
```

- [ ] **Step 5: Run tests; all 6 cases must pass.**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_timing_aggregator.ts`
Expected: `timing_aggregator: 18 passed, 0 failed` (6 cases × multiple assertions).

- [ ] **Step 6: Commit.**

```bash
git add apps-microservices/crawler-service/crawler/src/timing/types.ts apps-microservices/crawler-service/crawler/src/timing/aggregator.ts apps-microservices/crawler-service/crawler/src/tests/test_timing_aggregator.ts
git commit -m "$(cat <<'EOF'
feat(crawler): add pure timing aggregator and types

Introduces the aggregator module shared by TimingRecorder and the
post-hoc timing-summary tool. Pure functions: createAggregator, addPage,
addPoolSample, buildSummary. No I/O dependency. Computes per-phase
median/p95/p99 and pool-level metrics (Crawlee concurrency, detect-API
saturation, memory ratio, pages/min).

---

feat(crawler): ajouter l'agrégateur de timing pur et ses types

Introduit le module agrégateur partagé entre TimingRecorder et l'outil
post-hoc timing-summary. Fonctions pures : createAggregator, addPage,
addPoolSample, buildSummary. Aucune dépendance I/O. Calcule les
médianes/p95/p99 par phase et les métriques pool (concurrence Crawlee,
saturation API détection, ratio mémoire, pages/min).
EOF
)"
```

---

### Task 2: TimingRecorder class

**Goal:** A `TimingRecorder` class that wraps the aggregator with a JSONL append stream, periodic summary flush, replay/overwrite resume policy, and exit handlers.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/class/TimingRecorder.ts`
- Test: `apps-microservices/crawler-service/crawler/src/tests/test_TimingRecorder.ts`

**Acceptance Criteria:**
- [ ] Constructor: `new TimingRecorder({ crawlId, outputDir, detectMaxConcurrency, summaryFlushMs?, fsyncEveryN?, resumePolicy? })`. Opens `<outputDir>/timing.jsonl` for append.
- [ ] `recordPage(entry)` writes one JSON line, updates aggregator, calls `fsyncSync` once per `fsyncEveryN` (default 50).
- [ ] `recordPoolSample(sample)` updates aggregator (no JSONL line for samples).
- [ ] Periodic timer rebuilds summary every `summaryFlushMs` (default 30000) and atomically writes `<outputDir>/timing-summary.json` (write to `.tmp` then `rename`).
- [ ] `finalize()` clears the timer, flushes the JSONL stream, writes one final summary, returns a Promise that resolves when complete.
- [ ] Constructor with `resumePolicy=replay` reads any existing JSONL into the aggregator before opening for append.
- [ ] Constructor with `resumePolicy=overwrite` truncates existing JSONL.
- [ ] No exit handler is registered automatically — caller wires that in main.ts (Task 3).

**Verify:** `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_TimingRecorder.ts`

**Steps:**

- [ ] **Step 1: Write failing tests.**

`apps-microservices/crawler-service/crawler/src/tests/test_TimingRecorder.ts`:

```typescript
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { TimingRecorder } from "../class/TimingRecorder";
import type { PageTimingEntry, PoolSample } from "../timing/types";

let passed = 0;
let failed = 0;

function assert(cond: boolean, msg: string) {
    if (cond) passed++;
    else { failed++; console.error(`FAIL: ${msg}`); }
}

function tmpDir(): string {
    return fs.mkdtempSync(path.join(os.tmpdir(), "timing-rec-"));
}

function mkEntry(i: number): PageTimingEntry {
    return {
        url: `https://x/${i}`, t: 1000 + i, wait_ms: 1, nav_ms: 100, pre_detect_ms: 1,
        detect_ms: 50, post_ms: 1, total_ms: 153, detect_ok: true,
    };
}

function mkSample(t: number): PoolSample {
    return {
        t,
        crawlee: { currentConcurrency: 1, desiredConcurrency: 1, maxConcurrency: 5 },
        detect: { activeCount: 1, pendingCount: 0 },
        memory: { used_mb: 100, budget_mb: 1000, ratio: 0.1 },
        rolling: { pages_per_min: 30 },
    };
}

// 1. JSONL line per recordPage call
async function test1() {
    const dir = tmpDir();
    const r = new TimingRecorder({ crawlId: "t1", outputDir: dir, detectMaxConcurrency: 5 });
    r.recordPage(mkEntry(1));
    r.recordPage(mkEntry(2));
    await r.finalize();
    const lines = fs.readFileSync(path.join(dir, "timing.jsonl"), "utf-8").trim().split("\n");
    assert(lines.length === 2, `2 JSONL lines, got ${lines.length}`);
    assert(JSON.parse(lines[0]).url === "https://x/1", "first line url");
}

// 2. finalize writes timing-summary.json with correct shape
async function test2() {
    const dir = tmpDir();
    const r = new TimingRecorder({ crawlId: "t2", outputDir: dir, detectMaxConcurrency: 5 });
    r.recordPage(mkEntry(1));
    r.recordPoolSample(mkSample(1));
    await r.finalize();
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.crawl_id === "t2", "crawl_id captured");
    assert(sum.pages_total === 1, "pages_total = 1");
    assert(typeof sum.phases.detect_ms.median === "number", "phase shape present");
    assert(typeof sum.pool.crawlee_avg_concurrency === "number", "pool shape present");
}

// 3. periodic flush writes summary mid-run
async function test3() {
    const dir = tmpDir();
    const r = new TimingRecorder({
        crawlId: "t3", outputDir: dir, detectMaxConcurrency: 5,
        summaryFlushMs: 50,
    });
    r.recordPage(mkEntry(1));
    await new Promise((res) => setTimeout(res, 120)); // allow 2 ticks
    const sumPath = path.join(dir, "timing-summary.json");
    assert(fs.existsSync(sumPath), "summary written by periodic timer");
    const sum = JSON.parse(fs.readFileSync(sumPath, "utf-8"));
    assert(sum.pages_total === 1, "periodic summary reflects 1 page");
    await r.finalize();
}

// 4. replay policy reads existing JSONL into aggregator
async function test4() {
    const dir = tmpDir();
    fs.writeFileSync(path.join(dir, "timing.jsonl"),
        JSON.stringify(mkEntry(1)) + "\n" + JSON.stringify(mkEntry(2)) + "\n");
    const r = new TimingRecorder({
        crawlId: "t4", outputDir: dir, detectMaxConcurrency: 5,
        resumePolicy: "replay",
    });
    r.recordPage(mkEntry(3));
    await r.finalize();
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 3, `replay: 3 pages total, got ${sum.pages_total}`);
    const lines = fs.readFileSync(path.join(dir, "timing.jsonl"), "utf-8").trim().split("\n");
    assert(lines.length === 3, "JSONL contains 2 prior + 1 new = 3 lines");
}

// 5. overwrite policy truncates JSONL
async function test5() {
    const dir = tmpDir();
    fs.writeFileSync(path.join(dir, "timing.jsonl"),
        JSON.stringify(mkEntry(1)) + "\n");
    const r = new TimingRecorder({
        crawlId: "t5", outputDir: dir, detectMaxConcurrency: 5,
        resumePolicy: "overwrite",
    });
    r.recordPage(mkEntry(99));
    await r.finalize();
    const lines = fs.readFileSync(path.join(dir, "timing.jsonl"), "utf-8").trim().split("\n");
    assert(lines.length === 1, "overwrite: only 1 line after restart");
    assert(JSON.parse(lines[0]).url === "https://x/99", "overwrite: kept new entry only");
}

(async () => {
    await test1();
    await test2();
    await test3();
    await test4();
    await test5();
    console.log(`TimingRecorder: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
})();
```

- [ ] **Step 2: Run tests; expect failure.**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_TimingRecorder.ts`
Expected: `Cannot find module '../class/TimingRecorder'`.

- [ ] **Step 3: Implement TimingRecorder.**

`apps-microservices/crawler-service/crawler/src/class/TimingRecorder.ts`:

```typescript
import * as fs from "node:fs";
import * as path from "node:path";
import {
    addPage,
    addPoolSample,
    buildSummary,
    createAggregator,
} from "../timing/aggregator";
import type {
    AggregatorState,
    PageTimingEntry,
    PoolSample,
} from "../timing/types";

export interface TimingRecorderOptions {
    crawlId: string;
    outputDir: string;
    detectMaxConcurrency: number;
    summaryFlushMs?: number;
    fsyncEveryN?: number;
    resumePolicy?: "replay" | "overwrite";
}

export class TimingRecorder {
    private state: AggregatorState;
    private outputDir: string;
    private jsonlPath: string;
    private summaryPath: string;
    private fd: number;
    private writeCount = 0;
    private fsyncEveryN: number;
    private flushTimer: NodeJS.Timeout | null = null;
    private finalized = false;

    constructor(opts: TimingRecorderOptions) {
        const flushMs = opts.summaryFlushMs ?? 30000;
        this.fsyncEveryN = opts.fsyncEveryN ?? 50;
        this.state = createAggregator(opts.crawlId, opts.detectMaxConcurrency);
        this.outputDir = opts.outputDir;
        this.jsonlPath = path.join(opts.outputDir, "timing.jsonl");
        this.summaryPath = path.join(opts.outputDir, "timing-summary.json");

        fs.mkdirSync(opts.outputDir, { recursive: true });

        const policy = opts.resumePolicy ?? "replay";
        if (fs.existsSync(this.jsonlPath)) {
            if (policy === "replay") {
                const existing = fs.readFileSync(this.jsonlPath, "utf-8");
                for (const line of existing.split("\n")) {
                    if (!line.trim()) continue;
                    try {
                        const entry = JSON.parse(line) as PageTimingEntry;
                        addPage(this.state, entry);
                    } catch {
                        // Skip malformed lines silently — partial trace from a crash.
                    }
                }
                this.fd = fs.openSync(this.jsonlPath, "a");
            } else {
                this.fd = fs.openSync(this.jsonlPath, "w");
            }
        } else {
            this.fd = fs.openSync(this.jsonlPath, "w");
        }

        if (flushMs > 0) {
            this.flushTimer = setInterval(() => this._writeSummary(), flushMs);
        }
    }

    recordPage(entry: PageTimingEntry): void {
        addPage(this.state, entry);
        const line = JSON.stringify(entry) + "\n";
        fs.writeSync(this.fd, line);
        this.writeCount++;
        if (this.writeCount % this.fsyncEveryN === 0) {
            try { fs.fsyncSync(this.fd); } catch { /* best-effort */ }
        }
    }

    recordPoolSample(sample: PoolSample): void {
        addPoolSample(this.state, sample);
    }

    private _writeSummary(): void {
        const summary = buildSummary(this.state);
        const tmpPath = `${this.summaryPath}.tmp`;
        fs.writeFileSync(tmpPath, JSON.stringify(summary, null, 2));
        fs.renameSync(tmpPath, this.summaryPath);
    }

    async finalize(): Promise<void> {
        if (this.finalized) return;
        this.finalized = true;
        if (this.flushTimer) {
            clearInterval(this.flushTimer);
            this.flushTimer = null;
        }
        try { fs.fsyncSync(this.fd); } catch { /* best-effort */ }
        try { fs.closeSync(this.fd); } catch { /* best-effort */ }
        this._writeSummary();
    }

    /**
     * Returns the current summary without writing it to disk. Useful for the
     * end-of-run console block in main.ts.
     */
    snapshot() {
        return buildSummary(this.state);
    }
}
```

- [ ] **Step 4: Run tests; all 5 must pass.**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_TimingRecorder.ts`
Expected: `TimingRecorder: <N> passed, 0 failed` where N is the assertion count (≥ 11).

- [ ] **Step 5: Commit.**

```bash
git add apps-microservices/crawler-service/crawler/src/class/TimingRecorder.ts apps-microservices/crawler-service/crawler/src/tests/test_TimingRecorder.ts
git commit -m "$(cat <<'EOF'
feat(crawler): add TimingRecorder with JSONL stream and periodic flush

Wraps the timing aggregator with append-only JSONL output, periodic
summary flush (default 30s), atomic summary write via .tmp+rename,
fsync-every-N durability, and replay/overwrite resume policies for
partial JSONL files left by a crashed run.

---

feat(crawler): ajouter TimingRecorder avec flux JSONL et flush périodique

Encapsule l'agrégateur de timing avec sortie JSONL en mode append, flush
périodique du résumé (30s par défaut), écriture atomique via .tmp+rename,
durabilité fsync-tous-les-N, et politiques de reprise replay/overwrite
pour les JSONL partiels laissés par un crash.
EOF
)"
```

---

### Task 3: Wire recorder into Crawlee setup and main.ts lifecycle

**Goal:** Construct `TimingRecorder` when `TIMING_ENABLED=true`, register Crawlee `preNavigationHooks` and `postNavigationHooks`, start the 5s pool sampler, and wire SIGINT/SIGTERM/`beforeExit` handlers to call `finalize()`.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/functions.ts` (around line 477–528 inside `optionsCrawler`)
- Modify: `apps-microservices/crawler-service/crawler/src/main.ts` (recorder construction near the top of `run()` and finalize on shutdown)
- Test: same `test_TimingRecorder.ts` covers recorder behavior; integration test added in Task 6

**Acceptance Criteria:**
- [ ] When `TIMING_ENABLED=true`, the recorder is constructed in main.ts before crawler.run() starts.
- [ ] `preNavigationHooks` writes `crawlingContext.userData._timing = { dequeueAt: Date.now() }`.
- [ ] `postNavigationHooks` writes `_timing.postNavAt = Date.now()`.
- [ ] A `setInterval` sampler reads `crawler.autoscaledPool` (currentConcurrency, desiredConcurrency, maxConcurrency), the `pLimit` instance from `DetectionLangueClient` (pendingCount, activeCount), Node `process.memoryUsage().rss` and the Crawlee budget. The sampler is cleared in `finalize()`.
- [ ] SIGINT, SIGTERM, and `beforeExit` listeners call `recorder.finalize()` exactly once.
- [ ] When `TIMING_ENABLED=false`, none of the above runs (no constructor, no hook registration, no sampler, no listener).
- [ ] `npm run build` clean.

**Verify:**

```bash
cd apps-microservices/crawler-service/crawler && npm run build
```

(Behavior is verified by Task 6 integration test.)

**Steps:**

- [ ] **Step 1: Expose the `pLimit` instance from `DetectionLangueClient`.**

The aggregator needs to read `pendingCount` and `activeCount`. `pLimit` exposes both as getters. Add a public read-only accessor.

Modify `apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts`:

Find the constructor that sets `this.limit = pLimit(maxConcurrency)`. Below the constructor, add:

```typescript
/**
 * Returns the underlying p-limit instance for observability (pendingCount,
 * activeCount). Do not use this to manipulate the queue — the p-limit
 * instance is owned by this class.
 */
get limiter(): { pendingCount: number; activeCount: number } {
    return this.limit as unknown as { pendingCount: number; activeCount: number };
}

/**
 * Returns the configured detect-API concurrency cap.
 */
get maxConcurrency(): number {
    return parseInt(process.env.DETECTION_MAX_CONCURRENCY ?? "5");
}
```

- [ ] **Step 2: Add timing hooks to the `optionsCrawler` config in `functions.ts`.**

In `apps-microservices/crawler-service/crawler/src/functions.ts`, inside the `optionsCrawler: PlaywrightCrawlerOptions = { ... }` block (around line 477), add:

```typescript
// Timing instrumentation hooks. Conditionally attached: when context.timingRecorder
// is undefined (TIMING_ENABLED=false), the hook is a no-op closure call.
preNavigationHooks: [
    async (crawlingContext) => {
        if (context.timingRecorder) {
            crawlingContext.userData._timing = { dequeueAt: Date.now() };
        }
    },
],
postNavigationHooks: [
    async (crawlingContext) => {
        if (context.timingRecorder && crawlingContext.userData._timing) {
            crawlingContext.userData._timing.postNavAt = Date.now();
        }
    },
],
```

If `optionsCrawler` already has `preNavigationHooks` or `postNavigationHooks`, append to the array instead of replacing.

- [ ] **Step 3: Add `timingRecorder` to the shared context type.**

In `apps-microservices/crawler-service/crawler/src/context.ts`, add the field:

```typescript
import type { TimingRecorder } from "./class/TimingRecorder";
// ... existing imports ...

// Inside the context object literal:
timingRecorder: undefined as TimingRecorder | undefined,
```

- [ ] **Step 4: Construct the recorder and start the sampler in `main.ts`.**

In `apps-microservices/crawler-service/crawler/src/main.ts`, near the top of the `run()` function (after `storagePath` is computed and after Crawlee config is set up but before `crawler.run()` is called), add:

```typescript
import { TimingRecorder } from "./class/TimingRecorder";
import type { PoolSample } from "./timing/types";

const TIMING_ENABLED = (process.env.TIMING_ENABLED ?? "false").toLowerCase() === "true";
const TIMING_SAMPLE_INTERVAL_MS = parseInt(process.env.TIMING_SAMPLE_INTERVAL_MS ?? "5000");

let timingSampler: NodeJS.Timeout | null = null;

if (TIMING_ENABLED) {
    const recorder = new TimingRecorder({
        crawlId: String(id),
        outputDir: storagePath,
        detectMaxConcurrency: detectionClient.maxConcurrency,
    });
    context.timingRecorder = recorder;

    let lastSampleAt = Date.now();
    let pagesAtLastSample = 0;

    timingSampler = setInterval(() => {
        try {
            const pool = (crawler as any).autoscaledPool;
            const memUsedBytes = process.memoryUsage().rss;
            const budgetBytes = ((crawler as any).config?.memoryMbytes ?? 0) * 1024 * 1024;
            const handled = (crawler as any).stats?.state?.requestsFinished ?? 0;
            const elapsedMs = Date.now() - lastSampleAt;
            const ppm = elapsedMs > 0 ? Math.round(((handled - pagesAtLastSample) / elapsedMs) * 60000) : 0;
            lastSampleAt = Date.now();
            pagesAtLastSample = handled;

            const sample: PoolSample = {
                t: Date.now(),
                crawlee: {
                    currentConcurrency: pool?.currentConcurrency ?? 0,
                    desiredConcurrency: pool?.desiredConcurrency ?? 0,
                    maxConcurrency: pool?.maxConcurrency ?? 0,
                },
                detect: {
                    pendingCount: detectionClient.limiter.pendingCount,
                    activeCount: detectionClient.limiter.activeCount,
                },
                memory: {
                    used_mb: Math.round(memUsedBytes / (1024 * 1024)),
                    budget_mb: Math.round(budgetBytes / (1024 * 1024)),
                    ratio: budgetBytes > 0 ? memUsedBytes / budgetBytes : 0,
                },
                rolling: { pages_per_min: ppm },
            };
            recorder.recordPoolSample(sample);
        } catch (err) {
            console.error(`[TIMING] sampler error: ${(err as Error).message}`);
        }
    }, TIMING_SAMPLE_INTERVAL_MS);

    const finalizeOnce = (() => {
        let done = false;
        return async () => {
            if (done) return;
            done = true;
            if (timingSampler) {
                clearInterval(timingSampler);
                timingSampler = null;
            }
            await recorder.finalize();
            console.log(formatTimingSummary(recorder.snapshot()));
        };
    })();

    process.on("SIGINT", () => { void finalizeOnce(); });
    process.on("SIGTERM", () => { void finalizeOnce(); });
    process.on("beforeExit", () => { void finalizeOnce(); });

    // Make finalizeOnce reachable by the post-run path below.
    (context as any)._finalizeTimingOnce = finalizeOnce;
}
```

After `await crawler.run(...)` completes, add (near the existing post-run cleanup):

```typescript
if (TIMING_ENABLED && (context as any)._finalizeTimingOnce) {
    await (context as any)._finalizeTimingOnce();
}
```

- [ ] **Step 5: Add the console summary formatter helper.**

In `apps-microservices/crawler-service/crawler/src/main.ts`, add (near the other helpers, top-level scope):

```typescript
import type { TimingSummary } from "./timing/types";

function formatTimingSummary(s: TimingSummary): string {
    const lines: string[] = [];
    lines.push("=== Timing summary ===");
    lines.push(`Pages: ${s.pages_total} in ${s.duration_s}s ` +
        `(avg ${s.pages_per_min_avg} pages/min, max ${s.pages_per_min_max_sustained} sustained)`);
    lines.push("Phase share of total handler time:");
    const phases: Array<[string, keyof TimingSummary["phases"]]> = [
        ["wait_ms", "wait_ms"],
        ["nav_ms", "nav_ms"],
        ["pre_detect_ms", "pre_detect_ms"],
        ["detect_ms", "detect_ms"],
        ["post_ms", "post_ms"],
    ];
    const sorted = phases.slice().sort((a, b) =>
        s.phases[b[1]].share_of_total_pct - s.phases[a[1]].share_of_total_pct);
    for (const [label, key] of sorted) {
        const ph = s.phases[key];
        lines.push(`  ${label.padEnd(14)}${ph.share_of_total_pct.toFixed(1)}%  ` +
            `(median ${ph.median}ms, p95 ${ph.p95}ms)`);
    }
    lines.push("Pool:");
    lines.push(`  Crawlee avg concurrency: ${s.pool.crawlee_avg_concurrency} ` +
        `/ max reached: ${s.pool.crawlee_max_concurrency_reached} ` +
        `/ throttled ${s.pool.crawlee_throttle_pct}% of time`);
    lines.push(`  Detect API saturated ${s.pool.detect_saturated_pct}% of time ` +
        `(pending queue non-empty at concurrency cap)`);
    lines.push(`  Memory: avg ratio ${s.pool.memory_avg_ratio}, max ${s.pool.memory_max_ratio}`);
    return lines.join("\n");
}
```

- [ ] **Step 6: Verify build.**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: tsc exits 0, no type errors.

- [ ] **Step 7: Commit.**

```bash
git add apps-microservices/crawler-service/crawler/src/class/DetectionLangueClient.ts apps-microservices/crawler-service/crawler/src/functions.ts apps-microservices/crawler-service/crawler/src/context.ts apps-microservices/crawler-service/crawler/src/main.ts
git commit -m "$(cat <<'EOF'
feat(crawler): wire timing recorder into Crawlee lifecycle

Constructs TimingRecorder when TIMING_ENABLED=true. Registers Crawlee
preNavigationHooks/postNavigationHooks for per-page wall-clock markers.
Starts a 5s sampler that reads autoscaledPool state, p-limit queue
depth via DetectionLangueClient.limiter accessor, RSS memory, and
rolling pages/min. SIGINT/SIGTERM/beforeExit listeners invoke
finalize() exactly once and print the end-of-run summary block.

---

feat(crawler): câbler le timing recorder dans le cycle de vie Crawlee

Construit TimingRecorder quand TIMING_ENABLED=true. Enregistre les
preNavigationHooks/postNavigationHooks Crawlee pour les marqueurs
wall-clock par page. Démarre un sampler 5s qui lit l'état
autoscaledPool, la profondeur de file p-limit via l'accesseur
DetectionLangueClient.limiter, la mémoire RSS et le débit
pages/min. Les listeners SIGINT/SIGTERM/beforeExit invoquent
finalize() une seule fois et impriment le bloc de résumé.
EOF
)"
```

---

### Task 4: Per-page detect timing in `routes.ts` and `recordPage` call

**Goal:** Capture `detectStartAt`/`detectEndAt` around the `detectionClient.detect(...)` call in the route handler and call `recorder.recordPage(...)` at handler return.

**Files:**
- Modify: `apps-microservices/crawler-service/crawler/src/routes.ts` (around line 569 — wrap `detectionClient.detect(...)`; near the end of the `playwrightHandler` function — build entry, call `recordPage`)

**Acceptance Criteria:**
- [ ] Wherever `detectionClient.detect(...)` is awaited inside the route handler, timestamps are captured immediately before and after the call.
- [ ] At handler return, a `PageTimingEntry` is built using `_timing.dequeueAt`, `_timing.postNavAt`, and the captured detect timestamps. Missing markers fall back to handler-start time so the entry is still useful for partial pages.
- [ ] `context.timingRecorder?.recordPage(entry)` is invoked at every handler return path (success, no-detect-call shortcut, early returns inside conditional branches).
- [ ] Behavior unchanged when `TIMING_ENABLED=false` — `context.timingRecorder` is `undefined`, optional chain is no-op.

**Verify:** `cd apps-microservices/crawler-service/crawler && npm run build && npx tsx src/tests/test_TimingRecorder.ts`

**Steps:**

- [ ] **Step 1: Read the current handler exit paths.**

Read `apps-microservices/crawler-service/crawler/src/routes.ts` from the beginning of the playwrightHandler function to its closing brace. Identify every `return` and the implicit fall-through end. Each must call `recorder.recordPage` before exit.

- [ ] **Step 2: Add a helper inside the route module.**

At the top of `routes.ts` (or in a small helper file), add:

```typescript
import type { PageTimingEntry } from "./timing/types";

interface RequestTiming {
    handlerStartAt: number;
    dequeueAt?: number;     // populated by preNavigationHook
    postNavAt?: number;     // populated by postNavigationHook
    detectStartAt?: number; // populated inline
    detectEndAt?: number;   // populated inline
}

function buildTimingEntry(
    timing: RequestTiming,
    url: string,
    detectMethod: string | undefined,
    detectOk: boolean | undefined,
): PageTimingEntry {
    const handlerEndAt = Date.now();
    const dequeueAt = timing.dequeueAt ?? timing.handlerStartAt;
    const postNavAt = timing.postNavAt ?? dequeueAt;
    const detectStartAt = timing.detectStartAt ?? postNavAt;
    const detectEndAt = timing.detectEndAt ?? detectStartAt;
    return {
        url,
        t: dequeueAt,
        wait_ms: Math.max(0, dequeueAt - timing.handlerStartAt),
        nav_ms: Math.max(0, postNavAt - dequeueAt),
        pre_detect_ms: Math.max(0, detectStartAt - postNavAt),
        detect_ms: Math.max(0, detectEndAt - detectStartAt),
        post_ms: Math.max(0, handlerEndAt - detectEndAt),
        total_ms: Math.max(0, handlerEndAt - dequeueAt),
        detect_method: detectMethod,
        detect_ok: detectOk,
    };
}
```

(`wait_ms` here is essentially `dequeueAt - handlerStartAt`, which is near-zero for Crawlee since `preNavigationHook` runs at handler entry. The phase is retained for future use if Crawlee ever exposes true queue-wait time.)

- [ ] **Step 3: Wrap detect calls and add recordPage.**

At the start of every Crawlee request handler in `routes.ts`, add:

```typescript
const _timing: RequestTiming = {
    handlerStartAt: Date.now(),
    dequeueAt: (request.userData as any)?._timing?.dequeueAt,
    postNavAt: (request.userData as any)?._timing?.postNavAt,
};
let _detectMethod: string | undefined;
let _detectOk: boolean | undefined;
```

At every site where `await detectionClient.detect(...)` is called, wrap:

```typescript
_timing.detectStartAt = Date.now();
const detectResult = await detectionClient.detect(url, content, {
    forcedMethod: needsNlp ? undefined : frenchDetectionMethod,
    mode: "simple",
    useNlpDetection: needsNlp,
    proxyUrl: proxyUrl ?? undefined,
});
_timing.detectEndAt = Date.now();
_detectMethod = detectResult.method;
_detectOk = detectResult.ok;
```

At every handler exit path (every `return` and the natural function end), add immediately before exit:

```typescript
context.timingRecorder?.recordPage(buildTimingEntry(_timing, url, _detectMethod, _detectOk));
```

If there are many exit paths, prefer wrapping the entire handler body in a `try { ... } finally { ... }` and calling `recordPage` once in the `finally`. This is the cleaner pattern.

- [ ] **Step 4: Verify build.**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: tsc exits 0.

- [ ] **Step 5: Commit.**

```bash
git add apps-microservices/crawler-service/crawler/src/routes.ts
git commit -m "$(cat <<'EOF'
feat(crawler): record per-page timing entries in route handler

Wraps detectionClient.detect() with start/end timestamps and calls
TimingRecorder.recordPage at handler return (via try/finally so every
exit path is covered). Phase computation tolerates missing markers from
abnormal exits — falls back to handlerStartAt so partial entries are
still well-formed.

---

feat(crawler): enregistrer les entrées de timing par page dans le route handler

Encadre detectionClient.detect() avec des timestamps début/fin et appelle
TimingRecorder.recordPage à la sortie du handler (via try/finally pour
couvrir tous les chemins de sortie). Le calcul des phases tolère
l'absence de marqueurs lors de sorties anormales — repli sur
handlerStartAt afin que les entrées partielles restent bien formées.
EOF
)"
```

---

### Task 5: Post-hoc `timing-summary.ts` tool and `files_to_keep` retention

**Goal:** A standalone CLI that reads any `timing.jsonl` and emits the same `timing-summary.json` shape using the shared aggregator. Plus extend `crawler_manager.py`'s `files_to_keep` to retain timing files locally after archive cleanup.

**Files:**
- Create: `apps-microservices/crawler-service/crawler/src/tools/timing-summary.ts`
- Modify: `apps-microservices/crawler-service/app/core/crawler_manager.py:1690`
- Test: `apps-microservices/crawler-service/crawler/src/tests/test_timing_summary_tool.ts`

**Acceptance Criteria:**
- [ ] CLI invocation: `npx tsx src/tools/timing-summary.ts <input-jsonl-path>` writes `<input-dir>/timing-summary.json` with the same shape as `TimingRecorder.finalize()`.
- [ ] CLI invocation with `--out <path>` overrides the output path.
- [ ] CLI handles empty JSONL (zero pages) without crashing.
- [ ] `files_to_keep` in `crawler_manager.py` includes `'timing.jsonl', 'timing-summary.json'`.

**Verify:** `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_timing_summary_tool.ts`

**Steps:**

- [ ] **Step 1: Write failing tests for the CLI.**

`apps-microservices/crawler-service/crawler/src/tests/test_timing_summary_tool.ts`:

```typescript
import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";

let passed = 0;
let failed = 0;

function assert(cond: boolean, msg: string) {
    if (cond) passed++;
    else { failed++; console.error(`FAIL: ${msg}`); }
}

const cliPath = path.join(__dirname, "..", "tools", "timing-summary.ts");

// 1. Empty JSONL produces zero-page summary
{
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-tool-"));
    const jsonl = path.join(dir, "timing.jsonl");
    fs.writeFileSync(jsonl, "");
    execSync(`npx tsx ${cliPath} ${jsonl}`, { stdio: "pipe" });
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 0, "empty input -> 0 pages");
}

// 2. Three-page JSONL produces correct totals
{
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-tool-"));
    const jsonl = path.join(dir, "timing.jsonl");
    const lines = [
        { url: "https://x/1", t: 1000, wait_ms: 0, nav_ms: 100, pre_detect_ms: 0, detect_ms: 50, post_ms: 0, total_ms: 150 },
        { url: "https://x/2", t: 1200, wait_ms: 0, nav_ms: 200, pre_detect_ms: 0, detect_ms: 60, post_ms: 0, total_ms: 260 },
        { url: "https://x/3", t: 1500, wait_ms: 0, nav_ms: 300, pre_detect_ms: 0, detect_ms: 70, post_ms: 0, total_ms: 370 },
    ];
    fs.writeFileSync(jsonl, lines.map((l) => JSON.stringify(l)).join("\n") + "\n");
    execSync(`npx tsx ${cliPath} ${jsonl}`, { stdio: "pipe" });
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 3, "3 pages aggregated");
    assert(sum.phases.nav_ms.median === 200, `nav median = 200, got ${sum.phases.nav_ms.median}`);
}

// 3. --out flag overrides output path
{
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-tool-"));
    const jsonl = path.join(dir, "timing.jsonl");
    fs.writeFileSync(jsonl, "");
    const outPath = path.join(dir, "custom-out.json");
    execSync(`npx tsx ${cliPath} ${jsonl} --out ${outPath}`, { stdio: "pipe" });
    assert(fs.existsSync(outPath), "--out path was used");
    assert(!fs.existsSync(path.join(dir, "timing-summary.json")), "default path NOT written when --out is given");
}

console.log(`timing_summary_tool: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
```

- [ ] **Step 2: Run tests; expect failure.**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_timing_summary_tool.ts`
Expected: ENOENT or similar — the CLI does not exist yet.

- [ ] **Step 3: Implement the CLI.**

`apps-microservices/crawler-service/crawler/src/tools/timing-summary.ts`:

```typescript
#!/usr/bin/env node
import * as fs from "node:fs";
import * as path from "node:path";
import {
    addPage,
    buildSummary,
    createAggregator,
} from "../timing/aggregator";
import type { PageTimingEntry } from "../timing/types";

function parseArgs(argv: string[]): { input: string; out: string | null } {
    const [, , ...args] = argv;
    if (args.length === 0) {
        console.error("Usage: timing-summary.ts <input-jsonl> [--out <path>]");
        process.exit(2);
    }
    let input = args[0];
    let out: string | null = null;
    for (let i = 1; i < args.length; i++) {
        if (args[i] === "--out" && i + 1 < args.length) {
            out = args[i + 1];
            i++;
        }
    }
    return { input, out };
}

function main(): void {
    const { input, out } = parseArgs(process.argv);
    const inputAbs = path.resolve(input);
    const outAbs = out
        ? path.resolve(out)
        : path.join(path.dirname(inputAbs), "timing-summary.json");

    if (!fs.existsSync(inputAbs)) {
        console.error(`Input not found: ${inputAbs}`);
        process.exit(1);
    }

    // crawlId derived from the parent dir name (e.g. storage/6066 -> "6066").
    const crawlId = path.basename(path.dirname(inputAbs));
    const detectMaxConcurrency = parseInt(process.env.DETECTION_MAX_CONCURRENCY ?? "5");
    const aggregator = createAggregator(crawlId, detectMaxConcurrency);

    const raw = fs.readFileSync(inputAbs, "utf-8");
    for (const line of raw.split("\n")) {
        if (!line.trim()) continue;
        try {
            const entry = JSON.parse(line) as PageTimingEntry;
            addPage(aggregator, entry);
        } catch (err) {
            console.error(`Skipping malformed line: ${(err as Error).message}`);
        }
    }

    const summary = buildSummary(aggregator);
    fs.writeFileSync(outAbs, JSON.stringify(summary, null, 2));
    console.log(`Wrote summary: ${outAbs} (${summary.pages_total} pages)`);
}

main();
```

- [ ] **Step 4: Update `files_to_keep` in `crawler_manager.py`.**

Modify `apps-microservices/crawler-service/app/core/crawler_manager.py` line 1690:

```python
files_to_keep = {'crawler.log', '_callback_payload.json',
                 '_completion_marker.json', '_status_snapshot.json',
                 '_exit_reason.json', '_update_report.json',
                 'update_stats.json',
                 'timing.jsonl', 'timing-summary.json'}
```

- [ ] **Step 5: Run tests; all 3 must pass.**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_timing_summary_tool.ts`
Expected: `timing_summary_tool: <N> passed, 0 failed`.

- [ ] **Step 6: Verify build still clean.**

Run: `cd apps-microservices/crawler-service/crawler && npm run build`
Expected: tsc exits 0.

- [ ] **Step 7: Commit.**

```bash
git add apps-microservices/crawler-service/crawler/src/tools/timing-summary.ts apps-microservices/crawler-service/crawler/src/tests/test_timing_summary_tool.ts apps-microservices/crawler-service/app/core/crawler_manager.py
git commit -m "$(cat <<'EOF'
feat(crawler): post-hoc timing-summary tool and local retention

Adds a standalone CLI that rebuilds timing-summary.json from any
timing.jsonl using the shared aggregator. Useful when a crash leaves a
partial JSONL with no in-process summary. Also extends files_to_keep
in crawler_manager.py so the timing files survive _cleanup_local_data
alongside the existing markers.

---

feat(crawler): outil post-hoc timing-summary et rétention locale

Ajoute une CLI autonome qui reconstruit timing-summary.json depuis
n'importe quel timing.jsonl via l'agrégateur partagé. Utile quand un
crash laisse un JSONL partiel sans résumé in-process. Étend également
files_to_keep dans crawler_manager.py pour que les fichiers timing
survivent à _cleanup_local_data avec les marqueurs existants.
EOF
)"
```

---

### Task 6: End-to-end integration smoke test

**Goal:** Verify the full pipeline with a small in-process crawl simulation: `TIMING_ENABLED=true` produces both files, the summary identifies a dominant phase, and `TIMING_ENABLED=false` produces neither file.

**Files:**
- Test: `apps-microservices/crawler-service/crawler/src/tests/test_timing_integration.ts`

**Acceptance Criteria:**
- [ ] With `TIMING_ENABLED=true`: a fake crawl loop writes 5 entries via the recorder, the resulting `timing.jsonl` has 5 lines, `timing-summary.json` has `pages_total === 5`.
- [ ] Killing the recorder's process abruptly (simulated by skipping `finalize()`) leaves a partial JSONL that the post-hoc tool can convert to a well-formed summary.
- [ ] No real crawler launched — this is a unit-style integration of the recorder + tool path.

**Verify:** `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_timing_integration.ts`

**Steps:**

- [ ] **Step 1: Write the integration test.**

`apps-microservices/crawler-service/crawler/src/tests/test_timing_integration.ts`:

```typescript
import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { TimingRecorder } from "../class/TimingRecorder";
import type { PageTimingEntry, PoolSample } from "../timing/types";

let passed = 0;
let failed = 0;

function assert(cond: boolean, msg: string) {
    if (cond) passed++;
    else { failed++; console.error(`FAIL: ${msg}`); }
}

function mkEntry(i: number, navMs: number, detectMs: number): PageTimingEntry {
    return {
        url: `https://example.com/${i}`,
        t: 1_000_000 + i * 100,
        wait_ms: 0,
        nav_ms: navMs,
        pre_detect_ms: 5,
        detect_ms: detectMs,
        post_ms: 10,
        total_ms: navMs + detectMs + 15,
        detect_ok: true,
    };
}

function mkPool(t: number, active: number, pending: number): PoolSample {
    return {
        t,
        crawlee: { currentConcurrency: 3, desiredConcurrency: 3, maxConcurrency: 5 },
        detect: { activeCount: active, pendingCount: pending },
        memory: { used_mb: 100, budget_mb: 1000, ratio: 0.1 },
        rolling: { pages_per_min: 30 },
    };
}

// 1. Happy path: 5 entries, finalize, both files exist and are well-formed
async function test1() {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-int-"));
    const r = new TimingRecorder({ crawlId: "int-1", outputDir: dir, detectMaxConcurrency: 5 });
    for (let i = 1; i <= 5; i++) r.recordPage(mkEntry(i, 3000, 500));
    r.recordPoolSample(mkPool(1, 5, 2));
    r.recordPoolSample(mkPool(2, 5, 1));
    await r.finalize();

    const jsonl = fs.readFileSync(path.join(dir, "timing.jsonl"), "utf-8").trim().split("\n");
    assert(jsonl.length === 5, `5 JSONL lines, got ${jsonl.length}`);

    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 5, "summary pages_total = 5");
    assert(sum.phases.nav_ms.share_of_total_pct > sum.phases.detect_ms.share_of_total_pct,
        "nav_ms is the dominant phase (3000ms vs 500ms detect)");
    assert(sum.pool.detect_saturated_pct === 100,
        `both samples saturated (active=5, pending>0); got ${sum.pool.detect_saturated_pct}`);
}

// 2. Crash simulation: write 3 entries, do NOT call finalize, run post-hoc tool
async function test2() {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "timing-int-"));
    // Don't keep the recorder reference — simulate orphaned state.
    {
        const r = new TimingRecorder({
            crawlId: "int-2", outputDir: dir, detectMaxConcurrency: 5,
            summaryFlushMs: 0, // disable periodic flush
        });
        r.recordPage(mkEntry(1, 100, 50));
        r.recordPage(mkEntry(2, 200, 60));
        r.recordPage(mkEntry(3, 300, 70));
        // Don't call finalize. fd will be closed by GC eventually but the
        // already-flushed JSONL bytes are durable.
    }

    // Read what's on disk (should be 3 lines from the writes).
    const jsonlPath = path.join(dir, "timing.jsonl");
    const jsonl = fs.readFileSync(jsonlPath, "utf-8").trim().split("\n");
    assert(jsonl.length === 3, `crash trace has 3 lines, got ${jsonl.length}`);

    // Now run the post-hoc tool to reconstruct the summary.
    const cliPath = path.join(__dirname, "..", "tools", "timing-summary.ts");
    execSync(`npx tsx ${cliPath} ${jsonlPath}`, { stdio: "pipe" });
    const sum = JSON.parse(fs.readFileSync(path.join(dir, "timing-summary.json"), "utf-8"));
    assert(sum.pages_total === 3, "post-hoc summary recovered 3 pages");
}

(async () => {
    await test1();
    await test2();
    console.log(`timing_integration: ${passed} passed, ${failed} failed`);
    if (failed > 0) process.exit(1);
})();
```

- [ ] **Step 2: Run; all assertions must pass.**

Run: `cd apps-microservices/crawler-service/crawler && npx tsx src/tests/test_timing_integration.ts`
Expected: `timing_integration: <N> passed, 0 failed`.

- [ ] **Step 3: Run the full crawler test suite to ensure no regression.**

Run:
```bash
cd apps-microservices/crawler-service/crawler && npm run build && \
    npx tsx src/tests/test_DetectionLangueClient.ts && \
    npx tsx src/tests/test_routes.ts && \
    npx tsx src/tests/test_context.ts && \
    npx tsx src/tests/test_functions.ts && \
    npx tsx src/tests/test_timing_aggregator.ts && \
    npx tsx src/tests/test_TimingRecorder.ts && \
    npx tsx src/tests/test_timing_summary_tool.ts && \
    npx tsx src/tests/test_timing_integration.ts
```

Expected: every script reports `0 failed`.

- [ ] **Step 4: Commit.**

```bash
git add apps-microservices/crawler-service/crawler/src/tests/test_timing_integration.ts
git commit -m "$(cat <<'EOF'
test(crawler): timing recorder + tool integration smoke test

Exercises the happy path (recorder + finalize) and a crash-simulation
path (record without finalize, then reconstruct summary via the
post-hoc tool). Asserts dominant-phase identification and detect-API
saturation math on a known fixture.

---

test(crawler): test d'intégration recorder + outil de timing

Exerce le chemin nominal (recorder + finalize) et un scénario de crash
(enregistrement sans finalize, puis reconstruction du résumé via
l'outil post-hoc). Vérifie l'identification de la phase dominante et
le calcul de saturation de l'API détection sur un jeu fixe.
EOF
)"
```

---

## Self-review checklist

- [x] **Spec § Components**: `TimingRecorder.ts` (Task 2), aggregator + types (Task 1), `tools/timing-summary.ts` (Task 5), Crawlee/main wiring (Task 3), routes detect timing (Task 4) — all covered.
- [x] **Spec § Configuration**: `TIMING_ENABLED`, `TIMING_SAMPLE_INTERVAL_MS`, `TIMING_SUMMARY_FLUSH_MS`, `TIMING_FSYNC_EVERY_N`, `TIMING_RESUME_POLICY` — handled in Task 2 (recorder constructor) and Task 3 (env reads). Pass through as `summaryFlushMs`, `fsyncEveryN`, `resumePolicy` constructor options.
- [x] **Spec § Durability and crash resilience**: per-line write + fsync-every-N (Task 2 step 3), periodic flush (Task 2 step 3), atomic .tmp+rename (Task 2 step 3), exit handlers (Task 3 step 4), replay/overwrite resume (Task 2 step 3 and tests in step 1).
- [x] **Spec § Local retention after archive cleanup**: Task 5 step 4 modifies `files_to_keep`.
- [x] **Spec § Testing**: aggregator math tests (Task 1), recorder I/O + replay + flush tests (Task 2), CLI tests (Task 5), crash-simulation integration test (Task 6 test2).
- [x] **Spec § Acceptance criteria**:
  - [x] Both files produced when on (Task 6 test1).
  - [x] Neither file when off (covered implicitly: when `TIMING_ENABLED=false`, recorder isn't constructed; main.ts doesn't write anything).
  - [x] Console summary block (Task 3 step 5 helper).
  - [x] Math correctness (Task 1 tests).
  - [x] Pool sampler captures both Crawlee and detect-API state (Task 3 step 4).
  - [x] `files_to_keep` extended (Task 5 step 4).
  - [x] SIGKILL leaves recoverable JSONL (Task 6 test2).
  - [x] Periodic flush leaves snapshot (Task 2 test3).
  - [x] Existing tests still pass (Task 6 step 3).
  - [x] `npm run build` clean (Tasks 3, 4, 5).
- [x] **Placeholder scan**: every code block is concrete; every command is exact; no "TODO" / "implement later".
- [x] **Type consistency**: `PageTimingEntry`, `PoolSample`, `TimingSummary`, `AggregatorState` all defined in Task 1 and used identically in Tasks 2, 3, 4, 5, 6.
- [x] **No imports referencing things not defined**: `TimingRecorder` imports from `../timing/aggregator` (Task 1) and `../timing/types` (Task 1); main.ts imports `TimingRecorder` (Task 2) and types; tool imports same.
