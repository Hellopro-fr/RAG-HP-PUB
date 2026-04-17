import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  parsePlanningWindow,
  aggregateByReplica,
  computeTotals,
  computeCapacityPlanning,
} from '../src/lib/capacityPlanning.js';

test('parsePlanningWindow accepts 1h/24h/7d', () => {
  assert.equal(parsePlanningWindow('1h'), 3600000);
  assert.equal(parsePlanningWindow('24h'), 86400000);
  assert.equal(parsePlanningWindow('7d'), 604800000);
  assert.throws(() => parsePlanningWindow('5m'), /Invalid window/);
});

test('aggregateByReplica computes allocated/peak/avg/efficiency', () => {
  const GB = 1024 * 1024 * 1024;
  const input = {
    'r1': [
      { ts: 1, ram: 1 * GB, totalRam: 6 * GB },
      { ts: 2, ram: 3 * GB, totalRam: 6 * GB },
      { ts: 3, ram: 2 * GB, totalRam: 6 * GB },
    ],
    'r2': [
      { ts: 1, ram: 5 * GB, totalRam: 6 * GB },
      { ts: 2, ram: 5.5 * GB, totalRam: 6 * GB },
    ],
  };
  const result = aggregateByReplica(input);
  assert.equal(result.length, 2);
  // Sorted by peak desc: r2 (5.5GB) before r1 (3GB)
  assert.equal(result[0].replicaId, 'r2');
  assert.equal(result[0].peak, 5.5 * GB);
  assert.equal(result[0].allocated, 6 * GB);
  assert.ok(Math.abs(result[0].efficiency - 5.5 / 6) < 1e-6);
  assert.equal(result[1].replicaId, 'r1');
  assert.equal(result[1].peak, 3 * GB);
  assert.equal(result[1].avg, 2 * GB);
  assert.equal(result[1].sample_count, 3);
});

test('aggregateByReplica skips empty replicas', () => {
  const r = aggregateByReplica({ 'r1': [], 'r2': [{ ts: 1, ram: 100, totalRam: 1000 }] });
  assert.equal(r.length, 1);
  assert.equal(r[0].replicaId, 'r2');
});

test('computeTotals returns waste and efficiency', () => {
  const GB = 1024 * 1024 * 1024;
  const replicas = [
    { replicaId: 'r1', allocated: 6 * GB, peak: 3 * GB, avg: 1.5 * GB, efficiency: 0.5 },
    { replicaId: 'r2', allocated: 6 * GB, peak: 5.5 * GB, avg: 4 * GB, efficiency: 0.92 },
  ];
  const t = computeTotals(replicas);
  assert.equal(t.replica_count, 2);
  assert.equal(t.total_allocated, 12 * GB);
  assert.equal(t.total_peak_worst, 8.5 * GB);
  assert.equal(t.total_avg, 5.5 * GB);
  assert.equal(t.waste, 3.5 * GB);
  // waste_pct = 3.5 / 12
  assert.ok(Math.abs(t.waste_pct - 3.5 / 12) < 1e-6);
});

test('computeTotals handles empty list', () => {
  const t = computeTotals([]);
  assert.equal(t.replica_count, 0);
  assert.equal(t.total_allocated, 0);
  assert.equal(t.efficiency, 0);
  assert.equal(t.waste_pct, 0);
});

test('computeCapacityPlanning uses injected 1h reader', async () => {
  const fakeClient = {};
  const readReplicas = async () => ({
    'r1': [{ ts: 1, ram: 100, totalRam: 200 }],
  });
  const result = await computeCapacityPlanning(fakeClient, '1h', { readReplicas });
  assert.equal(result.replicas.length, 1);
  assert.equal(result.replicas[0].peak, 100);
  assert.equal(result.totals.total_allocated, 200);
});

test('computeCapacityPlanning uses injected long-window loader for 7d', async () => {
  const fakeClient = {};
  const scanJobPerf = async () => ({
    'r1': [{ ts: 1, ram: 500, totalRam: 1000, replicaId: 'r1' }],
    'r2': [{ ts: 1, ram: 800, totalRam: 1000, replicaId: 'r2' }],
  });
  const result = await computeCapacityPlanning(fakeClient, '7d', { scanJobPerf });
  assert.equal(result.window, '7d');
  assert.equal(result.replicas.length, 2);
  assert.equal(result.totals.total_peak_worst, 1300);
});
