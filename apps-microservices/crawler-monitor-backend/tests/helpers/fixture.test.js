// tests/helpers/fixture.test.js
// Verifies the fixture helper emits a queue file shape compatible with how
// Crawlee v3 writes request-queue entries on disk (top-level `orderNo`,
// nested `json` string, etc.).
import { describe, it, before, after } from 'node:test';
import assert from 'node:assert';
import { readFile, readdir } from 'fs/promises';
import { join } from 'path';
import { setupTestEnv } from './env.js';
import { setupFixture, teardownFixture, FIXTURE_ROOT } from './fixture.js';

setupTestEnv();

const JOB = 'fixture-helper-test';

describe('setupFixture — queue files', () => {
  before(async () => {
    await setupFixture(JOB, {
      queueFiles: [
        { url: 'https://example.com/pending', method: 'GET', retryCount: 0 },
        { url: 'https://example.com/handled', method: 'GET', retryCount: 1, handledAt: '2026-04-17T10:00:00Z' },
      ],
    });
  });
  after(async () => { await teardownFixture(JOB); });

  it('emits top-level orderNo=null for handled entries, positive int for pending', async () => {
    const dir = join(FIXTURE_ROOT, JOB, 'storage', 'request_queues', 'example.com');
    const files = (await readdir(dir)).sort();
    assert.strictEqual(files.length, 2);

    const pending = JSON.parse(await readFile(join(dir, files[0]), 'utf-8'));
    const handled = JSON.parse(await readFile(join(dir, files[1]), 'utf-8'));

    assert.strictEqual(typeof pending.orderNo, 'number', 'pending must have numeric orderNo');
    assert.ok(pending.orderNo > 0, 'pending orderNo must be positive');
    assert.strictEqual(handled.orderNo, null, 'handled must have orderNo=null');
  });

  it('nests request body (including handledAt) inside a `json` string field', async () => {
    const dir = join(FIXTURE_ROOT, JOB, 'storage', 'request_queues', 'example.com');
    const files = (await readdir(dir)).sort();
    const handled = JSON.parse(await readFile(join(dir, files[1]), 'utf-8'));

    assert.strictEqual(typeof handled.json, 'string', '`json` field must be a string');
    const inner = JSON.parse(handled.json);
    assert.strictEqual(inner.handledAt, '2026-04-17T10:00:00Z');
    assert.strictEqual(inner.url, 'https://example.com/handled');
  });
});
