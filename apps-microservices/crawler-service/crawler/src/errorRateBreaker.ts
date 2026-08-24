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
 * Pure function (no Crawlee/Redis) so it is unit-testable in isolation.
 */
export interface ErrorRateBreakerStats {
    /** Cumulative `errors` counter — BOTH natures. */
    errors: number;
    /** Cumulative `processed` — URLs that passed the HTTP status policy. */
    processed: number;
    /** Cumulative `errors_unprocessed` — the OFF-BOOK half of `errors` only. */
    errorsUnprocessed: number;
}

export interface ErrorRateBreakerConfig {
    minSample: number;
    maxErrorRate: number;
}

export function shouldTripErrorRateBreaker(
    stats: ErrorRateBreakerStats,
    cfg: ErrorRateBreakerConfig,
): { trip: boolean; rate: number; attempts: number; reason: string } {
    const attempts = stats.processed + stats.errorsUnprocessed;
    const rate = attempts > 0 ? stats.errors / attempts : 0;

    if (stats.processed < cfg.minSample) {
        return {
            trip: false,
            rate,
            attempts,
            reason: `below sample gate (processed ${stats.processed}/${cfg.minSample})`,
        };
    }
    if (!(cfg.maxErrorRate > 0)) {
        return { trip: false, rate, attempts, reason: "error-rate signal disabled (maxErrorRate = 0)" };
    }
    if (rate > cfg.maxErrorRate) {
        return {
            trip: true,
            rate,
            attempts,
            // Prefix is load-bearing: production logs are grepped on it.
            reason: `Error rate too high (${(rate * 100).toFixed(1)}% > ${(cfg.maxErrorRate * 100).toFixed(1)}%, `
                + `${stats.errors} errors / ${attempts} attempts)`,
        };
    }
    return {
        trip: false,
        rate,
        attempts,
        reason: `error rate ${(rate * 100).toFixed(1)}% within threshold`,
    };
}
