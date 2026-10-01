/**
 * Crawlee-free URL base-key helpers. Single home so facetCap / filterOnSeen /
 * questionMarkTier2 share one canonicalization and stay tsx-testable.
 */
export const PAGINATION_PARAMS = ["page", "p", "paged", "start", "offset"];

/**
 * The query keys `DetectionLangueClient.extractLanguageQueryParam` can elect — hence the exact
 * set the `?lang=fr` propagation can inject, and the set the `?`-machinery must never remove:
 * stripping one mid-crawl undoes the propagation on the session-i18n sites it rescues.
 *
 * Single definition, three consumers: `DetectionLangueClient.extractLanguageQueryParam` (which
 * elects them), `questionMarkTier2.candidateParams` (tier-2 sampling) and
 * `questionMarkDecision.readQmPersistedDecision` (OOM-relaunch rehydration).
 *
 * It lives HERE and not next to `extractLanguageQueryParam` for a measured reason:
 * `DetectionLangueClient` imports `p-limit@5`, which is ESM-only, and both `questionMarkTier2`
 * and `questionMarkDecision` are loaded through `createRequire` (CJS) by their siblings — a
 * transitive p-limit import there fails with ERR_INVALID_URL_SCHEME. This module is
 * dependency-free by design, which is what makes it importable from both worlds.
 *
 * NOT the same list as `filterOnSeen.MEANINGFUL_OPTIONAL_PARAMS`: that one serves a different
 * filter, omits `locale`/`language`, and carries `devise`/`currency`/`region`.
 */
export const LANGUAGE_PARAMS: readonly string[] = ["lang", "locale", "language", "hl"];

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
