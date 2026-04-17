# Crawler Monitor — Dataset Browser & Queue Insights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 3-category URL browser (succès/erreurs/non-FR) inside the Dataset page, a handled-vs-pending filter with live counts in the Queue page, and a syntax-highlighted JSON editor for queue files.

**Architecture:**
- Backend: two new endpoints (`/dataset/counts`, `/dataset/urls`) and one extended endpoint (`/request-queues` gains `status` + `counts`), self-contained (no Redis required — domain derived from filesystem).
- Frontend: refactor `DatasetAnalyzer.jsx` into a tabbed container with `DuplicatesTab` (existing UI extracted) + `UrlListBrowser` (new, shared across 3 category tabs). Extend `RequestQueueEditor.jsx` with counts bar + status filter + syntax-highlighted JSON via `react-simple-code-editor` + `prismjs`.
- Tests: backend endpoints have `node:test` + `supertest` integration tests against filesystem fixtures; frontend changes covered by a manual QA checklist.

**Tech Stack:** Node 20 ESM · Express 4 · node:test · supertest · React 19 · Vite · React Router · Tailwind · Lucide · react-simple-code-editor · prismjs.

**Spec:** [docs/superpowers/specs/2026-04-12-crawler-monitor-dataset-and-queue-insights-design.md](../specs/2026-04-12-crawler-monitor-dataset-and-queue-insights-design.md)

**Branch:** implementing directly on `features/poc` (current branch). Each task gets its own commit; commits should be bilingual (EN + FR body) per project convention — ask the user for language preference per commit.

---

## Task 1: Backend test harness (supertest + fixtures + exportable app)

**Goal:** Make `server.js` importable for tests without starting the HTTP listener, install `supertest`, add a reusable fixture helper, and convert the stub test into a real smoke test. This unblocks Tasks 2–4.

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js` (export `app`, gate `server.listen` on `NODE_ENV !== 'test'`)
- Modify: `apps-microservices/crawler-monitor-backend/package.json` (add `devDependencies.supertest`)
- Create: `apps-microservices/crawler-monitor-backend/tests/helpers/fixture.js`
- Create: `apps-microservices/crawler-monitor-backend/tests/helpers/env.js`
- Modify: `apps-microservices/crawler-monitor-backend/tests/server.test.js` (replace stub)

**Acceptance Criteria:**
- [ ] `npm test` in the backend dir passes.
- [ ] Importing `server.js` with `NODE_ENV=test` does NOT attempt to connect to Redis or bind a port.
- [ ] The smoke test makes a real HTTP call via supertest and asserts a 200 on `/health`.
- [ ] `supertest` appears under `devDependencies` in `package.json`.

**Verify:** `cd apps-microservices/crawler-monitor-backend && npm install && npm test` → all tests pass, no "connecting to Redis" logs during tests.

**Steps:**

- [ ] **Step 1: Add `supertest` as a dev dependency**

```bash
cd apps-microservices/crawler-monitor-backend
npm install --save-dev supertest@^7.0.0
```

Verify `package.json` now contains:
```json
"devDependencies": {
  "supertest": "^7.0.0"
}
```

- [ ] **Step 2: Make `server.js` test-friendly**

At the very bottom of `server.js`, replace the current startup block:

```js
// OLD (remove)
ensureRedisConnected()
  .then(() => {
    console.log('Connected to Redis (persistent client).');
    server.listen(PORT, '0.0.0.0', () => {
      console.log(`Crawler Monitor Backend running on port ${PORT}`);
      setupRedisListener();
    });
  })
  .catch(err => {
    console.error('Failed to connect to Redis:', err);
    process.exit(1);
  });
```

with:

```js
// NEW
async function start() {
  await ensureRedisConnected();
  console.log('Connected to Redis (persistent client).');
  server.listen(PORT, '0.0.0.0', () => {
    console.log(`Crawler Monitor Backend running on port ${PORT}`);
    setupRedisListener();
  });
}

if (process.env.NODE_ENV !== 'test') {
  start().catch(err => {
    console.error('Failed to start server:', err);
    process.exit(1);
  });
}

export { app };
```

Also update the env-var validation block (currently near the top) to be silent in tests — the stricter gate is for production. Change:

```js
// OLD
if (missingVars.length > 0) {
  console.error(`FATAL ERROR: Missing required environment variables: ${missingVars.join(', ')}`);
  process.exit(1);
}
```

to:

```js
// NEW
if (missingVars.length > 0) {
  console.error(`FATAL ERROR: Missing required environment variables: ${missingVars.join(', ')}`);
  if (process.env.NODE_ENV !== 'test') process.exit(1);
}
```

- [ ] **Step 3: Create env helper `tests/helpers/env.js`**

```js
// tests/helpers/env.js
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));

/**
 * Must be called BEFORE importing server.js in a test file.
 * Sets the env vars server.js expects and points storage to the fixtures dir.
 */
export function setupTestEnv() {
  process.env.NODE_ENV = 'test';
  process.env.REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';
  process.env.ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'test-password';
  process.env.JWT_SECRET = process.env.JWT_SECRET || 'test-jwt-secret';
  process.env.CRAWLER_STORAGE_PATH = join(__dirname, '..', 'fixtures');
}

/**
 * A JWT that the server's authenticateToken middleware will accept.
 * Import jwt after setupTestEnv() so JWT_SECRET is set.
 */
export async function getAuthHeader() {
  const { default: jwt } = await import('jsonwebtoken');
  const token = jwt.sign({ role: 'admin' }, process.env.JWT_SECRET, { expiresIn: '1h' });
  return `Bearer ${token}`;
}
```

- [ ] **Step 4: Create fixture helper `tests/helpers/fixture.js`**

```js
// tests/helpers/fixture.js
import { mkdir, writeFile, rm } from 'fs/promises';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
export const FIXTURE_ROOT = join(__dirname, '..', 'fixtures');

/**
 * Build a synthetic job on disk.
 *
 * @param {string} jobId
 * @param {object} [opts]
 * @param {string} [opts.domain='example.com']
 * @param {string[]} [opts.successUrls=[]]                          — URLs for the main dataset
 * @param {Array<{url, error?, statusCode?, statusText?}>} [opts.errorUrls=[]]
 * @param {string[]} [opts.nfrUrls=[]]                              — URLs for the nfr-{domain} dataset
 * @param {Array<{url, method?, retryCount?, errorMessages?, handledAt?}>} [opts.queueFiles=[]]
 * @param {Array<{dir, name, body}>} [opts.rawFiles=[]]             — arbitrary files (for malformed-JSON tests)
 */
