import { test, mock, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { Request } from '@crawlee/core';
import {
    BO_KNOWN_SOURCE,
    BO_KNOWN_UNIQUE_KEY_PREFIX,
    BO_KNOWN_ORIGIN,
    BO_KNOWN_REASON_NOT_ELIGIBLE,
    readKnownUrlsFile,
    buildBoKnownRequest,
    seedBoKnown,
} from '../boKnownSeed.js';

/**
 * A312 T03 — BO-known seed (identity class `bo_known`).
 *
 * Tests 1-11 exercise boKnownSeed.ts directly. Tests 12-15 are source-text assertions, same
 * stance as nonHtmlPrefixWiring.test.ts: main.ts is not importable (it runs at load), so the
 * wiring is pinned by exact literals, counts and ORDER at code anchors. Comments are blanked
 * before any count or absence check, so a comment that quotes a forbidden call can neither
 * satisfy nor break an assertion.
 */

const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'a312-t03-'));
after(() => fs.rmSync(TMP, { recursive: true, force: true }));

const writeTmp = (name: string, content: string): string => {
    const p = path.join(TMP, name);
    fs.writeFileSync(p, content, 'utf-8');
    return p;
};

const SRC = path.join(import.meta.dirname, '..');
const readSrc = (f: string) => fs.readFileSync(path.join(SRC, f), 'utf-8');
// Full-line `//` comments blanked to equal length: offsets stay comparable with the raw source.
const blankLineComments = (s: string) => s.replace(/^[ \t]*\/\/.*$/gm, (m) => ' '.repeat(m.length));
// For boKnownSeed.ts only (no string there contains a comment opener): block comments too.
const blankAllComments = (s: string) =>
    blankLineComments(s.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\r\n]/g, ' ')));
