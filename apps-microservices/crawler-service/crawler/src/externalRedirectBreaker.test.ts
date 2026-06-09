/**
 * Tests for shouldTripExternalRedirectBreaker().
 *
 * The breaker fires in update mode when all/most seeded URLs redirect
 * off-domain (the site relocated). It mirrors the existing rate-breaker
 * philosophy: a minimum sample gate, then a ratio threshold.
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldTripExternalRedirectBreaker } from './externalRedirectBreaker.js';

const CFG = { externalRedirectMinSample: 10, maxExternalRedirectRate: 0.90 };

test('moved domain: 5000 external / 0 processed → trips', () => {
    const r = shouldTripExternalRedirectBreaker(5000, 0, CFG);
    assert.equal(r.trip, true);
});

test('healthy update: 20 external / 4980 processed (0.4%) → no trip', () => {
    const r = shouldTripExternalRedirectBreaker(20, 4980, CFG);
    assert.equal(r.trip, false);
});

test('below sample gate: 9 external / 0 processed (denom 9 < 10) → no trip', () => {
    const r = shouldTripExternalRedirectBreaker(9, 0, CFG);
    assert.equal(r.trip, false);
});

test('at sample gate, all external: 10 external / 0 processed → trips', () => {
    const r = shouldTripExternalRedirectBreaker(10, 0, CFG);
    assert.equal(r.trip, true);
});

test('at gate, exactly at threshold: 9 external / 1 processed (90%) → trips', () => {
    const r = shouldTripExternalRedirectBreaker(9, 1, CFG);
    assert.equal(r.trip, true);
});

test('at gate, just below threshold: 8 external / 2 processed (80%) → no trip', () => {
    const r = shouldTripExternalRedirectBreaker(8, 2, CFG);
    assert.equal(r.trip, false);
});

test('reason string is populated for both outcomes', () => {
    assert.ok(shouldTripExternalRedirectBreaker(10, 0, CFG).reason.length > 0);
    assert.ok(shouldTripExternalRedirectBreaker(0, 0, CFG).reason.length > 0);
});
