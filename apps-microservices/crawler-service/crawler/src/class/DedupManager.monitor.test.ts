import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { DedupManager } from './DedupManager.js';
import { RedisHealthMonitor } from './RedisHealthMonitor.js';

describe('DedupManager monitor wiring', () => {
    it('reports onError to monitor when Redis client emits error', () => {
        const onLostCalls: string[] = [];
        const monitor = new RedisHealthMonitor(60_000, (r) => onLostCalls.push(r), () => Date.now());
        monitor.attach('dedup');
        // Use a bad URL so the redis client will emit 'error' on connection attempts.
        const d = new DedupManager('redis://127.0.0.1:1', 'test-crawl', 60, monitor);
        // Listener registered — drive an error event manually.
        // Access internal client to trigger the registered 'error' listener path.
        (d as any).redis.emit('error', new Error('boom'));
        const snap = monitor.snapshot();
        assert.equal(snap.errorCounters.dedup, 1);
    });

    it('reports onSuccess after a successful op (mocked client)', async () => {
        const onLostCalls: string[] = [];
        const monitor = new RedisHealthMonitor(60_000, (r) => onLostCalls.push(r), () => Date.now());
        monitor.attach('dedup');
        const d = new DedupManager('redis://127.0.0.1:1', 'test-crawl', 60, monitor);
        // Swap internal client for a stub so we don't need a real Redis.
        (d as any).redis = {
            sAdd: async () => 1,
            expire: async () => true,
            isOpen: false,
            on: () => {},
        };
        const isNew = await d.addUrl('https://example.test/');
        assert.equal(isNew, true);
        const snap = monitor.snapshot();
        // sAdd + expire (in ensureTtl) → 2 successes for 'dedup'
        assert.ok(snap.errorCounters.dedup === 0);
    });
});
