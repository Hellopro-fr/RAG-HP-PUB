/**
 * Phase-2: keep the URL fragment in the dedup identity so base and base#variant
 * are crawled as distinct requests. Crawlee's default keepUrlFragment=false
 * strips the fragment from the computed uniqueKey; setting uniqueKey = the
 * fragment-bearing url overrides that. When skipDiez has already stripped '#',
 * the url carries no fragment and this is a no-op identity.
 */
export const fragmentAwareUniqueKey = (url: string): string => url;
