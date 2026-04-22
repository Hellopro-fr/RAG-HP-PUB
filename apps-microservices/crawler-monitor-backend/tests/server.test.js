// tests/server.test.js
import { describe, it } from 'node:test';
import assert from 'node:assert';
import { setupTestEnv } from './helpers/env.js';

setupTestEnv();
const { app } = await import('../server.js');
const { default: request } = await import('supertest');

describe('crawler-monitor-backend smoke', () => {
  it('GET /health returns 200 and {status:"ok"}', async () => {
    const res = await request(app).get('/health');
    assert.strictEqual(res.status, 200);
    assert.deepStrictEqual(res.body, { status: 'ok' });
  });
});
