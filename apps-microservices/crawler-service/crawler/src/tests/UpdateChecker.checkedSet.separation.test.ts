import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PushedSet } from '../class/PushedSet.js';
import { UpdateChecker } from '../class/UpdateChecker.js';

// Mock Redis SENSIBLE À LA CLÉ : l'appartenance est suivie par couple (key, member),
// de sorte que deux PushedSet de clés DIFFÉRENTES ne collisionnent pas sur le même
// client — fidèle au vrai Redis. Enregistre aussi chaque clé passée à sAdd.
function makeKeyAwareRedis() {
    const members = new Set<string>();
    const sAddKeys: string[] = [];
    const slot = (key: string, member: string) => `${key} ${member}`;
    return {
        isOpen: true,
        _sAddKeys: sAddKeys,
        async sAdd(key: string, member: string) {
            sAddKeys.push(key);
            const s = slot(key, member);
            if (members.has(s)) return 0;
            members.add(s);
            return 1;
        },
        async sRem(key: string, member: string) { members.delete(slot(key, member)); return 1; },
        async expire(_key: string, _ttl: number) { return 1; },
        async del(_key: string) { return 1; },
    };
}

function makeMockConsolidator() {
    return { async isInDataset(_url: string) { return false; }, async cleanup() {} };
}
function makeMockStatsManager() {
    const calls: string[] = [];
    return { async increment(c: string) { calls.push(c); }, _calls: calls };
}
function makeMockJsonlWriter() {
    const calls: Array<[string, unknown]> = [];
    return { async writeLine(f: string, d: unknown) { calls.push([f, d]); }, _calls: calls };
}

// TEST 1 (RÉGRESSION — cœur du fix) : avec un set dédié `checked:{id}` pour checkUrl
// et le set `pushed:{id}` pour les écritures dataset, le claim de checkUrl ne doit PAS
// affamer la réclamation d'écriture dataset suivante pour la même URL.
test('checkUrl on the checked set does not starve the pushed set (regression)', async () => {
    const redis = makeKeyAwareRedis();
    const pushedSet = new PushedSet(redis as any, 'id');                              // clé pushed:id
    const checkedSet = new PushedSet(redis as any, 'id', { keyPrefix: 'checked' });   // clé checked:id
    const checker = new UpdateChecker(
        makeMockConsolidator() as any,
        makeMockStatsManager() as any,
        makeMockJsonlWriter() as any,
        checkedSet,
    );

    const url = 'https://example.com/produit/rampe-lite/';

    // source='dataset' + isFrenchContent=true → la branche la plus simple (action 'confirmed',
    // sans écriture JSONL ni incrément de stats) : le seul effet observable de checkUrl est le
    // claim sur checked:id. La preuve de non-affamement tient quelle que soit la branche prise.
    const r = await checker.checkUrl(url, url, 'dataset', 200, true);
    assert.equal(r.action, 'confirmed', 'a still-eligible dataset URL must be confirmed');

    // La garde d'écriture dataset s'exécute ensuite sur pushed:id — elle doit GAGNER
    // le claim (l'URL n'a jamais été réclamée sur pushed:id) → pushData s'exécuterait.
    const canPush = await pushedSet.tryClaim(url);
    assert.equal(canPush, true, 'pushData must not be starved by checkUrl (separate keys)');
});

// TEST 2 (keyPrefix — rétro-compat + nouvelle option).
test('PushedSet key uses default "pushed" prefix and honors keyPrefix override', async () => {
    const redis = makeKeyAwareRedis();
    const def = new PushedSet(redis as any, 'X');                                // clé attendue pushed:X
    const checked = new PushedSet(redis as any, 'X', { keyPrefix: 'checked' });  // clé attendue checked:X

    await def.tryClaim('u1');
    await checked.tryClaim('u1');

    assert.deepEqual(
        redis._sAddKeys,
        ['pushed:X', 'checked:X'],
        'default prefix must remain "pushed"; keyPrefix must namespace to "checked"',
    );
});

// TEST 3 (NON-RÉGRESSION — dédup d'écriture dataset préservée sur le set pushed).
test('pushed set still dedups the same URL across retries (no duplicate dataset row)', async () => {
    const redis = makeKeyAwareRedis();
    const pushedSet = new PushedSet(redis as any, 'id');
    const url = 'https://example.com/a';

    assert.equal(await pushedSet.tryClaim(url), true, 'first claim wins → push allowed');
    assert.equal(await pushedSet.tryClaim(url), false, 'second claim loses → push skipped (dedup preserved)');
});
