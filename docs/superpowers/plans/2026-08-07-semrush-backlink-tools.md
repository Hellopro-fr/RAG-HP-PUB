# Semrush Backlink Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `mcp-semrush-service` from 2 backlink tools to 9 by generating them from a declarative table, with a cost guard and correct error reporting.

**Architecture:** A `BACKLINK_REPORTS` table describes each Semrush backlink report (tool name, API `type`, parameter shape, `export_columns`). A `makeBacklinkTool()` factory turns each entry into an MCP tool object matching the shape of the existing 14 hand-written tools. Three parameter shapes exist — `standard`, `summary`, `multi` — because Semrush's backlink reports are not uniform. URL construction is a pure function so it can be tested without network calls or mocking.

**Tech Stack:** Node.js 20, zero runtime dependencies, `node:test` + `node:assert` for tests, Semrush v3 Analytics API.

**Spec:** `docs/superpowers/specs/2026-08-07-semrush-backlink-tools-design.md`

## Global Constraints

- `server.js` must require **only Node builtins** (`node:https`, `node:http`, `node:readline`). No npm dependencies at runtime.
- Tests use **only** `node:test` and `node:assert`. No test framework dependency.
- **No test may make a live Semrush API call.** Every call costs 40 API units. Test URL construction as a pure function instead.
- `MAX_DISPLAY_LIMIT = 100` (100 rows × 40 units = 4,000 unit ceiling per call).
- Semrush backlinks endpoint: `https://api.semrush.com/analytics/v1/` (the existing `BACK` constant).
- The **14 non-backlink tools must be unchanged in behavior.** Every task that touches shared code (`buildQS`, the `tools/call` handler) needs a regression assertion.
- Do **not** modify the `Dockerfile`. It copies only `server.js`, so the test file correctly never ships to the image.
- Commit messages follow Conventional Commits and are **bilingual EN + FR** per `.claude/rules/commit-messages.md`.
- Match the existing file style: 2-space indent, single quotes, trailing commas in multi-line structures.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `apps-microservices/mcp-semrush-service/server.js` | Modify | All production changes. Stays a single file — the spec sizes this at ~90 added lines, which does not justify a split. |
| `apps-microservices/mcp-semrush-service/server.test.js` | Create | All unit tests. Node's runner discovers `*.test.js`. Not copied into the Docker image. |
| `apps-microservices/mcp-semrush-service/package.json` | Modify | Add a `test` script. |
| `apps-microservices/mcp-semrush-service/BACKLINKS.md` | Modify | Document the 7 new tools; move resolved items out of "Known gaps". |
| `apps-microservices/mcp-semrush-service/CLAUDE.md` | Modify | Tool count 16 → 23; list new backlink tools. |

**Why `server.js` is not split:** the spec's approved architecture keeps everything in one file. Splitting into `lib/` modules would require changing the Dockerfile `COPY` line and is beyond approved scope. Revisit if the file passes ~800 lines.

---

### Task 1: Make `server.js` importable and wire up `node:test`

`server.js` is currently a pure script with no exports. Line 451 creates a `readline`
interface on `process.stdin` at module top level. Requiring the file from a test would
create that interface, keep the Node event loop alive, and **hang the test process
forever**. This task fixes that before any behavior changes, and establishes a baseline
test proving the current 16 tools are intact.

**Files:**
- Modify: `apps-microservices/mcp-semrush-service/server.js:451-516` (guard startup), end of file (add exports)
- Modify: `apps-microservices/mcp-semrush-service/package.json`
- Test: `apps-microservices/mcp-semrush-service/server.test.js` (create)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `module.exports = { TOOLS, buildQS, BACK }` from `server.js`. Every later task adds to this export object.

- [ ] **Step 1: Add the test script to `package.json`**

Replace the whole file:

```json
{
  "name": "mcp-semrush-service",
  "private": true,
  "scripts": {
    "test": "node --test"
  }
}
```

- [ ] **Step 2: Write the failing test**

Create `apps-microservices/mcp-semrush-service/server.test.js`:

```js
'use strict';

const test = require('node:test');
const assert = require('node:assert');

const { TOOLS, buildQS, BACK } = require('./server.js');

test('server.js can be required without hanging', () => {
  assert.ok(Array.isArray(TOOLS));
});

// This is the single tool-count assertion for the whole plan. Tasks 5, 6, 7 and 8
// each UPDATE the expected number here rather than adding their own count test.
test('registered tool count', () => {
  assert.strictEqual(TOOLS.length, 16);
});

test('baseline: every tool has name, description, inputSchema, run', () => {
  for (const tool of TOOLS) {
    assert.ok(tool.name, 'tool has a name');
    assert.ok(tool.description, `${tool.name} has a description`);
    assert.ok(tool.inputSchema, `${tool.name} has an inputSchema`);
    assert.strictEqual(typeof tool.run, 'function', `${tool.name}.run is a function`);
  }
});

test('baseline: the two existing backlink tools are present', () => {
  const names = TOOLS.map((t) => t.name);
  assert.ok(names.includes('backlinks'));
  assert.ok(names.includes('backlinks_domains'));
});

test('BACK points at the Semrush analytics endpoint', () => {
  assert.strictEqual(BACK, 'https://api.semrush.com/analytics/v1/');
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: FAIL. Either the process **hangs** (readline holds the event loop open), or it
errors with `TypeError: Cannot destructure property 'TOOLS' of ... as it is undefined`
because nothing is exported. If it hangs, kill it with Ctrl-C — that hang is the exact
failure this task fixes.

- [ ] **Step 4: Guard the startup and add exports**

In `server.js`, replace lines 451-516 (from `const rl = readline.createInterface(...)`
through the closing `});` of the `rl.on('line', ...)` handler) with the same logic wrapped
in a `main()` function:

```js
function handleLine(line) {
  return (async () => {
    line = line.trim();
    if (!line) return;

    let req;
    try {
      req = JSON.parse(line);
    } catch {
      return;
    }

    const { id, method, params = {} } = req;

    // Notifications (no id) — per MCP spec, no response
    if (id === undefined || id === null) return;

    try {
      switch (method) {
        case 'initialize':
          sendResult(id, {
            protocolVersion: '2024-11-05',
            capabilities: { tools: {} },
            serverInfo: { name: 'semrush-mcp', version: '2.0.0' },
          });
          break;

        case 'tools/list':
          sendResult(id, {
            tools: TOOLS.map((t) => ({
              name: t.name,
              description: t.description,
              inputSchema: t.inputSchema,
            })),
          });
          break;

        case 'tools/call': {
          const { name, arguments: args = {} } = params;
          const tool = toolByName[name];
          if (!tool) {
            sendError(id, -32602, `Unknown tool: ${name}`);
            break;
          }
          try {
            const text = await tool.run(args);
            sendResult(id, {
              content: [{ type: 'text', text: String(text) }],
            });
          } catch (err) {
            sendResult(id, {
              content: [{ type: 'text', text: `Error: ${err.message}` }],
              isError: true,
            });
          }
          break;
        }

        default:
          sendError(id, -32601, `Method not found: ${method}`);
      }
    } catch (err) {
      sendError(id, -32603, `Internal error: ${err.message}`);
    }
  })();
}

