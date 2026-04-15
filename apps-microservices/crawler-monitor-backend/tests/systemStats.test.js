import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  parseStatsWindow,
  aggregateJobStats,
  aggregateSaturation,
} from '../src/lib/systemStats.js';

test('parseStatsWindow accepts 1h, 24h, 7d', () => {
  assert.equal(parseStatsWindow('1h'), 3600000);
  assert.equal(parseStatsWindow('24h'), 86400000);
  assert.equal(parseStatsWindow('7d'), 604800000);
});

test('parseStatsWindow rejects others', () => {
  assert.throws(() => parseStatsWindow('30m'), /Invalid window/);
  assert.throws(() => parseStatsWindow(''), /Invalid window/);
  assert.throws(() => parseStatsWindow(null), /Invalid window/);
});

test('aggregateJobStats counts statuses, success rate, oom, update mode', () => {
  const now = Date.now();
  const jobs = [
    { start_time: new Date(now - 60000).toISOString(),  end_time: new Date(now - 30000).toISOString(), status: 'finished', crawl_mode: 'standard' },
    { start_time: new Date(now - 120000).toISOString(), end_time: new Date(now - 90000).toISOString(), status: 'finished', crawl_mode: 'update', oom_restart_count: 1 },
    { start_time: new Date(now - 180000).toISOString(), end_time: new Date(now - 150000).toISOString(), status: 'failed' },
    { start_time: new Date(now - 200000).toISOString(), status: 'running' },
    // outside 1h window
    { start_time: new Date(now - 7200000).toISOString(), end_time: new Date(now - 7100000).toISOString(), status: 'finished' },
  ];
  const s = aggregateJobStats(jobs, now, 3600000);
  assert.equal(s.total, 4);
  assert.equal(s.counts.finished, 2);
  assert.equal(s.counts.failed, 1);
  assert.equal(s.counts.running, 1);
  // success_rate = 2 finished / (2 finished + 1 failed) = 0.666...
  assert.ok(Math.abs(s.success_rate - 2 / 3) < 1e-6);
  assert.equal(s.oom_restarts_total, 1);
  assert.equal(s.update_mode_count, 1);
  assert.ok(s.avg_duration_ms > 0);
});

test('aggregateJobStats returns null success_rate when no terminal jobs', () => {
  const now = Date.now();
  const jobs = [{ start_time: new Date(now - 60000).toISOString(), status: 'running' }];
  const s = aggregateJobStats(jobs, now, 3600000);
  assert.equal(s.success_rate, null);
  assert.equal(s.avg_duration_ms, null);
});

test('aggregateJobStats returns zero totals on empty input', () => {
  const s = aggregateJobStats([], Date.now(), 3600000);
  assert.equal(s.total, 0);
  assert.equal(s.success_rate, null);
});

test('aggregateSaturation sums full intervals', () => {
  const now = Date.now();
  // 5 points 60s apart, 2 of them full=true contiguous
  const points = [
    { ts: now - 300000, running: 5, max: 10, full: false },
    { ts: now - 240000, running: 10, max: 10, full: true },  // full from -240 to -180 (60s)
    { ts: now - 180000, running: 10, max: 10, full: true },  // full from -180 to -120 (60s)
    { ts: now - 120000, running: 5,  max: 10, full: false }, // ends streak
    { ts: now - 60000,  running: 7,  max: 10, full: false },
  ];
  const s = aggregateSaturation(points, 300000);
  // saturated = 120 seconds
  assert.equal(s.saturated_seconds, 120);
  // 120000 / 300000 = 0.4
  assert.ok(Math.abs(s.saturated_pct - 0.4) < 1e-6);
});

test('aggregateSaturation handles too-few points', () => {
  const s = aggregateSaturation([], 3600000);
  assert.equal(s.saturated_seconds, 0);
  assert.equal(s.saturated_pct, null);
});