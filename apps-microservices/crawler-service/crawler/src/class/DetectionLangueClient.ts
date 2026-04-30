import axios, { AxiosInstance, AxiosError } from "axios";
import pLimit from "p-limit";

export interface AlternativeUrl {
    url: string;
    method: string;
    reliability: "high" | "medium" | "low";
    validated: boolean;
    region_priority?: number; // 0=France (fr-FR), 1=generic (/fr), 2=other region (fr-CA, fr-BE)
}

export interface DetectionResult {
    ok: boolean;
    method: string;
    url?: string;
    confidence?: number;
    alternative_urls?: AlternativeUrl[];
    error?: string;
}

export interface DetectOptions {
    mode?: "simple" | "complete";
    forcedMethod?: string;
    useNlpDetection?: boolean;
    proxyUrl?: string;
}

export interface CheckUrlResult {
    ok: boolean;
    method: string;
    url?: string;
    original_url?: string;
}

export class DetectionLangueClient {
    private client: AxiosInstance;
    private limit: ReturnType<typeof pLimit>;
    private maxRetries: number;
    private backoffBaseS: number;

    constructor(baseUrl?: string) {
        const url =
            baseUrl ||
            process.env.DETECTION_LANGUE_API_URL ||
            "http://api-detection-langue-fr-service:8999";
        if (!baseUrl && !process.env.DETECTION_LANGUE_API_URL) {
            console.warn('DETECTION_LANGUE_API_URL not set, using default: http://api-detection-langue-fr-service:8999');
        }

        const timeoutMs = parseInt(process.env.DETECTION_REQUEST_TIMEOUT_S ?? "180") * 1000;
        const maxConcurrency = parseInt(process.env.DETECTION_MAX_CONCURRENCY ?? "5");
        this.maxRetries = parseInt(process.env.DETECTION_MAX_RETRIES ?? "2");
        this.backoffBaseS = parseFloat(process.env.DETECTION_BACKOFF_BASE_S ?? "2");

        this.client = axios.create({
            baseURL: `${url}/api/v1`,
            timeout: timeoutMs,
        });
        this.limit = pLimit(maxConcurrency);
    }

    /**
     * Full detection: URL patterns + HTML content + NLP (optional).
     * Pass the HTML already fetched by the crawler to avoid double-fetch.
     */
    async detect(
        url: string,
        htmlContent?: string,
        options?: DetectOptions
    ): Promise<DetectionResult> {
        return this.limit(() => this._detectWithRetry(url, htmlContent, options));
    }

    private async _detectWithRetry(
        url: string,
        htmlContent?: string,
        options?: DetectOptions
    ): Promise<DetectionResult> {
        for (let attempt = 0; attempt <= this.maxRetries; attempt++) {
            try {
                const response = await this.client.post<DetectionResult>("/detect", {
                    url,
                    html_content: htmlContent || undefined,
                    mode: options?.mode ?? "complete",
                    forced_method: options?.forcedMethod ?? undefined,
                    use_nlp_detection: options?.useNlpDetection ?? true,
                    proxy_url: options?.proxyUrl ?? undefined,
                });
                return response.data;
            } catch (error: any) {
                const axiosErr = error as AxiosError;
                const status = axiosErr.response?.status;

                if (status === 503 && attempt < this.maxRetries) {
                    const retryAfterHeader = axiosErr.response?.headers?.["retry-after"];
                    const waitS = retryAfterHeader
                        ? parseFloat(String(retryAfterHeader))
                        : this.backoffBaseS * Math.pow(2, attempt);
                    console.warn(
                        `DetectionLangueClient got 503 for ${url} ` +
                        `(attempt ${attempt + 1}/${this.maxRetries + 1}); ` +
                        `waiting ${waitS}s before retry`
                    );
                    await new Promise((resolve) => setTimeout(resolve, waitS * 1000));
                    continue;
                }

                const message = (axiosErr.response?.data as any)?.detail || axiosErr.message || String(error);
                throw new Error(`Detection API error for ${url}: ${message}`);
            }
        }
        throw new Error(`Detection API retry loop exited without result for ${url}`);
    }