function main() {
  const rl = readline.createInterface({ input: process.stdin, terminal: false });
  rl.on('line', handleLine);
}

if (require.main === module) {
  main();
}

module.exports = { TOOLS, toolByName, buildQS, BACK, handleLine };
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: PASS, and the process **exits on its own** rather than hanging.

- [ ] **Step 6: Verify the server still runs as a server**

Run:

```bash
cd apps-microservices/mcp-semrush-service && \
  echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | node server.js | head -c 200
```

Expected: a JSON line beginning `{"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"domain_overview"`.
This proves the `require.main` guard did not break stdio operation.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/mcp-semrush-service/server.js \
        apps-microservices/mcp-semrush-service/server.test.js \
        apps-microservices/mcp-semrush-service/package.json
git commit -m "test(mcp-semrush): make server.js importable and add baseline tests

Guard stdio startup behind require.main so the module can be required
without hanging on a stdin readline. Add node:test baseline covering the
existing 16 tools.

Protege le demarrage stdio derriere require.main pour que le module soit
importable sans bloquer sur readline. Ajoute les tests node:test de base
couvrant les 16 outils existants."
```

---

### Task 2: `buildQS` array support

`backlinks_matrix` requires repeated parameters (`targets=a&targets=b`). `buildQS` maps over
`Object.entries`, so a plain object cannot express two identical keys. Array values must
expand into repeated pairs.

**Files:**
- Modify: `apps-microservices/mcp-semrush-service/server.js:36-41`
- Test: `apps-microservices/mcp-semrush-service/server.test.js`

**Interfaces:**
- Consumes: `buildQS` exported by Task 1
- Produces: `buildQS(params)` where a value may now be an array; arrays expand to repeated `key=value` pairs. Scalar behavior unchanged.

- [ ] **Step 1: Write the failing test**

Append to `server.test.js`:

```js
test('buildQS expands array values into repeated params', () => {
  const qs = buildQS({ targets: ['a.com', 'b.com'] });
  assert.strictEqual(qs, 'targets=a.com&targets=b.com');
});

test('buildQS url-encodes each array element', () => {
  const qs = buildQS({ targets: ['a b.com', 'c&d.com'] });
  assert.strictEqual(qs, 'targets=a%20b.com&targets=c%26d.com');
});

test('buildQS drops empty arrays', () => {
  const qs = buildQS({ targets: [], key: 'k' });
  assert.strictEqual(qs, 'key=k');
});

test('REGRESSION: buildQS scalar behavior is unchanged', () => {
  const qs = buildQS({ key: 'abc', type: 'domain_ranks', domain: 'hellopro.fr' });
  assert.strictEqual(qs, 'key=abc&type=domain_ranks&domain=hellopro.fr');
});

test('REGRESSION: buildQS still drops undefined, null and empty string', () => {
  const qs = buildQS({ a: 'x', b: undefined, c: null, d: '', e: 'y' });
  assert.strictEqual(qs, 'a=x&e=y');
});

