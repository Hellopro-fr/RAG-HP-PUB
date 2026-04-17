// tests/request-queues-status.test.js
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert';
import { setupTestEnv, getAuthHeader } from './helpers/env.js';
import { setupFixture, teardownFixture } from './helpers/fixture.js';

setupTestEnv();
const { app } = await import('../server.js');
const { default: request } = await import('supertest');

const JOB_ID = 'rq-status-job';
let auth;

describe('GET /api/jobs/:id/request-queues (status filter + counts)', () => {
  before(async () => {
    auth = await getAuthHeader();
    await setupFixture(JOB_ID, {
      queueFiles: [
        { url: 'https://example.com/p1', method: 'GET', retryCount: 0 }, // pending
        { url: 'https://example.com/p2', method: 'GET', retryCount: 0 }, // pending
        { url: 'https://example.com/p3', method: 'GET', retryCount: 0 }, // pending
        { url: 'https://example.com/h1', method: 'GET', retryCount: 0, handledAt: '2026-04-12T10:00:00Z' },
        { url: 'https://example.com/h2', method: 'GET', retryCount: 0, handledAt: '2026-04-12T10:05:00Z' },
      ],
    });
  });

  after(async () => { await teardownFixture(JOB_ID); });

  it('status=pending excludes handled files', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/request-queues?status=pending&limit=100`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.body.total, 3);
    assert.ok(res.body.items.every(it => it.url.includes('/p')));
  });

  it('status=handled excludes pending files', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/request-queues?status=handled&limit=100`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.body.total, 2);
    assert.ok(res.body.items.every(it => it.url.includes('/h')));
  });

  it('status=all (default) returns every file', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/request-queues?limit=100`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.body.total, 5);
  });

  it('counts is always unfiltered (regardless of status)', async () => {
    const expected = { total: 5, pending: 3, handled: 2 };
    for (const status of ['all', 'pending', 'handled']) {
      const res = await request(app)
        .get(`/api/jobs/${JOB_ID}/request-queues?status=${status}`)
        .set('Authorization', auth);
      assert.strictEqual(res.status, 200);
      assert.deepStrictEqual(res.body.counts, expected, `counts wrong for status=${status}`);
    }
  });
});
