/**
 * Update-mode health verdict decision.
 *
 * Answers ONE question: was this crawl representative of the previously known
 * Dataset population? It is deliberately NOT a deletion-safety net — the BO owns
 * the deletion and redirect caps that bound the destructive actions.
 *
 * Two properties are load-bearing and must survive any edit:
 *
 *  - STRICT RELAXATION. Every condition below is today's condition plus an extra
 *    AND'd conjunct, so no run that reaches HEALTHY under the pre-change code can
 *    become non-HEALTHY. The sample gate is a DISJUNCTION (absolute sample OR
 *    coverage), not a replacement, for the same reason.
 *  - ZERO MEANS DISABLED. A configured rate of 0 means the caller switched that
 *    signal off; the BO launcher does exactly that for redirects and growth on
 *    every update. The absolute floor must never resurrect a disabled signal —
 *    hence the rate guard leads each conjunction.
 *
 * Pure function (no Crawlee, no Redis, no fs) so it is unit-testable in isolation,
 * mirroring externalRedirectBreaker.ts.
 *
 * Design: docs/superpowers/specs/2026-08-17-update-health-verdict-decoupling-design.md
 */

export interface UpdateHealthStats {
    processed: number;
    errors: number;
    redirects: number;
    newUrls: number;
    /** Previously-known URLs whose state this crawl ESTABLISHED. Dataset-scoped. */
    accounted: number;
    /** Size of the previous Dataset population (NOT the whole previous corpus). */
    previousTotal: number;
}

export interface UpdateHealthConfig {
    minSample: number;
    minCoverage: number;
    maxErrorRate: number;
    maxRedirectRate: number;
    maxGrowthRate: number;
    maxAbsErrors: number;
    maxAbsRedirects: number;
    maxAbsNew: number;
}

export interface UpdateHealthVerdict {
    status: string;
    statusMessage: string;
    /** Signals skipped because their configured rate was <= 0. */
    disabledSignals: string[];
}

/** Fraction of the previous corpus that this crawl explained (0 when unknown). */
export function updateHealthCoverage(stats: UpdateHealthStats): number {
    return stats.previousTotal > 0 ? stats.accounted / stats.previousTotal : 0;
}

/**
 * The three rates, with their pre-change definitions and denominators.
 * Single source of truth: the verdict and the published report both use this.
 */
export function updateHealthRates(stats: UpdateHealthStats): {
    errorRate: number;
    redirectRate: number;
    growthRate: number;
} {
    return {
        errorRate: stats.processed > 0 ? stats.errors / stats.processed : 0,
        redirectRate: stats.processed > 0 ? stats.redirects / stats.processed : 0,
        growthRate: stats.previousTotal > 0 ? stats.newUrls / stats.previousTotal : 0,
    };
}

export function decideUpdateHealth(
    stats: UpdateHealthStats,
    cfg: UpdateHealthConfig,
): UpdateHealthVerdict {
    const { processed, errors, redirects, newUrls, accounted, previousTotal } = stats;
    const { errorRate, redirectRate, growthRate } = updateHealthRates(stats);
    const coverage = updateHealthCoverage(stats);

    const disabledSignals: string[] = [];
    if (!(cfg.maxErrorRate > 0)) disabledSignals.push("errors");
    if (!(cfg.maxRedirectRate > 0)) disabledSignals.push("redirects");
    if (!(cfg.maxGrowthRate > 0)) disabledSignals.push("growth");

    let status = "HEALTHY";
    let statusMessage = "Update progressing normally.";

    if (previousTotal > 0 && processed < cfg.minSample && coverage < cfg.minCoverage) {
        status = "PENDING_SAMPLE";
        statusMessage = `Crawl accounted for ${accounted}/${previousTotal} of the previous Dataset `
            + `(${(coverage * 100).toFixed(1)}%) with only ${processed} processed`;
    } else if (cfg.maxErrorRate > 0 && errorRate > cfg.maxErrorRate && errors >= cfg.maxAbsErrors) {
        status = "CRITICAL";
        statusMessage = `Error rate too high (${(errorRate * 100).toFixed(1)}%, ${errors} errors)`;
    } else if (cfg.maxRedirectRate > 0 && redirectRate > cfg.maxRedirectRate && redirects >= cfg.maxAbsRedirects) {
        status = "CRITICAL";
        statusMessage = `Redirect rate too high (${(redirectRate * 100).toFixed(1)}%, ${redirects} redirects)`;
    } else if (cfg.maxGrowthRate > 0 && growthRate > cfg.maxGrowthRate && newUrls >= cfg.maxAbsNew) {
        status = "WARNING";
        statusMessage = `Site growth high (${(growthRate * 100).toFixed(1)}%, ${newUrls} new URLs)`;
    }

    // Mass-deletion guard, moved verbatim from functions.ts. 'errors' approximates
    // deleted candidates, sourced from UpdateChecker CASE 1 (permanent HTTP status)
    // and CASE 3 ('not_eligible'). CASE 1 throws in routes.ts before 'processed' is
    // incremented, so a mass-404 restructure never reaches the sample floor. CASE 3
    // does NOT share that property — it runs after the increment, so those URLs are
    // counted in both 'errors' and 'processed'. Either way this guard holds because
    // it is corpus-relative and independent of 'processed' (incident 636-389-1783326914).
    // Only HEALTHY and PENDING_SAMPLE are overridden: WARNING and CRITICAL already
    // block and carry a more specific reason. Do NOT widen this.
    if (previousTotal > 0 && errors / previousTotal > 0.5
        && (status === "HEALTHY" || status === "PENDING_SAMPLE")) {
        status = "SUSPECT";
        statusMessage = `Deleted/error volume (${errors}) exceeds 50% of previous corpus (${previousTotal})`;
    }

    return { status, statusMessage, disabledSignals };
}