export async function setupFixture(jobId, opts = {}) {
  const {
    domain = 'example.com',
    successUrls = [],
    errorUrls = [],
    nfrUrls = [],
    queueFiles = [],
    rawFiles = [],
  } = opts;

  const jobRoot = join(FIXTURE_ROOT, jobId);
  await rm(jobRoot, { recursive: true, force: true });

  // success
  if (successUrls.length) {
    const dir = join(jobRoot, 'storage', 'datasets', domain);
    await mkdir(dir, { recursive: true });
    for (let i = 0; i < successUrls.length; i++) {
      await writeFile(join(dir, `${i}.json`), JSON.stringify({ url: successUrls[i] }));
    }
  }

  // error
  if (errorUrls.length) {
    const dir = join(jobRoot, 'storage', 'datasets', `error-${domain}`);
    await mkdir(dir, { recursive: true });
    for (let i = 0; i < errorUrls.length; i++) {
      const entry = errorUrls[i];
      const payload = { url: entry.url };
      if (entry.error) payload.errorMessages = [entry.error];
      if (entry.statusCode !== undefined) payload.statusCode = entry.statusCode;
      if (entry.statusText) payload.statusText = entry.statusText;
      await writeFile(join(dir, `${i}.json`), JSON.stringify(payload));
    }
  }

  // nfr
  if (nfrUrls.length) {
    const dir = join(jobRoot, 'storage', 'datasets', `nfr-${domain}`);
    await mkdir(dir, { recursive: true });
    for (let i = 0; i < nfrUrls.length; i++) {
      await writeFile(join(dir, `${i}.json`), JSON.stringify({ url: nfrUrls[i] }));
    }
  }

  // queue files
  if (queueFiles.length) {
    const dir = join(jobRoot, 'storage', 'request_queues', domain);
    await mkdir(dir, { recursive: true });
    for (let i = 0; i < queueFiles.length; i++) {
      await writeFile(join(dir, `${i}.json`), JSON.stringify(queueFiles[i]));
    }
  }

  // raw files (opts out of JSON wrapping — for malformed-JSON tests)
  for (const r of rawFiles) {
    const dir = join(jobRoot, r.dir);
    await mkdir(dir, { recursive: true });
    await writeFile(join(dir, r.name), r.body);
  }

  return jobRoot;
}

export async function teardownFixture(jobId) {
  await rm(join(FIXTURE_ROOT, jobId), { recursive: true, force: true });
}
```

- [ ] **Step 5: Replace the stub test with a real smoke test**

Overwrite `tests/server.test.js`:

```js
// tests/server.test.js
import { describe, it, before, after } from 'node:test';
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
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
cd apps-microservices/crawler-monitor-backend
npm test
```

Expected output (excerpt):
```
✔ crawler-monitor-backend smoke > GET /health returns 200 and {status:"ok"}
# tests 1
# pass 1
```

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/package.json \
        apps-microservices/crawler-monitor-backend/package-lock.json \
        apps-microservices/crawler-monitor-backend/server.js \
        apps-microservices/crawler-monitor-backend/tests/
git commit -m "test(crawler-monitor-backend): add supertest harness + fixture helpers"
```

---

## Task 2: Backend — `GET /api/jobs/:id/dataset/counts`

**Goal:** Return the total URL count per dataset category (`success`, `error`, `nfr`) for a given job. No Redis dependency — category directories are discovered from the filesystem.

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js` (add helper `listDatasetDirs` + handler)
- Create: `apps-microservices/crawler-monitor-backend/tests/dataset-counts.test.js`

**Acceptance Criteria:**
- [ ] `GET /api/jobs/:id/dataset/counts` returns `{ success, error, nfr }` with accurate counts from disk.
- [ ] Missing categories return 0 (not an error).
- [ ] Handler skips malformed JSON files (they don't count).
- [ ] Protected by JWT (requires `Authorization: Bearer`).

**Verify:** `cd apps-microservices/crawler-monitor-backend && npm test -- tests/dataset-counts.test.js` → 3 tests pass.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/dataset-counts.test.js`:

```js
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps-microservices/crawler-monitor-backend
npm test -- tests/dataset-counts.test.js
```

Expected: 3 failures (404 Not Found — endpoint does not exist yet).

- [ ] **Step 3: Implement the endpoint**

In `server.js`, just above the existing `app.get('/api/jobs/:id/dataset/analyze', ...)` block (around line 889), add the helper and the new route:

```js
/**
 * Discover the three dataset subdirectories (main/error/nfr) for a job.
 * Returns { mainDir, errorDir, nfrDir, domain } — any dir may be null if absent.
 * Does NOT require Redis — the domain is recovered from the directory names.
 */
async function listDatasetDirs(jobId) {
  const datasetsRoot = join(CRAWLER_STORAGE_PATH, jobId, 'storage', 'datasets');
  if (!existsSync(datasetsRoot)) {
    return { mainDir: null, errorDir: null, nfrDir: null, domain: null };
  }
  const entries = await readdir(datasetsRoot, { withFileTypes: true });
  let mainName = null, errorName = null, nfrName = null;
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    if (e.name.startsWith('error-')) errorName = e.name;
    else if (e.name.startsWith('nfr-')) nfrName = e.name;
    else if (!mainName) mainName = e.name;
  }
  const domain = mainName || errorName?.slice('error-'.length) || nfrName?.slice('nfr-'.length) || null;
  return {
    mainDir:  mainName  ? join(datasetsRoot, mainName)  : null,
    errorDir: errorName ? join(datasetsRoot, errorName) : null,
    nfrDir:   nfrName   ? join(datasetsRoot, nfrName)   : null,
    domain,
  };
}

/** Count valid JSON files in a directory (malformed files excluded). */
async function countValidJsonFiles(dir) {
  if (!dir || !existsSync(dir)) return 0;
  const files = await readdir(dir);
  let count = 0;
  for (const f of files) {
    if (!f.endsWith('.json')) continue;
    try {
      const content = await readFile(join(dir, f), 'utf-8');
      JSON.parse(content);
      count++;
    } catch {
      // malformed — skip silently, matches existing scanDataset() behavior
    }
  }
  return count;
}

app.get('/api/jobs/:id/dataset/counts', async (req, res) => {
  const { id } = req.params;
  try {
    const { mainDir, errorDir, nfrDir } = await listDatasetDirs(id);
    const [success, error, nfr] = await Promise.all([
      countValidJsonFiles(mainDir),
      countValidJsonFiles(errorDir),
      countValidJsonFiles(nfrDir),
    ]);
    res.json({ success, error, nfr });
  } catch (err) {
    console.error(`Error counting datasets for job ${id}:`, err);
    res.status(500).json({ error: 'Failed to count datasets' });
  }
});
```

Note: this route is automatically protected by the existing `app.use('/api/jobs', authenticateToken)` at the top of `server.js` (~line 91). No inline middleware needed.

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- tests/dataset-counts.test.js
```

Expected:
```
✔ returns accurate counts from filesystem
✔ returns 0 for a category with no directory
✔ returns all zeros when the job has no datasets at all
# pass 3
```

- [ ] **Step 5: Run the full test suite**

```bash
npm test
```

Expected: all tests (smoke + counts) pass.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js \
        apps-microservices/crawler-monitor-backend/tests/dataset-counts.test.js
git commit -m "feat(crawler-monitor-backend): GET /api/jobs/:id/dataset/counts"
```

---

## Task 3: Backend — `GET /api/jobs/:id/dataset/urls`

