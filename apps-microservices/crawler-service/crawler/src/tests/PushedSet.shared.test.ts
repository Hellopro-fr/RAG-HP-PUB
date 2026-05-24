import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PushedSet } from '../class/PushedSet.js';
import { RedisHealthMonitor } from '../class/RedisHealthMonitor.js';

function makeMockClient(opts?: { sAddImpl?: (key: string, member: string) => Promise<number> }) {
    const calls: Record<string, unknown[][]> = {
        sAdd: [],
        sRem: [],
        expire: [],
        del: [],
    };
    const seen = new Set<string>();
    const client = {
        isOpen: true as boolean,
        async sAdd(key: string, member: string): Promise<number> {
            calls.sAdd.push([key, member]);
            if (opts?.sAddImpl) return opts.sAddImpl(key, member);
            if (seen.has(member)) return 0;
            seen.add(member);
            return 1;
        },
        async sRem(key: string, member: string): Promise<number> {
            calls.sRem.push([key, member]);
            seen.delete(member);
            return 1;
        },
        async expire(key: string, ttl: number): Promise<number> {
            calls.expire.push([key, ttl]);
            return 1;
        },
        async del(key: string): Promise<number> {
            calls.del.push([key]);
            return 1;
        },
        _calls: calls,
    };
    return client;
}

test('tryClaim returns true on first call, false on second for same URL', async () => {
    const client = makeMockClient();
    const set = new PushedSet(client as any, 'crawl-1');
    const first = await set.tryClaim('https://example.com/a');
    const second = await set.tryClaim('https://example.com/a');
    assert.equal(first, true, 'first tryClaim must win the slot');
    assert.equal(second, false, 'second tryClaim for same URL must be rejected');
    assert.equal(client._calls.sAdd.length, 2);
    assert.equal(client._calls.sAdd[0][0], 'pushed:crawl-1');
    assert.equal(client._calls.sAdd[0][1], 'https://example.com/a');
});

test('tryClaim returns true on Redis error (fail-open)', async () => {
    const client = makeMockClient({
        sAddImpl: async () => { throw new Error('Redis exploded'); }
    });
    const set = new PushedSet(client as any, 'crawl-2');
    const result = await set.tryClaim('https://example.com/a');
    assert.equal(result, true, 'fail-open: Redis error must not block the write');
});

test('tryClaim invokes ensureTtl which calls expire once per window', async () => {
    const client = makeMockClient();
    const set = new PushedSet(client as any, 'crawl-3', { ttlSeconds: 86400 });
    await set.tryClaim('https://example.com/a');
    await set.tryClaim('https://example.com/b');
    // First tryClaim triggers ensureTtl. Second tryClaim is within the
    // ttlSeconds/2 window so ensureTtl is a no-op.
    assert.equal(client._calls.expire.length, 1, 'expire must fire exactly once in window');
    assert.equal(client._calls.expire[0][0], 'pushed:crawl-3');
    assert.equal(client._calls.expire[0][1], 86400);
});

test('release removes URL from the set', async () => {
    const client = makeMockClient();
    const set = new PushedSet(client as any, 'crawl-4');
    await set.tryClaim('https://example.com/a');
    await set.release('https://example.com/a');
    assert.equal(client._calls.sRem.length, 1);
    assert.equal(client._calls.sRem[0][0], 'pushed:crawl-4');
    assert.equal(client._calls.sRem[0][1], 'https://example.com/a');
    // After release, claim should win again.
    const reclaim = await set.tryClaim('https://example.com/a');
    assert.equal(reclaim, true);
});

test('monitor receives onSuccess/onError signals', async () => {
    const successCalls: string[] = [];
    const errorCalls: Array<[string, unknown]> = [];
    const monitor: Partial<RedisHealthMonitor> = {
        onSuccess: (channel: string) => { successCalls.push(channel); },
        onError: (channel: string, err: unknown) => { errorCalls.push([channel, err]); },
    };
    // Success path
    const okClient = makeMockClient();
    const okSet = new PushedSet(okClient as any, 'crawl-5', { monitor: monitor as RedisHealthMonitor });
    await okSet.tryClaim('https://example.com/a');
    assert.equal(successCalls.includes('pushed'), true, 'onSuccess must fire on tryClaim success');

    // Error path
    const badClient = makeMockClient({
        sAddImpl: async () => { throw new Error('boom'); }
    });
    const badSet = new PushedSet(badClient as any, 'crawl-6', { monitor: monitor as RedisHealthMonitor });
    await badSet.tryClaim('https://example.com/a');
    assert.equal(errorCalls.length, 1);
    assert.equal(errorCalls[0][0], 'pushed');
    assert.equal((errorCalls[0][1] as Error).message, 'boom');
});
