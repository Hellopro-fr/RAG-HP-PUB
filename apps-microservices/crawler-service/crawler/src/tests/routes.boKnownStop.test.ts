// A312 Final Review I1 (D7, décision user « tout couper ») — après le verdict `updateChecker.checkUrl`
// d'une requête bo_known, le handler s'arrête, dans la branche française comme dans la non française.
// Assertions sur le texte source : routes.ts (handler Crawlee) n'est pas exécutable par le runner —
// même méthode que routes.boKnown.test.ts.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const raw = fs.readFileSync(path.join(import.meta.dirname, '..', 'routes.ts'), 'utf-8');
// Commentaires pleine ligne blanchis à longueur égale : un commentaire qui cite un littéral
// ne peut ni satisfaire ni casser une position.
const src = raw.replace(/^[ \t]*\/\/.*$/gm, (m) => ' '.repeat(m.length));

const CALL = 'await context.updateChecker.checkUrl(';
const GUARD = /if \(source === BO_KNOWN_SOURCE\) \{\s*return;\s*\}/g;

// Fin de l'appel `checkUrl` (update mode) dont les arguments portent `argMarker`.
function verdictEnd(argMarker: string): number {
    const hits: number[] = [];
    for (let i = src.indexOf(CALL); i !== -1; i = src.indexOf(CALL, i + 1)) {
        const end = src.indexOf(');', i);
        if (src.slice(i, end).includes(argMarker)) hits.push(end);
    }
    assert.equal(hits.length, 1, `exactly one update-mode checkUrl call carrying "${argMarker}"`);
    return hits[0];
}

function assertGuardBefore(argMarker: string, sideEffects: string[]) {
    const after = verdictEnd(argMarker);
    const positions = sideEffects.map((s) => {
        const p = src.indexOf(s, after);
        assert.notEqual(p, -1, `side effect "${s}" must still follow the verdict`);
        return p;
    });
    const firstSideEffect = Math.min(...positions);
    GUARD.lastIndex = after;
    const g = GUARD.exec(src);
    assert.ok(g, 'a bo_known early return must follow the verdict');
    assert.ok(
        g.index < firstSideEffect,
        `the bo_known early return (at ${g.index}) must precede the first side effect (at ${firstSideEffect})`,
    );
}

test('I1 French branch: bo_known returns after its verdict, before facets, routerDefaultHandler and enqueueLinks', () => {
    assertGuardBefore('true // Page is French', [
        'const facetUrl =',
        'await routerDefaultHandler(',
        'await enqueueLinks({',
    ]);
});

test('I1 non-French branch: bo_known returns after its verdict, before the nfr- dataset and its tryClaim(url)', () => {
    assertGuardBefore('false // NOT French', [
        'Dataset.open("nfr-"',
        'context.pushedSet.tryClaim(url)',
    ]);
});

test('I1: exactly two bo_known early returns in routes.ts (one per update-mode verdict)', () => {
    assert.equal(src.match(GUARD)?.length ?? 0, 2);
});