    /**
     * Fast URL-only check (no HTML fetch, no NLP).
     * Equivalent to the old DomainFR.checkUrl(url, false).
     */
    async checkUrl(
        url: string,
        trackRedirect: boolean = false
    ): Promise<CheckUrlResult> {
        return this.limit(async () => {
            try {
                const response = await this.client.get<CheckUrlResult>("/check-url", {
                    params: { url, track_redirect: trackRedirect },
                });
                return response.data;
            } catch (error: any) {
                const message = error?.response?.data?.detail || error?.message || String(error);
                throw new Error(`Detection API check-url error for ${url}: ${message}`);
            }
        });
    }

    /**
     * Extract the primary detection method from a combined API method string.
     * Prefers HTML-based methods (langHtml, matchMeta, matchHttpEquiv) over
     * URL-based ones (direct_match, pattern_match_*), because HTML methods
     * are the only ones that forced_method can validate on internal pages.
     *
     * e.g. "direct_match+langHtml+nlp_confirmed" -> "langHtml"
     *      "langHtml+nlp_confirmed"               -> "langHtml"
     *      "direct_match+nlp_confirmed"            -> "direct_match"
     *      "nlp_confirmed"                         -> "nlp_confirmed"
     */
    static extractPrimaryMethod(method: string): string {
        if (!method) return "";
        const parts = method.split("+");
        const HTML_METHODS = ["langHtml", "matchMeta", "matchHttpEquiv"];
        const htmlMethod = parts.find((p) => HTML_METHODS.includes(p));
        return htmlMethod ?? parts[0];
    }

    /**
     * Returns true if the stored method is NOT an HTML-based method,
     * meaning forced_method validation won't work on internal pages
     * and NLP must be used instead.
     *
     * Uses a whitelist of the 3 HTML methods (closed set) rather than
     * a blacklist of non-HTML methods (open-ended, fragile).
     */
    static requiresNlpValidation(method: string): boolean {
        const HTML_METHODS = ["langHtml", "matchMeta", "matchHttpEquiv"];
        return !HTML_METHODS.includes(method);
    }

    /**
     * Extract the language query parameter from a URL.
     * Used for session-based i18n sites where the homepage has ?lang=fr
     * (method: pattern_match_query) but internal pages don't carry the param.
     *
     * Checks common language param names: lang, locale, language, hl.
     * Returns { key, value } if found with a French value, null otherwise.
     *
     * e.g. "http://www.awassos.com/index.php?lang=fr" -> { key: "lang", value: "fr" }
     */
    static extractLanguageQueryParam(
        url: string
    ): { key: string; value: string } | null {
        try {
            const urlObj = new URL(url);
            const LANGUAGE_PARAMS = ["lang", "locale", "language", "hl"];

            for (const param of LANGUAGE_PARAMS) {
                const value = urlObj.searchParams.get(param);
                if (value && /^fr/i.test(value)) {
                    return { key: param, value };
                }
            }
        } catch {
            // Invalid URL — ignore
        }
        return null;
    }

    /**
     * Extract the first path segment from a URL.
     * Used to identify regional path prefixes for exclusion filtering.
     *
     * e.g. "https://www.manitou.com/fr-FR/products" -> "/fr-FR"
     *      "https://www.manitou.com/fr/"             -> "/fr"
     *      "https://www.manitou.com/"                -> null (root)
     */
    static extractPathPrefix(url: string): string | null {
        try {
            const pathname = new URL(url).pathname;
            const cleaned = pathname.replace(/\/+$/, "");
            if (!cleaned || cleaned === "") return null;
            const firstSegment = cleaned.split("/").filter(Boolean)[0];
            return firstSegment ? `/${firstSegment}` : null;
        } catch {
            return null;
        }
    }

    /**
     * Check if a URL's path starts with any excluded regional prefix.
     * Matching rule: prefix must match exactly or be followed by "/".
     * e.g. prefix "/fr-BE" matches "/fr-BE", "/fr-BE/", "/fr-BE/products"
     *      but NOT "/fr-BEL/" or "/france/".
     */
    static isExcludedRegionalPath(url: string, excludedPrefixes: string[]): boolean {
        if (excludedPrefixes.length === 0) return false;
        try {
            const pathname = new URL(url).pathname;
            return excludedPrefixes.some(
                prefix => pathname === prefix || pathname.startsWith(prefix + "/")
            );
        } catch {
            return false;
        }
    }

