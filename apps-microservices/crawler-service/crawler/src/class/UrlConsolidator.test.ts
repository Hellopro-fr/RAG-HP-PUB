import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { RedisClientType } from 'redis';
import { UrlConsolidator } from './UrlConsolidator.js';

interface FakeRedisCalls {
    connect: number;
    disconnect: number;
    del: string[];
    sIsMember: Array<[string, string]>;
}

function makeFakeClient(
    overrides: Record<string, unknown> = {},
): { client: RedisClientType; calls: FakeRedisCalls } {
    const calls: FakeRedisCalls = { connect: 0, disconnect: 0, del: [], sIsMember: [] };
    const base = {
        isOpen: true,
        on: (_event: string, _fn: (...a: unknown[]) => void) => {},
        connect: async () => { calls.connect++; },
        disconnect: async () => { calls.disconnect++; },
        del: async (key: string) => { calls.del.push(key); return 1; },
        sIsMember: async (key: string, member: string) => {
            calls.sIsMember.push([key, member]);
            return true;
        },
        sAdd: async () => 1,
        sScan: async () => ({ cursor: 0, members: [] as string[] }),
        expire: async () => true,
    };
    const client = { ...base, ...overrides } as unknown as RedisClientType;
    return { client, calls };
}

test('injected client: connect/disconnect are no-ops (owner manages lifecycle)', async () => {
    const { client, calls } = makeFakeClient();
    const uc = new UrlConsolidator(client, 'job-1', 'prev-1', 'example.com');
    await uc.connect();
    await uc.disconnect();
    assert.equal(calls.connect, 0, 'connect() must not connect an injected client');
    assert.equal(calls.disconnect, 0, 'disconnect() must not disconnect an injected client');
});

test('injected client: cleanup dels rq+ru, KEEPS datasetKey, does NOT disconnect', async () => {
    const { client, calls } = makeFakeClient();
    const uc = new UrlConsolidator(client, 'job-2', 'prev-2', 'example.com');
    await uc.cleanup();
    assert.equal(calls.del.length, 2, 'cleanup() dels exactly two keys');
    assert.ok(calls.del.includes('update_rq:job-2'), 'cleanup() dels the request-queue key');
    assert.ok(calls.del.includes('update_ru:job-2'), 'cleanup() dels the request-url key');
    assert.ok(!calls.del.includes('update_dataset:job-2'), 'cleanup() must KEEP the dataset key (UpdateChecker needs it)');
    assert.equal(calls.disconnect, 0, 'cleanup() must not disconnect the shared client');
});

test('injected client: fullCleanup dels all three keys, does NOT disconnect', async () => {
    const { client, calls } = makeFakeClient();
    const uc = new UrlConsolidator(client, 'job-3', 'prev-3', 'example.com');
    await uc.fullCleanup();
    assert.equal(calls.del.length, 3, 'fullCleanup() dels three keys');
    assert.ok(calls.del.includes('update_dataset:job-3'), 'fullCleanup() dels the dataset key');
    assert.ok(calls.del.includes('update_rq:job-3'), 'fullCleanup() dels the request-queue key');
    assert.ok(calls.del.includes('update_ru:job-3'), 'fullCleanup() dels the request-url key');
    assert.equal(calls.disconnect, 0, 'fullCleanup() must not disconnect the shared client');
});

test('injected client: isInDataset delegates to sIsMember and returns its boolean', async () => {
    const { client, calls } = makeFakeClient();
    const uc = new UrlConsolidator(client, 'job-4', 'prev-4', 'example.com');
    const r = await uc.isInDataset('https://example.com/a');
    assert.equal(r, true);
    assert.deepEqual(calls.sIsMember, [['update_dataset:job-4', 'https://example.com/a']]);
});

test('error path: a rejecting sIsMember is swallowed and isInDataset returns false', async () => {
    const { client } = makeFakeClient({
        sIsMember: async () => {
            throw new Error('SocketClosedUnexpectedlyError: Socket closed unexpectedly');
        },
    });
    const uc = new UrlConsolidator(client, 'job-5', 'prev-5', 'example.com');
    const r = await uc.isInDataset('https://example.com/b');
    assert.equal(r, false, 'isInDataset must return false (not throw) when the socket is dead');
});

test('legacy URL path: constructs without throwing and without connecting', () => {
    // createClient is lazy — the constructor must not open a socket.
    const uc = new UrlConsolidator('redis://localhost:6379', 'job-6', 'prev-6', 'example.com');
    assert.equal(typeof uc.isInDataset, 'function');
});
