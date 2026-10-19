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

// ---------------------------------------------------------------------------
// not_eligible split (spec 2026-10-19-not-eligible-breaker-design.md §3).
// `rate` is the HTTP rate, `notEligibleRate` the on-book half. Every expectation
// below is derived as value / attempts, attempts = processed + errorsUnprocessed.
// ---------------------------------------------------------------------------

const CFG_NE = { minSample: 50, maxErrorRate: 0.15, maxNotEligibleRate: 0.5 };

test('HTTP errors alone trip: 30/130 = 23.1% > 15%, prefix kept, suffix counts HTTP errors', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 30, processed: 100, errorsUnprocessed: 30, notEligible: 0 },
        CFG_NE,
    );
    assert.equal(r.attempts, 130);
    assert.equal(r.rate, 30 / 130);
    assert.equal(r.notEligibleRate, 0);
    assert.equal(r.trip, true);
    assert.equal(r.reason, 'Error rate too high (23.1% > 15.0%, 30 HTTP errors / 130 attempts)');
});

test('not_eligible alone trips under its own prefix: 60/100 = 60.0% > 50%', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 60, processed: 100, errorsUnprocessed: 0, notEligible: 60 },
        CFG_NE,
    );
    assert.equal(r.rate, 0);
    assert.equal(r.notEligibleRate, 60 / 100);
    assert.equal(r.trip, true);
    assert.equal(
        r.reason,
        'Not-eligible rate too high (60.0% > 50.0%, 60 not-eligible / 100 attempts)',
    );
});

test('combined 30/110 = 27.3% > 15% but HTTP 10/110 = 9.1% and not_eligible 20/110 = 18.2%: no stop', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 30, processed: 100, errorsUnprocessed: 10, notEligible: 20 },
        CFG_NE,
    );
    assert.equal(r.attempts, 110);
    assert.equal(r.rate, 10 / 110);
    assert.equal(r.notEligibleRate, 20 / 110);
    assert.equal(r.trip, false);
    assert.match(r.reason, /within threshold/);
    // The former breaker (one rate, one threshold) WOULD have stopped this run.
    assert.ok(30 / 110 > 0.15);
});

test('maxNotEligibleRate = 0 or absent disables the not_eligible decision alone', () => {
    const stats = { errors: 60, processed: 100, errorsUnprocessed: 0, notEligible: 60 };
    const zero = shouldTripErrorRateBreaker(stats, { ...CFG_NE, maxNotEligibleRate: 0 });
    assert.equal(zero.trip, false);
    assert.equal(zero.notEligibleRate, 60 / 100);
    const absent = shouldTripErrorRateBreaker(stats, CFG);
    assert.equal(absent.trip, false);
    assert.equal(absent.notEligibleRate, 60 / 100);
});

test('maxErrorRate = 0 disables BOTH decisions (operator escape hatch)', () => {
    const http = shouldTripErrorRateBreaker(
        { errors: 500, processed: 100, errorsUnprocessed: 500, notEligible: 0 },
        { ...CFG_NE, maxErrorRate: 0 },
    );
    assert.equal(http.trip, false);
    assert.match(http.reason, /disabled/);
    const onBook = shouldTripErrorRateBreaker(
        { errors: 60, processed: 100, errorsUnprocessed: 0, notEligible: 60 },
        { ...CFG_NE, maxErrorRate: 0 },
    );
    assert.equal(onBook.trip, false);
    assert.equal(onBook.notEligibleRate, 60 / 100);
    assert.match(onBook.reason, /disabled/);
});

test('strict comparison on the not_eligible threshold: 50/100 = 0.5 does not trip, 51/100 does', () => {
    const at = shouldTripErrorRateBreaker(
        { errors: 50, processed: 100, errorsUnprocessed: 0, notEligible: 50 },
        CFG_NE,
    );
    assert.equal(at.notEligibleRate, 0.5);
    assert.equal(at.trip, false);
    const over = shouldTripErrorRateBreaker(
        { errors: 51, processed: 100, errorsUnprocessed: 0, notEligible: 51 },
        CFG_NE,
    );
    assert.equal(over.trip, true);
    assert.equal(
        over.reason,
        'Not-eligible rate too high (51.0% > 50.0%, 51 not-eligible / 100 attempts)',
    );
});

