'use strict';

const test = require('node:test');
const assert = require('node:assert');

const { TOOLS, toolByName, buildQS, BACK, handleLine, MAX_DISPLAY_LIMIT, clampDisplayLimit, isSemrushError, BACKLINK_REPORTS, buildBacklinkUrl, makeBacklinkTool } = require('./server.js');

test('server.js can be required without hanging', () => {
  assert.ok(Array.isArray(TOOLS));
});

// This is the single tool-count assertion for the whole plan. Tasks 5, 6, 7 and 8
// each UPDATE the expected number here rather than adding their own count test.
test('registered tool count', () => {
  assert.strictEqual(TOOLS.length, 21);
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