    /**
     * Returns true only for path prefixes shaped like a locale regional variant.
     *
     * Accepted shapes (case-insensitive):
     *   /fr, /fr/, /fr-FR, /fr-FR/, /fr_FR, /fr_FR/, /fr-be, /en, /en-GB, /de-DE, /es, /es-ES, etc.
     *
     * Rejected shapes:
     *   /nos-realisations, /produits, /a-propos, "", "/"
     *
     * Pattern: starts with "/", followed by 2-letter language code, optionally followed by
     *   ("-" or "_") + 2-4 letter region code. Optional trailing slash. No further path content.
     *
     * Used as a belt-and-braces gate before adding alt URL prefixes returned by the detection
     * API to `excludedRegionalPaths`, so a malformed hreflang declaration cannot drop content
     * sections. Guards SHAPE, not language — accepts all 2-letter language codes.
     */
    static isLocalePathPrefix(prefix: string): boolean {
        if (!prefix) return false;
        return /^\/[a-z]{2}([-_][a-z]{2,4})?\/?$/i.test(prefix);
    }

    /**
     * Compute the set of regional path prefixes to exclude during crawling, given the
     * homepage's `alternative_urls` and the winner/seed locale prefixes.
     *
     * For each alternative URL, extract its path prefix and add it to `excluded` iff:
     *   - the prefix differs from the winner's prefix (the locale we picked), and
     *   - the prefix differs from the seed's prefix (the URL the user requested), and
     *   - the prefix passes `isLocalePathPrefix` (belt-and-braces shape gate).
     *
     * Prefixes that fail the shape gate are returned in `rejected` alongside the source
     * URL so the caller can log them. Caller handles all logging — this helper is pure.
     *
     * Result `excluded` is deduped (each prefix appears at most once).
     *
     * **Implicit winner branch:** when both `winnerPrefix` and `seedPrefix` are
     * null (homepage at site root), the FR-shaped alt with the lowest
     * `region_priority` (undefined treated as worst) is treated as an implicit
     * winner and skipped. This prevents excluding the canonical /fr/ content
     * tree when the site exposes it via hreflang on a root-served homepage.
     * Other-locale alts (e.g., /de, /en) are still excluded.
     */
    static computeExcludedRegionalPaths(
        alternativeUrls: AlternativeUrl[],
        winnerPrefix: string | null,
        seedPrefix: string | null,
    ): { excluded: string[]; rejected: { prefix: string; sourceUrl: string }[] } {
        const excluded: string[] = [];
        const rejected: { prefix: string; sourceUrl: string }[] = [];

        // When the homepage is at the site root, the canonical FR content tree
        // (e.g., /fr/) is exposed via hreflang as an alternative URL. Treating it
        // as a non-winning alternate (and therefore excluding it) drops every
        // /fr/* link from the crawl. Detect this case by picking the FR-shaped
        // alt with the lowest region_priority as the implicit winner.
        let implicitWinnerPrefix: string | null = null;
        if (winnerPrefix === null && seedPrefix === null) {
            const FR_PREFIX_PATTERN = /^\/fr([-_][a-z]{2,4})?\/?$/i;
            const candidates: { prefix: string; priority: number }[] = [];
            for (const alt of alternativeUrls) {
                const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
                if (!altPrefix) continue;
                if (!FR_PREFIX_PATTERN.test(altPrefix)) continue;
                // undefined region_priority sorts last (treated as worst)
                const priority = alt.region_priority ?? Number.MAX_SAFE_INTEGER;
                candidates.push({ prefix: altPrefix, priority });
            }
            if (candidates.length > 0) {
                // Stable sort: lowest priority first, ties keep original order.
                candidates.sort((a, b) => a.priority - b.priority);
                implicitWinnerPrefix = candidates[0].prefix;
            }
        }

        for (const alt of alternativeUrls) {
            const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
            if (
                !altPrefix ||
                altPrefix === winnerPrefix ||
                altPrefix === seedPrefix ||
                altPrefix === implicitWinnerPrefix
            ) {
                continue;
            }
            if (!DetectionLangueClient.isLocalePathPrefix(altPrefix)) {
                rejected.push({ prefix: altPrefix, sourceUrl: alt.url });
                continue;
            }
            if (!excluded.includes(altPrefix)) {
                excluded.push(altPrefix);
            }
        }

        return { excluded, rejected };
    }
}
