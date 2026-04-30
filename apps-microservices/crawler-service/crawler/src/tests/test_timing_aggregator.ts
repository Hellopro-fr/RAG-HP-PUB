import {
    createAggregator,
    addPage,
    addPoolSample,
    buildSummary,
} from "../timing/aggregator.js";
import type { PageTimingEntry, PoolSample } from "../timing/types.js";

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
if (failed > 0 || passed === 0) process.exit(1);
