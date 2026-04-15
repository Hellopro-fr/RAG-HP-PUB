import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseTimelineWindow, aggregateTimeline } from '../src/lib/timeline.js';

test('parseTimelineWindow accepts known windows', () => {
  assert.equal(parseTimelineWindow('1h').ms, 3600000);
  assert.equal(parseTimelineWindow('6h').granularityMs, 5 * 60 * 1000);
  assert.equal(parseTimelineWindow('24h').granularityMs, 15 * 60 * 1000);
  assert.equal(parseTimelineWindow('7d').granularityMs, 60 * 60 * 1000);
});

test('parseTimelineWindow rejects others', () => {
  assert.throws(() => parseTimelineWindow('30m'), /Invalid window/);
  assert.throws(() => parseTimelineWindow(null), /Invalid window/);
});

test('aggregateTimeline produces fixed-width series with empty buckets', () => {
  const now = 1700000400000; // arbitrary aligned-ish timestamp
  const buckets = aggregateTimeline([], now, 60 * 60 * 1000, 60 * 1000);
  assert.equal(buckets.length, 60);
  // All zeros
  for (const b of buckets) {
    assert.equal(b.success, 0);
    assert.equal(b.failure, 0);
    assert.equal(b.running, 0);
    assert.equal(b.oom_events, 0);
  }
  // First bucket ts must be 60 * 60 * 1000 - 60 * 1000 before lastBucketTs
  const lastBucketTs = Math.floor(now / 60000) * 60000;
  assert.equal(buckets[buckets.length - 1].ts, lastBucketTs);
  assert.equal(buckets[0].ts, lastBucketTs - 59 * 60000);
});

test('aggregateTimeline counts statuses into the right bucket', () => {
  const now = Date.now();
  const granMs = 60 * 1000;
  const winMs = 60 * 60 * 1000;
  // Place a job 30 min ago, success
  const t1 = now - 30 * 60 * 1000;
  // Place a job 30 min ago, failed
  const t2 = now - 30 * 60 * 1000 + 100;
  // Job 5 min ago, running, with 2 OOM restarts
  const t3 = now - 5 * 60 * 1000;
  // Job outside window (2h ago) — must be ignored
  const t4 = now - 2 * 60 * 60 * 1000;

  const jobs = [
    { start_time: new Date(t1).toISOString(), status: 'finished' },
    { start_time: new Date(t2).toISOString(), status: 'failed' },
    { start_time: new Date(t3).toISOString(), status: 'running', oom_restart_count: 2 },
    { start_time: new Date(t4).toISOString(), status: 'finished' },
  ];

  const buckets = aggregateTimeline(jobs, now, winMs, granMs);

  // Sum the columns and compare with what we put in (within window only)
  const total = buckets.reduce((acc, b) => ({
    success: acc.success + b.success,
    failure: acc.failure + b.failure,
    running: acc.running + b.running,
    oom: acc.oom + b.oom_events,
  }), { success: 0, failure: 0, running: 0, oom: 0 });

  assert.equal(total.success, 1);
  assert.equal(total.failure, 1);
  assert.equal(total.running, 1);
  assert.equal(total.oom, 2);
});

test('aggregateTimeline aligns last bucket to current time, handles edge cases', () => {
  const now = Date.now();
  const granMs = 5 * 60 * 1000;
  const winMs = 60 * 60 * 1000; // 12 buckets of 5 min
  const buckets = aggregateTimeline([], now, winMs, granMs);
  assert.equal(buckets.length, 12);
  // last bucket ts must be a multiple of granularity
  assert.equal(buckets[buckets.length - 1].ts % granMs, 0);
});

test('aggregateTimeline ignores jobs with invalid start_time', () => {
  const now = Date.now();
  const jobs = [
    { start_time: 'not-a-date', status: 'finished' },
    { start_time: null, status: 'failed' },
    { /* missing start_time */ status: 'finished' },
  ];
  const buckets = aggregateTimeline(jobs, now, 3600000, 60000);
  const total = buckets.reduce((acc, b) => acc + b.success + b.failure + b.running, 0);
  assert.equal(total, 0);
});