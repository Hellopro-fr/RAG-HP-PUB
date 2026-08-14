import axios, { AxiosInstance, AxiosError } from "axios";
import pLimit from "p-limit";

// Local alias for the p-limit instance type. The installed p-limit version
// exports its types via the `pLimit.Limit` namespace (CommonJS `export =`),
// so `LimitFunction` is not directly importable. `ReturnType<typeof pLimit>`
// resolves to the same `Limit` interface and stays in sync if the dep is
// upgraded to the named-export variant.
type PLimitInstance = ReturnType<typeof pLimit>;

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
    validateAlternatives?: boolean;
}

export interface CheckUrlResult {
    ok: boolean;
    method: string;
    url?: string;
    original_url?: string;
}

export class DetectionLangueClient {
    private client: AxiosInstance;
    private limit: PLimitInstance;
    private maxRetries: number;
    private backoffBaseS: number;
    /**
     * Configured detect-API concurrency cap. Cached at construction time so
     * `pLimit(maxConcurrency)` and the public `maxConcurrency` accessor stay
     * in sync even if the env var mutates at runtime.
     */
    public readonly maxConcurrency: number;

    constructor(baseUrl?: string) {
        const url =
            baseUrl ||
            process.env.DETECTION_LANGUE_API_URL ||
            "http://api-detection-langue-fr-service:8999";
        if (!baseUrl && !process.env.DETECTION_LANGUE_API_URL) {
            console.warn('DETECTION_LANGUE_API_URL not set, using default: http://api-detection-langue-fr-service:8999');
        }

        const timeoutMs = parseInt(process.env.DETECTION_REQUEST_TIMEOUT_S ?? "180") * 1000;
        this.maxConcurrency = parseInt(process.env.DETECTION_MAX_CONCURRENCY ?? "5");
        this.maxRetries = parseInt(process.env.DETECTION_MAX_RETRIES ?? "2");
        this.backoffBaseS = parseFloat(process.env.DETECTION_BACKOFF_BASE_S ?? "2");

        this.client = axios.create({
            baseURL: `${url}/api/v1`,
            timeout: timeoutMs,
        });
        this.limit = pLimit(this.maxConcurrency);
    }

