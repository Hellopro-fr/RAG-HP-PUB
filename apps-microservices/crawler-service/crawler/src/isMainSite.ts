/**
 * True when a request URL is the crawl's seed ("main site"), fragment-insensitive.
 *
 * `site` is the raw --site arg and may carry a `#fragment` (e.g. a homepage picked from
 * a detector alternative such as `/fr/privacy-policy#anchor`), but Crawlee strips the
 * fragment from `request.url` (keepUrlFragment defaults false). A raw
 * `request.url === site` then wrongly returns false, so the seed is handled as an
 * internal page and its homepage-only "Page non détectée en Français" verdict is lost.
 * ponytail: fragment-only normalization — the exact `===` already matched every
 * non-fragment homepage; widen only for the observed break, nothing else.
 */
const stripFragment = (u: string): string => u.split("#")[0];

export const matchesMainSite = (requestUrl: string, site: string): boolean =>
    stripFragment(requestUrl) === stripFragment(site);
