import { test } from 'node:test';
import assert from 'node:assert/strict';
import { proxyToImageDownload } from '../src/lib/imageDownloadProxy.js';

const baseUrl = 'http://test-image-download:8505';

function makeRes() {
  const res = {
    statusCode: 200, headers: {}, body: null, ended: false,
    status(code) { this.statusCode = code; return this; },
    json(b) { this.body = b; this.ended = true; return this; },
    send(b) { this.body = b; this.ended = true; return this; },
    setHeader(k, v) { this.headers[k] = v; },
  };
  return res;
}

test('forwards 200 JSON response', async () => {
  const fakeFetch = async () => ({
    ok: true, status: 200, headers: new Map([['content-type', 'application/json']]),
    json: async () => ({ ok: true }),
  });
  const req = { method: 'GET', query: {}, body: null };
  const res = makeRes();
  await proxyToImageDownload(req, res, {
    method: 'GET', path: '/domains/_summary', baseUrl, fetchFn: fakeFetch,
  });
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body, { ok: true });
});

test('forwards 404 with error body', async () => {
  const fakeFetch = async () => ({
    ok: false, status: 404, headers: new Map([['content-type', 'application/json']]),
    json: async () => ({ detail: 'not found' }),
  });
  const res = makeRes();
  await proxyToImageDownload({ method: 'GET' }, res, {
    method: 'GET', path: '/domains/x/products', baseUrl, fetchFn: fakeFetch,
  });
  assert.equal(res.statusCode, 404);
  assert.deepEqual(res.body, { detail: 'not found' });
});

test('returns 503 on ECONNREFUSED', async () => {
  const fakeFetch = async () => { const e = new Error('connect ECONNREFUSED'); e.code = 'ECONNREFUSED'; throw e; };
  const res = makeRes();
  await proxyToImageDownload({ method: 'GET' }, res, {
    method: 'GET', path: '/x', baseUrl, fetchFn: fakeFetch,
  });
  assert.equal(res.statusCode, 503);
  assert.match(res.body.error, /unreachable/i);
});

test('returns 504 on AbortError (timeout)', async () => {
  const fakeFetch = async (url, opts) => {
    const e = new Error('aborted'); e.name = 'AbortError'; throw e;
  };
  const res = makeRes();
  await proxyToImageDownload({ method: 'POST', body: { x: 1 } }, res, {
    method: 'POST', path: '/x/redownload', baseUrl, fetchFn: fakeFetch, timeoutMs: 50,
  });
  assert.equal(res.statusCode, 504);
});

test('forwards query string', async () => {
  let captured;
  const fakeFetch = async (url) => {
    captured = url;
    return { ok: true, status: 200, headers: new Map([['content-type', 'application/json']]),
             json: async () => ({}) };
  };
  const res = makeRes();
  await proxyToImageDownload({ method: 'GET', query: { q: 'test', page: '2' } }, res, {
    method: 'GET', path: '/domains/x/products', baseUrl, fetchFn: fakeFetch,
  });
  assert.match(captured, /\?q=test&page=2$/);
});

test('forwards JSON body on POST', async () => {
  let capturedOpts;
  const fakeFetch = async (url, opts) => {
    capturedOpts = opts;
    return { ok: true, status: 200, headers: new Map([['content-type', 'application/json']]),
             json: async () => ({}) };
  };
  const res = makeRes();
  await proxyToImageDownload({ method: 'POST', body: { foo: 'bar' } }, res, {
    method: 'POST', path: '/sync/x', baseUrl, fetchFn: fakeFetch,
  });
  assert.equal(capturedOpts.body, JSON.stringify({ foo: 'bar' }));
  assert.equal(capturedOpts.headers['content-type'], 'application/json');
});

test('204 No Content does not parse body', async () => {
  const fakeFetch = async () => ({
    ok: true, status: 204, headers: new Map(),
    json: async () => { throw new Error('should not be called'); },
  });
  const res = makeRes();
  await proxyToImageDownload({ method: 'DELETE' }, res, {
    method: 'DELETE', path: '/products/x/1', baseUrl, fetchFn: fakeFetch,
  });
  assert.equal(res.statusCode, 204);
});