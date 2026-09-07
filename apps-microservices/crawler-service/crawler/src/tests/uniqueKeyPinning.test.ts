import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Request } from '@crawlee/core';

// POURQUOI ce test existe : le correctif de main.ts:1606 repose entièrement sur le fait
// que le uniqueKey PAR DÉFAUT de Crawlee diffère de l'URL brute (il retire le / final),
// alors que routes.ts:1277 épingle les liens découverts sur l'URL brute. Si une montée de
// version de Crawlee changeait cette normalisation, la prémisse tomberait — et ce test le
// dirait, au lieu de laisser le correctif devenir un no-op silencieux.
test('Crawlee default uniqueKey drops the trailing slash — the premise of the Phase-2 pin', () => {
    const url = 'https://www.example.fr/services/';
    assert.notEqual(
        new Request({ url }).uniqueKey,
        url,
        'si cette assertion casse, Crawlee ne normalise plus : relire main.ts:1606',
    );
    assert.equal(new Request({ url }).uniqueKey, 'https://www.example.fr/services');
});

test('pinning uniqueKey reproduces the raw URL, matching routes.ts:1277', () => {
    const url = 'https://www.example.fr/services/';
    assert.equal(new Request({ url, uniqueKey: url }).uniqueKey, url);
});

test('a URL with no trailing slash is unaffected either way', () => {
    const url = 'https://www.example.fr/services';
    assert.equal(new Request({ url }).uniqueKey, url);
    assert.equal(new Request({ url, uniqueKey: url }).uniqueKey, url);
});
