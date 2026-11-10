// A545 — hôtes exclus du crawl : isExcludedHost / normalizeExcludedHost / parseExcludedHosts.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isExcludedHost, normalizeExcludedHost, parseExcludedHosts } from '../excludedHosts.js';

const EXCL = ['collectivites.dpc.fr'];

test("exclu : l'hôte exact, un sous-domaine, un sous-sous-domaine", () => {
    assert.equal(isExcludedHost('collectivites.dpc.fr', EXCL), true);
    assert.equal(isExcludedHost('shop.collectivites.dpc.fr', EXCL), true);
    assert.equal(isExcludedHost('a.b.collectivites.dpc.fr', EXCL), true);
});

test('non exclu : même fin sans être un sous-domaine (jamais includes), et le parent', () => {
    assert.equal(isExcludedHost('xcollectivites.dpc.fr', EXCL), false);
    assert.equal(isExcludedHost('dpc.fr', EXCL), false);
    assert.equal(isExcludedHost('www.dpc.fr', EXCL), false);
    assert.equal(isExcludedHost('collectivites.dpc.fr.autre.com', EXCL), false);
});

test("liste vide ⇒ rien n'est exclu", () => {
    assert.equal(isExcludedHost('collectivites.dpc.fr', []), false);
    assert.equal(isExcludedHost('dpc.fr', []), false);
    assert.deepEqual(parseExcludedHosts(undefined), []);
    assert.deepEqual(parseExcludedHosts(''), []);
    assert.deepEqual(parseExcludedHosts(';; ;'), []);
});

test('www. : côté hôte crawlé comme côté liste', () => {
    assert.equal(isExcludedHost('www.collectivites.dpc.fr', EXCL), true);
    assert.equal(normalizeExcludedHost('www.collectivites.dpc.fr'), 'collectivites.dpc.fr');
    const list = parseExcludedHosts('www.collectivites.dpc.fr');
    assert.deepEqual(list, ['collectivites.dpc.fr']);
    assert.equal(isExcludedHost('collectivites.dpc.fr', list), true);
    assert.equal(isExcludedHost('dpc.fr', list), false);
});

test('majuscules : côté hôte crawlé comme côté liste', () => {
    assert.equal(isExcludedHost('WWW.Collectivites.DPC.fr', EXCL), true);
    assert.equal(normalizeExcludedHost('Collectivites.DPC.FR'), 'collectivites.dpc.fr');
    assert.equal(isExcludedHost('collectivites.dpc.fr', parseExcludedHosts('COLLECTIVITES.DPC.FR')), true);
});

test('choix 3a : schéma, chemin, espaces et point final retirés', () => {
    assert.equal(normalizeExcludedHost('https://collectivites.dpc.fr/'), 'collectivites.dpc.fr');
    assert.equal(normalizeExcludedHost('http://www.collectivites.dpc.fr/catalogue?x=1#y'), 'collectivites.dpc.fr');
    assert.equal(normalizeExcludedHost('collectivites.dpc.fr.'), 'collectivites.dpc.fr');
    assert.equal(normalizeExcludedHost('  collectivites.dpc.fr  '), 'collectivites.dpc.fr');
    // Hôte crawlé écrit avec le point final du DNS.
    assert.equal(isExcludedHost('collectivites.dpc.fr.', EXCL), true);
});

test('plusieurs entrées : séparées par « ; », nettoyées, dédoublonnées, ordre gardé', () => {
    assert.deepEqual(
        parseExcludedHosts('collectivites.dpc.fr;https://shop.dpc.fr/;www.collectivites.dpc.fr'),
        ['collectivites.dpc.fr', 'shop.dpc.fr'],
    );
});