test('the HTTP numerator is floored at 0 when notEligible exceeds errors (lost increment)', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 3, processed: 100, errorsUnprocessed: 0, notEligible: 5 },
        CFG_NE,
    );
    assert.equal(r.rate, 0);
    assert.equal(r.notEligibleRate, 5 / 100);
    assert.equal(r.trip, false);
});

test('the sample gate also shuts the not_eligible decision: processed 49 < 50', () => {
    const r = shouldTripErrorRateBreaker(
        { errors: 49, processed: 49, errorsUnprocessed: 0, notEligible: 49 },
        CFG_NE,
    );
    assert.equal(r.notEligibleRate, 1);
    assert.equal(r.trip, false);
    assert.match(r.reason, /sample gate/);
});

test('both decisions true: the HTTP reason wins (decision 3 before 4)', () => {
    // attempts = 100 + 30 = 130 ; HTTP 30/130 = 23.1% > 15% ; not_eligible 70/130 = 53.8% > 50%.
    const r = shouldTripErrorRateBreaker(
        { errors: 100, processed: 100, errorsUnprocessed: 30, notEligible: 70 },
        CFG_NE,
    );
    assert.equal(r.trip, true);
    assert.equal(r.rate, 30 / 130);
    assert.equal(r.notEligibleRate, 70 / 130);
    assert.ok(r.reason.startsWith('Error rate too high ('), r.reason);
});

test('a not_eligible threshold strictly between 0 and maxErrorRate breaks the relaxation property', () => {
    // 12/100 = 0.12 <= 0.15: the former breaker did not stop; at 0.1 the new one does.
    const r = shouldTripErrorRateBreaker(
        { errors: 12, processed: 100, errorsUnprocessed: 0, notEligible: 12 },
        { ...CFG_NE, maxNotEligibleRate: 0.1 },
    );
    assert.ok(12 / 100 <= 0.15);
    assert.equal(r.trip, true);
    assert.equal(
        r.reason,
        'Not-eligible rate too high (12.0% > 10.0%, 12 not-eligible / 100 attempts)',
    );
});

test('relaxation grid: trip(new) implies trip(old) for maxNotEligibleRate in {0, 0.15, 0.5, 1}', () => {
    // 6 processed x 6 eOff x 161 (eOn, ne) pairs x 4 thresholds = 3864 calls.
    let cases = 0;
    let newTrips = 0;
    let relaxed = 0;
    for (const maxNotEligibleRate of [0, 0.15, 0.5, 1]) {
        for (let processed = 0; processed <= 40; processed += 8) {
            for (let eOff = 0; eOff <= 40; eOff += 8) {
                for (let eOn = 0; eOn <= processed; eOn += 4) {
                    for (let ne = 0; ne <= eOn; ne += 4) {
                        const errors = eOff + eOn;
                        const attempts = processed + eOff;
                        const oldRate = attempts > 0 ? errors / attempts : 0;
                        const oldTrip = oldRate > 0.15;
                        const r = shouldTripErrorRateBreaker(
                            { errors, processed, errorsUnprocessed: eOff, notEligible: ne },
                            { minSample: 0, maxErrorRate: 0.15, maxNotEligibleRate },
                        );
                        cases += 1;
                        if (r.trip) {
                            newTrips += 1;
                            assert.ok(
                                oldTrip,
                                `new trips but old does not: processed=${processed} eOff=${eOff} eOn=${eOn} ne=${ne} max=${maxNotEligibleRate}`,
                            );
                        } else if (oldTrip) {
                            relaxed += 1;
                        }
                    }
                }
            }
        }
    }
    assert.equal(cases, 3864);
    assert.ok(newTrips > 0, 'the grid must contain trips, or the implication is vacuous');
    assert.ok(relaxed > 0, 'the grid must contain a relaxed run, or the split changes nothing');
});
