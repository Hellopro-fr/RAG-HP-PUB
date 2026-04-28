import { test } from 'node:test';
import assert from 'node:assert/strict';
import express from 'express';
import jwt from 'jsonwebtoken';
import request from 'supertest';
import { mountAlbumsRouter } from '../src/lib/albums.js';

const JWT_SECRET = 'test-secret';

// Helper: forge a JWT for an admin user.
function adminToken() {
  return jwt.sign({ role: 'admin' }, JWT_SECRET, { expiresIn: '1h' });
}

// Helper: a minimal authenticateToken middleware mirroring the one in server.js.
function authenticateToken(req, res, next) {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];
  if (!token) return res.sendStatus(401);
  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) return res.sendStatus(403);
    req.user = user;
    next();
  });
}

// Stub auditMiddleware so we can record every (action, options) call.
function makeAuditStub() {
  const calls = [];
  const mw = (action, options) => {
    calls.push({ action, options });
    return (req, _res, next) => next();
  };
  return { mw, calls };
}

// fakeFetch builder: lets each test assert on the URL/method/body forwarded
// to the Python service and craft a controlled response.
function makeFakeFetch(impl) {
  const calls = [];
  const fn = async (url, opts) => {
    calls.push({ url, opts });
    return impl(url, opts, calls.length);
  };
  return { fn, calls };
}

// Convenience to wire up a fresh Express app for each test.
function buildApp({ auditMiddleware, fetchFn, baseUrl = 'http://image-download:8505', destructiveLimit }) {
  const app = express();
  app.set('trust proxy', 1);
  app.use(express.json());
  app.use(
    '/api/albums',
    authenticateToken,
    mountAlbumsRouter({ auditMiddleware, fetchFn, baseUrl, destructiveLimit }),
  );
  return app;
}

test('GET / requires JWT (401 without)', async () => {
  const { mw } = makeAuditStub();
  const { fn } = makeFakeFetch(() => ({ status: 200, headers: new Map([['content-type', 'application/json']]), json: async () => ([]) }));
  const app = buildApp({ auditMiddleware: mw, fetchFn: fn });
  const res = await request(app).get('/api/albums/');
  assert.equal(res.status, 401);
});

test('GET / forwards to /domains/_summary and returns JSON', async () => {
  const { mw } = makeAuditStub();
  const { fn, calls } = makeFakeFetch(() => ({
    status: 200,
    headers: new Map([['content-type', 'application/json']]),
    json: async () => ([{ domain: 'example.com', images: 42 }]),
  }));
  const app = buildApp({ auditMiddleware: mw, fetchFn: fn });
  const res = await request(app)
    .get('/api/albums/')
    .set('Authorization', `Bearer ${adminToken()}`);
  assert.equal(res.status, 200);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/domains\/_summary$/);
  assert.equal(calls[0].opts.method, 'GET');
  assert.deepEqual(res.body, [{ domain: 'example.com', images: 42 }]);
});

test('GET /:domain/products forwards query string to upstream', async () => {
  const { mw } = makeAuditStub();
  const { fn, calls } = makeFakeFetch(() => ({
    status: 200,
    headers: new Map([['content-type', 'application/json']]),
    json: async () => ({ items: [], total: 0 }),
  }));
  const app = buildApp({ auditMiddleware: mw, fetchFn: fn });
  const res = await request(app)
    .get('/api/albums/example.com/products?page=2&limit=50&search=foo')
    .set('Authorization', `Bearer ${adminToken()}`);
  assert.equal(res.status, 200);
  assert.equal(calls.length, 1);
  // Path AND query must be forwarded.
  assert.match(calls[0].url, /\/domains\/example\.com\/products\?/);
  assert.match(calls[0].url, /page=2/);
  assert.match(calls[0].url, /limit=50/);
  assert.match(calls[0].url, /search=foo/);
});

test('DELETE /:domain/products/:id/images/:filename → 204 propagated', async () => {
  const { mw, calls: auditCalls } = makeAuditStub();
  const { fn, calls } = makeFakeFetch(() => ({
    status: 204,
    headers: new Map(),
  }));
  const app = buildApp({ auditMiddleware: mw, fetchFn: fn });
  const res = await request(app)
    .delete('/api/albums/example.com/products/abc123/images/img-001.jpg')
    .set('Authorization', `Bearer ${adminToken()}`);
  assert.equal(res.status, 204);
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/images\/example\.com\/abc123\/img-001\.jpg$/);
  assert.equal(calls[0].opts.method, 'DELETE');
  // auditMiddleware was registered with the right action name on this route.
  assert.ok(auditCalls.some((c) => c.action === 'delete_image'));
});

