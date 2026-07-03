/**
 * Crawlee-free URL base-key helpers. Single home so facetCap / filterOnSeen /
 * questionMarkTier2 share one canonicalization and stay tsx-testable.
 */
export const PAGINATION_PARAMS = ["page", "p", "paged", "start", "offset"];

/** origin + pathname; drops query + fragment. Parse-fail -> original url. */
export const pathBaseKey = (url: string): string => {
    try { const u = new URL(url); return u.origin + u.pathname; } catch { return url; }
};

/** Sorted query string, pagination params removed. Parse-fail -> "". */
export const variantSignature = (url: string): string => {
    try {
        const u = new URL(url);
        for (const p of PAGINATION_PARAMS) u.searchParams.delete(p);
        u.searchParams.sort();
        return u.searchParams.toString();
    } catch { return ""; }
};

/** URL with param p removed, remaining params sorted. Parse-fail -> url. */
export const baseKeyWithout = (url: string, p: string): string => {
    try { const u = new URL(url); u.searchParams.delete(p); u.searchParams.sort(); return u.toString(); }
    catch { return url; }
};

/** URL with params sorted (nothing removed). Parse-fail -> url. */
export const baseKeyAbsent = (url: string): string => {
    try { const u = new URL(url); u.searchParams.sort(); return u.toString(); }
    catch { return url; }
};

export const hasParam = (url: string, p: string): boolean => {
    try { return new URL(url).searchParams.has(p); } catch { return false; }
};