test('REGRESSION: buildQS keeps numeric zero', () => {
  const qs = buildQS({ display_offset: 0, a: 'x' });
  assert.strictEqual(qs, 'display_offset=0&a=x');
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: FAIL on the first three tests. `buildQS({targets:['a.com','b.com']})` currently
returns `targets=a.com%2Cb.com` because `String(['a.com','b.com'])` produces `'a.com,b.com'`.
The three REGRESSION tests must already PASS — they pin current behavior.

- [ ] **Step 3: Implement array support**

Replace the `buildQS` function at `server.js:36-41`:

```js
function buildQS(params) {
  return Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .flatMap(([k, v]) => {
      const key = encodeURIComponent(k);
      return Array.isArray(v)
        ? v.map((item) => `${key}=${encodeURIComponent(String(item))}`)
        : [`${key}=${encodeURIComponent(String(v))}`];
    })
    .join('&');
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: PASS. The three REGRESSION tests confirm the 14 existing tools are unaffected.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-semrush-service/server.js \
        apps-microservices/mcp-semrush-service/server.test.js
git commit -m "feat(mcp-semrush): support array values in buildQS

Array values expand into repeated key=value pairs, required by the
backlinks_matrix report which takes multiple targets. Scalar behavior is
unchanged and pinned by regression tests.

Les valeurs tableau se decomposent en paires key=value repetees, requis par
le rapport backlinks_matrix qui accepte plusieurs cibles. Le comportement
scalaire est inchange et verrouille par des tests de regression."
```

---

### Task 3: `display_limit` clamp

Backlink reports bill 40 API units per returned row. `display_limit` is currently forwarded
to Semrush unvalidated, so one bad LLM-generated argument is a direct billing event.
Clamping is silent by design: the call succeeds with fewer rows rather than failing the
agent's task.

**Files:**
- Modify: `apps-microservices/mcp-semrush-service/server.js` (add after `buildQS`)
- Test: `apps-microservices/mcp-semrush-service/server.test.js`

**Interfaces:**
- Consumes: nothing
- Produces: `MAX_DISPLAY_LIMIT` (number, 100) and `clampDisplayLimit(value, fallback)` → integer in `[1, 100]`. Both added to `module.exports`.

- [ ] **Step 1: Write the failing test**

Add `MAX_DISPLAY_LIMIT` and `clampDisplayLimit` to the destructured require at the top of
`server.test.js`, then append:

```js
test('clampDisplayLimit caps values above the maximum', () => {
  assert.strictEqual(clampDisplayLimit(5000, 10), MAX_DISPLAY_LIMIT);
});

test('clampDisplayLimit passes values at or below the maximum through', () => {
  assert.strictEqual(clampDisplayLimit(25, 10), 25);
  assert.strictEqual(clampDisplayLimit(MAX_DISPLAY_LIMIT, 10), MAX_DISPLAY_LIMIT);
});

test('clampDisplayLimit returns the fallback for missing values', () => {
  assert.strictEqual(clampDisplayLimit(undefined, 10), 10);
  assert.strictEqual(clampDisplayLimit(null, 10), 10);
});

test('clampDisplayLimit returns the fallback for junk and out-of-range values', () => {
  assert.strictEqual(clampDisplayLimit('abc', 10), 10);
  assert.strictEqual(clampDisplayLimit(0, 10), 10);
  assert.strictEqual(clampDisplayLimit(-5, 10), 10);
  assert.strictEqual(clampDisplayLimit(Infinity, 10), 10);
});

test('clampDisplayLimit floors fractional values', () => {
  assert.strictEqual(clampDisplayLimit(12.7, 10), 12);
});

test('clampDisplayLimit accepts numeric strings', () => {
  assert.strictEqual(clampDisplayLimit('42', 10), 42);
});

test('MAX_DISPLAY_LIMIT is 100 (4,000 API units per call)', () => {
  assert.strictEqual(MAX_DISPLAY_LIMIT, 100);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: FAIL with `TypeError: clampDisplayLimit is not a function`.

- [ ] **Step 3: Implement the clamp**

Add to `server.js` immediately after `buildQS`:

```js
// ── Cost guard ──────────────────────────────────────────────────────────────
// Backlink reports bill 40 Semrush API units per returned row. Clamp silently:
// the call succeeds with fewer rows rather than failing the caller's task.

const MAX_DISPLAY_LIMIT = 100;   // 100 rows x 40 units = 4,000 unit ceiling

function clampDisplayLimit(value, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 1) return fallback;
  return Math.min(Math.floor(n), MAX_DISPLAY_LIMIT);
}
```

Add `MAX_DISPLAY_LIMIT` and `clampDisplayLimit` to `module.exports`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-semrush-service/server.js \
        apps-microservices/mcp-semrush-service/server.test.js
git commit -m "feat(mcp-semrush): add display_limit cost guard

Clamp display_limit to 100 rows. Backlink reports bill 40 API units per
row, so an unvalidated limit is a direct billing risk. Clamping is silent
so agent calls degrade rather than fail.

Plafonne display_limit a 100 lignes. Les rapports backlink coutent 40
unites API par ligne, donc une limite non validee est un risque de
facturation direct. Le plafonnement est silencieux."
```

---

### Task 4: Semrush `ERROR` detection and richer tool results

The Semrush Analytics API returns **HTTP 200** with a plain-text body such as
`ERROR 50 :: NOTHING FOUND`. `httpGet` only rejects on non-2xx, so these currently reach the
caller as successful results with no `isError` flag — protocol-indistinguishable from real
data.

Fixing this needs two changes: a detector, and a `tools/call` handler that lets a tool
return a full result object instead of only a string. The handler change must stay
backward compatible with the 14 tools that return strings.

**Files:**
- Modify: `apps-microservices/mcp-semrush-service/server.js` (add detector; modify `handleLine`'s `tools/call` branch from Task 1)
- Test: `apps-microservices/mcp-semrush-service/server.test.js`

**Interfaces:**
- Consumes: `handleLine` from Task 1
- Produces: `isSemrushError(text)` → boolean. `tool.run()` may now return **either** a string (existing behavior) **or** an object shaped `{ content: [...], isError?: boolean }`.

- [ ] **Step 1: Write the failing test**

Add `isSemrushError` to the destructured require, then append:

```js
test('isSemrushError detects Semrush error bodies', () => {
  assert.strictEqual(isSemrushError('ERROR 50 :: NOTHING FOUND'), true);
  assert.strictEqual(isSemrushError('ERROR 120 :: WRONG KEY - ID PAIR'), true);
  assert.strictEqual(isSemrushError('ERROR 130 :: API DISABLED'), true);
  assert.strictEqual(isSemrushError('ERROR 134 :: API UNITS BALANCE IS ZERO'), true);
});

test('isSemrushError tolerates surrounding whitespace', () => {
  assert.strictEqual(isSemrushError('\n  ERROR 50 :: NOTHING FOUND\n'), true);
});

test('isSemrushError does not flag real CSV payloads', () => {
  const csv = 'page_ascore;source_url;anchor\n42;https://x.com/a;click here';
  assert.strictEqual(isSemrushError(csv), false);
});

test('isSemrushError does not flag CSV whose data merely contains the word ERROR', () => {
  const csv = 'anchor;backlinks_num\nERROR CODE GUIDE;12';
  assert.strictEqual(isSemrushError(csv), false);
});

test('isSemrushError handles empty and non-string input', () => {
  assert.strictEqual(isSemrushError(''), false);
  assert.strictEqual(isSemrushError(undefined), false);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: FAIL with `TypeError: isSemrushError is not a function`.

- [ ] **Step 3: Implement the detector**

Add to `server.js` after `clampDisplayLimit`:

```js
// The Semrush Analytics API answers HTTP 200 with a plain-text `ERROR n :: MESSAGE`
// body on failure. Without this check such a body reaches the caller as a success.
function isSemrushError(text) {
  return /^ERROR\s+\d+\s*::/.test(String(text ?? '').trim());
}
```

Add `isSemrushError` to `module.exports`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: PASS.

- [ ] **Step 5: Let `tools/call` return full result objects**

In `handleLine`, replace the `tools/call` success path:

```js
          try {
            const out = await tool.run(args);
            // A tool may return a plain string (the 14 original tools) or a
            // complete MCP result object (the backlink factory, which sets isError).
            if (out && typeof out === 'object' && Array.isArray(out.content)) {
              sendResult(id, out);
            } else {
              sendResult(id, { content: [{ type: 'text', text: String(out) }] });
            }
          } catch (err) {
```

- [ ] **Step 6: Write and run the handler regression test**

Append to `server.test.js`:

```js
test('REGRESSION: a string-returning tool still produces a plain text result', async () => {
  const results = [];
  const original = process.stdout.write;
  process.stdout.write = (chunk) => { results.push(String(chunk)); return true; };
  try {
    const stub = { name: 'stub_string', description: 'd', inputSchema: {}, run: async () => 'plain csv' };
    toolByName.stub_string = stub;
    await handleLine(JSON.stringify({
      jsonrpc: '2.0', id: 1, method: 'tools/call',
      params: { name: 'stub_string', arguments: {} },
    }));
  } finally {
    process.stdout.write = original;
    delete toolByName.stub_string;
  }
  const msg = JSON.parse(results.join(''));
  assert.deepStrictEqual(msg.result, { content: [{ type: 'text', text: 'plain csv' }] });
});

test('a tool returning a result object has it passed through with isError', async () => {
  const results = [];
  const original = process.stdout.write;
  process.stdout.write = (chunk) => { results.push(String(chunk)); return true; };
  try {
    const stub = {
      name: 'stub_object', description: 'd', inputSchema: {},
      run: async () => ({ content: [{ type: 'text', text: 'ERROR 50 :: NOTHING FOUND' }], isError: true }),
    };
    toolByName.stub_object = stub;
    await handleLine(JSON.stringify({
      jsonrpc: '2.0', id: 2, method: 'tools/call',
      params: { name: 'stub_object', arguments: {} },
    }));
  } finally {
    process.stdout.write = original;
    delete toolByName.stub_object;
  }
  const msg = JSON.parse(results.join(''));
  assert.strictEqual(msg.result.isError, true);
  assert.strictEqual(msg.result.content[0].text, 'ERROR 50 :: NOTHING FOUND');
});
```

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps-microservices/mcp-semrush-service/server.js \
        apps-microservices/mcp-semrush-service/server.test.js
git commit -m "feat(mcp-semrush): detect Semrush ERROR bodies returned with HTTP 200

Semrush answers 200 OK with a plain-text ERROR body on failure, which
previously reached callers as a successful result. Add a detector and let
tools return a full MCP result object so isError can be set. String
returns stay supported for the 14 existing tools.

Semrush repond 200 OK avec un corps ERROR en texte brut, jusqu'ici transmis
comme un succes. Ajoute un detecteur et permet aux outils de retourner un
objet resultat complet pour positionner isError."
```

---

### Task 5: Report table and factory — `standard` shape

Introduces `BACKLINK_REPORTS`, the pure URL builder, and `makeBacklinkTool`, then registers
the five new `standard`-shape tools: `backlinks_anchors`, `backlinks_pages`,
`backlinks_competitors`, `backlinks_geo`, `backlinks_tld`.

URL construction is a **pure function** so tests assert the exact query string without
network access or mocking.

All `export_columns` values are verbatim from
<https://developer.semrush.com/api/v3/analytics/backlinks/>.

**Files:**
- Modify: `apps-microservices/mcp-semrush-service/server.js` (add before `const toolByName`)
- Test: `apps-microservices/mcp-semrush-service/server.test.js`

**Interfaces:**
- Consumes: `buildQS` (Task 2), `clampDisplayLimit`/`MAX_DISPLAY_LIMIT` (Task 3), `isSemrushError` (Task 4), `BACK` (Task 1)
- Produces:
  - `BACKLINK_REPORTS` — array of `{ name, type, shape, description, columns }`
  - `buildBacklinkParams(spec, args)` → plain params object
  - `buildBacklinkUrl(spec, args)` → full URL string
  - `makeBacklinkTool(spec)` → `{ name, description, inputSchema, run }`

- [ ] **Step 1: Write the failing test**

Add `BACKLINK_REPORTS`, `buildBacklinkUrl`, `makeBacklinkTool` to the destructured require,
then append:

```js
const specByName = (n) => BACKLINK_REPORTS.find((s) => s.name === n);

test('standard shape builds the expected query', () => {
  const url = buildBacklinkUrl(specByName('backlinks_anchors'), { target: 'hellopro.fr' });
  assert.ok(url.startsWith('https://api.semrush.com/analytics/v1/?'));
  assert.ok(url.includes('type=backlinks_anchors'));
  assert.ok(url.includes('target=hellopro.fr'));
  assert.ok(url.includes('target_type=root_domain'));
  assert.ok(url.includes('display_limit=10'));
});

test('standard shape defaults target_type to root_domain and honours an override', () => {
  const url = buildBacklinkUrl(specByName('backlinks_pages'), {
    target: 'https://hellopro.fr/x.html', target_type: 'url',
  });
  assert.ok(url.includes('target_type=url'));
});

test('standard shape clamps display_limit', () => {
  const url = buildBacklinkUrl(specByName('backlinks_geo'), { target: 'hellopro.fr', display_limit: 9999 });
  assert.ok(url.includes('display_limit=100'));
  assert.ok(!url.includes('display_limit=9999'));
});

test('each standard report sends its documented export_columns', () => {
  const expected = {
    backlinks_anchors: 'anchor,domains_num,backlinks_num,first_seen,last_seen',
    backlinks_pages: 'source_url,source_title,response_code,backlinks_num,domains_num,last_seen,external_num,internal_num',
    backlinks_competitors: 'score,neighbour,similarity,common_refdomains,domains_num,backlinks_num',
    backlinks_geo: 'country,domains_num,backlinks_num',
    backlinks_tld: 'zone,domains_num,backlinks_num',
  };
  for (const [name, columns] of Object.entries(expected)) {
    const url = buildBacklinkUrl(specByName(name), { target: 'hellopro.fr' });
    assert.ok(
      url.includes(`export_columns=${encodeURIComponent(columns)}`),
      `${name} sends its documented columns`,
    );
  }
});

test('makeBacklinkTool produces a standard-shape inputSchema', () => {
  const tool = makeBacklinkTool(specByName('backlinks_anchors'));
  assert.strictEqual(tool.name, 'backlinks_anchors');
  assert.ok(tool.description.length > 0);
  assert.deepStrictEqual(tool.inputSchema.required, ['target']);
  assert.ok(tool.inputSchema.properties.target);
  assert.ok(tool.inputSchema.properties.target_type);
  assert.ok(tool.inputSchema.properties.display_limit);
});

test('the five new standard backlink tools are registered', () => {
  const names = TOOLS.map((t) => t.name);
  for (const n of ['backlinks_anchors', 'backlinks_pages', 'backlinks_competitors',
                   'backlinks_geo', 'backlinks_tld']) {
    assert.ok(names.includes(n), `${n} is registered`);
  }
});

```

Then update the single `registered tool count` test from Task 1: change `16` to `21`
(16 original + 5 new). Do not add a second count test.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: FAIL with `TypeError: Cannot read properties of undefined (reading 'find')` —
`BACKLINK_REPORTS` is not exported yet.

- [ ] **Step 3: Implement the table and factory**

Add to `server.js` immediately before `const toolByName = ...`:

```js
// ── Backlink reports (table-driven) ─────────────────────────────────────────
// Semrush backlink reports are not uniform. Three parameter shapes exist:
//   standard — target + target_type + display_limit  (billed per row)
//   summary  — target + target_type, single row      (billed per request)
//   multi    — targets[] + target_types[]            (billed per row)
// Columns are verbatim from developer.semrush.com/api/v3/analytics/backlinks/

const BACKLINK_REPORTS = [
  {
    name: 'backlinks_anchors',
    type: 'backlinks_anchors',
    shape: 'standard',
    description: 'Anchor texts used in backlinks pointing at a domain, with domain and backlink counts. Requires Semrush Business plan.',
    columns: 'anchor,domains_num,backlinks_num,first_seen,last_seen',
  },
  {
    name: 'backlinks_pages',
    type: 'backlinks_pages',
    shape: 'standard',
    description: 'Pages on the target that receive backlinks, ranked by backlink count. Requires Semrush Business plan.',
    columns: 'source_url,source_title,response_code,backlinks_num,domains_num,last_seen,external_num,internal_num',
  },
  {
    name: 'backlinks_competitors',
    type: 'backlinks_competitors',
    shape: 'standard',
    description: 'Domains with a backlink profile similar to the target, with the number of shared referring domains. Requires Semrush Business plan.',
    columns: 'score,neighbour,similarity,common_refdomains,domains_num,backlinks_num',
  },
  {
    name: 'backlinks_geo',
    type: 'backlinks_geo',
    shape: 'standard',
    description: 'Referring domains grouped by country. Requires Semrush Business plan.',
    columns: 'country,domains_num,backlinks_num',
  },
  {
    name: 'backlinks_tld',
    type: 'backlinks_tld',
    shape: 'standard',
    description: 'Referring domains grouped by top-level domain (zone). Requires Semrush Business plan.',
    columns: 'zone,domains_num,backlinks_num',
  },
];

const TARGET_TYPE_DESC = 'Target type: root_domain, domain, or url. Default: root_domain';

function backlinkInputSchema(spec) {
  const properties = {
    target: { type: 'string', description: 'Domain or URL to analyze (e.g. hellopro.fr)' },
    target_type: { type: 'string', description: TARGET_TYPE_DESC },
  };
  if (spec.shape === 'standard') {
    properties.display_limit = {
      type: 'integer',
      description: `Rows to return (default 10, max ${MAX_DISPLAY_LIMIT}). Each row costs 40 Semrush API units.`,
    };
  }
  return { type: 'object', properties, required: ['target'] };
}

function buildBacklinkParams(spec, args = {}) {
  const { target, target_type = 'root_domain', display_limit } = args;
  const params = {
    key: API_KEY,
    type: spec.type,
    target,
    target_type,
    export_columns: spec.columns,
  };
  if (spec.shape === 'standard') {
    params.display_limit = clampDisplayLimit(display_limit, 10);
  }
  return params;
}

function buildBacklinkUrl(spec, args) {
  return BACK + '?' + buildQS(buildBacklinkParams(spec, args));
}

function makeBacklinkTool(spec) {
  return {
    name: spec.name,
    description: spec.description,
    inputSchema: backlinkInputSchema(spec),
    async run(args) {
      const text = await httpGet(buildBacklinkUrl(spec, args));
      if (isSemrushError(text)) {
        return { content: [{ type: 'text', text: String(text) }], isError: true };
      }
      return text;
    },
  };
}

TOOLS.push(...BACKLINK_REPORTS.map(makeBacklinkTool));
```

Add `BACKLINK_REPORTS`, `buildBacklinkParams`, `buildBacklinkUrl`, `makeBacklinkTool` to
`module.exports`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: PASS. `TOOLS.length` is 21 (16 original + 5 new).

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-semrush-service/server.js \
        apps-microservices/mcp-semrush-service/server.test.js
git commit -m "feat(mcp-semrush): add five standard-shape backlink tools

Introduce the BACKLINK_REPORTS table and makeBacklinkTool factory, then
register backlinks_anchors, backlinks_pages, backlinks_competitors,
backlinks_geo and backlinks_tld. URL construction is a pure function so it
is tested without network access.

Introduit la table BACKLINK_REPORTS et la factory makeBacklinkTool, puis
enregistre cinq nouveaux rapports backlink. La construction d'URL est une
fonction pure, testee sans acces reseau."
```

---

### Task 6: `summary` shape — `backlinks_overview`

`backlinks_overview` is billed **per request** (40 units flat) rather than per row, and
returns a single summary row. It is the cheapest backlink call and the natural first call
before drilling into per-row reports — its description says so, to steer LLM tool choice.

**Files:**
- Modify: `apps-microservices/mcp-semrush-service/server.js` (add entry to `BACKLINK_REPORTS`)
- Test: `apps-microservices/mcp-semrush-service/server.test.js`

**Interfaces:**
- Consumes: `BACKLINK_REPORTS`, `buildBacklinkUrl`, `makeBacklinkTool` (Task 5)
- Produces: a `shape: 'summary'` entry. `backlinkInputSchema` already omits `display_limit` for non-`standard` shapes, and `buildBacklinkParams` already omits it — no factory change needed.

- [ ] **Step 1: Write the failing test**

Append to `server.test.js`:

```js
test('summary shape omits display_limit from the query', () => {
  const url = buildBacklinkUrl(specByName('backlinks_overview'), { target: 'hellopro.fr' });
  assert.ok(url.includes('type=backlinks_overview'));
  assert.ok(url.includes('target=hellopro.fr'));
  assert.ok(url.includes('target_type=root_domain'));
  assert.ok(!url.includes('display_limit'), 'summary reports have no display_limit');
});

test('summary shape ignores a display_limit passed by the caller', () => {
  const url = buildBacklinkUrl(specByName('backlinks_overview'), {
    target: 'hellopro.fr', display_limit: 500,
  });
  assert.ok(!url.includes('display_limit'));
});

test('summary shape omits display_limit from its inputSchema', () => {
  const tool = makeBacklinkTool(specByName('backlinks_overview'));
  assert.strictEqual(tool.inputSchema.properties.display_limit, undefined);
  assert.ok(tool.inputSchema.properties.target);
});

test('backlinks_overview sends its documented export_columns', () => {
  const columns = 'ascore,total,domains_num,urls_num,ips_num,ipclassc_num,follows_num,' +
                  'nofollows_num,sponsored_num,ugc_num,texts_num,images_num,forms_num,frames_num';
  const url = buildBacklinkUrl(specByName('backlinks_overview'), { target: 'hellopro.fr' });
  assert.ok(url.includes(`export_columns=${encodeURIComponent(columns)}`));
});

test('backlinks_overview description mentions it is the cheapest backlink call', () => {
  const tool = makeBacklinkTool(specByName('backlinks_overview'));
  assert.match(tool.description, /40 units|cheapest/i);
});

```

Then update the `registered tool count` test from `21` to `22`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: FAIL with `TypeError: Cannot read properties of undefined (reading 'shape')` —
`specByName('backlinks_overview')` returns `undefined`.

- [ ] **Step 3: Add the table entry**

Insert as the **first** element of `BACKLINK_REPORTS` (cheapest call listed first):

```js
  {
    name: 'backlinks_overview',
    type: 'backlinks_overview',
    shape: 'summary',
    description: 'Backlink profile summary for a domain: authority score, total backlinks, referring domains and IPs, and follow vs nofollow counts. Costs 40 units per request rather than per row, making it the cheapest backlink call — use it before drilling into per-row reports. Requires Semrush Business plan.',
    columns: 'ascore,total,domains_num,urls_num,ips_num,ipclassc_num,follows_num,' +
             'nofollows_num,sponsored_num,ugc_num,texts_num,images_num,forms_num,frames_num',
  },
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-semrush-service/server.js \
        apps-microservices/mcp-semrush-service/server.test.js
git commit -m "feat(mcp-semrush): add backlinks_overview summary tool

Billed per request rather than per row, so it is the cheapest backlink
call. Its description says so to steer tool selection toward checking the
summary before drilling into per-row reports.

Facture par requete et non par ligne, c'est l'appel backlink le moins
cher. Sa description l'indique pour orienter le choix d'outil vers le
resume avant les rapports detailles."
```

---

### Task 7: `multi` shape — `backlinks_matrix`

`backlinks_matrix` compares several domains by referring-domain overlap — it answers "who
links to my competitors but not to me". It takes repeated array parameters
(`targets[]`, `target_types[]`), which is why Task 2 added array support to `buildQS`.

**Open question this task must resolve:** the Semrush reference does not state whether
`backlinks_matrix` accepts `display_limit`. Step 1 resolves it before the schema is fixed.
Do not assume — a `display_limit` silently ignored by Semrush would make the cost guard
look effective while doing nothing.

**Files:**
- Modify: `apps-microservices/mcp-semrush-service/server.js` (`BACKLINK_REPORTS`, `backlinkInputSchema`, `buildBacklinkParams`)
- Test: `apps-microservices/mcp-semrush-service/server.test.js`

**Interfaces:**
- Consumes: `buildQS` array support (Task 2), the factory (Task 5)
- Produces: a `shape: 'multi'` branch in `backlinkInputSchema` and `buildBacklinkParams`. Input key is `targets` (array of strings); a single `target_type` is applied to every target.

- [ ] **Step 1: Resolve whether `backlinks_matrix` accepts `display_limit`**

Read <https://developer.semrush.com/api/v3/analytics/backlinks/>, section "Comparison by
Referring Domains".

- If `display_limit` **is** documented: keep it in the `multi` schema and clamp it exactly
  as the `standard` shape does.
- If it is **not** documented: omit `display_limit` from the `multi` schema entirely, and
  change the Step 3 code below to drop the `display_limit` line.

Record the finding as a comment above the `backlinks_matrix` table entry. The code in
Step 3 assumes it **is** supported; adjust if the reference says otherwise.

- [ ] **Step 2: Write the failing test**

Append to `server.test.js`:

```js
test('multi shape emits repeated targets parameters', () => {
  const url = buildBacklinkUrl(specByName('backlinks_matrix'), {
    targets: ['hellopro.fr', 'competitor.fr'],
  });
  assert.ok(url.includes('type=backlinks_matrix'));
  assert.ok(url.includes('targets=hellopro.fr'));
  assert.ok(url.includes('targets=competitor.fr'));
});

test('multi shape emits one target_types entry per target', () => {
  const url = buildBacklinkUrl(specByName('backlinks_matrix'), {
    targets: ['a.com', 'b.com', 'c.com'],
  });
  const count = (url.match(/target_types=root_domain/g) || []).length;
  assert.strictEqual(count, 3, 'one target_types per target');
});

test('multi shape applies a target_type override to every target', () => {
  const url = buildBacklinkUrl(specByName('backlinks_matrix'), {
    targets: ['a.com', 'b.com'], target_type: 'domain',
  });
  const count = (url.match(/target_types=domain/g) || []).length;
  assert.strictEqual(count, 2);
});

test('multi shape requires targets, not target, in its schema', () => {
  const tool = makeBacklinkTool(specByName('backlinks_matrix'));
  assert.deepStrictEqual(tool.inputSchema.required, ['targets']);
  assert.strictEqual(tool.inputSchema.properties.targets.type, 'array');
  assert.strictEqual(tool.inputSchema.properties.target, undefined);
});

test('backlinks_matrix sends its documented export_columns', () => {
  const columns = 'domain,domain_ascore,domain_score,matches_num,backlinks_num';
  const url = buildBacklinkUrl(specByName('backlinks_matrix'), { targets: ['a.com'] });
  assert.ok(url.includes(`export_columns=${encodeURIComponent(columns)}`));
});

```

Then update the `registered tool count` test from `22` to `23`.

- [ ] **Step 3: Implement the `multi` shape**

Append to `BACKLINK_REPORTS`:

```js
  {
    name: 'backlinks_matrix',
    type: 'backlinks_matrix',
    shape: 'multi',
    description: 'Compare the backlink profiles of up to five domains by referring-domain overlap. Finds domains that link to competitors but not to you. Requires Semrush Business plan.',
    columns: 'domain,domain_ascore,domain_score,matches_num,backlinks_num',
  },
```

In `backlinkInputSchema`, handle `multi` before the shared path:

```js
function backlinkInputSchema(spec) {
  if (spec.shape === 'multi') {
    return {
      type: 'object',
      properties: {
        targets: {
          type: 'array',
          items: { type: 'string' },
          description: 'Domains to compare (2 to 5, e.g. ["hellopro.fr", "competitor.fr"])',
        },
        target_type: { type: 'string', description: `${TARGET_TYPE_DESC}. Applied to every target.` },
        display_limit: {
          type: 'integer',
          description: `Rows to return (default 10, max ${MAX_DISPLAY_LIMIT}). Each row costs 40 Semrush API units.`,
        },
      },
      required: ['targets'],
    };
  }

  const properties = {
    target: { type: 'string', description: 'Domain or URL to analyze (e.g. hellopro.fr)' },
    target_type: { type: 'string', description: TARGET_TYPE_DESC },
  };
  if (spec.shape === 'standard') {
    properties.display_limit = {
      type: 'integer',
      description: `Rows to return (default 10, max ${MAX_DISPLAY_LIMIT}). Each row costs 40 Semrush API units.`,
    };
  }
  return { type: 'object', properties, required: ['target'] };
}
```

In `buildBacklinkParams`, handle `multi` before the shared path:

```js
function buildBacklinkParams(spec, args = {}) {
  if (spec.shape === 'multi') {
    const { targets = [], target_type = 'root_domain', display_limit } = args;
    const list = Array.isArray(targets) ? targets : [targets];
    return {
      key: API_KEY,
      type: spec.type,
      targets: list,
      target_types: list.map(() => target_type),
      export_columns: spec.columns,
      display_limit: clampDisplayLimit(display_limit, 10),
    };
  }

  const { target, target_type = 'root_domain', display_limit } = args;
  const params = {
    key: API_KEY,
    type: spec.type,
    target,
    target_type,
    export_columns: spec.columns,
  };
  if (spec.shape === 'standard') {
    params.display_limit = clampDisplayLimit(display_limit, 10);
  }
  return params;
}
```

If Step 1 found `display_limit` is **not** supported, delete the `display_limit` line from
both the `multi` schema and the `multi` params branch.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps-microservices/mcp-semrush-service/server.js \
        apps-microservices/mcp-semrush-service/server.test.js
git commit -m "feat(mcp-semrush): add backlinks_matrix multi-target comparison

Compares referring-domain overlap across several domains, answering which
domains link to competitors but not to us. Uses the repeated-parameter
support added to buildQS.

Compare le recouvrement des domaines referents entre plusieurs domaines,
pour identifier ceux qui pointent vers les concurrents mais pas vers nous.
Utilise le support des parametres repetes ajoute a buildQS."
```

---

### Task 8: Migrate the two existing backlink tools into the table

`backlinks` and `backlinks_domains` are still hand-written blocks at `server.js:325-364`.
Moving them into `BACKLINK_REPORTS` gives them the clamp and error detection, and adds the
`nofollow` column to `backlinks` — the gap that made link-quality auditing impossible.

The tool **name** `backlinks_domains` is deliberately preserved even though the Semrush
report type is `backlinks_refdomains`. Renaming would break every existing caller for no
benefit.

**Files:**
- Modify: `apps-microservices/mcp-semrush-service/server.js:325-364` (delete), `BACKLINK_REPORTS` (add two entries)
- Test: `apps-microservices/mcp-semrush-service/server.test.js`

**Interfaces:**
- Consumes: the factory (Task 5)
- Produces: no new interface. Tool count stays 23 — two hand-written tools are replaced by two table entries.

- [ ] **Step 1: Write the failing test**

Append to `server.test.js`:

```js
test('backlinks now requests the nofollow column', () => {
  const url = buildBacklinkUrl(specByName('backlinks'), { target: 'hellopro.fr' });
  const columns = 'page_ascore,source_url,target_url,anchor,nofollow,' +
                  'external_num,internal_num,first_seen,last_seen';
  assert.ok(url.includes(`export_columns=${encodeURIComponent(columns)}`));
});

test('backlinks still sends type=backlinks exactly', () => {
  const url = buildBacklinkUrl(specByName('backlinks'), { target: 'hellopro.fr' });
  // Anchored so it cannot pass on type=backlinks_anchors or any other prefix match.
  assert.match(url, /[?&]type=backlinks(&|$)/);
});

test('backlinks_domains keeps its tool name but sends type=backlinks_refdomains', () => {
  const spec = specByName('backlinks_domains');
  assert.strictEqual(spec.type, 'backlinks_refdomains');
  const url = buildBacklinkUrl(spec, { target: 'hellopro.fr' });
  assert.ok(url.includes('type=backlinks_refdomains'));
});

test('backlinks_domains columns are unchanged', () => {
  const columns = 'domain_ascore,domain,backlinks_num,ip,country,first_seen,last_seen';
  const url = buildBacklinkUrl(specByName('backlinks_domains'), { target: 'hellopro.fr' });
  assert.ok(url.includes(`export_columns=${encodeURIComponent(columns)}`));
});

test('the migrated tools inherit the display_limit clamp', () => {
  for (const name of ['backlinks', 'backlinks_domains']) {
    const url = buildBacklinkUrl(specByName(name), { target: 'hellopro.fr', display_limit: 9999 });
    assert.ok(url.includes('display_limit=100'), `${name} is clamped`);
  }
});

test('all nine backlink tools come from the table', () => {
  assert.strictEqual(BACKLINK_REPORTS.length, 9);
  const names = BACKLINK_REPORTS.map((s) => s.name).sort();
  assert.deepStrictEqual(names, [
    'backlinks', 'backlinks_anchors', 'backlinks_competitors', 'backlinks_domains',
    'backlinks_geo', 'backlinks_matrix', 'backlinks_overview', 'backlinks_pages',
    'backlinks_tld',
  ]);
});

// Catches a botched migration that leaves both the hand-written block and the
// table entry registered under the same name. The `registered tool count` test
// from Task 1 already pins the total at 23.
test('no duplicate tool names after the migration', () => {
  assert.strictEqual(new Set(TOOLS.map((t) => t.name)).size, TOOLS.length);
});

test('REGRESSION: the 14 non-backlink tools are still registered', () => {
  const names = TOOLS.map((t) => t.name);
  for (const n of ['domain_overview', 'domain_organic_keywords', 'domain_paid_keywords',
                   'competitors', 'keyword_overview', 'keyword_overview_single_db',
                   'batch_keyword_overview', 'keyword_organic_results', 'keyword_paid_results',
                   'keyword_ads_history', 'related_keywords', 'broad_match_keywords',
                   'phrase_questions', 'keyword_difficulty']) {
    assert.ok(names.includes(n), `${n} still registered`);
  }
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: FAIL. `specByName('backlinks')` returns `undefined` (not in the table yet), and
`BACKLINK_REPORTS.length` is 7, not 9. The duplicate check would also catch a botched
migration that leaves both the hand-written block and the table entry in place.

- [ ] **Step 3: Delete the hand-written blocks and add table entries**

Delete `server.js:325-364` entirely — the `// ── Backlinks (fixed: target_type now always
included) ──` comment and both tool object literals for `backlinks` and `backlinks_domains`.

Add to `BACKLINK_REPORTS`, immediately after the `backlinks_overview` entry:

```js
  {
    name: 'backlinks',
    type: 'backlinks',
    shape: 'standard',
    description: 'Individual backlinks pointing at a domain or URL, with source page authority, anchor text and follow status. Requires Semrush Business plan.',
    columns: 'page_ascore,source_url,target_url,anchor,nofollow,' +
             'external_num,internal_num,first_seen,last_seen',
  },
  {
    name: 'backlinks_domains',
    type: 'backlinks_refdomains',
    shape: 'standard',
    description: 'Referring domains linking to a target, with authority score and link counts. Cheaper per unit of insight than the backlinks report — one row covers many links. Requires Semrush Business plan.',
    columns: 'domain_ascore,domain,backlinks_num,ip,country,first_seen,last_seen',
  },
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps-microservices/mcp-semrush-service && npm test`

Expected: PASS.

- [ ] **Step 5: Verify the live server reports 23 tools**

Run:

```bash
cd apps-microservices/mcp-semrush-service && \
  echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | node server.js | \
  node -e "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{const t=JSON.parse(s).result.tools;console.log('tools:',t.length);console.log(t.filter(x=>x.name.startsWith('backlink')).map(x=>x.name).join('\n'));})"
```

Expected: `tools: 23`, followed by the nine backlink tool names.

- [ ] **Step 6: Commit**

```bash
git add apps-microservices/mcp-semrush-service/server.js \
        apps-microservices/mcp-semrush-service/server.test.js
git commit -m "refactor(mcp-semrush): move existing backlink tools into the table

backlinks and backlinks_domains now come from BACKLINK_REPORTS, inheriting
the display_limit clamp and ERROR detection. backlinks gains the nofollow
column, closing the link-quality gap. The backlinks_domains tool name is
kept despite the type being backlinks_refdomains, to avoid breaking callers.

backlinks et backlinks_domains proviennent desormais de BACKLINK_REPORTS et
heritent du plafond display_limit et de la detection ERROR. backlinks gagne
la colonne nofollow. Le nom backlinks_domains est conserve pour ne pas
casser les appelants."
```

---

### Task 9: Update documentation

**Files:**
- Modify: `apps-microservices/mcp-semrush-service/BACKLINKS.md`
- Modify: `apps-microservices/mcp-semrush-service/CLAUDE.md`

**Interfaces:**
- Consumes: the finished implementation
- Produces: nothing consumed by code

- [ ] **Step 1: Update `BACKLINKS.md`**

Make these specific edits:

1. Under `## Tools`, add a subsection for each of the 7 new tools following the existing
   two-table format (parameter table, then the `GET` request block, then a column-meaning
   table). Column meanings:
   - `ascore` — Authority Score of the target domain
   - `total` — total backlinks found
   - `domains_num` / `urls_num` / `ips_num` / `ipclassc_num` — distinct referring domains, URLs, IPs, class-C IP blocks
   - `follows_num` / `nofollows_num` / `sponsored_num` / `ugc_num` — link counts by rel attribute
   - `texts_num` / `images_num` / `forms_num` / `frames_num` — link counts by markup type
   - `anchor` — anchor text; `zone` — top-level domain; `country` — ISO country code
   - `score` / `neighbour` / `similarity` / `common_refdomains` — competitor match strength and shared referring domains
   - `matches_num` — referring domains shared with the compared set
   - `response_code` — HTTP status of the linked page
2. In the `backlinks` column table, add the `nofollow` row: "Whether the link carries
   `rel="nofollow"` — nofollow links do not pass authority."
3. Add a `## Cost guard` section stating `MAX_DISPLAY_LIMIT = 100`, that clamping is silent,
   and that `backlinks_overview` is billed per request.
4. Rewrite `## Error behavior`: the `ERROR` body case now sets `isError: true`. Remove the
   warning that errors are indistinguishable from success — it is no longer true.
5. In `## Known gaps`, **delete** the "No `nofollow` column" and "No `display_limit`
   validation" bullets, both now resolved. **Keep** the pagination, sorting, filtering and
   lost/new-link bullets, which remain deferred.

- [ ] **Step 2: Update `CLAUDE.md`**

1. Change "16 tools, all defined in the `TOOLS` array in `server.js`." to
   "23 tools. The 14 domain and keyword tools are hand-written in the `TOOLS` array; the 9
   backlink tools are generated from the `BACKLINK_REPORTS` table."
2. Replace the Backlinks row of the tools table with:
   `` | Backlinks | `backlinks`, `backlinks_domains`, `backlinks_overview`, `backlinks_anchors`, `backlinks_pages`, `backlinks_competitors`, `backlinks_geo`, `backlinks_tld`, `backlinks_matrix` — see [BACKLINKS.md](./BACKLINKS.md) | ``
3. In the "Backlinks — cost warning" section, replace "forwarded to Semrush unvalidated"
   with "clamped to 100 rows (4,000 units) by `MAX_DISPLAY_LIMIT`".
4. Add a `## Tests` section: "`npm test` runs `node --test` against `server.test.js`. No
   test makes a live Semrush call. The test file is not copied into the Docker image."

- [ ] **Step 3: Verify the docs match the code**

Run:

```bash
cd apps-microservices/mcp-semrush-service && \
  echo "claimed in CLAUDE.md:" && grep -o "23 tools" CLAUDE.md && \
  echo "actual:" && node -e "console.log(require('./server.js').TOOLS.length, 'tools')" && \
  echo "backlink specs:" && node -e "console.log(require('./server.js').BACKLINK_REPORTS.length)"
```

Expected: `23 tools` claimed, `23 tools` actual, `9` backlink specs.

- [ ] **Step 4: Commit**

```bash
git add apps-microservices/mcp-semrush-service/BACKLINKS.md \
        apps-microservices/mcp-semrush-service/CLAUDE.md
git commit -m "docs(mcp-semrush): document the seven new backlink tools

Add reference entries for the new reports, document the display_limit cost
guard and the new ERROR detection, and remove the nofollow and unvalidated
limit items from Known gaps now that both are resolved.

Ajoute les entrees de reference pour les nouveaux rapports, documente le
plafond display_limit et la detection ERROR, et retire de Known gaps les
points nofollow et limite non validee, desormais resolus."
```

---

## Verification checklist

Run after Task 9. Every item maps to a success criterion in the spec.

- [ ] `npm test` passes with every test green
- [ ] `tools/list` returns 23 tools with no duplicate names
- [ ] The 9 backlink tools are generated from `BACKLINK_REPORTS`
- [ ] `backlinks` requests the `nofollow` column
- [ ] `backlinks_matrix` emits repeated `targets` parameters
- [ ] `display_limit: 9999` becomes `display_limit=100` on every applicable tool
- [ ] A Semrush `ERROR` body yields `isError: true`
- [ ] The 14 non-backlink tools are unchanged
- [ ] `node server.js` still answers `tools/list` over stdio
- [ ] `docker compose --profile mcp build mcp-semrush-service` succeeds

**Live smoke test — costs 40 API units, run once, requires a Business plan:**

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"backlinks_overview","arguments":{"target":"hellopro.fr"}}}' \
  | SEMRUSH_API_KEY="$SEMRUSH_API_KEY" node server.js
```

Expected: a CSV summary row. If it returns `ERROR 130 :: API DISABLED`, the key lacks
backlink entitlement and **all nine backlink tools are non-functional** regardless of this
implementation — escalate rather than debug the code.
