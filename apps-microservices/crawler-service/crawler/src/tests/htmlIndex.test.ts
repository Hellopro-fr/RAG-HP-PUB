/**
 * Tests for htmlIndex.ts — normalizeUrl() + buildHtmlIndex().
 *
 * normalizeUrl() MUST stay byte-identical to PHP normalize_sfpi_url(); the
 * fixtures/url_normalization_cases.json file is the shared cross-language
 * contract mirrored from the PHP repo. buildHtmlIndex() must scan the per-domain
 * dataset dirs, write html_index.json (excluding itself), and never throw.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { normalizeUrl, buildHtmlIndex } from '../htmlIndex.js';

interface NormalizationCase {
    in: string;
    out: string;
}

const fixtureUrl = new URL('./fixtures/url_normalization_cases.json', import.meta.url);
const cases: NormalizationCase[] = JSON.parse(fs.readFileSync(fixtureUrl, 'utf-8'));

test('normalizeUrl: matches the PHP contract for all fixture cases (byte-identical)', () => {
    assert.equal(cases.length, 14, 'fixture case count must match (keep in sync with the PHP fixture url_normalization_cases.json)');
    for (const c of cases) {
        assert.equal(normalizeUrl(c.in), c.out, `normalizeUrl(${JSON.stringify(c.in)})`);
    }
});

test('buildHtmlIndex: happy path — maps normalized URL -> dataset filename', () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'htmlindex-happy-'));
    try {
        const datasetDir = path.join(tmp, 'storage', 'datasets', 'x.fr');
        fs.mkdirSync(datasetDir, { recursive: true });
        fs.writeFileSync(
            path.join(datasetDir, '000000001.json'),
            JSON.stringify({ url: 'https://www.x.fr/p/a/', content: '<html>A</html>' }),
        );
        fs.writeFileSync(
            path.join(datasetDir, '000000002.json'),
            JSON.stringify({ url: 'http://x.fr/p/b', content: '...' }),
        );

        buildHtmlIndex(tmp, 'x.fr');

        const out = path.join(datasetDir, 'html_index.json');
        assert.ok(fs.existsSync(out), 'html_index.json should be written');
        const written = JSON.parse(fs.readFileSync(out, 'utf-8'));
        assert.equal(written.version, '1.0');
        assert.equal(written.domain, 'x.fr');
        assert.equal(written.index['x.fr/p/a'], '000000001.json');
        assert.equal(written.index['x.fr/p/b'], '000000002.json');
        assert.ok(
            !Object.values(written.index).includes('html_index.json'),
            'index must not reference itself',
        );
    } finally {
        fs.rmSync(tmp, { recursive: true, force: true });
    }
});

test('buildHtmlIndex: fail-open — missing dataset dir does not throw', () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'htmlindex-failopen-'));
    try {
        assert.doesNotThrow(() => {
            buildHtmlIndex(tmp, 'nonexistent.fr');
        });
        const out = path.join(tmp, 'storage', 'datasets', 'nonexistent.fr', 'html_index.json');
        assert.ok(!fs.existsSync(out), 'no index should be written for a missing domain dir');
    } finally {
        fs.rmSync(tmp, { recursive: true, force: true });
    }
});

test('buildHtmlIndex: two-dir — indexes both {domain} and update-{domain}', () => {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'htmlindex-twodir-'));
    try {
        const mainDir = path.join(tmp, 'storage', 'datasets', 'y.fr');
        const updateDir = path.join(tmp, 'storage', 'datasets', 'update-y.fr');
        fs.mkdirSync(mainDir, { recursive: true });
        fs.mkdirSync(updateDir, { recursive: true });
        fs.writeFileSync(
            path.join(mainDir, '000000001.json'),
            JSON.stringify({ url: 'https://y.fr/a', content: '<html>A</html>' }),
        );
        fs.writeFileSync(
            path.join(updateDir, '000000001.json'),
            JSON.stringify({ url: 'https://y.fr/b', content: '<html>B</html>' }),
        );

        buildHtmlIndex(tmp, 'y.fr');

        const mainOut = path.join(mainDir, 'html_index.json');
        const updateOut = path.join(updateDir, 'html_index.json');
        assert.ok(fs.existsSync(mainOut), 'html_index.json should be written in y.fr');
        assert.ok(fs.existsSync(updateOut), 'html_index.json should be written in update-y.fr');

        const mainWritten = JSON.parse(fs.readFileSync(mainOut, 'utf-8'));
        const updateWritten = JSON.parse(fs.readFileSync(updateOut, 'utf-8'));
        assert.equal(mainWritten.index['y.fr/a'], '000000001.json');
        assert.equal(updateWritten.index['y.fr/b'], '000000001.json');
    } finally {
        fs.rmSync(tmp, { recursive: true, force: true });
    }
});
