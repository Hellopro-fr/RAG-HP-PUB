/**
 * Phase-2: keep the URL fragment in the dedup identity so base and base#variant
 * are crawled as distinct requests. Crawlee's default keepUrlFragment=false
 * strips the fragment from the computed uniqueKey; setting uniqueKey = the
 * fragment-bearing url overrides that. When skipDiez has already stripped '#',
 * the url carries no fragment and this is a no-op identity.
 */
export const fragmentAwareUniqueKey = (url: string): string => url;

/**
 * Drop a cosmetic empty trailing '#' ("page#" === "page", RFC 3986). Applied to
 * BOTH request.url (at enqueue) and loadedUrl (before it becomes the stored +
 * counted identity), so the browser/JS keeping a bare '#' can't inflate the diez
 * counter or pollute the dataset. Named anchors (#foo) are left for tier-1/tier-2.
 */
export const stripEmptyFragment = (url: string): string =>
    url.endsWith("#") ? url.slice(0, -1) : url;
