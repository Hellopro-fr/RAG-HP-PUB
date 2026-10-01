/**
 * Tests for shouldTripErrorRateBreaker().
 *
 * This breaker had NO test, which is how it shipped a "rate" that production
 * observed at 722%. The cases below are derived from the 69 stopped runs of the
 * 2026-08-10 batch (spec §1) — a rate is reproduced by a (errors, processed)
 * pair that yields it, not by the run's own raw counters, which are archived.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldTripErrorRateBreaker } from './errorRateBreaker.js';

const CFG = { minSample: 50, maxErrorRate: 0.15 };

test('the impossible rate becomes a proportion: 722% measured → 87.8%', () => {
    // 361/50 = 722%, the maximum over the 69 runs. All errors off-book.
    const r = shouldTripErrorRateBreaker(
        { errors: 361, processed: 50, errorsUnprocessed: 361 },
        CFG,
    );
    assert.equal(r.attempts, 411);
    assert.ok(r.rate <= 1, `rate must be a proportion, got ${r.rate}`);
    assert.equal((r.rate * 100).toFixed(1), '87.8');
    assert.equal(r.trip, true); // still far above 15% — the fix does not rescue this one
});

test('the rate can NEVER exceed 1, whatever the legal mixture', () => {
    // e_on <= processed is the invariant; sweep the whole legal space.
    for (let processed = 0; processed <= 40; processed += 8) {
        for (let eOff = 0; eOff <= 40; eOff += 8) {
            for (let eOn = 0; eOn <= processed; eOn += 4) {
                const r = shouldTripErrorRateBreaker(
                    { errors: eOff + eOn, processed, errorsUnprocessed: eOff },
                    { minSample: 0, maxErrorRate: 0.15 },
                );
                assert.ok(
                    r.rate <= 1,
                    `rate ${r.rate} > 1 for processed=${processed} eOff=${eOff} eOn=${eOn}`,
                );
            }
        }
    }
});

test('§4.2 UPPER bound — marginal run, all errors off-book: 15.2% → 13.2%, no trip', () => {
    // douillet-agricole.fr shape: stopped at 15.2% after storing 262 files.
    const r = shouldTripErrorRateBreaker(
        { errors: 40, processed: 263, errorsUnprocessed: 40 },
        CFG,
    );
    assert.equal((r.rate * 100).toFixed(1), '13.2');
    assert.equal(r.trip, false);
});

test('§4.2 LOWER bound — same run, all errors already in processed: still trips', () => {
    // This is the honest half of the bound: when every error is `not_eligible`,
    // the old denominator was already correct and this fix changes nothing.
    const r = shouldTripErrorRateBreaker(
        { errors: 40, processed: 263, errorsUnprocessed: 0 },
        CFG,
    );
    assert.equal((r.rate * 100).toFixed(1), '15.2');
    assert.equal(r.trip, true);
});

test('the sample gate stays on `processed`, so the fix adds NO new stop', () => {
    // attempts = 149 would clear a gate of 50; processed = 49 must keep it shut.
    const r = shouldTripErrorRateBreaker(
        { errors: 100, processed: 49, errorsUnprocessed: 100 },
        CFG,
    );
    assert.equal(r.trip, false);
    assert.match(r.reason, /sample gate/);
});

test('strict comparison preserved: exactly at the threshold does not trip', () => {
    // 15/100 = 15.0% exactly → not > 0.15 → no trip.
    const at = shouldTripErrorRateBreaker(
        { errors: 15, processed: 100, errorsUnprocessed: 0 },
        CFG,
    );
    assert.equal(at.trip, false);

    // 1504/10000 = 15.04% → trips, and DISPLAYS as "15.0%". This is the rounding
    // artefact behind the three runs logged at exactly 15,0% (spec §1).
    const justOver = shouldTripErrorRateBreaker(
        { errors: 1504, processed: 10000, errorsUnprocessed: 0 },
        CFG,
    );
    assert.equal(justOver.trip, true);
    // Both the rate and the threshold render at .toFixed(1) now, so a bare
    // /15\.0%/ would pass even if the RATE render broke (the threshold's own
    // "15.0%" would still satisfy it). Anchor right after the opening paren so
    // this can only match the rate side.
    assert.match(justOver.reason, /too high \(15\.0% > /);
});

test('maxErrorRate = 0 disables the signal (routes.ts `> 0` semantics)', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 500, processed: 100, errorsUnprocessed: 500 },
        { minSample: 50, maxErrorRate: 0 },
    );
    assert.equal(r.trip, false);
});

test('zero denominator yields 0, not NaN', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 0, processed: 0, errorsUnprocessed: 0 },
        { minSample: 0, maxErrorRate: 0.15 },
    );
    assert.equal(r.rate, 0);
    assert.equal(r.trip, false);
});

test('the reason keeps the grepped prefix on trip', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 50, processed: 100, errorsUnprocessed: 0 },
        CFG,
    );
    assert.equal(r.trip, true);
    assert.ok(
        r.reason.startsWith('Error rate too high ('),
        `production logs are grepped on this prefix, got: ${r.reason}`,
    );
});
