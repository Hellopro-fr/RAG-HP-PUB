import type {
    AggregatorState,
    PageTimingEntry,
    PhaseStats,
    PoolSample,
    TimingSummary,
} from "./types.js";

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
    // Nearest-rank percentile (1-indexed): rank = ceil(p/100 * N), value = sorted[rank-1].
    // Matches the test expectations documented inline (e.g. p95 of 1..100*10 = 950).
    const rank = Math.max(1, Math.ceil((p / 100) * sorted.length));
    return sorted[Math.min(rank - 1, sorted.length - 1)];
}

function median(sorted: number[]): number {
    if (sorted.length === 0) return 0;
    if (sorted.length === 1) return sorted[0];
    // Median: average of the two middle values for even N, middle value for odd N.
    const mid = Math.floor(sorted.length / 2);
    if (sorted.length % 2 === 0) {
        return (sorted[mid - 1] + sorted[mid]) / 2;
    }
    return sorted[mid];
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
        endAt = Math.max(...state.pages.map((p: PageTimingEntry) => p.t + p.total_ms));
    }
    const durationS = N === 0 ? 0 : Math.max(1, Math.round((endAt - startedAt) / 1000));

    const phaseValues = (key: keyof PageTimingEntry): number[] =>
        state.pages.map((p: PageTimingEntry) => Number(p[key] ?? 0));

    const totalSum = phaseValues("total_ms").reduce((a: number, b: number) => a + b, 0);

    // Pages per minute: average across the run, max sustained over a 60s window.
    const ppmAvg = N === 0 || durationS === 0 ? 0 : round1((N / durationS) * 60);
    let ppmMax = 0;
    if (N > 0) {
        const sortedTs = state.pages
            .map((p: PageTimingEntry) => p.t)
            .sort((a: number, b: number) => a - b);
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
