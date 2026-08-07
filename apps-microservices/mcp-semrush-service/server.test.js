'use strict';

const test = require('node:test');
const assert = require('node:assert');

const { TOOLS, buildQS, BACK, MAX_DISPLAY_LIMIT, clampDisplayLimit } = require('./server.js');

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
