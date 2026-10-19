/**
 * Error-rate breaker decision (update mode, standard rates).
 *
 * Extracted from the inline block in routes.ts so it can be unit-tested at all:
 * this breaker was the only one of the three still computing its rate inline,
 * and it is the one that shipped a "rate" production observed at 722%.
 *
 * THE DEFECT THIS FIXES — the denominator excluded part of its own numerator.
 * `increment("processed")` happens at exactly one site, AFTER the HTTP status
 * policy. A dataset URL answering >= 400 or status 0 throws before that
 * increment, yet still increments `errors`. It counted in the numerator and
 * never in the denominator, so `errors / processed` was not a proportion —
 * 12 of the 69 runs stopped in the 2026-08-10 batch reported above 100%.
 *
 * ⚠ `errors` MIXES TWO NATURES, unlike the numerators of the two neighbouring
 * breakers (`shouldTripProxyWall`, `shouldTripExternalRedirectBreaker`), which
 * are disjoint from `processed` by construction:
 *   - CASE 1, HTTP error on a dataset URL   → never reaches `processed`  (OFF-BOOK)
 *   - CASE 3, 2xx same URL, no longer eligible → counted after it        (ON-BOOK)
 * `processed + errors` would therefore double-count the on-book half and dilute
 * the rate for the runs whose rate is already correct. The denominator is
 * `processed + errorsUnprocessed`, isolating the off-book half only.
 *
 * INVARIANT — the rate cannot exceed 1. Every on-book error is a URL already
 * inside `processed`, so `errors <= processed + errorsUnprocessed = attempts`.
 * A rate above 1 now means a counter bug, not a broken site.
 *
 * ⚠ THE SAMPLE GATE STAYS ON `processed`, NOT on `attempts`. Widening it would
 * let the breaker evaluate runs it never evaluated before (processed = 10 with
 * errorsUnprocessed = 45 opens a gate of 50 that 10 kept shut), i.e. it would
 * ADD stops. This change exists to remove stops decided on an invalid number.
 *
 * TWO DECISIONS SINCE THE `not_eligible` COUNTER (spec
 * docs/superpowers/specs/2026-10-19-not-eligible-breaker-design.md). The two natures of
 * `errors` above deserve two thresholds, on the SAME denominator (`attempts`):
 *   - HTTP rate         = max(0, errors - notEligible) / attempts  > maxErrorRate (0.15)
 *   - not-eligible rate = notEligible / attempts                   > maxNotEligibleRate (0.5)
 * `rate` is the HTTP rate; `notEligibleRate` is returned beside it. `notEligible` absent
 * counts 0, so a caller that does not pass it gets the former breaker's result exactly.
 * The max(0, ...) floor exists because StatsManager.increment() swallows Redis errors: a lost
 * `errors` increment followed by a successful `not_eligible` one would go negative.
 *
 * STRICT RELAXATION PROPERTY — httpRate + notEligibleRate = the former rate (while
 * errors >= notEligible), so for maxNotEligibleRate = 0 (decision off) or
 * maxNotEligibleRate >= maxErrorRate, `trip(new) => trip(old)`: this split only ever REMOVES
 * stops. A threshold strictly between 0 and maxErrorRate breaks it (a 10% non-French run
 * would stop that the former breaker let through). Whoever sets the threshold from a
 * referential (BO) must keep it at 0 or >= maxErrorRate.
 *
 * Both comparisons are strict (`>`). maxErrorRate <= 0 switches BOTH decisions off;
 * maxNotEligibleRate <= 0 or absent switches the second one off alone.
 *
 * Pure function (no Crawlee/Redis) so it is unit-testable in isolation.
 */
export interface ErrorRateBreakerStats {
    /** Cumulative `errors` counter — BOTH natures. */
    errors: number;
    /** Cumulative `processed` — URLs that passed the HTTP status policy. */
    processed: number;
    /** Cumulative `errors_unprocessed` — the OFF-BOOK half of `errors` only. */
    errorsUnprocessed: number;
    /** Cumulative `not_eligible` — the ON-BOOK half of `errors` (CASE 3). Absent = 0. */
    notEligible?: number;
}

export interface ErrorRateBreakerConfig {
    minSample: number;
    maxErrorRate: number;
    /** 0 or absent disables the not-eligible decision. */
    maxNotEligibleRate?: number;
}

const pct = (r: number): string => (r * 100).toFixed(1);

export function shouldTripErrorRateBreaker(
    stats: ErrorRateBreakerStats,
    cfg: ErrorRateBreakerConfig,
): { trip: boolean; rate: number; notEligibleRate: number; attempts: number; reason: string } {
    const attempts = stats.processed + stats.errorsUnprocessed;
    const notEligible = stats.notEligible ?? 0;
    const httpErrors = Math.max(0, stats.errors - notEligible);
    const rate = attempts > 0 ? httpErrors / attempts : 0;
    const notEligibleRate = attempts > 0 ? notEligible / attempts : 0;
    const verdict = (trip: boolean, reason: string) => ({ trip, rate, notEligibleRate, attempts, reason });

    if (stats.processed < cfg.minSample) {
        return verdict(false, `below sample gate (processed ${stats.processed}/${cfg.minSample})`);
    }
    if (!(cfg.maxErrorRate > 0)) {
        return verdict(false, "error-rate signal disabled (maxErrorRate = 0)");
    }
    if (rate > cfg.maxErrorRate) {
        // Prefix is load-bearing: production logs are grepped on it.
        return verdict(
            true,
            `Error rate too high (${pct(rate)}% > ${pct(cfg.maxErrorRate)}%, `
                + `${httpErrors} HTTP errors / ${attempts} attempts)`,
        );
    }
    const maxNotEligibleRate = cfg.maxNotEligibleRate ?? 0;
    if (maxNotEligibleRate > 0 && notEligibleRate > maxNotEligibleRate) {
        return verdict(
            true,
            `Not-eligible rate too high (${pct(notEligibleRate)}% > ${pct(maxNotEligibleRate)}%, `
                + `${notEligible} not-eligible / ${attempts} attempts)`,
        );
    }
    return verdict(false, `error rate ${pct(rate)}% within threshold`);
}
