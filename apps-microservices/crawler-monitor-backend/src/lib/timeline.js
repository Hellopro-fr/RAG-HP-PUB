/**
 * Timeline aggregator.
 *
 * Buckets jobs by their `start_time` over a sliding window and produces a
 * series of {ts, success, failure, running, oom} counts ready to plot
 * as a stacked bar chart.
 *
 * Granularity is derived from the window so the chart always lands ~60-180
 * buckets wide (sweet spot for readability).
 */

const WINDOWS = {
  '1h':  { ms: 60 * 60 * 1000,        granularityMs: 60 * 1000 },        // 60 buckets of 1 min
  '6h':  { ms: 6 * 60 * 60 * 1000,    granularityMs: 5 * 60 * 1000 },    // 72 buckets of 5 min
  '24h': { ms: 24 * 60 * 60 * 1000,   granularityMs: 15 * 60 * 1000 },   // 96 buckets of 15 min
  '7d':  { ms: 7 * 24 * 60 * 60 * 1000, granularityMs: 60 * 60 * 1000 }, // 168 buckets of 1 hour
};

export function parseTimelineWindow(input) {
  if (typeof input !== 'string' || !(input in WINDOWS)) {
    throw new Error("Invalid window. Use '1h', '6h', '24h' or '7d'.");
  }
  return WINDOWS[input];
}

const TERMINAL_OK = new Set(['finished', 'archived']);
const TERMINAL_KO = new Set(['failed']);
const RUNNING = new Set(['running', 'stopping', 'restarting_oom']);

/**
 * Bucket jobs into a fixed-width time series.
 * `nowMs` snapshot used for window slicing (testable).
 *
 * Each bucket counts jobs whose start_time falls in [bucket.ts, bucket.ts + granularityMs).
 * Buckets are ordered chronologically (oldest first), inclusive of empty ones.
 */
export function aggregateTimeline(jobs, nowMs, windowMs, granularityMs) {
  // Snap "now" to a bucket boundary so the latest bucket is fully visible
  const lastBucketTs = Math.floor(nowMs / granularityMs) * granularityMs;
  const firstBucketTs = lastBucketTs - windowMs + granularityMs;
  const numBuckets = Math.round(windowMs / granularityMs);

  // Pre-allocate buckets
  const buckets = new Array(numBuckets);
  for (let i = 0; i < numBuckets; i++) {
    buckets[i] = {
      ts: firstBucketTs + i * granularityMs,
      success: 0,
      failure: 0,
      running: 0,
      other: 0,
      oom_events: 0,
    };
  }

  for (const j of jobs || []) {
    const t = Date.parse(j.start_time);
    if (!Number.isFinite(t)) continue;
    if (t < firstBucketTs || t >= firstBucketTs + numBuckets * granularityMs) continue;
    const idx = Math.floor((t - firstBucketTs) / granularityMs);
    const b = buckets[idx];
    if (!b) continue;
    const status = (j.status || '').toLowerCase();
    if (TERMINAL_OK.has(status)) b.success++;
    else if (TERMINAL_KO.has(status)) b.failure++;
    else if (RUNNING.has(status)) b.running++;
    else b.other++;
    b.oom_events += j.oom_restart_count || 0;
  }

  return buckets;
}

/**
 * Derive a sensible granularity for a given window size.
 * Returns the granularityMs that keeps the chart at ~60-180 buckets.
 */
export function autoGranularity(windowMs) {
  if (windowMs <= 60 * 60 * 1000)          return 60 * 1000;          // ≤1h → 1 min
  if (windowMs <= 6 * 60 * 60 * 1000)      return 5 * 60 * 1000;     // ≤6h → 5 min
  if (windowMs <= 24 * 60 * 60 * 1000)     return 15 * 60 * 1000;    // ≤24h → 15 min
  if (windowMs <= 7 * 24 * 60 * 60 * 1000) return 60 * 60 * 1000;    // ≤7d → 1h
  return 6 * 60 * 60 * 1000;                                          // >7d → 6h
}

/**
 * Top-level: load jobs (via injected loader for tests) and aggregate.
 *
 * Accepts either:
 *   windowKey    — preset string like '6h'
 *   from/to      — ISO dates for a custom range (windowKey is ignored)
 */
export async function computeTimeline(client, windowKey, { loadJobs, from, to } = {}) {
  let windowMs, granularityMs, now;

  if (from && to) {
    const fromMs = Date.parse(from);
    const toMs = Date.parse(to);
    if (!Number.isFinite(fromMs) || !Number.isFinite(toMs) || toMs <= fromMs) {
      throw new Error("Invalid 'from'/'to' dates.");
    }
    windowMs = toMs - fromMs;
    granularityMs = autoGranularity(windowMs);
    now = toMs; // anchor at 'to' so the last bucket is aligned there
  } else {
    const w = parseTimelineWindow(windowKey);
    windowMs = w.ms;
    granularityMs = w.granularityMs;
    now = Date.now();
  }

  const jobs = await loadJobs(client);
  const buckets = aggregateTimeline(jobs, now, windowMs, granularityMs);
  return {
    window: from ? 'custom' : windowKey,
    window_ms: windowMs,
    granularity_ms: granularityMs,
    from: from || null,
    to: to || null,
    buckets,
    generated_at: new Date().toISOString(),
  };
}