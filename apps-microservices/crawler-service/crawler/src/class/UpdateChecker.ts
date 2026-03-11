import { UrlConsolidator } from './UrlConsolidator.js';
import { StatsManager } from './StatsManager.js';
import { DomainFR } from './DomainFR.js';
import { rightTrimSlash, processUrl } from '../functions.js';

/**
 * Result returned by checkUrl for each processed page.
 */
export interface CheckUrlResult {
    action: 'deleted' | 'redirected' | 'new_url' | 'confirmed' | 'ignored';
    url: string;
    source: string;
    reason?: string;
    destination?: string;
}

/**
 * ignoredExtensions and FORBIDDEN_PARAMS — duplicated from routes.ts
 * to avoid circular imports. These are used for eligibility checks.
 */
const IGNORED_EXTENSIONS_SET = new Set([
    // archives
    "7z", "7zip", "bz2", "rar", "tar", "tar.gz", "xz", "zip",
    // images
    "mng", "pct", "bmp", "gif", "jpg", "jpeg", "png", "pst", "psp", "tif", "tiff",
    "ai", "drw", "dxf", "eps", "ps", "svg", "cdr", "ico", "webp",
    // audio
    "mp3", "wma", "ogg", "wav", "ra", "aac", "mid", "au", "aiff",
    // video
    "3gp", "asf", "asx", "avi", "mov", "mp4", "mpg", "qt", "rm", "swf", "wmv", "m4a", "m4v", "flv", "webm",
    // office suites
    "xls", "xlsx", "ppt", "pptx", "pps", "doc", "docx", "odt", "ods", "odg", "odp",
    // other
    "css", "pdf", "exe", "bin", "rss", "dmg", "iso", "apk", "xml",
]);

const FORBIDDEN_PARAMS = [
    'order', 'sort', 'dir', 'limit', 'resultsPerPage',
    'filter', 'price', 'price_min', 'price_max',
    'id_category', 'categoryId', 'productListView',
    'q', 'search', 'query', 'offset', 'start',
    'view', 'mode', 'display', 'per_page', 'items',
    'year', 'month', 'day', 'date', 'from', 'to',
    'ref', 'referrer', 'source', 'sort_by',
    'size_', 'taille_', 'color_', 'couleur_',
    'price_', 'prix_', 'brand_', 'marque_', 'type_', 'vendor_'
];

/**
 * UpdateChecker — Centralized check_url engine for Update Mode.
 *
 * Implements the decision matrix:
 *
 *                    ┌─────────────┬────────────────────────────┐
 *                    │ Source =    │ Source = Other              │
 *                    │ Dataset     │ (rq / ru / discovered)     │
 * ┌──────────────────┼─────────────┼────────────────────────────┤
 * │ HTTP Error       │ +deleted    │ Ignore                     │
 * │ (non 2xx)        │             │                            │
 * ├──────────────────┼─────────────┼────────────────────────────┤
 * │ Redirect (3xx)   │ Dest in DS? │ Dest in DS? Yes: ignore    │
 * │ url != loadedUrl │ Yes: noop   │ No: eligible? → +new_url   │
 * │                  │ No: +redir  │                            │
 * ├──────────────────┼─────────────┼────────────────────────────┤
 * │ Success (2xx)    │ Eligible?   │ Eligible? Yes → +new_url   │
 * │ url == loadedUrl │ No: +del    │ No → Ignore                │
 * │                  │ Yes: OK     │                            │
 * └──────────────────┴─────────────┴────────────────────────────┘
 *
 * Eligibility = French + ignoredExtensions + FORBIDDEN_PARAMS
 */
export class UpdateChecker {
    private consolidator: UrlConsolidator;
    private statsManager: StatsManager;

    constructor(
        consolidator: UrlConsolidator,
        statsManager: StatsManager,
    ) {
        this.consolidator = consolidator;
        this.statsManager = statsManager;
    }

    /**
     * Check if a URL has a forbidden file extension.
     */
    private hasIgnoredExtension(url: string): boolean {
        try {
            const urlObj = new URL(url);
            const pathname = urlObj.pathname;
            const lastDot = pathname.lastIndexOf('.');
            if (lastDot === -1) return false;
            const ext = pathname.substring(lastDot + 1).toLowerCase();
            return IGNORED_EXTENSIONS_SET.has(ext);
        } catch {
            return false;
        }
    }

    /**
     * Check if a URL contains any forbidden query parameter.
     */
    private hasForbiddenParams(url: string): boolean {
        try {
            const urlObj = new URL(url);
            const keys = Array.from(urlObj.searchParams.keys());
            for (const param of FORBIDDEN_PARAMS) {
                if (keys.some(key => key === param || key.startsWith(param))) {
                    return true;
                }
            }
            return false;
        } catch {
            return false;
        }
    }