**Goal:** Paginated, searchable list of URLs for one dataset category. Error rows include an `error` field derived from `errorMessages[0]` (or `statusCode`/`statusText` fallback).

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js` (new route handler)
- Create: `apps-microservices/crawler-monitor-backend/tests/dataset-urls.test.js`

**Acceptance Criteria:**
- [ ] Returns `{category, total, page, totalPages, items}` per spec §5.2.
- [ ] `items` shape is `{url}` for success/nfr and `{url, error}` for error category.
- [ ] Case-insensitive URL substring search; pagination correct under search.
- [ ] Unknown `category` returns 400.
- [ ] Malformed JSON files are skipped silently (not counted in `total`).
- [ ] `limit` capped at 200; `page < 1` coerced to 1.

**Verify:** `cd apps-microservices/crawler-monitor-backend && npm test -- tests/dataset-urls.test.js` → 6 tests pass.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/dataset-urls.test.js`:

```js
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
    // 25 success URLs + 3 error URLs (mix of errorMessages / statusCode fallback) + 2 nfr
    const successUrls = Array.from({ length: 25 }, (_, i) => `https://example.com/success/${i}`);
    const errorUrls = [
      { url: 'https://example.com/err/1', error: 'HTTP 500 Server Error' },
      { url: 'https://example.com/err/2', statusCode: 404, statusText: 'Not Found' },
      { url: 'https://example.com/err/3' }, // no error info → falls back to "Unknown error"
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
    // Items should be URLs, not necessarily in a specific order — just check we got 10 unique urls
    assert.ok(res.body.items.every(it => typeof it.url === 'string'));
    assert.strictEqual(new Set(res.body.items.map(it => it.url)).size, 10);
  });

  it('search is case-insensitive substring over url', async () => {
    const res = await request(app)
      .get(`/api/jobs/${JOB_ID}/dataset/urls?category=success&search=SUCCESS/1`)
      .set('Authorization', auth);
    assert.strictEqual(res.status, 200);
    // "success/1" matches success/1, success/10..19 → 11 items
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
    // 25 items total; with limit clamped to 200 (>25) all 25 returned on page 1
    assert.strictEqual(res.body.items.length, 25);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- tests/dataset-urls.test.js
```

Expected: 6 failures (404 — endpoint missing).

- [ ] **Step 3: Implement the endpoint**

In `server.js`, immediately after the `/dataset/counts` route, add:

```js
/** Derive a human-readable error string from an error-dataset entry. */
function deriveErrorMessage(entry) {
  if (Array.isArray(entry.errorMessages) && entry.errorMessages.length > 0) {
    return String(entry.errorMessages[0]);
  }
  if (entry.statusCode !== undefined) {
    const text = entry.statusText ? ` ${entry.statusText}` : '';
    return `HTTP ${entry.statusCode}${text}`;
  }
  return 'Unknown error';
}

app.get('/api/jobs/:id/dataset/urls', async (req, res) => {
  const { id } = req.params;
  const category = String(req.query.category || '');
  if (!['success', 'error', 'nfr'].includes(category)) {
    return res.status(400).json({ error: 'Invalid category. Must be one of: success, error, nfr' });
  }
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const limit = Math.min(200, Math.max(1, parseInt(req.query.limit) || 50));
  const search = String(req.query.search || '').toLowerCase();

  try {
    const dirs = await listDatasetDirs(id);
    const dir = category === 'success' ? dirs.mainDir
              : category === 'error'   ? dirs.errorDir
              :                          dirs.nfrDir;

    if (!dir || !existsSync(dir)) {
      return res.json({ category, total: 0, page, totalPages: 0, items: [] });
    }

    const filenames = (await readdir(dir)).filter(n => n.endsWith('.json'));

    // Single pass: read every file, skip malformed, apply optional search, then paginate.
    // This gives an accurate `total` (malformed files excluded) regardless of search.
    // Datasets are bounded; if this becomes a hotspot, add /dataset/counts as the
    // source of truth for badges and relax this handler to lazy-parse the page slice.
    const valid = [];
    for (const name of filenames) {
      try {
        const raw = await readFile(join(dir, name), 'utf-8');
        const data = JSON.parse(raw);
        if (!data.url) continue;
        if (search && !data.url.toLowerCase().includes(search)) continue;
        valid.push(category === 'error'
          ? { url: data.url, error: deriveErrorMessage(data) }
          : { url: data.url });
      } catch {
        console.warn(`[dataset/urls] skipped malformed file ${join(dir, name)}`);
      }
    }
    const total = valid.length;
    const totalPages = Math.ceil(total / limit);
    const startIdx = (page - 1) * limit;
    const items = valid.slice(startIdx, startIdx + limit);
    res.json({ category, total, page, totalPages, items });
  } catch (err) {
    console.error(`Error listing dataset URLs for job ${id}:`, err);
    res.status(500).json({ error: 'Failed to list dataset URLs' });
  }
});
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- tests/dataset-urls.test.js
```

Expected: 6 passes.

- [ ] **Step 5: Run the full suite**

```bash
npm test
```

Expected: 10 tests total passing (smoke + counts + urls).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js \
        apps-microservices/crawler-monitor-backend/tests/dataset-urls.test.js
git commit -m "feat(crawler-monitor-backend): GET /api/jobs/:id/dataset/urls (paginated, searchable)"
```

---

## Task 4: Backend — extend `GET /api/jobs/:id/request-queues` with `status` + `counts`

**Goal:** Add `status` filter (`all` | `pending` | `handled`) and a new unfiltered `counts: {total, pending, handled}` field so the UI can keep a steady counts bar while toggling filters.

**Files:**
- Modify: `apps-microservices/crawler-monitor-backend/server.js` (around line 482)
- Create: `apps-microservices/crawler-monitor-backend/tests/request-queues-status.test.js`

**Acceptance Criteria:**
- [ ] `status=pending` returns only files without `handledAt`.
- [ ] `status=handled` returns only files with non-null, non-empty `handledAt`.
- [ ] `status=all` (default) returns all matching files — behavior identical to pre-change.
- [ ] Response always includes `counts: {total, pending, handled}` with unfiltered totals.
- [ ] `search` and `status` compose (both applied).
- [ ] Existing callers (no `status` param) see no behavior change aside from the added `counts` field.

**Verify:** `cd apps-microservices/crawler-monitor-backend && npm test -- tests/request-queues-status.test.js` → 4 tests pass.

**Steps:**

- [ ] **Step 1: Write the failing tests**

Create `tests/request-queues-status.test.js`:

```js
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm test -- tests/request-queues-status.test.js
```

Expected: 4 failures (no `status` filtering and no `counts` field in current response).

- [ ] **Step 3: Modify the existing `/request-queues` handler**

Replace the current handler (`server.js` around lines 482–589) with:

```js
app.get('/api/jobs/:id/request-queues', async (req, res) => {
  const { id } = req.params;
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const limit = Math.min(200, Math.max(1, parseInt(req.query.limit) || 50));
  const search = (req.query.search || '').toLowerCase();
  const status = ['all', 'pending', 'handled'].includes(req.query.status) ? req.query.status : 'all';

  try {
    const baseDir = await findRequestQueuesDir(id);
    if (!baseDir) {
      return res.json({
        items: [], total: 0, page, limit, totalPages: 0,
        counts: { total: 0, pending: 0, handled: 0 },
      });
    }

    // Single pass over every file: collect { name, domain, url, method, retryCount, errorMessages, isHandled }
    // from which we derive both the filtered page AND the unfiltered counts.
    const allFiles = [];
    const entries = await readdir(baseDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const domainDir = join(baseDir, entry.name);
      const domainFiles = await readdir(domainDir);
      for (const file of domainFiles) {
        if (!file.endsWith('.json')) continue;
        const filePath = join(domainDir, file);
        try {
          const content = await readFile(filePath, 'utf-8');
          const data = JSON.parse(content);
          allFiles.push({
            name: file,
            domain: entry.name,
            path: join(entry.name, file),
            url: data.url,
            method: data.method,
            retryCount: data.retryCount,
            errorMessages: data.errorMessages,
            isHandled: Boolean(data.handledAt),
            rawContent: content, // for search (matches legacy behavior)
          });
        } catch {
          // Unreadable / malformed — still counted in `total` but not surfaced
          allFiles.push({
            name: file,
            domain: entry.name,
            path: join(entry.name, file),
            url: 'Error reading file',
            method: 'UNKNOWN',
            isHandled: false,
            rawContent: '',
          });
        }
      }
    }

    // Unfiltered counts (always from the full set — drives the UI counts bar).
    const counts = {
      total: allFiles.length,
      pending: allFiles.filter(f => !f.isHandled).length,
      handled: allFiles.filter(f => f.isHandled).length,
    };

    // Apply search + status filters for the page set.
    let matching = allFiles;
    if (search) matching = matching.filter(f => f.rawContent.toLowerCase().includes(search));
    if (status === 'pending') matching = matching.filter(f => !f.isHandled);
    else if (status === 'handled') matching = matching.filter(f => f.isHandled);

    const total = matching.length;
    const totalPages = Math.ceil(total / limit);
    const startIdx = (page - 1) * limit;
    const pageItems = matching.slice(startIdx, startIdx + limit).map(f => ({
      name: f.name,
      domain: f.domain,
      path: f.path,
      url: f.url,
      method: f.method,
      retryCount: f.retryCount,
      errorMessages: f.errorMessages,
      isHandled: f.isHandled,  // NEW — used by the row status glyph
    }));

    res.json({ items: pageItems, total, page, limit, totalPages, counts });
  } catch (error) {
    console.error(`Error listing request queues for job ${id}:`, error);
    res.status(500).json({ error: 'Failed to list request queues' });
  }
});
```

**Note on performance:** the old handler lazily parsed only the page slice. The new one reads every file in one pass to compute `counts` accurately. For queues up to tens of thousands of files this is acceptable; if it becomes a hotspot, add a separate `/request-queues/counts` endpoint and revert the list handler to lazy parsing.

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm test -- tests/request-queues-status.test.js
```

Expected: 4 passes.

- [ ] **Step 5: Run the full suite**

```bash
npm test
```

Expected: 14 tests passing (smoke + 3 counts + 6 urls + 4 request-queues-status).

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/crawler-monitor-backend/server.js \
        apps-microservices/crawler-monitor-backend/tests/request-queues-status.test.js
git commit -m "feat(crawler-monitor-backend): add status filter + unfiltered counts to /request-queues"
```

---

## Task 5: Frontend — install `react-simple-code-editor` + `prismjs`

**Goal:** Add the two small libraries used by the new syntax-highlighted JSON editor.

**Files:**
- Modify: `apps-microservices/crawler-monitor-frontend/package.json`
- Modify: `apps-microservices/crawler-monitor-frontend/yarn.lock`

**Acceptance Criteria:**
- [ ] `react-simple-code-editor` and `prismjs` appear under `dependencies` in `package.json`.
- [ ] `yarn build` succeeds without warnings about these modules.

**Verify:** `cd apps-microservices/crawler-monitor-frontend && yarn build` → exits 0.

**Steps:**

- [ ] **Step 1: Install**

```bash
cd apps-microservices/crawler-monitor-frontend
yarn add react-simple-code-editor@^0.14.0 prismjs@^1.29.0
```

- [ ] **Step 2: Sanity-build**

```bash
yarn build
```

Expected: Vite build succeeds (`dist/` produced).

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/package.json \
        apps-microservices/crawler-monitor-frontend/yarn.lock
git commit -m "chore(crawler-monitor-frontend): add react-simple-code-editor + prismjs"
```

---

## Task 6: Frontend — extract `DuplicatesTab.jsx` (pure refactor)

**Goal:** Move the existing duplicate-analysis UI out of `DatasetAnalyzer.jsx` into its own file. No behavior change. This isolates the refactor from the feature work that comes next.

**Files:**
- Create: `apps-microservices/crawler-monitor-frontend/src/components/DuplicatesTab.jsx`
- Modify: `apps-microservices/crawler-monitor-frontend/src/components/DatasetAnalyzer.jsx`

**Acceptance Criteria:**
- [ ] `DatasetAnalyzer.jsx` imports and renders `<DuplicatesTab jobId={jobId} token={token} />`.
- [ ] Clicking through `/jobs/:id/dataset` still shows the same duplicate analysis (counts, example list, purge button, confirmation flow).
- [ ] No console errors.

**Verify:** `cd apps-microservices/crawler-monitor-frontend && yarn build && yarn lint` → both exit 0. Manually navigate to `/jobs/<id>/dataset` and confirm the old UI appears unchanged.

**Steps:**

- [ ] **Step 1: Create `DuplicatesTab.jsx`**

```jsx
// src/components/DuplicatesTab.jsx
import { useState, useEffect } from 'react';
import { RefreshCw, AlertTriangle, Trash2, CheckCircle } from 'lucide-react';
import { api } from '../lib/api';
import ConfirmDestructive from './ConfirmDestructive';

/**
 * Duplicates analysis tab inside the Dataset page.
 *
 * Behavior identical to the legacy body of DatasetAnalyzer before it became tabbed:
 *   - fetches /dataset/analyze on mount,
 *   - shows total / unique / duplicate counts,
 *   - lists up to 5 duplicate URL examples,
 *   - offers a "Purger les doublons" button gated by ConfirmDestructive.
 */
const DuplicatesTab = ({ jobId, token }) => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [purging, setPurging] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [showPurgeConfirm, setShowPurgeConfirm] = useState(false);

  const analyze = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/jobs/${jobId}/dataset/analyze`, token);
      setStats(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const performPurge = async () => {
    setPurging(true);
    setError(null);
    try {
      const data = await api.post(`/jobs/${jobId}/dataset/deduplicate`, token);
      setSuccess(`Opération réussie: ${data.removedCount} fichiers supprimés.`);
      analyze();
      setShowPurgeConfirm(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setPurging(false);
    }
  };

  useEffect(() => { analyze(); }, [jobId]);

  if (loading && !stats) {
    return (
      <div className="flex justify-center py-12">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }
  if (!stats) {
    return (
      <div className="bg-red-900/20 p-4 text-red-400 rounded">
        Erreur impossible de charger les stats. {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ConfirmDestructive
        open={showPurgeConfirm}
        title="Purge duplicates"
        description={
          <>
            Va supprimer <strong>{stats.duplicateCount || 0}</strong> fichier{(stats.duplicateCount || 0) > 1 ? 's' : ''} doublon
            pour le job <code className="text-orange-300">{jobId}</code>.
            <br /><br />
            Le dataset garde la copie la plus récente de chaque URL.
            Cette action est <strong>irréversible</strong>.
          </>
        }
        shortId={String(jobId).slice(0, 8)}
        onConfirm={performPurge}
        onCancel={() => setShowPurgeConfirm(false)}
        busy={purging}
      />

      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-700 p-4 rounded-lg text-center">
          <p className="text-gray-400 text-sm">Total Items</p>
          <p className="text-2xl font-bold text-white">{stats.totalItems}</p>
        </div>
        <div className="bg-gray-700 p-4 rounded-lg text-center">
          <p className="text-gray-400 text-sm">URLs Uniques</p>
          <p className="text-2xl font-bold text-green-400">{stats.uniqueUrls}</p>
        </div>
        <div className="bg-gray-700 p-4 rounded-lg text-center border border-red-500/30">
          <p className="text-gray-400 text-sm">Doublons</p>
          <p className="text-2xl font-bold text-red-400">{stats.duplicateCount}</p>
        </div>
      </div>

      {stats.duplicateCount > 0 ? (
        <div className="bg-red-900/20 border border-red-500/50 p-4 rounded-lg">
          <h4 className="font-bold text-red-400 mb-2 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> Doublons détectés
          </h4>
          <p className="text-sm text-gray-300 mb-4">
            Le dataset contient <strong>{stats.duplicateCount}</strong> entrées en double.
            Cela arrive souvent après une reprise de crawl ("resume") suite à un arrêt d'urgence.
          </p>
          <button
            onClick={() => setShowPurgeConfirm(true)}
            disabled={purging}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded font-medium flex items-center gap-2 transition-colors disabled:opacity-50"
          >
            {purging ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            Purger les doublons
          </button>
        </div>
      ) : (
        <div className="bg-green-900/20 border border-green-500/30 p-4 rounded-lg flex items-center gap-3">
          <CheckCircle className="w-6 h-6 text-green-400" />
          <span className="text-green-300 font-medium">Le dataset est propre. Aucun doublon détecté.</span>
        </div>
      )}

      {stats.duplicatesExample && stats.duplicatesExample.length > 0 && (
        <div className="bg-gray-900 p-4 rounded-lg font-mono text-xs text-gray-400">
          <p className="mb-2 uppercase text-gray-500">Exemples de doublons :</p>
          <ul className="list-disc pl-4 space-y-1">
            {stats.duplicatesExample.map((url, i) => <li key={i}>{url}</li>)}
          </ul>
        </div>
      )}

      {success && (
        <div className="bg-green-900/30 text-green-400 p-3 rounded flex items-center gap-2">
          <CheckCircle className="w-4 h-4" /> {success}
        </div>
      )}
    </div>
  );
};

export default DuplicatesTab;
```

- [ ] **Step 2: Temporarily wire `DuplicatesTab` inside `DatasetAnalyzer.jsx` (placeholder before Task 8)**

Replace the whole body of `src/components/DatasetAnalyzer.jsx` with:

```jsx
// src/components/DatasetAnalyzer.jsx
import { Server, XCircle } from 'lucide-react';
import DuplicatesTab from './DuplicatesTab';

/**
 * Dataset page shell.
 * After Task 8 this becomes a tabbed container (Succès/Erreurs/Non-FR/Doublons).
 * For now it renders only the extracted DuplicatesTab — behavior unchanged vs. the
 * legacy monolithic version.
 */
const DatasetAnalyzer = ({ jobId, onClose, token }) => (
  <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
    <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl overflow-hidden">
      <div className="flex justify-between items-center p-4 border-b border-gray-700 bg-gray-750">
        <h3 className="text-xl font-bold text-white flex items-center gap-2">
          <Server className="w-5 h-5 text-purple-400" /> Analyse Dataset
        </h3>
        <button onClick={onClose} className="text-gray-400 hover:text-white">
          <XCircle className="w-6 h-6" />
        </button>
      </div>
      <div className="p-6">
        <DuplicatesTab jobId={jobId} token={token} />
      </div>
    </div>
  </div>
);

export default DatasetAnalyzer;
```

- [ ] **Step 3: Build + lint**

```bash
yarn build
yarn lint
```

Expected: both exit 0.

- [ ] **Step 4: Manual smoke test**

Run `yarn dev` (or rebuild the docker image), navigate to `/jobs/<any-id>/dataset`, confirm the duplicate UI looks identical to before.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/DuplicatesTab.jsx \
        apps-microservices/crawler-monitor-frontend/src/components/DatasetAnalyzer.jsx
git commit -m "refactor(crawler-monitor-frontend): extract DuplicatesTab from DatasetAnalyzer"
```

---

## Task 7: Frontend — create `UrlListBrowser.jsx`

**Goal:** A new shared component used by the three URL-browsing tabs (Succès / Erreurs / Non-FR). Server-side pagination, debounced search, per-row layout that adapts for `error` category.

**Files:**
- Create: `apps-microservices/crawler-monitor-frontend/src/components/UrlListBrowser.jsx`

**Acceptance Criteria:**
- [ ] Fetches `/api/jobs/:id/dataset/urls?category&page&limit&search` via `api.get`.
- [ ] Debounces search input (300 ms) and resets page to 1 when search changes.
- [ ] Renders `{url}` rows for success/nfr and two-line `{url, error}` rows for error.
- [ ] Shows pagination controls (Prev / Page X / Y / Next) when `totalPages > 1`.
- [ ] Shows empty/error/loading states per spec §6.2.

**Verify:** `yarn build && yarn lint` both exit 0. Component is verified functionally in Task 8 when it's wired into the Dataset page.

**Steps:**

- [ ] **Step 1: Create the component**

```jsx
// src/components/UrlListBrowser.jsx
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, RefreshCw, ChevronLeft, ChevronRight, ExternalLink, AlertTriangle,
} from 'lucide-react';
import { api } from '../lib/api';

const LIMIT = 50;

/**
 * Paginated, searchable URL list for one dataset category.
 *
 * Props:
 *   jobId    — crawl job id (route param)
 *   category — 'success' | 'error' | 'nfr'
 *   token    — JWT
 */
const UrlListBrowser = ({ jobId, category, token }) => {
  const [items, setItems] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [debounced, setDebounced] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Debounce search input (300ms) — reset to page 1 on change.
  const searchTimer = useRef(null);
  useEffect(() => {
    clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      setDebounced(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(searchTimer.current);
  }, [search]);

  // Reset pagination + search when the category changes (tab switch).
  useEffect(() => {
    setSearch(''); setDebounced(''); setPage(1);
  }, [category]);

  const fetchPage = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/jobs/${jobId}/dataset/urls`, token, {
        query: { category, page: String(page), limit: String(LIMIT), search: debounced },
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
      setTotalPages(data.totalPages || 0);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchPage(); }, [jobId, category, page, debounced]);

  const counterLabel = useMemo(() => {
    if (loading) return 'Chargement…';
    if (total === 0) return '0 URL';
    return `${total.toLocaleString('fr-FR')} URL${total > 1 ? 's' : ''}`;
  }, [loading, total]);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="w-4 h-4 text-gray-500 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher une URL…"
            className="w-full bg-gray-900 border border-gray-700 rounded pl-9 pr-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
          />
        </div>
        <span className="text-xs text-gray-400">{counterLabel}</span>
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-500/50 text-red-300 p-3 rounded flex items-center justify-between gap-3">
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" /> Impossible de charger les URLs. {error}
          </span>
          <button
            onClick={fetchPage}
            className="text-xs px-2 py-1 bg-red-600 hover:bg-red-700 rounded text-white"
          >Réessayer</button>
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="flex justify-center py-12">
          <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
        </div>
      ) : !error && items.length === 0 ? (
        <div className="text-gray-500 text-sm py-8 text-center">
          Aucune URL dans cette catégorie.
        </div>
      ) : (
        <ul className="divide-y divide-gray-700 bg-gray-900 border border-gray-700 rounded">
          {items.map((it, i) => (
            <li key={`${it.url}-${i}`} className="p-3 hover:bg-gray-800/60 transition-colors">
              <a
                href={it.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300 text-sm break-all flex items-start gap-2"
              >
                <ExternalLink className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                <span>{it.url}</span>
              </a>
              {category === 'error' && it.error && (
                <p className="text-red-400 text-xs mt-1 pl-5">{it.error}</p>
              )}
            </li>
          ))}
        </ul>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between gap-3">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
            className="flex items-center gap-1 text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded disabled:opacity-40"
          ><ChevronLeft className="w-3.5 h-3.5" /> Préc.</button>
          <span className="text-xs text-gray-400">
            Page {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages || loading}
            className="flex items-center gap-1 text-xs px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded disabled:opacity-40"
          >Suiv. <ChevronRight className="w-3.5 h-3.5" /></button>
        </div>
      )}
    </div>
  );
};

export default UrlListBrowser;
```

- [ ] **Step 2: Build + lint**

```bash
yarn build
yarn lint
```

Expected: both exit 0. (Functional verification happens in Task 8.)

- [ ] **Step 3: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/UrlListBrowser.jsx
git commit -m "feat(crawler-monitor-frontend): add UrlListBrowser shared component"
```

---

## Task 8: Frontend — refactor `DatasetAnalyzer.jsx` into a tabbed container

**Goal:** Replace the temporary single-tab shell (from Task 6) with a real tabbed container holding 4 tabs: Succès / Erreurs / Non-FR / Doublons. Each URL tab renders `UrlListBrowser`; the last tab renders `DuplicatesTab`.

**Files:**
- Modify: `apps-microservices/crawler-monitor-frontend/src/components/DatasetAnalyzer.jsx`

**Acceptance Criteria:**
- [ ] Opens `GET /dataset/counts` on mount; tab labels include the count (e.g. `Erreurs (1 234)`).
- [ ] Tab switch unmounts the previous tab's state (each tab reopens fresh — acceptable per spec §6.1).
- [ ] Active tab is visually distinct (blue underline or bg).
- [ ] Modal close button (X) still navigates back.
- [ ] Counts loading state shows a subtle spinner next to the tabs (not a full-modal spinner).

**Verify:** `yarn build && yarn lint` both exit 0. Manual QA: navigate `/jobs/<id>/dataset`, click each tab, confirm URL lists appear; confirm counts appear in tab labels.

**Steps:**

- [ ] **Step 1: Rewrite `DatasetAnalyzer.jsx`**

```jsx
// src/components/DatasetAnalyzer.jsx
import { useEffect, useState } from 'react';
import { Server, XCircle, RefreshCw } from 'lucide-react';
import { api } from '../lib/api';
import UrlListBrowser from './UrlListBrowser';
import DuplicatesTab from './DuplicatesTab';

const TABS = [
  { id: 'success',    label: 'Succès',   kind: 'urls' },
  { id: 'error',      label: 'Erreurs',  kind: 'urls' },
  { id: 'nfr',        label: 'Non-FR',   kind: 'urls' },
  { id: 'duplicates', label: 'Doublons', kind: 'duplicates' },
];

const formatInt = (n) => (n ?? 0).toLocaleString('fr-FR');

const DatasetAnalyzer = ({ jobId, onClose, token }) => {
  const [activeTab, setActiveTab] = useState('success');
  const [counts, setCounts] = useState(null);
  const [countsLoading, setCountsLoading] = useState(false);
  const [countsError, setCountsError] = useState(null);

  const fetchCounts = async () => {
    setCountsLoading(true);
    setCountsError(null);
    try {
      const data = await api.get(`/jobs/${jobId}/dataset/counts`, token);
      setCounts(data);
    } catch (err) {
      setCountsError(err.message);
    } finally {
      setCountsLoading(false);
    }
  };

  useEffect(() => { fetchCounts(); }, [jobId]);

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex justify-between items-center p-4 border-b border-gray-700 bg-gray-750">
          <h3 className="text-xl font-bold text-white flex items-center gap-2">
            <Server className="w-5 h-5 text-purple-400" /> Analyse Dataset
            {countsLoading && <RefreshCw className="w-4 h-4 animate-spin text-gray-400" />}
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white" aria-label="Fermer">
            <XCircle className="w-6 h-6" />
          </button>
        </div>

        {/* Tabs */}
        <nav className="flex gap-1 px-4 pt-3 border-b border-gray-700 bg-gray-850">
          {TABS.map(t => {
            const isActive = activeTab === t.id;
            const countLabel =
              t.kind === 'urls' && counts ? ` (${formatInt(counts[t.id])})` : '';
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={
                  'px-4 py-2 text-sm rounded-t-md transition-colors ' +
                  (isActive
                    ? 'bg-gray-900 text-white border border-b-0 border-gray-700'
                    : 'text-gray-400 hover:text-white hover:bg-gray-700/50')
                }
                aria-selected={isActive}
                role="tab"
              >
                {t.label}{countLabel}
              </button>
            );
          })}
        </nav>

        {countsError && (
          <div className="mx-4 mt-3 bg-red-900/20 border border-red-500/50 text-red-300 p-3 rounded text-sm">
            Impossible de charger les comptes. {countsError}
            <button onClick={fetchCounts} className="ml-3 underline">Réessayer</button>
          </div>
        )}

        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === 'duplicates'
            ? <DuplicatesTab jobId={jobId} token={token} />
            : <UrlListBrowser jobId={jobId} category={activeTab} token={token} />}
        </div>
      </div>
    </div>
  );
};

