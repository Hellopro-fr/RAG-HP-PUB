import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildCallbackUrl, replayCallback } from '../src/lib/callbacks.js';

test('buildCallbackUrl appends params to a clean base URL', () => {
  const out = buildCallbackUrl('https://api.example.com/hook', { id: 42, foo: 'bar' });
  const u = new URL(out);
  assert.equal(u.searchParams.get('id'), '42');
  assert.equal(u.searchParams.get('foo'), 'bar');
});

test('buildCallbackUrl preserves pre-existing query string', () => {
  const out = buildCallbackUrl('https://api.example.com/hook?token=abc', { id: 1 });
  const u = new URL(out);
  assert.equal(u.searchParams.get('token'), 'abc');
  assert.equal(u.searchParams.get('id'), '1');
});

test('buildCallbackUrl skips null and undefined values', () => {
  const out = buildCallbackUrl('https://api.example.com/hook', { a: null, b: undefined, c: 'ok' });
  const u = new URL(out);
  assert.equal(u.searchParams.has('a'), false);
  assert.equal(u.searchParams.has('b'), false);
  assert.equal(u.searchParams.get('c'), 'ok');
});

test('buildCallbackUrl tolerates missing params', () => {
  const out = buildCallbackUrl('https://api.example.com/hook');
  assert.equal(out, 'https://api.example.com/hook');
});

test('replayCallback returns ok on 2xx', async () => {
  const fakeFetch = async () => ({ ok: true, status: 200 });
  const r = await replayCallback({ url: 'https://x.test/y', params: {} }, { fetchImpl: fakeFetch });
  assert.equal(r.ok, true);
  assert.equal(r.status, 200);
  assert.equal(r.error, null);
});

test('replayCallback returns error on 5xx', async () => {
  const fakeFetch = async () => ({ ok: false, status: 502 });
  const r = await replayCallback({ url: 'https://x.test/y', params: {} }, { fetchImpl: fakeFetch });
  assert.equal(r.ok, false);
  assert.equal(r.status, 502);
  assert.equal(r.error, 'HTTP 502');
});

test('replayCallback returns timeout when aborted', async () => {
  const fakeFetch = (_url, opts) => new Promise((_, rej) => {
    opts.signal.addEventListener('abort', () => {
      const e = new Error('abort');
      e.name = 'AbortError';
      rej(e);
    });
  });
  const r = await replayCallback({ url: 'https://x.test/y' }, { fetchImpl: fakeFetch, timeoutMs: 10 });
  assert.equal(r.ok, false);
  assert.equal(r.error, 'timeout');
});

test('replayCallback rejects invalid entry', async () => {
  const r = await replayCallback(null);
  assert.equal(r.ok, false);
  assert.equal(r.error, 'invalid_entry');
  const r2 = await replayCallback({ params: {} });
  assert.equal(r2.ok, false);
  assert.equal(r2.error, 'invalid_entry');
});