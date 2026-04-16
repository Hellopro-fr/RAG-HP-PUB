// tests/dataset-urls.test.js
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert';
import { setupTestEnv, getAuthHeader } from './helpers/env.js';
import { setupFixture, teardownFixture } from './helpers/fixture.js';

setupTestEnv();
const { app } = await import('../server.js');
const { default: request } = await import('supertest');

const JOB_ID = 'urls-test-job';
let auth;

describe('GET /api/jobs/:id/dataset/urls', () => {
  before(async () => {
    auth = await getAuthHeader();
    const successUrls = Array.from({ length: 25 }, (_, i) => `https://example.com/success/${i}`);
    const errorUrls = [
      { url: 'https://example.com/err/1', error: 'HTTP 500 Server Error' },
      { url: 'https://example.com/err/2', statusCode: 404, statusText: 'Not Found' },
      { url: 'https://example.com/err/3' }, // no error info → "Unknown error"
    ];
    const nfrUrls = ['https://example.com/en/1', 'https://example.com/en/2'];
    await setupFixture(JOB_ID, { successUrls, errorUrls, nfrUrls });
  });

  after(async () => { await teardownFixture(JOB_ID); });

  it('paginates correctly (page 2, limit 10 → items 11–20)', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/dataset/urls?category=success&page=2&limit=10`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.body.category, 'success');
    assert.strictEqual(res.body.total, 25);
    assert.strictEqual(res.body.page, 2);
    assert.strictEqual(res.body.totalPages, 3);
    assert.strictEqual(res.body.items.length, 10);
    assert.ok(res.body.items.every(it => typeof it.url === 'string'));
    assert.strictEqual(new Set(res.body.items.map(it => it.url)).size, 10);
  });

  it('search is case-insensitive substring over url', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/dataset/urls?category=success&search=SUCCESS/1`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    // success/1 matches success/1, success/10..19 → 11 items
    assert.strictEqual(res.body.total, 11);
    assert.ok(res.body.items.every(it => it.url.toLowerCase().includes('success/1')));
  });

  it('returns {url, error} shape for error category', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/dataset/urls?category=error&limit=50`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.body.total, 3);
    const byUrl = Object.fromEntries(res.body.items.map(it => [it.url, it.error]));
    assert.strictEqual(byUrl['https://example.com/err/1'], 'HTTP 500 Server Error');
    assert.strictEqual(byUrl['https://example.com/err/2'], 'HTTP 404 Not Found');
    assert.strictEqual(byUrl['https://example.com/err/3'], 'Unknown error');
  });

  it('returns 400 on invalid category', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/dataset/urls?category=foo`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 400);
    assert.match(res.body.error, /Invalid category/);
  });

  it('skips malformed JSON files', async () => {
    const j = 'urls-malformed-job';
    await setupFixture(j, {
      successUrls: ['https://example.com/ok'],
      rawFiles: [
        { dir: 'storage/datasets/example.com', name: 'broken.json', body: '{not valid json' },
      ],
    });
    const res = await request(app)
      .get(`/api/jobs/${j}/dataset/urls?category=success`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.body.total, 1);
    assert.strictEqual(res.body.items[0].url, 'https://example.com/ok');
    await teardownFixture(j);
  });

  it('caps limit at 200 and coerces page < 1 to 1', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/dataset/urls?category=success&page=0&limit=9999`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    assert.strictEqual(res.body.page, 1);
    assert.strictEqual(res.body.items.length, 25);
  });
});