export default DatasetAnalyzer;
```

Note: `bg-gray-850` is not a Tailwind default; replace with `bg-gray-800` (the existing pattern) if the class doesn't resolve. Use `bg-gray-800` for both header and tab strip.

- [ ] **Step 2: Build + lint**

```bash
yarn build
yarn lint
```

Expected: both exit 0.

- [ ] **Step 3: Manual QA**

Run the dev server (`yarn dev` + local backend with a known job on disk) OR deploy to the remote. Open `/jobs/<id>/dataset`:
- Tab labels show counts e.g. `Succès (5 000)`, `Erreurs (1 234)`, `Non-FR (300)`, `Doublons`.
- Clicking Succès shows paginated URL list; search works; links open in new tab.
- Clicking Erreurs shows URLs with error messages beneath.
- Clicking Non-FR shows URL list.
- Clicking Doublons shows the original duplicate analysis UI (unchanged).
- Close button (X) navigates back to `/jobs/:id`.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/DatasetAnalyzer.jsx
git commit -m "feat(crawler-monitor-frontend): tabbed Dataset page with Succès/Erreurs/Non-FR/Doublons"
```

---

## Task 9: Frontend — Queue page counts bar + status toggle + row glyphs

**Goal:** Extend `RequestQueueEditor.jsx` with the Total/Traités/En attente counts bar, a `[Tous] [Traités] [En attente]` segmented toggle, and a per-row status glyph (`○` pending / `✓` handled). Uses the extended backend from Task 4.

