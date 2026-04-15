/**
 * System stats helpers — aggregated counters over time windows.
 *
 * Sources:
 *  - Jobs: Redis MGET on crawl_job:* keys (filter by start_time)
 *  - Capacity: optional, from capacity:history:zset
 */

import { readCapacityHistory } from './capacityHistory.js';

const WINDOW_MAP = {
  '1h': 3600000,
  '24h': 86400000,
  '7d': 604800000,
};

export function parseStatsWindow(input) {
  if (typeof input !== 'string' || !(input in WINDOW_MAP)) {
    throw new Error("Invalid window. Use '1h', '24h' or '7d'.");
  }
  return WINDOW_MAP[input];
}

/**
 * Aggregate metrics from a list of jobs that started within `windowMs`.
 * Pure: no side effects, easy to test.
 */
export function aggregateJobStats(jobs, nowMs, windowMs) {
  const cutoff = nowMs - windowMs;
  const inWindow = jobs.filter(j => {
    const t = Date.parse(j.start_time);
    return Number.isFinite(t) && t >= cutoff;
  });

  const counts = { finished: 0, failed: 0, running: 0, archived: 0, restarting_oom: 0, stopping: 0, other: 0 };
  let oomTotal = 0;
  let updateMode = 0;
  let durationsMs = []; // for finished jobs only

  for (const j of inWindow) {
    const status = (j.status || 'other').toLowerCase();
    if (status in counts) counts[status]++;
    else counts.other++;
    oomTotal += j.oom_restart_count || 0;
    if (j.crawl_mode === 'update') updateMode++;
    if (status === 'finished' && j.start_time && j.end_time) {
      const d = Date.parse(j.end_time) - Date.parse(j.start_time);
      if (Number.isFinite(d) && d >= 0) durationsMs.push(d);
    }
  }

  const total = inWindow.length;
  const completed = counts.finished + counts.failed; // jobs with terminal status (excludes archived/running)
  const successRate = completed > 0 ? counts.finished / completed : null;

  const avgDurationMs = durationsMs.length > 0
    ? Math.round(durationsMs.reduce((a, b) => a + b, 0) / durationsMs.length)
    : null;

  return {
    total,
    counts,
    success_rate: successRate,            // 0..1 or null if no terminal jobs
    avg_duration_ms: avgDurationMs,        // null if no finished jobs
    oom_restarts_total: oomTotal,
    update_mode_count: updateMode,
  };
}

/**
 * Aggregate saturation stats from capacity history points.
 * Returns saturated_seconds (sum of intervals where full was true) and saturated_pct.
 */
export function aggregateSaturation(points, windowMs) {
  if (!points || points.length < 2) {
    return { saturated_seconds: 0, saturated_pct: null };
  }
  let saturatedMs = 0;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    if (prev.full) {
      const dt = curr.ts - prev.ts;
      if (dt > 0) saturatedMs += dt;
    }
  }
  return {
    saturated_seconds: Math.round(saturatedMs / 1000),
    saturated_pct: windowMs > 0 ? saturatedMs / windowMs : null,
  };
}

/**
 * High-level: load jobs + capacity history and compute everything for a single window.
 * `loadJobs(client) -> Promise<Job[]>` is injected for testability.
 */
export async function computeSystemStats(client, windowMs, { loadJobs } = {}) {
  const now = Date.now();
  const jobs = await loadJobs(client);
  const jobStats = aggregateJobStats(jobs, now, windowMs);

  let saturationStats = { saturated_seconds: 0, saturated_pct: null };
  try {
    const points = await readCapacityHistory(client, windowMs);
    saturationStats = aggregateSaturation(points, windowMs);
  } catch (err) {
    // capacity history is best-effort
  }

  return {
    jobs: jobStats,
    capacity: saturationStats,
  };
}