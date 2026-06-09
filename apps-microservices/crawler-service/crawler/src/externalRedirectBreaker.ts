/**
 * External-redirect breaker decision (update mode).
 *
 * A "external redirect" is a seeded URL whose final loaded host is off-domain
 * (routes.ts external-redirect guard). When all/most seeded URLs are external
 * redirects, the supplier site has relocated — abort and fail rather than
 * waste a full re-crawl and report a misleading success.
 *
 * Denominator = external + processed (internal pages that entered the breaker
 * block). Blocked-status throws / content-type skips are intentionally excluded,
 * making the ratio slightly more sensitive — acceptable at the 0.90 default.
 *
 * Pure function (no Crawlee/Redis) so it is unit-testable in isolation.
 */
export interface ExternalRedirectBreakerConfig {
    externalRedirectMinSample: number;
    maxExternalRedirectRate: number;
}

export function shouldTripExternalRedirectBreaker(
    external: number,
    processed: number,
    cfg: ExternalRedirectBreakerConfig,
): { trip: boolean; reason: string } {
    const denom = external + processed;
    if (denom < cfg.externalRedirectMinSample) {
        return { trip: false, reason: `below sample gate (${denom}/${cfg.externalRedirectMinSample})` };
    }
    const ratio = external / denom;
    if (ratio >= cfg.maxExternalRedirectRate) {
        return {
            trip: true,
            reason: `external-redirect ratio ${(ratio * 100).toFixed(1)}% >= ${(cfg.maxExternalRedirectRate * 100).toFixed(0)}% (external=${external}, processed=${processed})`,
        };
    }
    return { trip: false, reason: `external-redirect ratio ${(ratio * 100).toFixed(1)}% below threshold` };
}
