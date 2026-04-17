// tests/dataset-counts.test.js
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert';
import { setupTestEnv, getAuthHeader } from './helpers/env.js';
import { setupFixture, teardownFixture } from './helpers/fixture.js';

setupTestEnv();
const { app } = await import('../server.js');
const { default: request } = await import('supertest');

const JOB_ID = 'counts-test-job';
let auth;

describe('GET /api/jobs/:id/dataset/counts', () => {
  before(async () => {
    auth = await getAuthHeader();
    await setupFixture(JOB_ID, {
      successUrls: ['https://example.com/a', 'https://example.com/b'],
      errorUrls: [{ url: 'https://example.com/x', error: 'HTTP 500' }],
      nfrUrls: ['https://example.com/fr/1', 'https://example.com/fr/2', 'https://example.com/fr/3'],
    });
  });

  after(async () => { await teardownFixture(JOB_ID); });

  it('returns accurate counts from filesystem', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/dataset/counts`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.deepStrictEqual(res.body, { success: 2, error: 1, nfr: 3 });
  });

  it('returns 0 for a category with no directory', async () => {
    const soloJob = 'counts-solo-job';
    await setupFixture(soloJob, { successUrls: ['https://example.com/a'] });
    const res = await request(app)
      .get(`/api/jobs/${soloJob}/dataset/counts`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.deepStrictEqual(res.body, { success: 1, error: 0, nfr: 0 });
    await teardownFixture(soloJob);
  });

  it('returns all zeros when the job has no datasets at all', async () => {
    const emptyJob = 'counts-empty-job';
    const res = await request(app)
      .get(`/api/jobs/${emptyJob}/dataset/counts`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.deepStrictEqual(res.body, { success: 0, error: 0, nfr: 0 });
  });
});
