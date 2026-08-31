/**
 * Tests for decideUpdateHealth().
 *
 * The verdict answers one question: was this crawl representative of the
 * previously known Dataset population? Two properties matter most and are
 * pinned here:
 *   1. No run that is HEALTHY under the pre-change code may become non-HEALTHY.
 *   2. A signal whose configured rate is 0 is OFF — its absolute floor must not
 *      resurrect it (the BO launcher disables redirects and growth this way).
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { decideUpdateHealth, updateHealthRates, effectiveMinSample } from './updateHealthVerdict.js';

// Production configuration: the BO sends max_redirect_rate = 0 and
// max_growth_rate = 0 (shell.php), and does not send min_sample or the
// max_abs_* values, so those keep their context.ts defaults.
const PROD = {
    minSample: 50,
    minCoverage: 0.8,
    maxErrorRate: 0.15,
    maxRedirectRate: 0,
    maxGrowthRate: 0,
    maxAbsErrors: 5,
    maxAbsRedirects: 10,
    maxAbsNew: 20,
};

// All three signals enabled — used only to prove the disabled-signal logic is
// what silences redirects and growth in production, not the module itself.
const ALL_ON = { ...PROD, maxRedirectRate: 0.30, maxGrowthRate: 0.50 };

const S = (o: Partial<Parameters<typeof decideUpdateHealth>[0]>) => ({
    processed: 0, errors: 0, redirects: 0, newUrls: 0, accounted: 0, previousTotal: 0, ...o,
});

test('small site, fully accounted → HEALTHY (the defect being fixed)', () => {
    const r = decideUpdateHealth(S({ processed: 12, accounted: 12, previousTotal: 12 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('large partial crawl still passes on the absolute sample → HEALTHY (non-regression)', () => {
    // 60 >= minSample, coverage only 12% — today this passes, so it must keep passing.
    const r = decideUpdateHealth(S({ processed: 60, accounted: 60, previousTotal: 500 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('collapsed crawl: 17% accounted, no errors, under sample → PENDING_SAMPLE', () => {
    // Domain 884's shape: 41 of 243 previously-known URLs, zero errors.
    const r = decideUpdateHealth(S({ processed: 41, accounted: 41, previousTotal: 243 }), PROD);
    assert.equal(r.status, 'PENDING_SAMPLE');
});

test('mass deletion is judged on errors, not on coverage', () => {
    // Same low fetch coverage, but every previously-known URL is accounted for.
    const r = decideUpdateHealth(
        S({ processed: 10, errors: 30, accounted: 40, previousTotal: 40 }), PROD);
    assert.notEqual(r.status, 'PENDING_SAMPLE');
});

test('materiality conjunct: bad rate but only 2 errors → HEALTHY', () => {
    // 2/12 = 16.7% > 15%, but 2 < maxAbsErrors. This is the small-sample noise
    // that a rate-only test would have flagged.
    const r = decideUpdateHealth(
        S({ processed: 12, errors: 2, accounted: 12, previousTotal: 12 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('exactly maxAbsErrors with the rate above threshold → CRITICAL', () => {
    // 5/20 = 25% > 15% and errors >= 5. Pins >= on the count and > on the rate.
    const r = decideUpdateHealth(
        S({ processed: 20, errors: 5, accounted: 20, previousTotal: 20 }), PROD);
    assert.equal(r.status, 'CRITICAL');
});

test('grown site: many errors but a low rate → HEALTHY (killed the max() form)', () => {
    // previousTotal 100 < processed 200. A max(floor, rate x previousTotal) form
    // would have made this CRITICAL; the conjunction keeps today's answer.
    const r = decideUpdateHealth(
        S({ processed: 200, errors: 20, accounted: 100, previousTotal: 100 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('disabled error signal: rate 0 with errors above the floor → not CRITICAL', () => {
    // Operator force-resume (shell.php bypasscberrors). The floor must not resurrect it.
    const cfg = { ...PROD, maxErrorRate: 0 };
    const r = decideUpdateHealth(
        S({ processed: 100, errors: 90, accounted: 100, previousTotal: 100 }), cfg);
    assert.notEqual(r.status, 'CRITICAL');
    assert.ok(r.disabledSignals.includes('errors'));
});

test('production config silences redirects and growth', () => {
    // 30 redirects / 38 processed = 79%, 30 new / 40 previous = 75%: both far above
    // the default rates, both inert because the BO sends 0.
    const r = decideUpdateHealth(
        S({ processed: 38, redirects: 30, newUrls: 30, accounted: 40, previousTotal: 40 }), PROD);
    assert.equal(r.status, 'HEALTHY');
    assert.deepEqual(r.disabledSignals.sort(), ['growth', 'redirects']);
});

test('same shape with all signals enabled → CRITICAL on redirects', () => {
    const r = decideUpdateHealth(
        S({ processed: 38, redirects: 30, newUrls: 30, accounted: 40, previousTotal: 40 }), ALL_ON);
    assert.equal(r.status, 'CRITICAL');
});

test('previousTotal = 0: no coverage verdict, error test still applies', () => {
    const r = decideUpdateHealth(S({ processed: 40, errors: 20, accounted: 0, previousTotal: 0 }), PROD);
    assert.equal(r.status, 'CRITICAL');
});

test('SUSPECT overrides HEALTHY', () => {
    const r = decideUpdateHealth(
        S({ processed: 0, errors: 12, accounted: 12, previousTotal: 12 }), PROD);
    assert.equal(r.status, 'SUSPECT');
});

test('SUSPECT does NOT override CRITICAL', () => {
    // 60/100 errors: over the 50% corpus bound AND over the rate with 60 >= 5.
    const r = decideUpdateHealth(
        S({ processed: 100, errors: 60, accounted: 100, previousTotal: 100 }), PROD);
    assert.equal(r.status, 'CRITICAL');
});

test('positive control: a run that MUST NOT be HEALTHY', () => {
    // Without this, a module returning HEALTHY unconditionally passes every
    // assertion above that uses assert.equal(..., 'HEALTHY').
    const r = decideUpdateHealth(
        S({ processed: 100, errors: 50, accounted: 100, previousTotal: 100 }), PROD);
    assert.notEqual(r.status, 'HEALTHY');
});

test('updateHealthRates matches the pre-change definitions', () => {
    const rates = updateHealthRates(S({ processed: 200, errors: 20, redirects: 40, newUrls: 50, previousTotal: 100 }));
    assert.equal(rates.errorRate, 0.1);
    assert.equal(rates.redirectRate, 0.2);
    assert.equal(rates.growthRate, 0.5);
});

test('rates are 0 when their denominator is 0 (no NaN leaks into the report)', () => {
    const rates = updateHealthRates(S({ processed: 0, errors: 5, previousTotal: 0, newUrls: 3 }));
    assert.equal(rates.errorRate, 0);
    assert.equal(rates.redirectRate, 0);
    assert.equal(rates.growthRate, 0);
});

// ─────────────────────────────────────────────────────────────────────────────
// effectiveMinSample() — the sample floor never exceeds the corpus it judges
// ─────────────────────────────────────────────────────────────────────────────
// The four cases below are real runs from the 2026-08-28 audit of the 98
// guard-blocked runs of the month. Each was a PENDING_SAMPLE block on a crawl
// its own log showed as healthy, and each is unreachable-by-construction: the
// corpus is smaller than the floor it was held to.

test('effectiveMinSample: a corpus smaller than the floor lowers the floor', () => {
    assert.equal(effectiveMinSample({ ...S({}), previousTotal: 9 }, PROD), 9);
    assert.equal(effectiveMinSample({ ...S({}), previousTotal: 6 }, PROD), 6);
});

test('effectiveMinSample: a corpus larger than the floor leaves it alone', () => {
    assert.equal(effectiveMinSample({ ...S({}), previousTotal: 500 }, PROD), 50);
    assert.equal(effectiveMinSample({ ...S({}), previousTotal: 50 }, PROD), 50);
});

test('effectiveMinSample: an unknown corpus keeps the configured floor', () => {
    // previousTotal 0 means "no baseline", and the gate has its own
    // previousTotal > 0 guard. Returning the corpus here would hand back 0 and
    // silently disable the gate for every initial-shaped run.
    assert.equal(effectiveMinSample({ ...S({}), previousTotal: 0 }, PROD), 50);
    assert.equal(effectiveMinSample({ ...S({}), previousTotal: -4 }, PROD), 50);
});

test('norpalex.fr shape: 9-URL corpus, 23 processed → HEALTHY, not PENDING_SAMPLE', () => {
    // Measured 2026-08-25: "accounted for 0/9 (0.0%) with only 23 processed".
    // The crawl covered its corpus 2.5x over and was still held.
    const r = decideUpdateHealth(S({ processed: 23, accounted: 0, previousTotal: 9 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('barriere-titan.fr shape: 6-URL corpus, 12 processed → HEALTHY', () => {
    const r = decideUpdateHealth(S({ processed: 12, accounted: 0, previousTotal: 6 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('smc-palettes.com shape: 11-URL corpus, 31 processed → HEALTHY', () => {
    const r = decideUpdateHealth(S({ processed: 31, accounted: 1, previousTotal: 11 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('ckelprocess.fr shape: 18-URL corpus, 19 processed → HEALTHY', () => {
    // The tightest of the four: one URL above its own corpus size.
    const r = decideUpdateHealth(S({ processed: 19, accounted: 2, previousTotal: 18 }), PROD);
    assert.equal(r.status, 'HEALTHY');
});

test('a small corpus NOT yet covered still trips the gate', () => {
    // The other half of the rule, and the one that keeps it honest: 5 processed
    // against a 9-URL corpus is genuinely partial, so the gate must still fire.
    const r = decideUpdateHealth(S({ processed: 5, accounted: 0, previousTotal: 9 }), PROD);
    assert.equal(r.status, 'PENDING_SAMPLE');
});

test('a genuinely partial large crawl is untouched (the regression that matters)', () => {
    // 30 processed on a 100-URL corpus: floor stays min(50, 100) = 50, so the
    // gate fires exactly as before this change.
    const r = decideUpdateHealth(S({ processed: 30, accounted: 30, previousTotal: 100 }), PROD);
    assert.equal(r.status, 'PENDING_SAMPLE');
});

test('the message names the floor actually applied', () => {
    // Without this the trace shows "only 5 processed" against an invisible
    // threshold, and the reader cannot tell which floor was used.
    const r = decideUpdateHealth(S({ processed: 5, accounted: 0, previousTotal: 9 }), PROD);
    assert.match(r.statusMessage, /sample gate 9/);
});

// The two brakes that remain on a small corpus once the sample gate stops
// holding it. Both are derived from the chain, not guessed: the first `else if`
// that matches wins, and the SUSPECT override only applies to HEALTHY and
// PENDING_SAMPLE. The numbers below were computed backwards from those rules —
// a first version of this test asserted SUSPECT on figures that trip CRITICAL
// two branches earlier, and failed against correct code.

test('a small corpus with a high error RATE is still caught, by CRITICAL', () => {
    // 6/23 = 26% > 15% and 6 >= maxAbsErrors, so CRITICAL matches before the
    // SUSPECT override is ever considered.
    const r = decideUpdateHealth(S({ processed: 23, errors: 6, accounted: 6, previousTotal: 9 }), PROD);
    assert.equal(r.status, 'CRITICAL');
});

test('a small corpus losing over half itself is caught by SUSPECT', () => {
    // The rate is deliberately kept UNDER the CRITICAL threshold so the mass
    // guard is the one doing the work: 5/34 = 14.7% < 15%, while 5/9 = 56% of
    // the previous corpus. SUSPECT is corpus-relative, so it does not weaken
    // when the sample floor drops — this is what replaces the gate.
    const r = decideUpdateHealth(S({ processed: 34, errors: 5, accounted: 5, previousTotal: 9 }), PROD);
    assert.equal(r.status, 'SUSPECT');
});
