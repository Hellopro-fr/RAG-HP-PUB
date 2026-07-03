/**
 * Queue-purge #1: per-base facet-variant cap. Content-agnostic backstop — once a
 * base path has accumulated K distinct query-signatures, further variants are
 * skipped. In-memory Map, size-capped to bound memory under a trap.
 */
import { pathBaseKey, variantSignature } from "./urlBase.js";

export const QM_FACET_ENABLED =
    (process.env.QM_FACET_ENABLED ?? "false").toLowerCase() === "true";

export const QM_FACET_CAP_K = (() => {
    const n = parseInt(process.env.QM_FACET_CAP_K ?? "30", 10);
    return Number.isFinite(n) && n > 0 ? n : 30;
})();

const MAX_BASES = 5000; // bound the outer map under a many-base trap

/** Record this url's variant signature under its base. No-op for query-less urls. */
export const recordVariant = (map: Map<string, Set<string>>, url: string): void => {
    const sig = variantSignature(url);
    if (!sig) return;
    const base = pathBaseKey(url);
    let set = map.get(base);
    if (!set) {
        if (map.size >= MAX_BASES) return;
        set = new Set<string>();
        map.set(base, set);
    }
    if (set.size < 10000) set.add(sig);
};

/** True iff the url's base already holds >= k distinct signatures. */
export const isOverCap = (map: Map<string, Set<string>>, url: string, k: number): boolean => {
    if (!variantSignature(url)) return false;
    const set = map.get(pathBaseKey(url));
    return !!set && set.size >= k;
};
