/**
 * Alerts rules engine.
 *
 * Pure functions: given recent state (jobs, capacity history, replicas
 * history, callbacks count), evaluate the configured rules and return a
 * normalized list of alerts.
 *
 * Thresholds come from env vars (Phase 3 = hardcoded). Phase 4 will allow
 * runtime configuration.
 */

export const DEFAULT_THRESHOLDS = {
  // error_rate_high: failed/completed >= threshold (over last 1h)
  errorRateThreshold:    parseFloat(process.env.ALERT_ERROR_RATE_THRESHOLD || '0.05'),
  errorRateMinJobs:      parseInt(process.env.ALERT_ERROR_RATE_MIN_JOBS || '5', 10),
  // oom_spike: sum of oom_restart_count over 1h >= threshold
  oomSpikeThreshold:     parseInt(process.env.ALERT_OOM_SPIKE_THRESHOLD || '3', 10),
  // replica_high_cpu_sustained: cpu > threshold for >= duration
  replicaHighCpu:        parseFloat(process.env.ALERT_REPLICA_HIGH_CPU || '0.85'),
  replicaHighCpuDurMs:   parseInt(process.env.ALERT_REPLICA_HIGH_CPU_MIN_DURATION || '240000', 10),
  // capacity_full_sustained: full=true continuously for >= duration
  capacityFullDurMs:     parseInt(process.env.ALERT_CAPACITY_FULL_DURATION || '300000', 10),
  // callbacks_failing: count >= min
  callbacksFailedMin:    parseInt(process.env.ALERT_CALLBACKS_FAILED_MIN || '1', 10),
};

const ONE_HOUR_MS = 60 * 60 * 1000;

/* ---------- Individual rules (pure) ---------- */

export function evalErrorRate(jobs, nowMs, thresholds) {
  const cutoff = nowMs - ONE_HOUR_MS;
  const inWindow = jobs.filter(j => {
    const t = Date.parse(j.start_time);
    return Number.isFinite(t) && t >= cutoff;
  });
  const failed   = inWindow.filter(j => (j.status || '').toLowerCase() === 'failed').length;
  const finished = inWindow.filter(j => ['finished', 'archived'].includes((j.status || '').toLowerCase())).length;
  const completed = failed + finished;
  if (completed < thresholds.errorRateMinJobs) return null;
  const rate = failed / completed;
  if (rate < thresholds.errorRateThreshold) return null;
  return {
    id: 'error_rate_high:1h',
    severity: 'warn',
    kind: 'error_rate_high',
    message: `Taux d'erreur ${(rate * 100).toFixed(1)}% sur 1h (${failed}/${completed})`,
    since: null,
    metadata: { rate, failed, completed, window: '1h', threshold: thresholds.errorRateThreshold },
  };
}

export function evalOomSpike(jobs, nowMs, thresholds) {
  const cutoff = nowMs - ONE_HOUR_MS;
  let total = 0;
  for (const j of jobs) {
    const t = Date.parse(j.start_time);
    if (!Number.isFinite(t) || t < cutoff) continue;
    total += j.oom_restart_count || 0;
  }
  if (total < thresholds.oomSpikeThreshold) return null;
  return {
    id: 'oom_spike:1h',
    severity: 'critical',
    kind: 'oom_spike',
    message: `${total} OOM restarts cumulés sur 1h`,
    since: null,
    metadata: { total, window: '1h', threshold: thresholds.oomSpikeThreshold },
  };
}

/**
 * For a single replica: if the last contiguous streak of points where
 * cpu > threshold has duration >= durMs, emit an alert.
 *
 * `points`: chronological array of { ts, cpu } objects.
 */
export function evalReplicaHighCpu(replicaId, points, nowMs, thresholds) {
  if (!points || points.length === 0) return null;
  const last = points[points.length - 1];
  if ((last.cpu || 0) <= thresholds.replicaHighCpu) return null;
  // Walk back to find streak start
  let streakStart = last.ts;
  for (let i = points.length - 2; i >= 0; i--) {
    if ((points[i].cpu || 0) > thresholds.replicaHighCpu) {
      streakStart = points[i].ts;
    } else {
      break;
    }
  }
  const dur = last.ts - streakStart;
  if (dur < thresholds.replicaHighCpuDurMs) return null;
  return {
    id: `replica_high_cpu:${replicaId}`,
    severity: 'warn',
    kind: 'replica_high_cpu_sustained',
    message: `Replica ${replicaId.slice(0, 12)} : CPU > ${(thresholds.replicaHighCpu * 100).toFixed(0)}% depuis ${Math.floor(dur / 60000)} min`,
    since: streakStart,
    metadata: { replicaId, current_cpu: last.cpu, duration_ms: dur, threshold: thresholds.replicaHighCpu },
  };
}

/**
 * Capacity has been continuously full for >= capacityFullDurMs.
 * `points`: chronological [{ts, full}, ...].
 */
export function evalCapacitySaturation(points, nowMs, thresholds) {
  if (!points || points.length === 0) return null;
  const last = points[points.length - 1];
  if (!last.full) return null;
  let streakStart = last.ts;
  for (let i = points.length - 2; i >= 0; i--) {
    if (points[i].full) {
      streakStart = points[i].ts;
    } else {
      break;
    }
  }
  const dur = last.ts - streakStart;
  if (dur < thresholds.capacityFullDurMs) return null;
  return {
    id: 'capacity_full',
    severity: 'critical',
    kind: 'capacity_full_sustained',
    message: `Capacité saturée depuis ${Math.floor(dur / 60000)} min`,
    since: streakStart,
    metadata: { duration_ms: dur, threshold_ms: thresholds.capacityFullDurMs },
  };
}

export function evalCallbacksFailing(failedCallbackCount, thresholds) {
  if (!failedCallbackCount || failedCallbackCount < thresholds.callbacksFailedMin) return null;
  return {
    id: 'callbacks_failing',
    severity: 'critical',
    kind: 'callbacks_failing',
    message: `${failedCallbackCount} callback${failedCallbackCount > 1 ? 's' : ''} en échec à rejouer`,
    since: null,
    metadata: { count: failedCallbackCount },
  };
}

/* ---------- Aggregator ---------- */

/**
 * Evaluate every rule and return the non-null alerts.
 *
 * `inputs`:
 *   { jobs, capacityPoints, replicasHistory: { id: [{ts, cpu}, ...] },
 *     failedCallbackCount }
 */
export function evaluateAlerts(inputs, nowMs = Date.now(), thresholds = DEFAULT_THRESHOLDS) {
  const out = [];

  const er = evalErrorRate(inputs.jobs || [], nowMs, thresholds);
  if (er) out.push(er);

  const oom = evalOomSpike(inputs.jobs || [], nowMs, thresholds);
  if (oom) out.push(oom);

  const cap = evalCapacitySaturation(inputs.capacityPoints || [], nowMs, thresholds);
  if (cap) out.push(cap);

  const cb = evalCallbacksFailing(inputs.failedCallbackCount || 0, thresholds);
  if (cb) out.push(cb);

  for (const [id, points] of Object.entries(inputs.replicasHistory || {})) {
    const a = evalReplicaHighCpu(id, points, nowMs, thresholds);
    if (a) out.push(a);
  }

  // Sort: critical first, then by kind for stability
  const sevWeight = { critical: 0, warn: 1, info: 2 };
  out.sort((a, b) => (sevWeight[a.severity] - sevWeight[b.severity]) || a.kind.localeCompare(b.kind));
  return out;
}