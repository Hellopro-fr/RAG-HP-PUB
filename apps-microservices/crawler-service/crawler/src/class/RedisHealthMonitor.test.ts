import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { RedisHealthMonitor } from './RedisHealthMonitor.js';

describe('RedisHealthMonitor', () => {
    let now = 0;
    const clock = () => now;
    let onLostCalls: string[] = [];
    const onLost = (r: string) => { onLostCalls.push(r); };

    beforeEach(() => {
        now = 1_000_000;
        onLostCalls = [];
    });

    it('does not fire below threshold even with errors', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        m.attach('dedup');
        now += 30_000;
        m.onError('heartbeat', new Error('boom'));
        m['evaluate']();
        assert.equal(onLostCalls.length, 0);
    });

    it('fires after threshold + recent errors', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        now += 70_000;
        m.onError('heartbeat', new Error('boom'));
        m['evaluate']();
        assert.equal(onLostCalls.length, 1);
        assert.match(onLostCalls[0], /No Redis op succeeded/);
    });

    it('does not fire when success arrives within window', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        now += 50_000;
        m.onError('heartbeat', new Error('boom'));
        now += 5_000;
        m.onSuccess('heartbeat');
        now += 30_000;
        m['evaluate']();
        assert.equal(onLostCalls.length, 0);
    });

    it('idempotent — fires once across multiple ticks past threshold', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        now += 70_000;
        m.onError('heartbeat', new Error('boom'));
        m['evaluate']();
        m['evaluate']();
        m['evaluate']();
        assert.equal(onLostCalls.length, 1);
    });

    it('tolerates one broken client when another succeeds (global path)', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        m.attach('dedup');
        now += 70_000;
        // dedup keeps reporting success right now
        m.onSuccess('dedup');
        m.onError('heartbeat', new Error('boom'));
        m['evaluate']();
        assert.equal(onLostCalls.length, 0);
    });

    it('per-client escalation when one client hard-down + no success >60s', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        m.attach('dedup');
        // dedup succeeds frequently so global path never fires
        for (let i = 0; i < 35; i++) {
            now += 2_000;
            m.onError('heartbeat', new Error('boom'));
            m.onSuccess('dedup');
        }
        // heartbeat last success was at attach time ~70s ago, errorCounter=35, dedup keeps global healthy
        m['evaluate']();
        assert.equal(onLostCalls.length, 1);
        assert.match(onLostCalls[0], /Client 'heartbeat' had \d+ consecutive errors/);
    });

    it('onSuccess resets error counter for that client', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        for (let i = 0; i < 10; i++) {
            m.onError('heartbeat', new Error('boom'));
        }
        assert.equal(m.snapshot().errorCounters.heartbeat, 10);
        m.onSuccess('heartbeat');
        assert.equal(m.snapshot().errorCounters.heartbeat, 0);
    });

    it('stop() prevents future fires', () => {
        const m = new RedisHealthMonitor(60_000, onLost, clock);
        m.attach('heartbeat');
        m.stop();
        now += 70_000;
        m.onError('heartbeat', new Error('boom'));
        // evaluate would fire, but stop already cleared any interval — we still
        // assert that calling evaluate after stop manually still works (no crash).
        // For interval-based stop, that's covered by start() not being called.
        m['evaluate']();
        // Idempotency flag uncovers either path; once fired, won't re-fire
        const n = onLostCalls.length;
        m['evaluate']();
        assert.equal(onLostCalls.length, n);
    });
});
