import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { ProgressMonitor } from './ProgressMonitor.js';

describe('ProgressMonitor', () => {
    let now = 0;
    const clock = () => now;
    let onStalledCalls: string[] = [];
    const onStalled = (r: string) => { onStalledCalls.push(r); };
    let finished = 0;
    const readFinished = () => finished;

    beforeEach(() => {
        now = 1_000_000;
        onStalledCalls = [];
        finished = 0;
    });

    it('does not fire before stall window age reached', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        for (let i = 0; i < 5; i++) {
            now += 30_000;
            m['tick']();
        }
        // ~150s elapsed, window=600s — should not fire
        assert.equal(onStalledCalls.length, 0);
    });

    it('fires once after full stall window with no progress', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        for (let i = 0; i < 21; i++) {
            now += 30_000;
            m['tick']();
        }
        // 21 * 30s = 630s elapsed, oldest sample at ~600s ago — fire
        assert.equal(onStalledCalls.length, 1);
        assert.match(onStalledCalls[0], /No URL progress/);
    });

    it('does not fire when progress observed within window', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        for (let i = 0; i < 21; i++) {
            now += 30_000;
            if (i === 10) finished += 1;
            m['tick']();
        }
        assert.equal(onStalledCalls.length, 0);
    });

    it('idempotent across multiple ticks past threshold', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        for (let i = 0; i < 30; i++) {
            now += 30_000;
            m['tick']();
        }
        assert.equal(onStalledCalls.length, 1);
    });

    it('samples pruned to threshold + slack', () => {
        const m = new ProgressMonitor(readFinished, 600_000, onStalled, 30_000, clock);
        // Force progress so it never fires
        for (let i = 0; i < 100; i++) {
            now += 30_000;
            finished += 1;
            m['tick']();
        }
        const internal = (m as any).samples as Array<{at: number; finished: number}>;
        // 100 ticks * 30s = 3000s, threshold+slack = 660s → ~22 samples retained
        assert.ok(internal.length <= 25, `expected <=25, got ${internal.length}`);
    });
});
