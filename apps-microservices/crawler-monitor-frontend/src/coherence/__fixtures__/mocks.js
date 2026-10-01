/**
 * Shared test fixtures for coherence rules.
 * Helpers return shapes that mirror the real props/query data.
 */

export const mkReplica = (id, overrides = {}) => ({
  replicaId: id,
  cpu: 0,
  ram: 0,
  totalRam: 6 * 1024 * 1024 * 1024,
  jobId: null,
  timestamp: Date.now(),
  ...overrides,
});

export const mkCapacity = (overrides = {}) => ({
  running_jobs: 0,
  max_global_jobs: 7,
  is_full: false,
  ...overrides,
});

export const mkJob = (id, overrides = {}) => ({
  id,
  status: 'running',
  start_time: new Date().toISOString(),
  end_time: null,
  ...overrides,
});

export const mkCapacityPlanningData = (replicas = []) => ({
  replicas,
  totals: {
    total_allocated: replicas.reduce((s, r) => s + (r.allocated ?? 0), 0),
    total_peak_worst: replicas.reduce((s, r) => s + (r.peak ?? 0), 0),
    total_avg: 0,
    waste: 0,
    waste_pct: 0,
    efficiency: 0,
    replica_count: replicas.length,
  },
  window: '1h',
  window_ms: 3600000,
  generated_at: new Date().toISOString(),
});
