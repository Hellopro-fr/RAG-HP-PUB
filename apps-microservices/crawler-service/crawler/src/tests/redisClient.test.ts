import { test } from 'node:test';
import assert from 'node:assert/strict';

import { __setCreateClientForTests, createSharedRedisClient } from '../redisClient.js';

interface FakeClient {
    on: (event: string, handler: (...args: unknown[]) => void) => FakeClient;
    _emit: (event: string, err: unknown) => void;
    _handlers: Map<string, (...args: unknown[]) => void>;
}

function makeFakeClient(): FakeClient {
    const handlers = new Map<string, (...args: unknown[]) => void>();
    const fake: FakeClient = {
        on(event, handler) {
            handlers.set(event, handler);
            return fake;
        },
        _emit(event, err) {
            const h = handlers.get(event);
            if (h) h(err);
        },
        _handlers: handlers,
    };
    return fake;
}

const createClientCalls: any[] = [];
let fakeClient: FakeClient;

function resetMock() {
    createClientCalls.length = 0;
    fakeClient = makeFakeClient();
    __setCreateClientForTests((opts: any) => {
        createClientCalls.push(opts);
        return fakeClient as any;
    });
}

test('factory passes name option', () => {
    resetMock();
    createSharedRedisClient('redis://x:6379', { crawlId: 'abc123' });
    assert.equal(createClientCalls.length, 1);
    assert.equal(createClientCalls[0].name, 'crawler-node-abc123');
});

test('factory passes keepAlive 30000 and connectTimeout 5000', () => {
    resetMock();
    createSharedRedisClient('redis://x:6379', { crawlId: 'abc123' });
    const opts = createClientCalls[0];
    assert.equal(opts.socket.keepAlive, 30_000);
    assert.equal(opts.socket.connectTimeout, 5_000);
});

test('error handler reports to monitor as shared', () => {
    resetMock();
    const seen: Array<[string, unknown]> = [];
    const monitor: any = { onError: (name: string, err: unknown) => seen.push([name, err]) };
    createSharedRedisClient('redis://x:6379', { crawlId: 'abc123', monitor });
    const e = new Error('boom');
    fakeClient._emit('error', e);
    assert.equal(seen.length, 1);
    assert.equal(seen[0][0], 'shared');
    assert.equal(seen[0][1], e);
});

test('factory tolerates monitor undefined', () => {
    resetMock();
    createSharedRedisClient('redis://x:6379', { crawlId: 'abc123' });
    assert.doesNotThrow(() => fakeClient._emit('error', new Error('x')));
});
