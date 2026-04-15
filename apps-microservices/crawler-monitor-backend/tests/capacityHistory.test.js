import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseWindow,
  snapshotCapacity,
  readCapacityHistory,
  CAPACITY_HISTORY_KEY,
  RETENTION_MS,
} from '../src/lib/capacityHistory.js';

test('parseWindow accepts 1h, 6h, 24h', () => {
  assert.equal(parseWindow('1h'), 3600000);
  assert.equal(parseWindow('6h'), 21600000);
  assert.equal(parseWindow('24h'), 86400000);
});

test('parseWindow rejects invalid input', () => {
  assert.throws(() => parseWindow('2h'), /Invalid window/);
  assert.throws(() => parseWindow(''), /Invalid window/);
  assert.throws(() => parseWindow(null), /Invalid window/);
  assert.throws(() => parseWindow(60), /Invalid window/);
});

// Stub Redis client supporting only what we need.
function makeFakeClient(initial = {}) {
  const store = { ...initial };
  const zset = []; // { score, value }
  return {
    _zset: zset,
    async get(key) { return store[key] ?? null; },
    async set(key, value) { store[key] = value; },
    async zAdd(_key, { score, value }) { zset.push({ score, value }); },
    async zRangeByScore(_key, min, max) {
      const lo = Number(min);
      const hi = max === '+inf' ? Infinity : Number(max);
      return zset.filter(e => e.score >= lo && e.score <= hi).map(e => e.value);
    },
    async zRemRangeByScore(_key, min, max) {
      const lo = min === '-inf' ? -Infinity : Number(min);
      const hi = Number(max);
      const before = zset.length;
      for (let i = zset.length - 1; i >= 0; i--) {
        if (zset[i].score >= lo && zset[i].score <= hi) zset.splice(i, 1);
      }
      return before - zset.length;
    },
  };
}

test('snapshotCapacity writes a point and prunes old ones', async () => {
  const client = makeFakeClient({ run: '5', max: '10' });
  // Plant an old point
  client._zset.push({ score: Date.now() - RETENTION_MS - 1000, value: JSON.stringify({ ts: 1, running: 0, max: 0, full: false }) });

  const point = await snapshotCapacity(client, 'run', 'max');
  assert.equal(point.running, 5);
  assert.equal(point.max, 10);
  assert.equal(point.full, false);

  // Old point should have been pruned
  assert.equal(client._zset.length, 1);
  assert.equal(JSON.parse(client._zset[0].value).running, 5);
});

test('snapshotCapacity flags full when running >= max', async () => {
  const client = makeFakeClient({ run: '60', max: '60' });
  const point = await snapshotCapacity(client, 'run', 'max');
  assert.equal(point.full, true);
});

test('snapshotCapacity defaults missing keys to 0', async () => {
  const client = makeFakeClient({});
  const point = await snapshotCapacity(client, 'run', 'max');
  assert.equal(point.running, 0);
  assert.equal(point.max, 0);
  assert.equal(point.full, false);
});

test('readCapacityHistory returns points within window', async () => {
  const client = makeFakeClient();
  const now = Date.now();
  client._zset.push(
    { score: now - 7200000, value: JSON.stringify({ ts: now - 7200000, running: 1, max: 10, full: false }) }, // 2h ago
    { score: now - 1800000, value: JSON.stringify({ ts: now - 1800000, running: 5, max: 10, full: false }) }, // 30 min ago
    { score: now - 60000,   value: JSON.stringify({ ts: now - 60000,   running: 9, max: 10, full: false }) }, // 1 min ago
  );
  const last1h = await readCapacityHistory(client, 3600000);
  assert.equal(last1h.length, 2);
  assert.equal(last1h[0].running, 5);
  assert.equal(last1h[1].running, 9);
});