import { test } from 'node:test';
import assert from 'node:assert/strict';
import { UpdateChecker } from '../class/UpdateChecker.js';

// Consolidateur simulé : le dataset est un Set explicite, et chaque appel est compté.
// Le compteur sert la 4e assertion — prouver que source='dataset' court-circuite.
function makeConsolidator(urls: string[]) {
    const set = new Set(urls);
    const calls: string[] = [];
    return {
        _calls: calls,
        async isInDataset(url: string) { calls.push(url); return set.has(url); },
        async cleanup() {},
    };
}
function makeStats() {
    const calls: string[] = [];
    return { async increment(c: string) { calls.push(c); }, _calls: calls };
}
function makeWriter() {
    const calls: Array<[string, unknown]> = [];
    return { async writeLine(f: string, d: unknown) { calls.push([f, d]); }, _calls: calls };
}
// PushedSet absent : checkUrl ne réclame rien, on isole la seule décision de provenance.
function makeChecker(consolidator: unknown, stats: unknown, writer: unknown) {
    return new UpdateChecker(consolidator as any, stats as any, writer as any, undefined as any);
}

// TEST 1 — le cœur du correctif. La copie DÉCOUVERTE gagne la course de 65 ms
// (enqueueLinks à 16:00:51.018 contre [PHASE 2] à 16:00:51.083, mesuré sur atox.fr),
// donc la requête survivante porte source='discovered'. Elle doit malgré tout compter.
test('a dataset URL arriving as discovered still credits accounted exactly once', async () => {
    const url = 'https://www.example.fr/services/';
    const consolidator = makeConsolidator([url]);
    const stats = makeStats();
    const checker = makeChecker(consolidator, stats, makeWriter());

    const r = await checker.checkUrl(url, url, 'discovered', 200, true);

    assert.equal(r.action, 'confirmed');
    assert.deepEqual(stats._calls, ['accounted']);
});

// TEST 2 — repli sur le / final, DANS LES DEUX SENS. L'URL stockée vient du dataset
// précédent, l'URL présentée vient du lien tel qu'écrit dans la page : rien ne garantit
// la même orthographe.
test('the trailing-slash fold works both ways', async () => {
    const stored = 'https://www.example.fr/produits';
    const c1 = makeConsolidator([stored]);
    const s1 = makeStats();
    const r1 = await makeChecker(c1, s1, makeWriter())
        .checkUrl(stored + '/', stored + '/', 'discovered', 200, true);
    assert.equal(r1.action, 'confirmed', 'stocké sans /, présenté avec /');
    assert.deepEqual(s1._calls, ['accounted']);

    const c2 = makeConsolidator([stored + '/']);
    const s2 = makeStats();
    const r2 = await makeChecker(c2, s2, makeWriter())
        .checkUrl(stored, stored, 'discovered', 200, true);
    assert.equal(r2.action, 'confirmed', 'stocké avec /, présenté sans /');
    assert.deepEqual(s2._calls, ['accounted']);
});

// TEST 3 — la garde contre un correctif trop gourmand. Une URL réellement neuve doit
// rester neuve : si celle-ci passait 'confirmed', le correctif aurait supprimé la
// détection des nouvelles pages au lieu de réparer un compteur.
test('a genuinely unknown URL stays new and never credits accounted', async () => {
    const consolidator = makeConsolidator(['https://www.example.fr/connue/']);
    const stats = makeStats();
    const writer = makeWriter();
    const r = await makeChecker(consolidator, stats, writer)
        .checkUrl('https://www.example.fr/toute-neuve/', 'https://www.example.fr/toute-neuve/',
                  'discovered', 200, true);

    assert.equal(r.action, 'new_url');
    assert.deepEqual(stats._calls, ['new_urls']);
    assert.ok(!stats._calls.includes('accounted'));
});

// TEST 4 — court-circuit. Quand la provenance est déjà connue, on n'ajoute aucun
// aller-retour Redis : le || de JavaScript n'évalue pas sa droite si la gauche est vraie,
// et ce test empêche qu'un refactor le perde.
test('source=dataset short-circuits: the consolidator is never consulted', async () => {
    const url = 'https://www.example.fr/services/';
    const consolidator = makeConsolidator([url]);
    const stats = makeStats();
    const r = await makeChecker(consolidator, stats, makeWriter())
        .checkUrl(url, url, 'dataset', 200, true);

    assert.equal(r.action, 'confirmed');
    assert.deepEqual(stats._calls, ['accounted']);
    assert.deepEqual(consolidator._calls, [], 'aucun appel Redis ajouté sur ce chemin');
});

// TEST 5 — Correction IMPORTANT de la revue finale de branche. Le dataset contient /a ; une
// page lie /a/, qui n'a JAMAIS été au dataset ; un serveur à routage strict rend 404 sur /a/
// pendant que /a est vivant. Un appariement REPLIÉ ne peut pas fonder un verdict de
// suppression : il doit retomber sur la branche non-dataset, à l'identique d'avant ce lot.
test('a folded match on a 404 is ignored — no deleted, no errors, no accounted', async () => {
    const stored = 'https://www.example.fr/a';
    const consolidator = makeConsolidator([stored]);
    const stats = makeStats();
    const writer = makeWriter();
    const r = await makeChecker(consolidator, stats, writer)
        .checkUrl(stored + '/', stored + '/', 'discovered', 404, true);

    assert.equal(r.action, 'ignored');
    assert.equal(r.reason, 'non_dataset_error');
    assert.deepEqual(writer._calls, [], 'aucun evenement deleted ecrit');
    assert.deepEqual(stats._calls, [], 'ni errors, ni errors_unprocessed, ni accounted');
});

// TEST 6 — même geste, mais l'appariement est EXACT : le comportement CASE 1 pré-existant
// (deleted + errors + errors_unprocessed + accounted) reste inchangé.
test('an exact match on a 404 still deletes and accounts, unchanged', async () => {
    const url = 'https://www.example.fr/a';
    const consolidator = makeConsolidator([url]);
    const stats = makeStats();
    const writer = makeWriter();
    const r = await makeChecker(consolidator, stats, writer)
        .checkUrl(url, url, 'discovered', 404, true);

    assert.equal(r.action, 'deleted');
    assert.equal(r.reason, 'http_error_404');
    assert.deepEqual(stats._calls, ['errors', 'errors_unprocessed', 'accounted']);
    assert.equal(writer._calls.length, 1);
    assert.equal(writer._calls[0][0], UpdateChecker.DELETED_FILE);
});

// TEST 7 — CASE 3 garde le repli : un 200 éligible sur la variante repliée reste confirmed,
// à la différence de CASE 1. C'est l'asymétrie que ce correctif introduit délibérément.
test('a folded match on an eligible 200 stays confirmed — CASE 3 keeps the fold', async () => {
    const stored = 'https://www.example.fr/a';
    const consolidator = makeConsolidator([stored]);
    const stats = makeStats();
    const r = await makeChecker(consolidator, stats, makeWriter())
        .checkUrl(stored + '/', stored + '/', 'discovered', 200, true);

    assert.equal(r.action, 'confirmed');
    assert.deepEqual(stats._calls, ['accounted']);
});