    /**
     * Check if a URL is eligible to be in/enter the Dataset.
     * Criteria (all 3 must pass):
     *   1. Not an ignored extension
     *   2. No forbidden parameters
     *   3. French content (requires pageContent for full check)
     *
     * @param url - The URL to check
     * @param isFrenchContent - Whether the page content was detected as French (from DomainFR)
     */
    isEligible(url: string, isFrenchContent: boolean): boolean {
        // Check 1: Extension
        if (this.hasIgnoredExtension(url)) {
            return false;
        }

        // Check 2: Forbidden params
        if (this.hasForbiddenParams(url)) {
            return false;
        }

        // Check 3: French content
        return isFrenchContent;
    }

    /**
     * Main decision engine method. Called from routes.ts for each processed page in update mode.
     *
     * @param originalUrl - request.url (the URL as it was in the queue)
     * @param loadedUrl - request.loadedUrl (the final URL after any browser redirects)
     * @param source - The origin source of the URL (dataset / request_queue / request_url / discovered)
     * @param httpStatus - HTTP response status code
     * @param isFrenchContent - Whether the page content is French (from DomainFR)
     */
    async checkUrl(
        originalUrl: string,
        loadedUrl: string,
        source: string,
        httpStatus: number,
        isFrenchContent: boolean,
    ): Promise<CheckUrlResult> {
        const isFromDataset = source === 'dataset';
        const isHttpError = httpStatus >= 400 || httpStatus === 0;
        const isRedirect = rightTrimSlash(originalUrl) !== rightTrimSlash(loadedUrl);

        // ═══════════════════════════════════════════
        //  CASE 1: HTTP Error (non 2xx/3xx)
        // ═══════════════════════════════════════════
        if (isHttpError) {
            if (isFromDataset) {
                // Dataset URL returned an error → it should be removed
                await this.statsManager.increment("errors");
                return {
                    action: 'deleted',
                    url: originalUrl,
                    source,
                    reason: `http_error_${httpStatus}`,
                };
            } else {
                // Non-dataset URL error → just ignore, don't track
                return { action: 'ignored', url: originalUrl, source, reason: 'non_dataset_error' };
            }
        }

        // ═══════════════════════════════════════════
        //  CASE 2: Redirect (loaded URL differs from original)
        // ═══════════════════════════════════════════
        if (isRedirect) {
            const destInDataset = await this.consolidator.isInDataset(loadedUrl);

            if (isFromDataset) {
                if (destInDataset) {
                    // Redirect to another Dataset URL → the source URL becomes redundant
                    // No action needed, the destination is already tracked
                    return { action: 'confirmed', url: originalUrl, source, reason: 'redirect_to_existing' };
                } else {
                    // Redirect to a URL NOT in Dataset → track the redirection
                    await this.statsManager.increment("redirects");
                    return {
                        action: 'redirected',
                        url: originalUrl,
                        source,
                        destination: loadedUrl,
                    };
                }
            } else {
                // Non-dataset URL redirected
                if (destInDataset) {
                    // Redirects to an existing Dataset URL → ignore
                    return { action: 'ignored', url: originalUrl, source, reason: 'redirect_to_existing_dataset' };
                } else {
                    // Redirects to a new URL — check eligibility of the DESTINATION
                    if (this.isEligible(loadedUrl, isFrenchContent)) {
                        await this.statsManager.increment("new_urls");
                        return {
                            action: 'new_url',
                            url: loadedUrl,
                            source,
                            reason: 'redirect_eligible_destination',
                        };
                    }
                    return { action: 'ignored', url: originalUrl, source, reason: 'redirect_ineligible_destination' };
                }
            }
        }

        // ═══════════════════════════════════════════
        //  CASE 3: Success (2xx, no redirect)
        // ═══════════════════════════════════════════
        if (isFromDataset) {
            // Dataset URL, 2xx, same URL → check if still eligible
            if (this.isEligible(loadedUrl, isFrenchContent)) {
                // Confirmed: URL is still valid in Dataset
                return { action: 'confirmed', url: originalUrl, source };
            } else {
                // No longer eligible → mark as deleted
                await this.statsManager.increment("errors");
                return {
                    action: 'deleted',
                    url: originalUrl,
                    source,
                    reason: 'not_eligible',
                };
            }
        } else {
            // Non-dataset URL, 2xx → check if eligible for insertion
            if (this.isEligible(loadedUrl, isFrenchContent)) {
                await this.statsManager.increment("new_urls");
                return {
                    action: 'new_url',
                    url: loadedUrl,
                    source,
                    reason: 'eligible_new_content',
                };
            }
            return { action: 'ignored', url: originalUrl, source, reason: 'not_eligible' };
        }
    }
}
