/**
 * Queue-purge #2: a query param is a "filter" when removing it yields a base URL
 * already crawled (present in seenBases). Structural — no content comparison.
 * Meaningful-optional params (lang/currency/...) never trigger.
 */
import { baseKeyWithout, baseKeyAbsent } from "./urlBase.js";

export const MEANINGFUL_OPTIONAL_PARAMS = ["lang", "hl", "devise", "currency", "region"];

export const isFilterParam = (url: string, seenBases: Set<string>): boolean => {
    if (seenBases.size === 0) return false;
    let params: string[];
    try { params = Array.from(new URL(url).searchParams.keys()); } catch { return false; }
    const self = baseKeyAbsent(url);
    const allow = new Set(MEANINGFUL_OPTIONAL_PARAMS.map((s) => s.toLowerCase()));
    for (const p of params) {
        if (allow.has(p.toLowerCase())) continue;
        const b = baseKeyWithout(url, p);
        if (b !== self && seenBases.has(b)) return true;
    }
    return false;
};