    /**
     * Returns the underlying p-limit instance for observability
     * (pendingCount, activeCount). Read-only — do not call it.
     */
    get limiter(): Pick<PLimitInstance, "pendingCount" | "activeCount"> {
        return this.limit;
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
                    validate_alternatives: options?.validateAlternatives ?? undefined,
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
     * Returns true if the method denotes a TECHNICAL FAILURE — the absence of a
     * verdict — and false if it denotes a linguistic judgement. "The detection did
     * not answer" must never be laundered into "the site is not French".
     *
     * Closed set, with each member's reachability on the crawler's own calls:
     *   - `challenge_page`      REACHABLE — the service's challenge classifier runs
     *                           on *provided* html, ahead of the decision matrix.
     *   - `error`               REACHABLE — the service's generic exception handler
     *                           answers HTTP 200 carrying this method.
     *   - `fetch_empty_content` REACHABLE — the N1 guard returns it in place of a
     *                           negative verdict on a page with no visible text.
     *   - `admission_rejected`  **NOT REACHABLE TODAY.** The crawler always sends
     *                           `html_content`, which bypasses the service's
     *                           admission control, so no crawler call can observe
     *                           it — do not read its presence here as evidence that
     *                           production sees it. It is here on purpose: a
     *                           service saturation is never a property of the site,
     *                           and if a future change ever routes the crawler
     *                           through admission, the silent laundering would come
     *                           back with nobody re-reading this predicate. The
     *                           service already classes it `_NEVER_CACHE_METHODS`.
     *
     * The service's other technical methods (`soft_404`, `redirected_to_home`,
     * `http_error`, `http_error_transient`, `fetch_failed`) are deliberately absent:
     * they are produced only inside `if not html_was_provided`, so they cannot reach
     * the crawler. Do not add them "just in case" — the set has to stay readable as
     * the verifiable claim it is.
     *
     * **Membership after `+`-split, NOT strict equality.** `method` is `+`-composed
     * (`direct_match+langHtml+nlp_confirmed`, `…+variant_rescue`) and this predicate
     * is handed the raw string, before any `extractPrimaryMethod` pass. Every member
     * above is returned bare today, so equality would also work — the choice is
     * about which way to be wrong when that stops being true. A composed technical
     * method read as a verdict re-opens the false `not_french` stamp and the
     * update-mode deletion claim (silent, destructive). A composed method wrongly
     * read as technical only costs crawl budget on a non-French site (visible as a
     * drop in `filtered_nonfr`, and it claims no deletion). Split-membership errs on
     * the recoverable side, and it reads a part found *anywhere* in the split just
     * as `extractPrimaryMethod` (`:170-176`) already does.
     */
    static isTechnicalFailureMethod(method: string): boolean {
        if (!method) return false;
        const TECHNICAL_FAILURE_METHODS = [
            "challenge_page",
            "error",
            "fetch_empty_content",
            "admission_rejected",
        ];
        return method.split("+").some((p) => TECHNICAL_FAILURE_METHODS.includes(p));
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
     * Remove from a URL the language query param **we injected ourselves**, so the
     * `?`-counting machinery never observes it.
     *
     * Why (a category error, not a cosmetic detail): `transformRequestFunction`
     * (`routes.ts:1116`) appends `context.languageQueryParam` to every discovered
     * internal URL, so on a session-i18n site every page then loads carrying a `?`.
     * The `?` machinery — `countQuestionMark`, the facet-variant cap, the tier-1
     * observer, the tier-2 engine — exists to detect a faceted-navigation explosion,
     * i.e. an unbounded parameter space *the site* generates. A parameter the crawler
     * added is not a facet, so counting it measures our own behaviour, not the site's.
     *
     * And it is not merely noisy: `shouldStopForQuestionMark` (`functions.ts:907`) ends
     * the crawl with `isError=limitQuestionMark` at 100 such pages, and BOTH of its
     * escape hatches default to **false** — `bypassQuestionMark` and `skipQuestionMark`
     * (`context.ts:41-43`, `main.ts:104-106`). The stop is therefore live in the default
     * configuration, and without this strip the very sites the injection was written to
     * rescue would stop early because of the rescue.
     *
     * Strips on an exact key AND value match only, so a site's own `?lang=de` still
     * counts as the site's own parameter. (A site's own `?lang=fr` is byte-identical to
     * our injection and cannot be told apart without carrying provenance per request —
     * accepted: it costs at most the seed page out of a 100 budget.)
     *
     * Returns the URL with no `?` at all when nothing else remains, and returns the
     * input **unchanged** for a null param, a query-less URL, an absent or
     * different-valued param, and an unparseable URL — this runs on every page, so it
     * must never throw.
     */
    static stripInjectedLanguageParam(
        url: string,
        param: { key: string; value: string } | null,
    ): string {
        if (!param || !url.includes("?")) return url;
        try {
            const urlObj = new URL(url);
            if (urlObj.searchParams.get(param.key) !== param.value) return url;
            // Two-arg delete: on the exotic `?lang=fr&lang=de` it drops only our pair.
            urlObj.searchParams.delete(param.key, param.value);
            return urlObj.toString();
        } catch {
            // Invalid URL — leave it alone; over-counting is safer than throwing here.
            return url;
        }
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

        // Locale codes are case-insensitive per BCP-47 (e.g. "fr-FR"). The detection
        // API may surface detectResult.url normalized to lowercase ("/fr-fr") while an
        // alternative_urls entry keeps the raw hreflang casing ("/fr-FR"). Compare the
        // skip prefixes case-insensitively so the winner/seed locale is never excluded
        // by mere casing drift. excluded[] keeps each alt's ORIGINAL casing so the
        // downstream isExcludedRegionalPath gate still matches the served link paths.
        const winnerPrefixLc = winnerPrefix?.toLowerCase() ?? null;
        const seedPrefixLc = seedPrefix?.toLowerCase() ?? null;
        const implicitWinnerPrefixLc = implicitWinnerPrefix?.toLowerCase() ?? null;

        for (const alt of alternativeUrls) {
            const altPrefix = DetectionLangueClient.extractPathPrefix(alt.url);
            const altPrefixLc = altPrefix?.toLowerCase() ?? null;
            if (
                !altPrefix ||
                altPrefixLc === winnerPrefixLc ||
                altPrefixLc === seedPrefixLc ||
                altPrefixLc === implicitWinnerPrefixLc
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