const count = (s: string, needle: string) => s.split(needle).length - 1;
const at = (s: string, needle: string): number => {
    const i = s.indexOf(needle);
    assert.notEqual(i, -1, `anchor not found: ${needle}`);
    return i;
};
// Any increment(...) whose counter name does not start with bo_known_.
const NON_BO_KNOWN_INCREMENT = /\bincrement\(\s*"(?!bo_known_)/;

test('1. constants are the contract literals', () => {
    assert.equal(BO_KNOWN_SOURCE, 'bo_known');
    assert.equal(BO_KNOWN_UNIQUE_KEY_PREFIX, 'bo_known:');
    assert.equal(BO_KNOWN_ORIGIN, 'bo_known');
    assert.equal(BO_KNOWN_REASON_NOT_ELIGIBLE, 'not_eligible');
});

test('2. readKnownUrlsFile: no path => [] and no warning', () => {
    const warn = mock.method(console, 'warn', () => {});
    try {
        assert.deepEqual(readKnownUrlsFile(undefined), []);
        assert.deepEqual(readKnownUrlsFile(''), []);
        assert.equal(warn.mock.callCount(), 0);
    } finally {
        warn.mock.restore();
    }
});

test('3. readKnownUrlsFile: missing file => [] and one warning', () => {
    const warn = mock.method(console, 'warn', () => {});
    try {
        assert.deepEqual(readKnownUrlsFile(path.join(TMP, 'absent.json')), []);
        assert.equal(warn.mock.callCount(), 1);
    } finally {
        warn.mock.restore();
    }
});

test('4. readKnownUrlsFile: invalid JSON => [] and one warning', () => {
    const warn = mock.method(console, 'warn', () => {});
    try {
        assert.deepEqual(readKnownUrlsFile(writeTmp('bad.json', '["https://www.a.fr/x/"')), []);
        assert.equal(warn.mock.callCount(), 1);
    } finally {
        warn.mock.restore();
    }
});

test('5. readKnownUrlsFile: JSON that is not an array => [] and one warning', () => {
    const warn = mock.method(console, 'warn', () => {});
    try {
        assert.deepEqual(readKnownUrlsFile(writeTmp('obj.json', '{"urls":["https://www.a.fr/x/"]}')), []);
        assert.equal(warn.mock.callCount(), 1);
    } finally {
        warn.mock.restore();
    }
});

test('6. readKnownUrlsFile: keeps non-empty strings only, in order, byte-exact', () => {
    const decomposed = 'https://www.exemple.fr/cate\u0301gorie/fiche-1/';
    const withQuery = 'https://www.exemple.fr/p?b=2&a=1#x';
    const warn = mock.method(console, 'warn', () => {});
    try {
        const p = writeTmp('mixed.json', JSON.stringify([decomposed, '', 42, null, withQuery, '  ', { u: 'x' }]));
        const got = readKnownUrlsFile(p);
        assert.deepEqual(got, [decomposed, withQuery, '  ']);
        assert.notEqual(got[0], decomposed.normalize('NFC'), 'no Unicode normalisation');
        assert.equal(warn.mock.callCount(), 1, 'one warning for the dropped entries');
        assert.deepEqual(readKnownUrlsFile(writeTmp('empty.json', '[]')), []);
        assert.equal(warn.mock.callCount(), 1, 'an empty array is not a warning');
    } finally {
        warn.mock.restore();
    }
});

test('7. buildBoKnownRequest: raw url, prefixed uniqueKey, source and rawUrl', () => {
    const raw = 'https://www.exemple.fr/fiche/?ref=A%2FB';
    assert.deepEqual(buildBoKnownRequest(raw), {
        url: raw,
        uniqueKey: 'bo_known:' + raw,
        userData: { source: 'bo_known', rawUrl: raw },
    });
});

test('8. Crawlee keeps request.url raw and the pinned uniqueKey (index fact 8)', () => {
    const raw = 'https://www.example.fr/Produit/Fiche-1/?b=2&a=1#ancre';
    const r = new Request(buildBoKnownRequest(raw));
    assert.equal(r.url, raw);
    assert.equal(r.uniqueKey, BO_KNOWN_UNIQUE_KEY_PREFIX + raw);
    assert.equal(r.userData.source, BO_KNOWN_SOURCE);
    assert.equal(r.userData.rawUrl, raw);
    assert.notEqual(new Request({ url: raw }).uniqueKey, raw, 'without the pin Crawlee normalises the identity');
});

test('9. seedBoKnown: regional, then extension, then exempt, then addRequest; rejections counted', async () => {
    const warn = mock.method(console, 'warn', () => {});
    const events: string[] = [];
    const added: Array<ReturnType<typeof buildBoKnownRequest>> = [];
    try {
        const r = await seedBoKnown(
            [
                'https://www.a.fr/en/fiche-1/',
                'https://www.a.fr/en/notice.pdf',
                'https://www.a.fr/notice.pdf',
                'https://www.a.fr/fiche-2/',
                'https://www.a.fr/rejet/',
                'https://www.a.fr/fiche-3?x=1#y',
            ],
            {
                async addRequest(req) {
                    events.push(`add:${req.url}`);
                    added.push(req);
                    if (req.url.includes('/rejet/')) throw new Error('queue refused');
                    return {};
                },
                isExcludedRegional: (u) => u.includes('/en/'),
                hasIgnoredExtension: (u) => u.endsWith('.pdf'),
                addExempt: (u) => {
                    events.push(`exempt:${u}`);
                },
            },
        );
        assert.deepEqual(r, { seeded: 2, skippedRegional: 2, skippedExt: 1, rejected: 1 });
        assert.deepEqual(events, [
            'exempt:https://www.a.fr/fiche-2/',
            'add:https://www.a.fr/fiche-2/',
            'exempt:https://www.a.fr/rejet/',
            'add:https://www.a.fr/rejet/',
            'exempt:https://www.a.fr/fiche-3?x=1#y',
            'add:https://www.a.fr/fiche-3?x=1#y',
        ]);
        assert.deepEqual(
            added,
            ['https://www.a.fr/fiche-2/', 'https://www.a.fr/rejet/', 'https://www.a.fr/fiche-3?x=1#y'].map(buildBoKnownRequest),
        );
        assert.equal(warn.mock.callCount(), 1, 'one warning for the rejected request');
    } finally {
        warn.mock.restore();
    }
});

test('10. seedBoKnown: without a nonHtml gate (addExempt absent) it still seeds', async () => {
    const added: Array<ReturnType<typeof buildBoKnownRequest>> = [];
    const r = await seedBoKnown(['https://www.a.fr/p/'], {
        addRequest: async (req) => {
            added.push(req);
        },
        isExcludedRegional: () => false,
        hasIgnoredExtension: () => false,
    });
    assert.deepEqual(r, { seeded: 1, skippedRegional: 0, skippedExt: 0, rejected: 0 });
    assert.deepEqual(added, [buildBoKnownRequest('https://www.a.fr/p/')]);
});

test('11. seedBoKnown: empty list => zero counters, no collaborator called', async () => {
    let calls = 0;
    const r = await seedBoKnown([], {
        addRequest: async () => {
            calls++;
        },
        isExcludedRegional: () => {
            calls++;
            return false;
        },
        hasIgnoredExtension: () => {
            calls++;
            return false;
        },
        addExempt: () => {
            calls++;
        },
    });
    assert.deepEqual(r, { seeded: 0, skippedRegional: 0, skippedExt: 0, rejected: 0 });
    assert.equal(calls, 0);
});

test('12. boKnownSeed.ts: imports node:fs only; no processUrl, check or increment call', () => {
    const code = blankAllComments(readSrc('boKnownSeed.ts'));
    const specifiers = [...code.matchAll(/^\s*import\b[^;]*?from\s*['"]([^'"]+)['"]/gm)].map((m) => m[1]);
    assert.deepEqual(specifiers, ['node:fs']);
    assert.doesNotMatch(code, /\bimport\s*\(/, 'no dynamic import');
    assert.doesNotMatch(code, /\brequire\s*\(/, 'no require');
    assert.doesNotMatch(code, /\bprocessUrl\s*\(/, 'the seed URL is never re-cleaned');
    assert.doesNotMatch(code, /\.check\s*\(/, 'no nonHtml check on a bo_known seed');
    assert.doesNotMatch(code, /\bincrement\s*\(/, 'counters are written by main.ts only');
});

test('13. main.ts: --knownUrlsFile option, Phase 1 after consolidate and before the two-phase seeding', () => {
    const src = readSrc('main.ts');
    const code = blankLineComments(src);
    assert.equal(count(code, "getArg('knownUrlsFile', 'npm_config_knownurlsfile')"), 1);
    assert.equal(count(code, 'let boKnownUrls: string[] = [];'), 1);
    assert.ok(at(code, 'let remainingUrls:') < at(code, 'let boKnownUrls: string[] = [];'));
    assert.equal(count(code, 'readKnownUrlsFile(knownUrlsFile)'), 1);
    assert.equal(count(code, 'consolidator.addBoKnown('), 1);
    const consolidate = at(code, 'await consolidator.consolidate(');
    const read = at(code, 'readKnownUrlsFile(knownUrlsFile)');
    const inject = at(code, 'consolidator.addBoKnown(');
    const twoPhase = at(src, '// --- TWO-PHASE SEEDING (Regional Path Exclusion) ---');
    assert.ok(consolidate < read && read < inject && inject < twoPhase, 'Phase 1 sits between consolidate() and the two-phase seeding');
    const region = code.slice(read, twoPhase);
    assert.doesNotMatch(region, NON_BO_KNOWN_INCREMENT, 'Phase 1 writes bo_known_* counters only');
    assert.doesNotMatch(region, /\bsAdd\s*\(/, 'Phase 1 goes through addBoKnown, never a direct sAdd');
    assert.match(region, /\bboKnownUrls\s*=\s*\w+\.injected\b/, 'the injected list is kept for Phase 2');
});

test('14. main.ts: Phase 2 bo_known block after the dataset loop, before phase2SeedingComplete', () => {
    const src = readSrc('main.ts');
    const code = blankLineComments(src);
    assert.equal(count(code, 'seedBoKnown('), 1);
    const start = at(code, 'const seedPhase2 = async () => {');
    const loop = code.indexOf('for (const { url, source } of remainingUrls) {', start);
    const finished = code.indexOf('[PHASE 2] Finished seeding', start);
    const call = at(code, 'seedBoKnown(');
    const extLog = code.indexOf('if (skippedExtCount > 0) {', start);
    const done = code.indexOf('context.phase2SeedingComplete = true;', start);
    assert.ok(loop !== -1 && finished !== -1 && extLog !== -1 && done !== -1, 'seedPhase2 anchors present');
    assert.ok(
        start < loop && loop < finished && finished < call && call < extLog && extLog < done,
        'bo_known seeding is its own block: after the dataset loop, before phase2SeedingComplete',
    );
    const region = code.slice(call, extLog);
    assert.doesNotMatch(region, /\bprocessUrl\s*\(/, 'raw URL: no queue-purge re-clean');
    assert.doesNotMatch(region, /\bstripActionAnchor\s*\(/, 'raw URL: no action-anchor strip');
    assert.doesNotMatch(region, /\.check\s*\(/, 'nonHtml exempted, never checked');
    assert.doesNotMatch(region, NON_BO_KNOWN_INCREMENT, 'Phase 2 bo_known writes bo_known_* counters only');
    assert.match(region, /\bboKnownUrls\b/);
    assert.match(region, /isExcludedRegionalPath\(/);
    assert.match(region, /\bhasIgnoredExtensionForSeed\b/);
    assert.match(region, /\.addExempt\b/);
});

test('15. main.ts: the four T03 counters are each written exactly once', () => {
    const code = blankLineComments(readSrc('main.ts'));
    for (const name of ['bo_known_injected', 'bo_known_ignored_dataset', 'bo_known_seeded', 'bo_known_seed_skipped']) {
        assert.equal(count(code, `increment("${name}"`), 1, name);
    }
    assert.equal(count(code, 'increment("bo_known_'), 4, 'main.ts writes exactly the four T03 bo_known_* counters');
});