**Files:**
- Modify: `apps-microservices/crawler-monitor-frontend/src/components/RequestQueueEditor.jsx`

**Acceptance Criteria:**
- [ ] Counts bar displays `Total N · ✓ Traités M · ○ En attente K` and stays constant across filter changes.
- [ ] Segmented toggle filters the list client-visibly (driven by the backend `status` query).
- [ ] Changing the filter resets `page` to 1.
- [ ] Each row shows a status glyph reflecting `item.isHandled`.
- [ ] Counts refresh automatically after Clean Patterns / Drop Queue / Save.

**Verify:** `yarn build && yarn lint` → exit 0. Manual QA per the checklist below.

**Steps:**

- [ ] **Step 1: Add state + fetch-param support**

In `RequestQueueEditor.jsx`, add these state hooks near the other `useState` calls (around line 10):

```jsx
// NEW state
const [statusFilter, setStatusFilter] = useState('all'); // 'all' | 'pending' | 'handled'
const [counts, setCounts] = useState(null);              // { total, pending, handled }
```

Update the `useEffect` that triggers `fetchFiles` to include `statusFilter`:

```jsx
// OLD
useEffect(() => {
  fetchFiles();
}, [jobId, page, searchTerm]);

// NEW
useEffect(() => {
  fetchFiles();
}, [jobId, page, searchTerm, statusFilter]);
```

