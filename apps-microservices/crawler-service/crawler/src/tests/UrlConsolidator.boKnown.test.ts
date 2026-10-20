// A312 — Phase 1 « bo_known » : identité dataset partagée + SET Redis update_bo_known:<crawlId>.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { RedisClientType } from 'redis';
import { UrlConsolidator } from '../class/UrlConsolidator.js';
import { matchDatasetIdentity } from '../class/datasetIdentity.js';

const DATASET_KEY = 'update_dataset:job-b';
const BO_KEY = 'update_bo_known:job-b';

interface FakeCalls {
    sAdd: Array<[string, string[]]>;
    del: string[];
    expire: string[];
}

function makeClient(
    datasetMembers: string[],
    overrides: Record<string, unknown> = {},
): { client: RedisClientType; calls: FakeCalls } {
    const calls: FakeCalls = { sAdd: [], del: [], expire: [] };
    const dataset = new Set(datasetMembers);
    const base = {
        isOpen: true,
        on: (_event: string, _fn: (...a: unknown[]) => void) => {},
        connect: async () => {},
        disconnect: async () => {},
        del: async (key: string) => { calls.del.push(key); return 1; },
        sIsMember: async (key: string, member: string) => key === DATASET_KEY && dataset.has(member),
        sAdd: async (key: string, members: string[]) => {
            calls.sAdd.push([key, [...members]]);
            return members.length;
        },
        sScan: async () => ({ cursor: 0, members: [] as string[] }),
        expire: async (key: string, _seconds: number) => { calls.expire.push(key); return true; },
    };
    const client = { ...base, ...overrides } as unknown as RedisClientType;
    return { client, calls };
}

function makeProbe(members: string[]): { probe: (u: string) => Promise<boolean>; seen: string[] } {
    const set = new Set(members);
    const seen: string[] = [];
    return { probe: async (u: string) => { seen.push(u); return set.has(u); }, seen };
}

async function silenced<T>(fn: () => Promise<T>): Promise<T> {
    const original = console.error;
    console.error = () => {};
    try {
        return await fn();
    } finally {
        console.error = original;
    }
}

test('A matchDatasetIdentity: exact match stops after one probe', async () => {
    const { probe, seen } = makeProbe(['https://e.fr/x']);
    assert.equal(await matchDatasetIdentity('https://e.fr/x', probe), 'exact');
    assert.deepEqual(seen, ['https://e.fr/x']);
});

test('B matchDatasetIdentity: folded match in both trailing-slash directions', async () => {
    const stored = makeProbe(['https://e.fr/p']);
    assert.equal(await matchDatasetIdentity('https://e.fr/p/', stored.probe), 'folded');
    const storedSlash = makeProbe(['https://e.fr/q/']);
    assert.equal(await matchDatasetIdentity('https://e.fr/q', storedSlash.probe), 'folded');
});

test('C matchDatasetIdentity: none probes the URL then its alternate, in that order', async () => {
    const { probe, seen } = makeProbe([]);
    assert.equal(await matchDatasetIdentity('https://e.fr/z', probe), 'none');
    assert.deepEqual(seen, ['https://e.fr/z', 'https://e.fr/z/']);
});

test('E addBoKnown: dedups the input, drops exact and folded dataset members, writes only the rest', async () => {
    const { client, calls } = makeClient(['https://e.fr/exact', 'https://e.fr/fold']);
    const uc = new UrlConsolidator(client, 'job-b', 'prev-b', 'e.fr');
    const r = await uc.addBoKnown([
        'https://e.fr/new1',
        'https://e.fr/exact',
        'https://e.fr/new1',
        'https://e.fr/fold/',
        'https://e.fr/new2',
    ]);
    assert.deepEqual(r, { injected: ['https://e.fr/new1', 'https://e.fr/new2'], ignoredDataset: 2, failed: false });
    assert.deepEqual(calls.sAdd, [[BO_KEY, ['https://e.fr/new1', 'https://e.fr/new2']]]);
    assert.ok(!calls.sAdd.some(([key]) => key === DATASET_KEY), 'addBoKnown must never write the dataset SET');
});

test('F addBoKnown: writes by chunks of 1000 on the bo_known key only', async () => {
    const { client, calls } = makeClient([]);
    const uc = new UrlConsolidator(client, 'job-b', 'prev-b', 'e.fr');
    const urls = Array.from({ length: 2500 }, (_v, i) => `https://e.fr/p${i}`);
    const r = await uc.addBoKnown(urls);
    assert.deepEqual(calls.sAdd.map(([key, members]) => [key, members.length]), [[BO_KEY, 1000], [BO_KEY, 1000], [BO_KEY, 500]]);
    assert.equal(r.injected.length, 2500);
    assert.equal(r.ignoredDataset, 0);
    assert.equal(r.failed, false);
});

test('G addBoKnown: a rejecting sAdd gives failed=true, injected=[], and keeps the ignored count', async () => {
    const { client } = makeClient(['https://e.fr/exact'], {
        sAdd: async () => { throw new Error('SocketClosedUnexpectedlyError: Socket closed unexpectedly'); },
    });
    const uc = new UrlConsolidator(client, 'job-b', 'prev-b', 'e.fr');
    const r = await silenced(() => uc.addBoKnown(['https://e.fr/exact', 'https://e.fr/new1']));
    assert.deepEqual(r, { injected: [], ignoredDataset: 1, failed: true });
});

test('H addBoKnown: a dead dataset probe fails OPEN (isInDataset swallows it), URLs become candidates', async () => {
    const { client, calls } = makeClient([], {
        sIsMember: async () => { throw new Error('Socket closed unexpectedly'); },
    });
    const uc = new UrlConsolidator(client, 'job-b', 'prev-b', 'e.fr');
    const r = await silenced(() => uc.addBoKnown(['https://e.fr/a']));
    assert.deepEqual(r, { injected: ['https://e.fr/a'], ignoredDataset: 0, failed: false });
    assert.deepEqual(calls.sAdd, [[BO_KEY, ['https://e.fr/a']]]);
});

test('I addBoKnown: sets the TTL of the bo_known key even when ensureTtl() already ran', async () => {
    const { client, calls } = makeClient([]);
    const uc = new UrlConsolidator(client, 'job-b', 'prev-b', 'e.fr');
    await (uc as unknown as { ensureTtl(): Promise<void> }).ensureTtl();
    calls.expire.length = 0;
    await uc.addBoKnown(['https://e.fr/t']);
    assert.ok(calls.expire.includes(BO_KEY), 'the bo_known key must get its TTL after addBoKnown');
});

test('J fullCleanup: dels four keys, the bo_known key included', async () => {
    const { client, calls } = makeClient([]);
    const uc = new UrlConsolidator(client, 'job-b', 'prev-b', 'e.fr');
    await uc.fullCleanup();
    assert.equal(calls.del.length, 4);
    assert.ok(calls.del.includes(BO_KEY), 'fullCleanup() dels the bo_known key');
});

test('K cleanup: leaves the bo_known key alone', async () => {
    const { client, calls } = makeClient([]);
    const uc = new UrlConsolidator(client, 'job-b', 'prev-b', 'e.fr');
    await uc.cleanup();
    assert.ok(!calls.del.includes(BO_KEY), 'cleanup() must not del the bo_known key');
});
