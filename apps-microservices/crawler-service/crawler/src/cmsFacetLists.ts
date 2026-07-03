/**
 * Queue-purge CMS denylist: per-CMS-label cosmetic facet params, strip-if-present.
 * Curated to UNIVERSALLY-COSMETIC facets only; identity params deliberately excluded.
 * Empty/unknown label -> [] (no fallback list). Label is coarse ("WordPress", not
 * "WooCommerce") so the WordPress list carries the WooCommerce facets — harmless on a
 * non-Woo blog (params never present).
 */
const LISTS: Record<string, string[]> = {
    wordpress: ["min_price", "max_price", "stock_status", "sale_status", "orderby"],
    prestashop: ["q", "order", "resultsperpage", "layout"],
    magento: ["price", "product_list_order", "product_list_dir", "product_list_limit"],
    shopify: ["sort_by", "filter.v.price.gte", "filter.v.price.lte", "filter.v.availability"],
    opencart: ["sort", "order", "limit"],
};

export const facetParamsForCms = (cms: string | undefined | null): string[] => {
    if (!cms) return [];
    return LISTS[cms.trim().toLowerCase()] ?? [];
};