Update `fetchFiles` to send `status` and consume `counts`:

```jsx
const fetchFiles = async () => {
  setLoading(true);
  try {
    const data = await api.get(
      `/jobs/${jobId}/request-queues`,
      token,
      { query: {
          page: String(page),
          limit: String(limit),
          search: searchTerm,
          status: statusFilter,
        } }
    );
    if (data.items) {
      setFiles(data.items);
      setTotalPages(data.totalPages);
      setTotalItems(data.total);
      if (data.counts) setCounts(data.counts);
    } else {
      setFiles(Array.isArray(data) ? data : []);
      setTotalPages(1);
      setTotalItems(Array.isArray(data) ? data.length : 0);
    }
  } catch (err) {
    setError(err.message);
  } finally {
    setLoading(false);
  }
};
```

Add a helper to change the filter and reset page:

```jsx
const changeStatusFilter = (next) => {
  setStatusFilter(next);
  setPage(1);
};
```

- [ ] **Step 2: Add the counts bar + segmented toggle + row glyph to the JSX**

Find the left panel in the existing JSX (look for the search input) and insert the counts bar and toggle ABOVE the existing search input. Use the following snippets; place them right under the modal's left-panel container div:

```jsx
{/* Counts bar */}
{counts && (
  <div className="flex items-center gap-3 text-xs text-gray-300 bg-gray-900/60 border border-gray-700 rounded px-3 py-2 mb-2">
    <span className="text-gray-400">Total</span>
    <span className="text-white font-semibold">{counts.total.toLocaleString('fr-FR')}</span>
    <span className="text-gray-600">·</span>
    <span className="text-gray-400">✓ Traités</span>
    <span className="text-green-400 font-semibold">{counts.handled.toLocaleString('fr-FR')}</span>
    <span className="text-gray-600">·</span>
    <span className="text-gray-400">○ En attente</span>
    <span className="text-yellow-400 font-semibold">{counts.pending.toLocaleString('fr-FR')}</span>
  </div>
)}

{/* Status segmented toggle */}
<div className="flex gap-1 mb-2">
  {[
    { id: 'all',     label: 'Tous' },
    { id: 'handled', label: '✓ Traités' },
    { id: 'pending', label: '○ En attente' },
  ].map(opt => (
    <button
      key={opt.id}
      onClick={() => changeStatusFilter(opt.id)}
      className={
        'text-xs px-3 py-1.5 rounded transition-colors ' +
        (statusFilter === opt.id
          ? 'bg-blue-600 text-white'
          : 'bg-gray-700 text-gray-300 hover:bg-gray-600')
      }
    >
      {opt.label}
    </button>
  ))}
</div>
```

