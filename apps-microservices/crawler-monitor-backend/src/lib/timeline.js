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
 * Top-level: load jobs (via injected loader for tests) and aggregate.
 */
export async function computeTimeline(client, windowKey, { loadJobs }) {
  const w = parseTimelineWindow(windowKey);
  const jobs = await loadJobs(client);
  const buckets = aggregateTimeline(jobs, Date.now(), w.ms, w.granularityMs);
  return {
    window: windowKey,
    window_ms: w.ms,
    granularity_ms: w.granularityMs,
    buckets,
    generated_at: new Date().toISOString(),
  };
}