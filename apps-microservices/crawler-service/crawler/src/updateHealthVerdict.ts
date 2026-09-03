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
    /** Cumulative `errors` counter — BOTH natures, on-book and off-book. */
    errors: number;
    /**
     * Cumulative `errors_unprocessed` — the OFF-BOOK half of `errors` only: the
     * errors that never incremented `processed`.
     *
     * REQUIRED, not optional, and deliberately so: an optional field would let a
     * caller omit it and silently restore the denominator this change removes.
     * A missed call site has to be a compile error, not a wrong number.
     */
    errorsUnprocessed: number;
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
 * The sample floor this run is actually held to: never more than the corpus it has.
 *
 * THE DEFECT THIS FIXES — a site with fewer than `minSample` previously-known URLs could
 * never clear the gate. The condition is a conjunction (`processed < minSample` AND
 * `coverage < minCoverage`), and the coverage term is not a working escape hatch today (see
 * the note below), so on a small site the gate degenerated into `processed < 50` alone —
 * unreachable by construction. That is not a detection, it is a permanent hold.
 *
 * MEASURED on the 98 guard-blocked runs of 2026-08 (audit of 2026-08-28): PENDING_SAMPLE
 * accounted for 38 blocks, 24 of them on runs whose own log showed a healthy crawl. Four
 * cases, re-derived against this rule:
 *
 *   norpalex.fr        previousTotal  9, processed 23  -> gate 9,  23 < 9  false
 *   barriere-titan.fr  previousTotal  6, processed 12  -> gate 6,  12 < 6  false
 *   smc-palettes.com   previousTotal 11, processed 31  -> gate 11, 31 < 11 false
 *   ckelprocess.fr     previousTotal 18, processed 19  -> gate 18, 19 < 18 false
 *
 * All four leave PENDING_SAMPLE, and none of them needed `coverage` to do so.
 *
 * ⚠ STRICT RELAXATION, and it is provable rather than asserted: `Math.min` can only lower
 * the floor, so `processed < min(minSample, previousTotal)` implies `processed < minSample`.
 * The set of runs that trip the gate can therefore only shrink. This is the same invariant
 * the file header states for every other condition here — see "STRICT RELAXATION" above.
 *
 * ⚠ What it deliberately does NOT do: loosen a genuinely partial crawl. A corpus of 100 seen
 * with 30 processed still gets a floor of 50 (`min(50, 100)`), so the gate still fires. Only
 * the sites whose corpus is SMALLER than the floor change behaviour — exactly the population
 * that could never satisfy it.
 *
 * ⚠ Why `coverage` cannot be relied on instead, measured 2026-08-31 on symotronic.com:
 * `previousTotal` is counted BEFORE Phase-2 seeding (main.ts), while `accounted` can only
 * credit a URL that was seeded AND visited AND matched exactly. Seeding drops excluded
 * regional paths and ignored extensions, so those URLs sit in the denominator and can never
 * reach the numerator: the ratio has a site-dependent ceiling below 1 (78.79% on that run,
 * against a 0.8 threshold). Aligning the two populations is a separate change — and it moves
 * `growthRate` too, which shares the same denominator.
 */
export function effectiveMinSample(stats: UpdateHealthStats, cfg: UpdateHealthConfig): number {
    if (!(stats.previousTotal > 0)) {
        return cfg.minSample;
    }
    return Math.min(cfg.minSample, stats.previousTotal);
}

