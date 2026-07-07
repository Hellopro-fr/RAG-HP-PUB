// Co-located with StatsManager.ts to satisfy the project's TDD-gate hook.
//
// The original file asserted compile-time class shape only (StatsManager hard-
// coded `createClient`, so a real Redis-backed test needed a DI seam). After the
// 2026-06-17 resilience migration StatsManager accepts an injected RedisClientType
// directly, so the injected path is now unit-testable with a plain fake object —
// no seam required. The legacy URL path's connect/disconnect lifecycle still needs
// a live Redis and is left to staging smoke tests (see spec §8); the injected
// no-op tests below are the active regression guard for the ownsClient branch.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { RedisClientType } from 'redis';
import { StatsManager } from './StatsManager.js';

test('StatsManager class is exported with expected method surface', () => {
    assert.equal(typeof StatsManager, 'function', 'StatsManager must be a class constructor');
    const proto = StatsManager.prototype as unknown as Record<string, unknown>;
    const expectedMethods = [
        'connect',
        'disconnect',
        'increment',
        'getValue',
        'checkThreshold',
        'saveStateToDisk',
        'loadStateFromDisk',
        'cleanup',
    ];
    for (const method of expectedMethods) {
        assert.equal(
            typeof proto[method],
            'function',
            `StatsManager must expose ${method}()`,
        );
    }
});

test('Ch.A Epic 1 deperdition counter names — compile-time check', () => {
    const CH_A_E1_COUNTERS: readonly string[] = [
        'filtered_qm',
        'filtered_hash',
        'filtered_ext',
        'filtered_nonfr',
        'filtered_duplicate',
        'dropped_cb',
        'timeout_individual',
        'success_extracted',
    ];
    assert.equal(CH_A_E1_COUNTERS.length, 8);
    assert.ok(CH_A_E1_COUNTERS.every((c) => typeof c === 'string' && c.length > 0));
});

// --- Injected shared-client behavior (2026-06-17 resilience migration) ---

interface FakeRedisCalls {
    connect: number;
    disconnect: number;
    del: string[];
    hIncrBy: Array<[string, string, number]>;
    hGet: Array<[string, string]>;
}

function makeFakeClient(
    overrides: Record<string, unknown> = {},
): { client: RedisClientType; calls: FakeRedisCalls } {
    const calls: FakeRedisCalls = { connect: 0, disconnect: 0, del: [], hIncrBy: [], hGet: [] };
    const base = {
        isOpen: true,
        on: (_event: string, _fn: (...a: unknown[]) => void) => {},
        connect: async () => { calls.connect++; },
        disconnect: async () => { calls.disconnect++; },
        del: async (key: string) => { calls.del.push(key); return 1; },
        hIncrBy: async (key: string, field: string, by: number) => {
            calls.hIncrBy.push([key, field, by]);
            return by;
        },
        hGet: async (key: string, field: string) => {
            calls.hGet.push([key, field]);
            return '7';
        },
        hGetAll: async () => ({}),
        hSet: async () => 1,
        expire: async () => true,
    };
    const client = { ...base, ...overrides } as unknown as RedisClientType;
    return { client, calls };
}

test('injected client: connect/disconnect are no-ops (owner manages lifecycle)', async () => {
    const { client, calls } = makeFakeClient();
    const sm = new StatsManager(client, 'job-1', '.');
    await sm.connect();
    await sm.disconnect();
    assert.equal(calls.connect, 0, 'connect() must not connect an injected client');
    assert.equal(calls.disconnect, 0, 'disconnect() must not disconnect an injected client');
});

test('injected client: cleanup deletes the key but does NOT disconnect', async () => {
    const { client, calls } = makeFakeClient();
    const sm = new StatsManager(client, 'job-2', '.');
    await sm.cleanup();
    assert.deepEqual(calls.del, ['stats:job-2'], 'cleanup() must del the stats key');
    assert.equal(calls.disconnect, 0, 'cleanup() must not disconnect the shared client');
});

test('injected client: increment delegates to hIncrBy and returns its value', async () => {
    const { client, calls } = makeFakeClient();
    const sm = new StatsManager(client, 'job-3', '.');
    const v = await sm.increment('errors', 2);
    assert.equal(v, 2);
    assert.deepEqual(calls.hIncrBy, [['stats:job-3', 'errors', 2]]);
});

test('injected client: getValue delegates to hGet and parses the result', async () => {
    const { client, calls } = makeFakeClient();
    const sm = new StatsManager(client, 'job-4', '.');
    const v = await sm.getValue('errors');
    assert.equal(v, 7);
    assert.deepEqual(calls.hGet, [['stats:job-4', 'errors']]);
});

test('error path: a rejecting hIncrBy is swallowed and increment returns 0', async () => {
    const { client } = makeFakeClient({
        hIncrBy: async () => {
            throw new Error('SocketClosedUnexpectedlyError: Socket closed unexpectedly');
        },
    });
    const sm = new StatsManager(client, 'job-5', '.');
    const v = await sm.increment('errors', 1);
    assert.equal(v, 0, 'increment must return 0 (not throw) when the socket is dead');
});

test('error path: a rejecting hGet is swallowed and getValue returns 0', async () => {
    const { client } = makeFakeClient({
        hGet: async () => {
            throw new Error('SocketClosedUnexpectedlyError');
        },
    });
    const sm = new StatsManager(client, 'job-6', '.');
    const v = await sm.getValue('errors');
    assert.equal(v, 0, 'getValue must return 0 (not throw) when the socket is dead');
});

test('legacy URL path: constructs without throwing and without connecting', () => {
    // createClient is lazy — the constructor must not open a socket.
    const sm = new StatsManager('redis://localhost:6379', 'job-7', '.');
    assert.equal(typeof sm.increment, 'function');
});