test('DELETE /:domain → 202 propagated with body { job_id }', async () => {
  const { mw, calls: auditCalls } = makeAuditStub();
  const { fn } = makeFakeFetch(() => ({
    status: 202,
    headers: new Map([['content-type', 'application/json']]),
    json: async () => ({ job_id: 'delete-album-uuid', status: 'queued' }),
  }));
  const app = buildApp({ auditMiddleware: mw, fetchFn: fn });
  const res = await request(app)
    .delete('/api/albums/example.com')
    .set('Authorization', `Bearer ${adminToken()}`);
  assert.equal(res.status, 202);
  assert.deepEqual(res.body, { job_id: 'delete-album-uuid', status: 'queued' });
  assert.ok(auditCalls.some((c) => c.action === 'delete_album'));
});

test('rate-limit: 11th DELETE within window → 429 (limit=10/min)', async () => {
  const { mw } = makeAuditStub();
  const { fn } = makeFakeFetch(() => ({ status: 204, headers: new Map() }));
  const app = buildApp({ auditMiddleware: mw, fetchFn: fn, destructiveLimit: 10 });
  const tok = adminToken();
  // 10 DELETEs should all succeed.
  for (let i = 0; i < 10; i++) {
    const r = await request(app)
      .delete(`/api/albums/example.com/products/p${i}`)
      .set('Authorization', `Bearer ${tok}`);
    assert.equal(r.status, 204, `request #${i + 1} expected 204, got ${r.status}`);
  }
  // 11th must hit the limiter.
  const over = await request(app)
    .delete('/api/albums/example.com/products/p11')
    .set('Authorization', `Bearer ${tok}`);
  assert.equal(over.status, 429);
});

test('rate-limit: GETs are NOT rate-limited even after many calls', async () => {
  const { mw } = makeAuditStub();
  const { fn } = makeFakeFetch(() => ({
    status: 200,
    headers: new Map([['content-type', 'application/json']]),
    json: async () => ([]),
  }));
  const app = buildApp({ auditMiddleware: mw, fetchFn: fn, destructiveLimit: 5 });
  const tok = adminToken();
  for (let i = 0; i < 20; i++) {
    const r = await request(app)
      .get('/api/albums/')
      .set('Authorization', `Bearer ${tok}`);
    assert.equal(r.status, 200, `GET #${i + 1} expected 200, got ${r.status}`);
  }
});

test('auditMiddleware is invoked for every destructive route', async () => {
  const { mw, calls } = makeAuditStub();
  const { fn } = makeFakeFetch(() => ({ status: 204, headers: new Map() }));
  buildApp({ auditMiddleware: mw, fetchFn: fn });
  // Destructive routes registered: sync, redownload x2, delete x3 = 6 audited routes.
  // Read routes (GET) must NOT be audited.
  const actions = calls.map((c) => c.action);
  assert.ok(actions.includes('sync_album'), `expected sync_album, got ${actions}`);
  assert.ok(actions.includes('redownload_product'), `expected redownload_product, got ${actions}`);
  assert.ok(actions.includes('redownload_image'), `expected redownload_image, got ${actions}`);
  assert.ok(actions.includes('delete_album'), `expected delete_album, got ${actions}`);
  assert.ok(actions.includes('delete_product'), `expected delete_product, got ${actions}`);
  assert.ok(actions.includes('delete_image'), `expected delete_image, got ${actions}`);
  // Make sure no audit was registered for GET-only actions.
  assert.ok(!actions.some((a) => a.startsWith('get_') || a === 'list_albums'));
});

test('POST /:domain/sync forwards body and returns upstream response', async () => {
  const { mw } = makeAuditStub();
  const { fn, calls } = makeFakeFetch(() => ({
    status: 202,
    headers: new Map([['content-type', 'application/json']]),
    json: async () => ({ job_id: 'sync-uuid' }),
  }));
  const app = buildApp({ auditMiddleware: mw, fetchFn: fn });
  const res = await request(app)
    .post('/api/albums/example.com/sync')
    .set('Authorization', `Bearer ${adminToken()}`)
    .send({ force: true });
  assert.equal(res.status, 202);
  assert.match(calls[0].url, /\/sync\/example\.com$/);
  assert.equal(calls[0].opts.method, 'POST');
  // Body forwarded as JSON
  assert.equal(calls[0].opts.headers['content-type'], 'application/json');
  assert.equal(JSON.parse(calls[0].opts.body).force, true);
});