Find the row rendering inside the file list (the `files.map(f => ...)` section). Add a status glyph as the first element of each row. Example — before:

```jsx
<li key={...}>
  <span>{f.url}</span>
  <span>{f.method}</span>
  <span>retry:{f.retryCount}</span>
</li>
```

After:

```jsx
<li key={...}>
  <span
    className={f.isHandled ? 'text-green-400 mr-2' : 'text-gray-500 mr-2'}
    title={f.isHandled ? 'Traité' : 'En attente'}
  >
    {f.isHandled ? '✓' : '○'}
  </span>
  <span>{f.url}</span>
  <span>{f.method}</span>
  <span>retry:{f.retryCount}</span>
</li>
```

Use the exact existing markup surrounding each row — do not rewrite unrelated parts.

- [ ] **Step 3: Build + lint**

```bash
yarn build
yarn lint
```

Expected: both exit 0.

- [ ] **Step 4: Manual QA**

With a job that has both pending and handled queue files:
- Counts bar shows `Total N · ✓ Traités M · ○ En attente K`.
- Toggle `[Traités]` — list shrinks to handled rows; counts unchanged.
- Toggle `[En attente]` — list shrinks to pending rows; counts unchanged.
- Toggle `[Tous]` — full list returns.
- Row glyphs reflect `isHandled`.
- After running Clean Patterns or saving a file, the counts bar refreshes.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/RequestQueueEditor.jsx
git commit -m "feat(crawler-monitor-frontend): queue counts bar + handled/pending filter"
```

---

## Task 10: Frontend — syntax-highlighted JSON editor in `RequestQueueEditor`

**Goal:** Replace the plain `<textarea>` on the right panel with `react-simple-code-editor` + `prismjs`. Pretty-print queue file content on load. Preserve the existing Save + Format buttons.

**Files:**
- Modify: `apps-microservices/crawler-monitor-frontend/src/components/RequestQueueEditor.jsx`

**Acceptance Criteria:**
- [ ] Queue JSON opens pretty-printed with syntax highlighting.
- [ ] The content area remains editable (typing, paste, keyboard selection work).
- [ ] Format and Save buttons behave exactly as before.
- [ ] Dark-theme token colors match spec §6.4.
- [ ] Styles are scoped — Prism's default light theme does not leak across the app.

**Verify:** `yarn build && yarn lint` → exit 0. Manual QA below.

**Steps:**

- [ ] **Step 1: Add Prism imports + registration**

At the top of `RequestQueueEditor.jsx`, add (alongside the existing imports):

```jsx
import Editor from 'react-simple-code-editor';
import Prism from 'prismjs';
import 'prismjs/components/prism-json';
```

- [ ] **Step 2: Pretty-print on load**

Find `loadFile` (around line 57). Change the last line that sets content:

```jsx
// OLD
setContent(JSON.stringify(data, null, 2));
```

This is already pretty-printed — no change needed. But for robustness against saved-minified content, update to:

```jsx
// NEW — defensive pretty-print
try {
  setContent(JSON.stringify(data, null, 2));
} catch {
  setContent(typeof data === 'string' ? data : String(data));
}
```

(The `api.get` already JSON-parses the response body, so `data` is an object here. Defensive code only matters if the backend ever returns a string — which the GET file endpoint doesn't today, but the guard costs nothing.)

- [ ] **Step 3: Replace the textarea with `<Editor>`**

Find the textarea in the right-panel JSX (where `value={content}` / `onChange={e => setContent(e.target.value)}` appear). Replace it with:

```jsx
<div className="queue-json-editor bg-gray-900 border border-gray-700 rounded overflow-auto max-h-[70vh]">
  <Editor
    value={content}
    onValueChange={setContent}
    highlight={code => Prism.highlight(code, Prism.languages.json, 'json')}
    padding={12}
    textareaClassName="focus:outline-none"
    preClassName=""
    style={{
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
      fontSize: 13,
      minHeight: 400,
    }}
  />
