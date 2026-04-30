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
