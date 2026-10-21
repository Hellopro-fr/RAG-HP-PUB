// A312 T05 — garde `processed`, `isExisting` et métriques `bo_known_*` du rapport.
// Assertions sur le texte source : routes.ts (handler Crawlee) n'est pas exécutable par le runner, et
// generateUpdateReport lit un contexte global — même méthode que nonHtmlPrefixWiring.test.ts.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const raw = (f: string) => fs.readFileSync(path.join(import.meta.dirname, '..', f), 'utf-8');
// Commentaires pleine ligne blanchis à longueur égale : un commentaire qui cite un littéral
// ne peut ni satisfaire ni casser un compte.
const code = (f: string) => raw(f).replace(/^[ \t]*\/\/.*$/gm, (m) => ' '.repeat(m.length));
const count = (s: string, needle: string) => s.split(needle).length - 1;

// [nom du compteur, variable locale de generateUpdateReport]
const BO_KNOWN_COUNTERS: Array<[string, string]> = [
    ['bo_known_injected', 'boKnownInjected'],
    ['bo_known_ignored_dataset', 'boKnownIgnoredDataset'],
    ['bo_known_seeded', 'boKnownSeeded'],
    ['bo_known_seed_skipped', 'boKnownSeedSkipped'],
    ['bo_known_deleted', 'boKnownDeleted'],
    ['bo_known_redirected', 'boKnownRedirected'],
    ['bo_known_alive', 'boKnownAlive'],
    ['bo_known_errors', 'boKnownErrors'],
];

// Même découpe que statNameParity.test.ts : `report` jusqu'au premier `};`, `metrics` jusqu'au premier `}`.
function metricsOf(functions: string): string {
    const start = functions.indexOf('const report = {');
    assert.notEqual(start, -1, 'generateUpdateReport must build a `report` object literal');
    const report = functions.slice(start, functions.indexOf('};', start));
    const m = report.indexOf('metrics: {');
    assert.notEqual(m, -1, 'report.metrics not found');
    return report.slice(m, report.indexOf('}', m));
}

test('routes.ts imports BO_KNOWN_SOURCE from ./boKnownSeed.js, once', () => {
    assert.equal(count(code('routes.ts'), 'import { BO_KNOWN_SOURCE } from "./boKnownSeed.js";'), 1);
});

test('routes.ts: increment("processed") exists once, under the bo_known guard, before the breaker reads', () => {
    const src = code('routes.ts');
    assert.equal(count(src, 'increment("processed")'), 1, 'the literal must stay in exactly one copy');
    const guarded =
        /if \(request\.userData\.source !== BO_KNOWN_SOURCE\) \{\s*await context\.statsManager\.increment\("processed"\);\s*\}/g;
    assert.equal(src.match(guarded)?.length ?? 0, 1, 'the single increment must sit inside the bo_known guard');
    const breaker = src.indexOf('const cb = context.config.circuitBreaker;');
    assert.notEqual(breaker, -1, 'the circuit breaker block must still exist');
    assert.ok(src.search(guarded) < breaker, 'the guarded increment must precede the breaker reads');
});

test('routes.ts: isExisting covers dataset and bo_known, in one declaration', () => {
    const src = code('routes.ts');
    const line =
        "const isExisting = request.userData.is_existing || (source === 'dataset') || (source === BO_KNOWN_SOURCE);";
    assert.equal(count(src, line), 1);
    assert.equal(count(src, 'const isExisting ='), 1);
});

test('routes.ts writes and reads no bo_known_ counter (T03/T04 write them, the breaker never reads them)', () => {
    assert.doesNotMatch(code('routes.ts'), /(increment|getValue)\(\s*["']bo_known_/);
});

test('functions.ts: generateUpdateReport reads the 8 bo_known_* counters from the counter itself', () => {
    const src = code('functions.ts');
    for (const [name, variable] of BO_KNOWN_COUNTERS) {
        assert.match(
            src,
            new RegExp(`const\\s+${variable}\\s*=\\s*await[^;]*getValue\\("${name}"\\)`),
            `${variable} must be bound to getValue("${name}")`,
        );
    }
});

test('functions.ts: report.metrics carries the 8 bo_known_* keys, between not_eligible and previous_total', () => {
    const metrics = metricsOf(code('functions.ts'));
    for (const [name, variable] of BO_KNOWN_COUNTERS) {
        assert.match(metrics, new RegExp(`\\b${name}:\\s*${variable}\\b`), `metrics.${name}`);
    }
    assert.equal(count(metrics, 'bo_known_'), 8, 'exactly the 8 contract keys, no extra bo_known_ key');
    assert.ok(metrics.indexOf('not_eligible:') < metrics.indexOf('bo_known_injected:'), 'after not_eligible');
    assert.ok(metrics.indexOf('bo_known_errors:') < metrics.indexOf('previous_total:'), 'before previous_total');
});

test('the 8 bo_known_* names are spelled in the files that write them (T03, T04)', () => {
    const writers = ['main.ts', 'boKnownSeed.ts', 'class/UpdateChecker.ts', 'class/UrlConsolidator.ts']
        .map((f) => code(f))
        .join('\n');
    for (const [name] of BO_KNOWN_COUNTERS) {
        assert.ok(
            writers.includes(`"${name}"`) || writers.includes(`'${name}'`),
            `no writer file spells "${name}" — a name mismatch publishes a counter nobody increments`,
        );
    }
});