/**
 * The three rates and their denominators.
 * Single source of truth: the verdict and the published report both use this.
 *
 * THE ERROR DENOMINATOR IS `processed + errorsUnprocessed`, NOT `processed`.
 * `errors` counts two natures and only one of them is inside `processed`; the
 * off-book half was never in the denominator at all, so the ratio was not a
 * rate. Measured on the 2026-08 guard-blocked runs: 6105%, 2446%, and two more
 * above 100% — arithmetically impossible for a proportion, and the number a
 * CRITICAL verdict was pronounced on. Same formula as errorRateBreaker.ts:53-54,
 * and for the same reason stated there: `processed + errors` would double-count
 * the on-book half.
 *
 * INVARIANT — errorRate cannot exceed 1. Every on-book error is a URL already
 * inside `processed`, so `errors <= processed + errorsUnprocessed`. A rate above
 * 1 now means a counter bug, not a broken site.
 *
 * DIRECTION OF THE CHANGE, stated rather than left to be discovered: the
 * denominator can only GROW, so errorRate can only FALL. This removes CRITICAL
 * verdicts, it can never add one. That is the intent — they were decided on an
 * invalid number — and it is why no run needs re-checking for a new stop.
 *
 * WHAT IT DOES NOT TOUCH, and why:
 *   - `redirectRate` keeps `processed`. Production sends maxRedirectRate = 0
 *     (shell.php), so the signal is off, and no measurement showed a redirect
 *     rate above 100%. Changing it would be untested scope.
 *   - the SUSPECT mass-deletion guard below keeps `errors / previousTotal`. It is
 *     corpus-relative on purpose and is what actually catches a mass-404
 *     restructure. A run this change moves out of CRITICAL falls through to that
 *     guard, so it is not released unchecked.
 *   - the sample gate keeps `processed`. Widening it would ADD holds, the exact
 *     inverse of this change (errorRateBreaker.ts says the same of its own gate).
 */
export function updateHealthRates(stats: UpdateHealthStats): {
    errorRate: number;
    redirectRate: number;
    growthRate: number;
} {
    const attempts = stats.processed + stats.errorsUnprocessed;
    return {
        errorRate: attempts > 0 ? stats.errors / attempts : 0,
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

    const minSample = effectiveMinSample(stats, cfg);
    if (previousTotal > 0 && processed < minSample && coverage < cfg.minCoverage) {
        status = "PENDING_SAMPLE";
        statusMessage = `Crawl accounted for ${accounted}/${previousTotal} of the previous Dataset `
            + `(${(coverage * 100).toFixed(1)}%) with only ${processed} processed `
            + `(sample gate ${minSample})`;
    } else if (cfg.maxErrorRate > 0 && errorRate > cfg.maxErrorRate && errors >= cfg.maxAbsErrors) {
        status = "CRITICAL";
        // ⚠ Deliberately NOT the words "Error rate too high (" — errorRateBreaker.ts:73 emits that
        // exact prefix and production logs are grepped on it (the 69-run measurement of the
        // 2026-08-10 batch was taken that way).
        // ⚠⚠ THE TWO FORMULAS NOW AGREE, AND THE WORDINGS MUST STILL NOT. An earlier version of
        // this comment made the distinction conditional on the formulas differing; they no longer
        // do, and that is NOT a licence to merge the prefixes. These remain two different
        // decisions — a breaker that stops a crawl mid-run, and a health verdict on a finished
        // one — and every existing grep of production logs separates them by this prefix. Merging
        // them would silently fold two populations into one count.
        statusMessage = `Error rate over threshold (${(errorRate * 100).toFixed(1)}%, ${errors} errors)`;
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
    // incremented, keeping 'processed' low — but it also increments 'accounted'
    // (UpdateChecker.ts CASE 1, 404/410), and the sample gate above is a DISJUNCTION
    // (processed OR coverage). A corpus that 404s in full still reaches
    // coverage >= minCoverage on 'accounted' alone, so it clears the sample gate with
    // processed=0: CASE 1's low 'processed' does NOT keep such a run out. CASE 3 does
    // not share even that low-'processed' property either way — it runs after the
    // increment, so those URLs are counted in both 'errors' and 'processed'. Either
    // way, THIS guard — corpus-relative and independent of 'processed' — is what
    // actually catches a mass-404 restructure (incident 636-389-1783326914); the
    // sample gate above does not.
    // Only HEALTHY and PENDING_SAMPLE are overridden: WARNING and CRITICAL already
    // block and carry a more specific reason. Do NOT widen this.
    if (previousTotal > 0 && errors / previousTotal > 0.5
        && (status === "HEALTHY" || status === "PENDING_SAMPLE")) {
        status = "SUSPECT";
        statusMessage = `Deleted/error volume (${errors}) exceeds 50% of previous corpus (${previousTotal})`;
    }

    return { status, statusMessage, disabledSignals };
}