</div>
```

- [ ] **Step 4: Add Prism token colors (scoped to `.queue-json-editor`)**

Append this block somewhere in the component return (e.g. just inside the modal root div, above the header) — or create `src/styles/prism-dark.css` and import it in `main.jsx`. The inline `<style>` variant keeps it colocated with the component:

```jsx
<style>{`
  .queue-json-editor .token.property    { color: #22d3ee; } /* cyan-400 */
  .queue-json-editor .token.string      { color: #4ade80; } /* green-400 */
  .queue-json-editor .token.number      { color: #fb923c; } /* orange-400 */
  .queue-json-editor .token.boolean,
  .queue-json-editor .token.null        { color: #c084fc; } /* purple-400 */
  .queue-json-editor .token.punctuation { color: #6b7280; } /* gray-500 */
  .queue-json-editor .token.operator    { color: #9ca3af; } /* gray-400 */
  .queue-json-editor textarea,
  .queue-json-editor pre {
    white-space: pre !important;
    overflow-wrap: normal !important;
    word-break: normal !important;
  }
`}</style>
```

- [ ] **Step 5: Build + lint**

```bash
yarn build
yarn lint
```

Expected: both exit 0.

- [ ] **Step 6: Manual QA**

- Open a queue file — content appears indented with colored tokens.
- Type in the editor — characters are accepted; highlighting updates live.
- Click `Format` — no regression (still works).
- Click `Save` — POST succeeds; after reload, content is still highlighted.
- Open another file that was saved as minified JSON in the past — it displays pretty-printed.
- Confirm no Prism styles leak to the rest of the app (check an unrelated page e.g. `/domains`).

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/crawler-monitor-frontend/src/components/RequestQueueEditor.jsx
git commit -m "feat(crawler-monitor-frontend): syntax-highlighted JSON editor for queue files"
```

---

## Task 11: End-to-end manual QA + final sanity commit

**Goal:** Walk through the full spec acceptance checklist against a live deployment, fix any regressions found, and commit any final tweaks.

**Files:** (potentially any of the above, if regressions surface)

**Acceptance Criteria:** spec §9 checklist passes end-to-end.

**Verify:**

Use a test job on the remote cluster (or the local docker-compose crawler-monitor stack) with non-trivial datasets and queues.

**Steps:**

- [ ] **Step 1: Deploy / restart**

```bash
# Rebuild both containers with the new code
docker-compose build crawler-monitor-backend crawler-monitor-frontend
docker-compose up -d crawler-monitor-backend crawler-monitor-frontend
```

- [ ] **Step 2: Manual QA — Dataset page**

- [ ] Open `/jobs/<id>/dataset` on a job with many success / error / nfr URLs.
- [ ] All 3 tabs show counts in their labels.
- [ ] Search `example` in Erreurs → list filters; pagination updates.
- [ ] Click a URL → opens in new tab.
- [ ] Switch between tabs → each shows its own list; no bleed-over.
- [ ] Doublons tab still shows the existing duplicate analysis and purge.

- [ ] **Step 3: Manual QA — Queue page**

- [ ] Open `/jobs/<id>/queue` on a job with both handled and pending queue files.
- [ ] Counts bar displays Total / Traités / En attente.
- [ ] Toggle `[Traités]` / `[En attente]` / `[Tous]` → list filters correctly; counts constant.
- [ ] Row glyphs (`○` / `✓`) reflect `isHandled`.
- [ ] Click a file → JSON opens pretty-printed + highlighted.
- [ ] Edit and Save → backend accepts; reloading shows the new content still highlighted.
- [ ] Click `Tout Supprimer` → queue drops to 0; counts update; filter toggle still functional.

- [ ] **Step 4: Regression check**

- [ ] Legacy Callbacks page still works (`/callbacks`).
- [ ] Overview page (`/`) still shows jobs / replicas / capacity.
- [ ] Login / logout still works.
- [ ] No console errors on any page.

- [ ] **Step 5: Fix any regressions**

If anything's broken, diagnose and fix as a small follow-up commit:

```bash
git add <file>
git commit -m "fix(crawler-monitor): <concise description>"
```

- [ ] **Step 6: Final tidy-up**

No action if nothing's wrong. If all green, nothing to commit.

---

## Summary

11 tasks, sequenced so the backend is fully tested before the frontend starts. The refactor (Task 6) is separated from the feature work (Task 8) so each can be reviewed in isolation. The JSON editor (Task 10) is last because it's the most independent piece — can be paused or cut without affecting the rest.

Backend tests: 14 total (1 smoke + 3 counts + 6 urls + 4 request-queues-status). Frontend changes are verified by the manual QA checklist in Task 11.
