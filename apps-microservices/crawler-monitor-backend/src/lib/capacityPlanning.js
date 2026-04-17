/**
 * Capacity planning helpers — answer "can we reduce RAM per replica and run
 * more of them?". Aggregates historical heartbeats (stored per-job in
 * job:perf:* with 7d retention) grouped by replicaId.
 *
 * Source of truth:
 *   - window=1h  : replica:history:<id> (2s granularity)
 *   - window=24h : job:perf:* scanned + regrouped (covers up to 7d of data)
 *   - window=7d  : job:perf:*
 *
 * Stats per replica: allocated (max totalRam seen), peak (max ram),
 * avg (mean ram), sample count, last seen timestamp.
 */

import { JOB_PERF_PREFIX } from './jobPerformance.js';
import { readAllReplicasHistory } from './replicaHistory.js';

const WINDOW_MAP = {
  '1h':  60 * 60 * 1000,
  '24h': 24 * 60 * 60 * 1000,
  '7d':  7 * 24 * 60 * 60 * 1000,
};

export function parsePlanningWindow(input) {
  if (typeof input !== 'string' || !(input in WINDOW_MAP)) {
    throw new Error("Invalid window. Use '1h', '24h' or '7d'.");
  }
  return WINDOW_MAP[input];
}

/**
 * Fold points into per-replica stats.
 * points: [{ ts, cpu, ram, totalRam, replicaId?, jobId? }, ...]
 */
export function aggregateByReplica(pointsByReplica) {
  const replicas = [];
  for (const [id, points] of Object.entries(pointsByReplica)) {
    if (!points || points.length === 0) continue;
    let allocated = 0;
    let peak = 0;
    let sum = 0;
    let lastTs = 0;
    for (const p of points) {
      const ram = p.ram || 0;
      const tot = p.totalRam || 0;
      if (tot > allocated) allocated = tot;
      if (ram > peak) peak = ram;
      sum += ram;
      if (p.ts > lastTs) lastTs = p.ts;
    }
    const avg = sum / points.length;
    replicas.push({
      replicaId: id,
      allocated,
      peak,
      avg,
      sample_count: points.length,
      last_seen: lastTs,
      efficiency: allocated > 0 ? peak / allocated : 0,
    });
  }
  // Sort by peak desc (most loaded first)
  replicas.sort((a, b) => b.peak - a.peak);
  return replicas;
}

/**
 * Totals + a naive "worst-case" peak-if-everyone-peaks-simultaneously figure.
 * Not the true temporal peak (which would require aligned time buckets) but
 * a safe upper bound useful for planning.
 */
export function computeTotals(replicas) {
  const total_allocated = replicas.reduce((a, r) => a + r.allocated, 0);
  const total_peak_worst = replicas.reduce((a, r) => a + r.peak, 0);
  const total_avg = replicas.reduce((a, r) => a + r.avg, 0);
  const waste = total_allocated - total_peak_worst;
  return {
    replica_count: replicas.length,
    total_allocated,
    total_peak_worst,
    total_avg,
    waste,
    waste_pct: total_allocated > 0 ? waste / total_allocated : 0,
    // Overall efficiency = peak used / total allocated
    efficiency: total_allocated > 0 ? total_peak_worst / total_allocated : 0,
  };
}

/**
 * Main entry: assemble per-replica stats over the given window.
 * Uses replica:history (fast, 1h) or scans job:perf (longer windows).
 *
 * `loaders`:
 *   - readReplicas(client, windowMs)           → { id: [points] }  (1h fast path)
 *   - scanJobPerf(client, windowMs, nowMs)     → { id: [points] }  (fallback long windows)
 */
export async function computeCapacityPlanning(client, windowKey, loaders = {}) {
  const windowMs = parsePlanningWindow(windowKey);
  const now = Date.now();

  let pointsByReplica;
  if (windowKey === '1h') {
    pointsByReplica = await (loaders.readReplicas || readAllReplicasHistory)(client, windowMs);
  } else {
    // Scan job:perf:* and group per-replica (24h / 7d)
    pointsByReplica = await (loaders.scanJobPerf || defaultScanJobPerf)(client, windowMs, now);
  }

  const replicas = aggregateByReplica(pointsByReplica);
  const totals = computeTotals(replicas);
  return {
    window: windowKey,
    window_ms: windowMs,
    generated_at: new Date(now).toISOString(),
    replicas,
    totals,
  };
}

/**
 * Default implementation of the long-window loader. Iterates all job:perf:*
 * keys, reads their points, and regroups by replicaId within the window.
 */
async function defaultScanJobPerf(client, windowMs, nowMs) {
  const cutoff = nowMs - windowMs;
  // KEYS is fine here — we keep a bounded set (few hundred jobs max in 7d).
  // A full SCAN would be safer for very large datasets; revisit if needed.
  const keys = await client.keys(`${JOB_PERF_PREFIX}*`);
  const pointsByReplica = {};
  for (const key of keys) {
    let raw;
    try {
      raw = await client.zRangeByScore(key, cutoff, '+inf');
    } catch { continue; }
    for (const s of raw) {
      let p;
      try { p = JSON.parse(s); } catch { continue; }
      if (!p || !p.replicaId) continue;
      if (!pointsByReplica[p.replicaId]) pointsByReplica[p.replicaId] = [];
      pointsByReplica[p.replicaId].push(p);
    }
  }
  return pointsByReplica;
}
