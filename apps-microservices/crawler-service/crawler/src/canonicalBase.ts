/**
 * Canonicalization helpers for the end-of-crawl content-dedup pass. Pure +
 * Crawlee-free (tsx-testable). Reuses PAGINATION_PARAMS so pagination is never
 * merged away by grouping.
 */
import { PAGINATION_PARAMS } from "./urlBase.js";

/** URL without its #fragment. No '#' -> unchanged. */
export const stripFragment = (url: string): string => {
  const i = url.indexOf("#");
  return i === -1 ? url : url.slice(0, i);
};

/**
 * Grouping key: origin + path + ONLY pagination params (sorted). Fragment and
 * all non-pagination query are dropped, so ?facet/?utm/?sid/#frag variants of a
 * path share a key while ?page=N keeps its own. Parse-fail -> stripFragment(url).
 */
export const canonicalGroupKey = (url: string): string => {
  try {
    const u = new URL(url);
    const kept = new URLSearchParams();
    for (const p of PAGINATION_PARAMS) {
      for (const v of u.searchParams.getAll(p)) kept.append(p, v);
    }
    kept.sort();
    const qs = kept.toString();
    return u.origin + u.pathname + (qs ? `?${qs}` : "");
  } catch {
    return stripFragment(url);
  }
};

/** Query-param count (survivor tie-break: fewer = more canonical). Parse-fail -> Infinity. */
export const queryParamCount = (url: string): number => {
  try { return [...new URL(url).searchParams].length; } catch { return Infinity; }
};

/**
 * Read the __collapsed_urls.json sidecar in either shape: the current
 * {collapsedUrl: survivorUrl} map, or the legacy string array (survivor unknown
 * → ""). Anything else → empty map. Keys are always the collapsed URLs, so
 * Object.keys() is the update-baseline list and values feed survivor-aware
 * consumers (BO rename/doublon path).
 */
export const parseCollapsedSidecar = (raw: unknown): Record<string, string> => {
  const out: Record<string, string> = {};
  if (Array.isArray(raw)) {
    for (const u of raw) if (typeof u === "string" && u) out[u] = "";
  } else if (raw && typeof raw === "object") {
    for (const [collapsed, survivor] of Object.entries(raw as Record<string, unknown>)) {
      if (collapsed) out[collapsed] = typeof survivor === "string" ? survivor : "";
    }
  }
  return out;
};

/** Feature flag: extend content-collision pass to ?param canonical dedup. Default off. */
export const canonicalDedupEnabled = (): boolean =>
  (process.env.DATASET_CANONICAL_DEDUP_ENABLED ?? "false").toLowerCase() === "true";
