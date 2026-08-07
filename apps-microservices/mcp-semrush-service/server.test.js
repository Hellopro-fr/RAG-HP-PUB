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
