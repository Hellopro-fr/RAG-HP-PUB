// A312 Final Review I2 — clé de claim PushedSet par classe : une copie native découverte et la copie
// bo_known de la même URL émettent chacune leur verdict ; la déduplication des relances reste par classe.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { UpdateChecker } from '../class/UpdateChecker.js';
import { PushedSet } from '../class/PushedSet.js';
import { BO_KNOWN_UNIQUE_KEY_PREFIX } from '../boKnownSeed.js';

function makeMockRedisClient() {
    const seen = new Set<string>();
    const added: string[] = [];
    return {
        isOpen: true,
        async sAdd(_key: string, member: string) {
            added.push(member);
            if (seen.has(member)) return 0;
            seen.add(member);
            return 1;
        },
        async sRem(_key: string, member: string) { seen.delete(member); return 1; },
        async expire(_key: string, _ttl: number) { return 1; },
        async del(_key: string) { return 1; },
        _added: added,
    };
}

// UN seul PushedSet partagé par les deux classes de requêtes, comme en production (main.ts).
function makeChecker() {
    const redis = makeMockRedisClient();
    const pushedSet = new PushedSet(redis as any, 'crawl-update');
    const stats = { calls: [] as string[], async increment(c: string) { this.calls.push(c); } };
    const writer = { calls: [] as Array<[string, any]>, async writeLine(f: string, d: any) { this.calls.push([f, d]); } };
    const consolidator = { async isInDataset(_u: string) { return false; }, async cleanup() {} };
    const checker = new UpdateChecker(consolidator as any, stats as any, writer as any, pushedSet);
    return { checker, redis, stats };
}

const U = 'https://www.e.fr/produits/cuve-a.html';

test('I2 (a) : native d\'abord, puis bo_known sur la même URL : deux verdicts, aucun already_pushed', async () => {
    const { checker, stats } = makeChecker();
    const native = await checker.checkUrl(U, U, 'discovered', 200, true);
    const boKnown = await checker.checkUrl(U, U, 'bo_known', 404, false);
    assert.notEqual(native.reason, 'already_pushed');
    assert.notEqual(boKnown.reason, 'already_pushed', 'la copie bo_known doit émettre son verdict');
    assert.equal(boKnown.action, 'deleted');
    assert.equal(boKnown.url, U);
    assert.ok(stats.calls.includes('bo_known_deleted'), `compteurs : ${stats.calls.join(' ')}`);
});

test('I2 (b) : bo_known d\'abord, puis native sur la même URL : deux verdicts, clés de claim distinctes', async () => {
    const { checker, redis, stats } = makeChecker();
    const boKnown = await checker.checkUrl(U, U, 'bo_known', 200, true);
    const native = await checker.checkUrl(U, U, 'discovered', 200, true);
    assert.equal(boKnown.action, 'confirmed');
    assert.notEqual(native.reason, 'already_pushed', 'la copie native doit émettre son verdict');
    assert.equal(native.action, 'new_url');
    assert.deepEqual(redis._added, [BO_KNOWN_UNIQUE_KEY_PREFIX + U, U]);
    assert.ok(stats.calls.includes('bo_known_alive'), `compteurs : ${stats.calls.join(' ')}`);
});

test('I2 (c) : après une copie native, la 1re vérification bo_known émet, la 2e est already_pushed (dédup par classe)', async () => {
    const { checker, stats } = makeChecker();
    await checker.checkUrl(U, U, 'discovered', 200, true);
    const first = await checker.checkUrl(U, U, 'bo_known', 404, false);
    const second = await checker.checkUrl(U, U, 'bo_known', 404, false);
    assert.equal(first.action, 'deleted');
    assert.equal(second.action, 'ignored');
    assert.equal(second.reason, 'already_pushed');
    assert.equal(second.url, U, 'url brute dans le résultat already_pushed');
    assert.equal(stats.calls.filter((c) => c === 'bo_known_deleted').length, 1);
});
