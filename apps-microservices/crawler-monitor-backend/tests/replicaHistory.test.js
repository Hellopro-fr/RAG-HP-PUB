import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseReplicaWindow,
  persistHeartbeat,
  readReplicaHistory,
  readAllReplicasHistory,
  REPLICA_HISTORY_PREFIX,
  KNOWN_REPLICAS_KEY,
  REPLICA_HISTORY_RETENTION_MS,
} from '../src/lib/replicaHistory.js';

function makeFakeClient() {
  const zsets = new Map(); // key -> [{score, value}]
  const sets = new Map();  // key -> Set
  const zsetOf = (key) => {
    if (!zsets.has(key)) zsets.set(key, []);
    return zsets.get(key);
  };
  const setOf = (key) => {
    if (!sets.has(key)) sets.set(key, new Set());
    return sets.get(key);
  };
  return {
    _zsets: zsets,
    _sets: sets,
    async zAdd(key, { score, value }) { zsetOf(key).push({ score, value }); },
    async zRangeByScore(key, min, max) {
      const lo = Number(min);
      const hi = max === '+inf' ? Infinity : Number(max);
      return zsetOf(key).filter(e => e.score >= lo && e.score <= hi).map(e => e.value);
    },
    async zRemRangeByScore(key, min, max) {
      const lo = min === '-inf' ? -Infinity : Number(min);
      const hi = Number(max);
      const arr = zsetOf(key);
      for (let i = arr.length - 1; i >= 0; i--) {
        if (arr[i].score >= lo && arr[i].score <= hi) arr.splice(i, 1);
      }
    },
    async sAdd(key, ...members) { for (const m of members.flat()) setOf(key).add(m); },
    async sRem(key, ...members) { for (const m of members.flat()) setOf(key).delete(m); },
    async sMembers(key) { return Array.from(setOf(key)); },
  };
}

test('parseReplicaWindow accepts 15m and 1h, rejects others', () => {
  assert.equal(parseReplicaWindow('15m'), 15 * 60 * 1000);
  assert.equal(parseReplicaWindow('1h'), 60 * 60 * 1000);
  assert.throws(() => parseReplicaWindow('1d'), /Invalid window/);
  assert.throws(() => parseReplicaWindow(''), /Invalid window/);
});

test('persistHeartbeat ZADDs sample and registers known replica', async () => {
  const c = makeFakeClient();
  await persistHeartbeat(c, {
    replicaId: 'r1',
    jobId: 'job-a',
    timestamp: Date.now(),
    cpu: 0.42,
    ram: 1024,
    totalRam: 4096,
  });
  const samples = c._zsets.get(REPLICA_HISTORY_PREFIX + 'r1');
  assert.equal(samples.length, 1);
  const parsed = JSON.parse(samples[0].value);
  assert.equal(parsed.cpu, 0.42);
  assert.equal(parsed.jobId, 'job-a');
  assert.ok(c._sets.get(KNOWN_REPLICAS_KEY).has('r1'));
});

test('persistHeartbeat tolerates missing fields without throwing', async () => {
  const c = makeFakeClient();
  await persistHeartbeat(c, null);
  await persistHeartbeat(c, {});
  await persistHeartbeat(c, { replicaId: 'r1' }); // valid
  assert.equal(c._zsets.get(REPLICA_HISTORY_PREFIX + 'r1').length, 1);
});

test('persistHeartbeat trims samples older than retention', async () => {
  const c = makeFakeClient();
  // Inject an old sample directly
  const oldTs = Date.now() - REPLICA_HISTORY_RETENTION_MS - 60000;
  c._zsets.set(REPLICA_HISTORY_PREFIX + 'r1', [{ score: oldTs, value: '{"ts":0,"cpu":0,"ram":0,"totalRam":0,"jobId":null}' }]);
  await persistHeartbeat(c, { replicaId: 'r1', timestamp: Date.now(), cpu: 0.5, ram: 100, totalRam: 1000 });
  const samples = c._zsets.get(REPLICA_HISTORY_PREFIX + 'r1');
  // Old sample should be pruned, new one kept
  assert.equal(samples.length, 1);
  assert.equal(JSON.parse(samples[0].value).cpu, 0.5);
});

test('readReplicaHistory returns recent points', async () => {
  const c = makeFakeClient();
  const now = Date.now();
  await persistHeartbeat(c, { replicaId: 'r1', timestamp: now - 1000, cpu: 0.1, ram: 10, totalRam: 1000 });
  await persistHeartbeat(c, { replicaId: 'r1', timestamp: now,        cpu: 0.2, ram: 20, totalRam: 1000 });
  const points = await readReplicaHistory(c, 'r1', 60 * 60 * 1000);
  assert.equal(points.length, 2);
  assert.equal(points[0].cpu, 0.1);
  assert.equal(points[1].cpu, 0.2);
});

test('readAllReplicasHistory returns map of replicaId -> points and drops orphans', async () => {
  const c = makeFakeClient();
  const now = Date.now();
  await persistHeartbeat(c, { replicaId: 'r1', timestamp: now, cpu: 0.1, ram: 10 });
  // Inject orphan replica with no recent points
  await c.sAdd(KNOWN_REPLICAS_KEY, 'r-ghost');
  const all = await readAllReplicasHistory(c, 60 * 60 * 1000);
  assert.equal(Object.keys(all).length, 1);
  assert.ok(all.r1);
  assert.ok(!all['r-ghost']);
  // Ghost should have been removed from known set
  assert.ok(!c._sets.get(KNOWN_REPLICAS_KEY).has('r-ghost'));
});