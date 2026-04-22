import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_THRESHOLDS,
  evalErrorRate,
  evalOomSpike,
  evalReplicaHighCpu,
  evalCapacitySaturation,
  evalCallbacksFailing,
  evaluateAlerts,
} from '../src/lib/alerts.js';

const T = {
  errorRateThreshold: 0.05,
  errorRateMinJobs: 5,
  oomSpikeThreshold: 3,
  replicaHighCpu: 0.85,
  replicaHighCpuDurMs: 240000,
  capacityFullDurMs: 300000,
  callbacksFailedMin: 1,
};

test('evalErrorRate ignored when too few jobs', () => {
  const now = Date.now();
  const jobs = [
    { start_time: new Date(now - 60000).toISOString(), status: 'failed' },
    { start_time: new Date(now - 60000).toISOString(), status: 'finished' },
  ];
  assert.equal(evalErrorRate(jobs, now, T), null);
});

test('evalErrorRate fires when threshold exceeded', () => {
  const now = Date.now();
  const jobs = [];
  for (let i = 0; i < 8; i++) jobs.push({ start_time: new Date(now - 1000 * i).toISOString(), status: 'finished' });
  for (let i = 0; i < 2; i++) jobs.push({ start_time: new Date(now - 1000 * i).toISOString(), status: 'failed' });
  // 2 / 10 = 20% > 5%
  const a = evalErrorRate(jobs, now, T);
  assert.ok(a);
  assert.equal(a.kind, 'error_rate_high');
  assert.ok(a.metadata.rate >= 0.2);
});

test('evalErrorRate ignores jobs outside 1h window', () => {
  const now = Date.now();
  const jobs = [];
  for (let i = 0; i < 10; i++) jobs.push({ start_time: new Date(now - 2 * 60 * 60 * 1000).toISOString(), status: 'failed' });
  assert.equal(evalErrorRate(jobs, now, T), null);
});

test('evalOomSpike sums oom counts across in-window jobs', () => {
  const now = Date.now();
  const jobs = [
    { start_time: new Date(now - 60000).toISOString(), status: 'finished', oom_restart_count: 2 },
    { start_time: new Date(now - 60000).toISOString(), status: 'finished', oom_restart_count: 2 },
  ];
  const a = evalOomSpike(jobs, now, T);
  assert.ok(a);
  assert.equal(a.metadata.total, 4);
  assert.equal(a.severity, 'critical');
});

test('evalOomSpike below threshold returns null', () => {
  const now = Date.now();
  const jobs = [{ start_time: new Date(now).toISOString(), status: 'finished', oom_restart_count: 2 }];
  assert.equal(evalOomSpike(jobs, now, T), null);
});

test('evalReplicaHighCpu fires when streak >= duration', () => {
  const now = Date.now();
  const points = [
    { ts: now - 5 * 60000, cpu: 0.5 },
    { ts: now - 4 * 60000, cpu: 0.9 },
    { ts: now - 3 * 60000, cpu: 0.91 },
    { ts: now - 2 * 60000, cpu: 0.92 },
    { ts: now - 1 * 60000, cpu: 0.93 },
    { ts: now,             cpu: 0.94 },
  ];
  const a = evalReplicaHighCpu('r1', points, now, T);
  assert.ok(a);
  assert.equal(a.kind, 'replica_high_cpu_sustained');
  assert.ok(a.metadata.duration_ms >= 240000);
});

test('evalReplicaHighCpu does not fire if recent dip', () => {
  const now = Date.now();
  const points = [
    { ts: now - 4 * 60000, cpu: 0.95 },
    { ts: now - 3 * 60000, cpu: 0.5 }, // dip
    { ts: now - 2 * 60000, cpu: 0.95 },
    { ts: now - 1 * 60000, cpu: 0.95 },
    { ts: now,             cpu: 0.95 },
  ];
  // Latest streak is only 4 min long (since now-4min after the dip... wait, dip was at -3, so streak is 3 min)
  assert.equal(evalReplicaHighCpu('r1', points, now, T), null);
});

test('evalReplicaHighCpu null when current cpu below threshold', () => {
  const now = Date.now();
  const points = [{ ts: now, cpu: 0.5 }];
  assert.equal(evalReplicaHighCpu('r1', points, now, T), null);
});

test('evalCapacitySaturation fires after sustained full', () => {
  const now = Date.now();
  const points = [
    { ts: now - 7 * 60000, full: false },
    { ts: now - 6 * 60000, full: true },
    { ts: now - 5 * 60000, full: true },
    { ts: now - 4 * 60000, full: true },
    { ts: now - 3 * 60000, full: true },
    { ts: now - 2 * 60000, full: true },
    { ts: now - 1 * 60000, full: true },
    { ts: now,             full: true },
  ];
  const a = evalCapacitySaturation(points, now, T);
  assert.ok(a);
  assert.equal(a.kind, 'capacity_full_sustained');
  assert.equal(a.severity, 'critical');
});

test('evalCallbacksFailing fires above min', () => {
  const a = evalCallbacksFailing(3, T);
  assert.ok(a);
  assert.equal(a.metadata.count, 3);
  assert.equal(evalCallbacksFailing(0, T), null);
});

test('evaluateAlerts aggregates and sorts critical-first', () => {
  const now = Date.now();
  const jobs = [];
  for (let i = 0; i < 10; i++) jobs.push({ start_time: new Date(now).toISOString(), status: i < 8 ? 'finished' : 'failed', oom_restart_count: 1 });
  const inputs = {
    jobs,
    capacityPoints: [],
    replicasHistory: {},
    failedCallbackCount: 2,
  };
  const alerts = evaluateAlerts(inputs, now, T);
  // 3 alerts: error_rate_high (warn) + oom_spike (critical, 10 * 1 = 10) + callbacks_failing (critical)
  assert.equal(alerts.length, 3);
  assert.equal(alerts[0].severity, 'critical');
  assert.equal(alerts[alerts.length - 1].severity, 'warn');
});

test('evaluateAlerts returns empty array on quiet system', () => {
  const alerts = evaluateAlerts({ jobs: [], capacityPoints: [], replicasHistory: {}, failedCallbackCount: 0 });
  assert.deepEqual(alerts, []);
});

test('DEFAULT_THRESHOLDS exposes the env-resolved values', () => {
  assert.ok(DEFAULT_THRESHOLDS);
  assert.ok(typeof DEFAULT_THRESHOLDS.errorRateThreshold === 'number');
});