import { test } from 'node:test';
import assert from 'node:assert/strict';
import { DedupManager } from '../class/DedupManager.js';

function makeMockClient() {
    const calls: Record<string, unknown[][]> = {
        connect: [],
        disconnect: [],
        sAdd: [],
        expire: [],
    };
    const handlers = new Map<string, (...args: unknown[]) => void>();
    const client = {
        isOpen: true as boolean,
        on(event: string, handler: (...args: unknown[]) => void) {
            handlers.set(event, handler);
            return client;
        },
        async connect() { calls.connect.push([]); return client; },
        async disconnect() { calls.disconnect.push([]); return client; },
        async sAdd(key: string, members: string | string[]) {
            calls.sAdd.push([key, members]);
            return Array.isArray(members) ? members.length : 1;
        },
        async expire(key: string, ttl: number) { calls.expire.push([key, ttl]); return 1; },
        _calls: calls,
    };
    return client;
}

test('accepts injected client; connect is no-op', async () => {
    const client = makeMockClient();
    const dedup = new DedupManager(client as any, 'crawl-x');
    await dedup.connect();
    assert.equal(client._calls.connect.length, 0,
        'shared client must NOT be connect()-ed by DedupManager');
});

test('accepts injected client; disconnect is no-op', async () => {
    const client = makeMockClient();
    const dedup = new DedupManager(client as any, 'crawl-x');
    await dedup.disconnect();
    assert.equal(client._calls.disconnect.length, 0,
        'shared client must NOT be disconnect()-ed by DedupManager');
});

test('addUrl uses injected client with dedup:{crawlId} key', async () => {
    const client = makeMockClient();
    const dedup = new DedupManager(client as any, 'crawl-x');
    const isNew = await dedup.addUrl('https://example.com/a');
    assert.equal(client._calls.sAdd.length >= 1, true);
    assert.equal(client._calls.sAdd[0][0], 'dedup:crawl-x');
    assert.equal(client._calls.sAdd[0][1], 'https://example.com/a');
    assert.equal(isNew, true);
});

test('URL form owns the client (ownsClient=true)', () => {
    const dedup = new DedupManager('redis://x:6379', 'crawl-y');
    // ownsClient is private — bracket-access via cast is acceptable in a unit
    // test because the legacy-path contract IS the ownership flag.
    assert.equal((dedup as unknown as { ownsClient: boolean }).ownsClient, true);
});
