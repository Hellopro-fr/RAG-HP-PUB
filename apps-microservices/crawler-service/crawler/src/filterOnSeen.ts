/**
 * Queue-purge #2: a query param is a "filter" when removing it yields a base URL
 * already crawled (present in seenBases). Structural — no content comparison.
 * Meaningful-optional params (lang/currency/...) AND pagination params (page/paged/...)
 * never trigger — removing a pagination param would collapse page 2+ onto the seen
 * page 1 and drop real content (parity with facetCap's variantSignature exclusion).
 */
import { baseKeyWithout, baseKeyAbsent, PAGINATION_PARAMS } from "./urlBase.js";

export const MEANINGFUL_OPTIONAL_PARAMS = ["lang", "hl", "devise", "currency", "region"];

/** The seen base this url would collapse onto by removing one non-allowlisted param, else null. */
export const filterParamCollapseTarget = (url: string, seenBases: Set<string>): string | null => {
    if (seenBases.size === 0) return null;
    let params: string[];
    try { params = Array.from(new URL(url).searchParams.keys()); } catch { return null; }
    const self = baseKeyAbsent(url);
    const allow = new Set([...MEANINGFUL_OPTIONAL_PARAMS, ...PAGINATION_PARAMS].map((s) => s.toLowerCase()));
    for (const p of params) {
        if (allow.has(p.toLowerCase())) continue;
        const b = baseKeyWithout(url, p);
        if (b !== self && seenBases.has(b)) return b;
    }
    return null;
};

export const isFilterParam = (url: string, seenBases: Set<string>): boolean =>
    filterParamCollapseTarget(url, seenBases) !== null;
