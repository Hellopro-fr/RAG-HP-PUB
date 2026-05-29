import { createPlaywrightRouter, Dataset } from "crawlee";
// Removed circular imports from main.js (domain, skipquestionmark etc)
import {
    domain, // Keep basic exports if needed, but prefer context for config
    requestQueue,
    robots,
    site,
    storagePath,
} from "./main.js";
import {
    manageFrenchDetectionMethod,
    maskProxyUrl,
    processPage,
    processUrl,
    rightTrimSlash,
    routerDefaultHandler,
    stopCrawler,
    detectChallengePage,
    waitForChallengeResolution,
} from "./functions.js";
import { DetectionLangueClient } from "./class/DetectionLangueClient.js";
import { context } from "./context.js";
import { recordClassification, maybeCommitDecision, commitSkipDiez, commitBypassDiez } from "./diezDecision.js";
import { recordQuestionMarkObservation } from "./questionMarkDecision.js";
import { trackQmHashStatsForUrl } from "./qmHashTracker.js";
import type { PageTimingEntry } from "./timing/types.js";

export const router = createPlaywrightRouter();

/**
 * Per-request timing markers. `handlerStartAt` is captured at handler entry;
 * the rest are populated lazily by Crawlee preNav/postNav hooks (T3) and
 * inline detect-call wrappers below. Missing markers fall back to nearby
 * markers in `buildTimingEntry` so every page produces a well-formed entry,
 * even on abnormal exits before navigation completes.
 */
interface RequestTiming {
    handlerStartAt: number;
    dequeueAt?: number;     // populated by preNavigationHook (T3)
    postNavAt?: number;     // populated by postNavigationHook (T3)
    detectStartAt?: number; // populated inline before detect()
    detectEndAt?: number;   // populated inline after detect()
}

/**
 * Build a PageTimingEntry from accumulated markers. Tolerates missing markers
 * (abnormal exits before postNav, or pages that never called detect) by
 * folding the missing phase into zero — total_ms still reflects real
 * handler wall-clock time.
 */
function buildTimingEntry(
    timing: RequestTiming,
    url: string,
    detectMethod: string | undefined,
    detectOk: boolean | undefined,
): PageTimingEntry {
    const handlerEndAt = Date.now();
    const dequeueAt = timing.dequeueAt ?? timing.handlerStartAt;
    const postNavAt = timing.postNavAt ?? dequeueAt;
    const detectStartAt = timing.detectStartAt ?? postNavAt;
    const detectEndAt = timing.detectEndAt ?? detectStartAt;
    return {
        url,
        t: dequeueAt,
        wait_ms: Math.max(0, dequeueAt - timing.handlerStartAt),
        nav_ms: Math.max(0, postNavAt - dequeueAt),
        pre_detect_ms: Math.max(0, detectStartAt - postNavAt),
        detect_ms: Math.max(0, detectEndAt - detectStartAt),
        post_ms: Math.max(0, handlerEndAt - detectEndAt),
        total_ms: Math.max(0, handlerEndAt - dequeueAt),
        detect_method: detectMethod,
        detect_ok: detectOk,
    };
}

// --- Blocked URL Log Deduplication ---
// Logs each blocked URL only ONCE per crawl launch to reduce log pollution.
// Uses Redis (via DedupManager) to track blocked URLs across all instances.
// Local buffering ensures async Redis calls don't block synchronous transformRequestFunction.
// --- END Blocked URL Log Deduplication ---

const ignoredExtensions = [
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
].join("|");

// FORBIDDEN_PARAMS: If ANY of these params are present, the entire URL is REJECTED (not crawled).
// Use only for params that indicate a page variant with NO unique content (filters, sorts, pagination).
// Params that are just noise (tracking, session) belong in alwaysRemove instead (strip param, keep URL).
// NOTE: Uses startsWith matching — 'size_' blocks 'size_42', 'size_xl', etc.
const FORBIDDEN_PARAMS = [
    // === SORTING & ORDERING ===
    'sort', 'sort_by', 'order', 'dir',

    // === PAGINATION ===
    'limit', 'resultsPerPage', 'per_page', 'items',
    'offset', 'start',

    // === DISPLAY / VIEW MODE ===
    'view', 'mode', 'display', 'productListView',

    // === SEARCH (user-initiated, infinite variations) ===
    'search', 'query',

    // === PRICE & FILTER FACETS ===
    'filter', 'price', 'price_min', 'price_max',

    // === DATE FILTERS ===
    'year', 'month', 'day', 'date', 'from', 'to',

    // === FACET PREFIXES (startsWith match) ===
    'size_', 'taille_', 'color_', 'couleur_',
    'price_', 'prix_', 'brand_', 'marque_', 'type_', 'vendor_',
];

// alwaysRemove: These params are STRIPPED from the URL, but the URL is still crawled.
// Use for noise params (tracking, session, actions) that don't change page content.
// Hoisted to module-level to avoid re-instantiation on every discovered link.
const ALWAYS_REMOVE_PARAMS = [
    // === CART, WISHLIST & USER ACTIONS ===
    "add-to-cart", "add_to_cart", "addtocart",
    "add-to-compare", "add_to_compare",
    "add-to-wishlist", "add_to_wishlist", "addtowishlist",
    "remove_from_wishlist", "remove_wishlist",
    "remove_compare", "remove_item",
    "quantity", "qty",

    // === UTM (Marketing) ===
    "utm_source", "utm_medium", "utm_campaign",
    "utm_content", "utm_term", "utm_id",
    "utm_referrer", "utm_name",

    // === FACEBOOK & META ===
    "fbclid", "fb_action_ids", "fb_action_types",
    "fb_source", "fb_ref",

    // === GOOGLE ADS & ANALYTICS ===
    "gclid", "gclsrc", "dclid",
    "srsltid", "utmcct", "utmcsr", "utmcmd", "utmccn",
    "_ga", "_gid", "_gat", "_gl",

    // === HUBSPOT ===
    "hsa_acc", "hsa_cam", "hsa_grp",
    "hsa_ad", "hsa_src", "hsa_mt",
    "hsa_kw", "hsa_tgt", "hsa_ver", "hsa_net",
    "hsCtaTracking", "hsCta",

    // === MAILCHIMP ===
    "mc_cid", "mc_eid",

    // === SOCIAL MEDIA TRACKING ===
    "twclid", "li_fat_id", "msclkid",
    "igshid", "tt_medium", "tt_content",

    // === OTHER TRACKING ===
    "_openstat", "yclid", "wickedid", "_kx", "epik", "pp",
    "click_id", "transaction_id",
    "ref", "referrer", "source", "medium", "campaign",

    // === SESSION ===
    "sessionid", "session_id", "PHPSESSID",
    "sid", "s_id", "SID",

    // === AFFILIATE & MARKETING ===
    "aff_id", "affiliate", "partner",
    "coupon", "discount", "promo", "voucher",

    // === CMS INTERNALS (noise, not navigation) ===
    // WordPress
    "_wpnonce", "preview", "preview_id", "preview_nonce", "et_blog",
    // PrestaShop (non-routing params only)
    "id_product_attribute", "isolang", "id_lang",
    // Shopify (recommendation tracking only)
    "pr_prod_strat", "pr_rec_id", "pr_rec_pid", "pr_ref_pid", "pr_seq",
    "selling_plan",
    // Magento
    "___store", "___from_store",

    // === DEDUP HELPERS (same content, different presentation) ===
    // NOTE: "view", "mode", "display", "order", "sort", "resultsPerPage", "productListView"
    // are intentionally NOT listed here — they belong in FORBIDDEN_PARAMS (reject the URL entirely).
    "timestamp", "random", "nocache",
];

router.addDefaultHandler(
    async ({ request, page, enqueueLinks, log, proxyInfo, crawler, response }) => {
        // Shared detect client (Part B). Constructed once in main.ts so the
        // timing sampler observes the SAME p-limit queue (live pendingCount /
        // activeCount). Fail fast if main.ts has not initialised it — a silent
        // fallback would re-introduce the dual-client p-limit split that T4 fixes.
        const detectionClient = context.detectionClient;
        if (!detectionClient) {
            throw new Error("context.detectionClient not initialised — main.ts must construct it before the router runs");
        }

        // Per-request timing markers. dequeueAt and postNavAt may already be
        // present on request.userData when TIMING_ENABLED=true (written by the
        // Crawlee pre/postNavigationHooks installed in functions.ts). Read from
        // the SAME location the hooks write to (`request.userData._timing`),
        // not `crawlingContext.userData._timing`.
        const _timing: RequestTiming = {
            handlerStartAt: Date.now(),
            dequeueAt: (request.userData as any)?._timing?.dequeueAt,
            postNavAt: (request.userData as any)?._timing?.postNavAt,
        };
        let _detectMethod: string | undefined;
        let _detectOk: boolean | undefined;

        const proxyUrl = proxyInfo?.url || null;
        let url = request.loadedUrl;
        try {

        // Resource Blocking (Images, Fonts, Media, Binaries, etc.)
        // Uses ignoredExtensions as single source of truth for blocked file types
        const blockedExtensionsRegex = new RegExp(`\\.(${ignoredExtensions})$`, 'i');
        await page.route('**/*', (route) => {
            const req = route.request();
            const resourceType = req.resourceType();
            const reqUrl = req.url().toLowerCase();

            // Block heavy media and fonts
            if (['image', 'media', 'font', 'stylesheet'].includes(resourceType)) {
                return route.abort();
            }
            // Block download scripts and binary files (uses ignoredExtensions list)
            if (
                reqUrl.includes('download.php') ||
                reqUrl.includes('imp=1') ||
                blockedExtensionsRegex.test(reqUrl)
            ) {
                return route.abort();
            }
            return route.continue();
        });

        // If we don't check this, the crawler might start crawling the external site.
        const urlObj = new URL(url);
        const targetDomain = context.config.domain;
        const siteHostname = context.config.siteHostname;

        // Local buffer for blocked URLs to handle async Redis logging
        const blockedBuffer: { reason: string, url: string }[] = [];
        const logBlocked = (reason: string, url: string) => {
            blockedBuffer.push({ reason, url });
        };

        // Check if hostname belongs to either the target domain or the site hostname.
        // This handles cases where domain and site have different hosts
        // (e.g. domain="pmd-materiel.com", site="https://www.pmd-location.com/")
        const hostname = urlObj.hostname;
        const isInternal = (targetDomain && hostname.includes(targetDomain))
            || (siteHostname && hostname.includes(siteHostname));
        if (!isInternal) {
            log.warning(`Blocked external redirect: ${url} (Target: ${targetDomain})`);
            // Set structured error message for "1 seul URL crawlé" case: domain change
            if (request.url === site) {
                context.crawlErrorMessage = "L'URL après la page d'accueil change de domaine";
            }
            return;
        }

        let enqueueLinksExcludePath: Array<string> = [
            `**/*.@(${ignoredExtensions}){,\?*}{,\#*}`,
        ];

        // Content-Type guard: skip non-HTML responses (PDF, binary downloads, etc.)
        // This prevents Playwright from crashing on binary content served from extension-less URLs
        if (response) {
            const contentType = (response.headers()['content-type'] || '').toLowerCase();
            if (contentType && !contentType.includes('text/html') && !contentType.includes('text/plain') && !contentType.includes('application/xhtml')) {
                log.warning(`Skipping non-HTML response: ${url} (Content-Type: ${contentType})`);
                return;
            }
        }

        // Blocked Status Check
        if (response) {
            const status = response.status();
            if ([401, 403, 429, 404, 410, 423, 502, 500, 503].includes(status)) {
                log.error(`🚫 BLOCKED: HTTP ${status} on ${url}`);
                // Set structured error message for "1 seul URL crawlé" case: HTTP error on homepage
                if (request.url === site) {
                    context.crawlErrorMessage = `Erreur HTTP ${status}`;
                }
                // Delegate error tracking to UpdateChecker in update mode
                const source = request.userData.source || '';
                if (context.updateChecker && source) {
                    await context.updateChecker.checkUrl(request.url, request.loadedUrl, source, status, false);
                } else if (context.statsManager && request.userData.is_existing) {
                    // Legacy fallback for non-update mode
                    await context.statsManager.increment("errors");
                }
                // Don't process, let failedRequestHandler handle it
                throw new Error(`BLOCKED: HTTP ${status}`);
            }
        }

        // --- Circuit Breaker Check (Dual-Mode) ---
        if (context.statsManager) {
            // Track total processed for percentages (Increment for every handled page)
            // Note: This metric is cumulative across restarts via StatsManager
            await context.statsManager.increment("processed");
            
            const cb = context.config.circuitBreaker;
            
            if (cb && cb.enabled) {
                const errors = await context.statsManager.getValue("errors");
                const redirects = await context.statsManager.getValue("redirects");
                const newUrls = await context.statsManager.getValue("new_urls");
                const processed = await context.statsManager.getValue("processed");
                
                let abortReason = "";

                if (cb.isMicroMode) {
                    // --- MICRO MODE (Absolute Limits) ---
                    if (cb.maxAbsErrors > 0 && errors >= cb.maxAbsErrors) abortReason = `Too many errors for small site (${errors} >= ${cb.maxAbsErrors})`;
                    else if (cb.maxAbsRedirects > 0 && redirects >= cb.maxAbsRedirects) abortReason = `Too many redirects for small site (${redirects} >= ${cb.maxAbsRedirects})`;
                    else if (cb.maxAbsNew > 0 && newUrls >= cb.maxAbsNew) abortReason = `Too many new URLs for small site (${newUrls} >= ${cb.maxAbsNew})`;
                } else {
                    // --- STANDARD MODE (Rate Limits) ---
                    if (processed >= cb.minSample) {
                        const errorRate = errors / processed;
                        const redirectRate = redirects / processed;
                        
                        if (errorRate > cb.maxErrorRate) abortReason = `Error rate too high (${(errorRate*100).toFixed(1)}% > ${(cb.maxErrorRate*100)}%)`;
                        else if (redirectRate > cb.maxRedirectRate) abortReason = `Redirect rate too high (${(redirectRate*100).toFixed(1)}% > ${(cb.maxRedirectRate*100)}%)`;
                        
                        // Check growth relative to previous total
                        if (cb.previousTotal > 0 && (newUrls / cb.previousTotal) > cb.maxGrowthRate) {
                            abortReason = `Site growth too fast (> ${(cb.maxGrowthRate*100)}% of previous size)`;
                        }
                    }
                }

                if (abortReason) {
                    log.warning(`🛑 Circuit breaker triggered: ${abortReason}`);
                    context.stopReason = "circuitBreaker";
                    if (context.statsManager) {
                        await context.statsManager.increment("dropped_cb");
                    }
                    await stopCrawler(crawler, `Circuit breaker: ${abortReason}`);
                    return;
                }
            } else {
                // Fallback to legacy global config checks if V1 breaker is disabled
                // (Preserves backward compatibility with legacy args like --maxErrors=100)
                let breached = false;
                if (context.config.maxErrors && await context.statsManager.checkThreshold("errors", context.config.maxErrors)) breached = true;
                if (context.config.maxRedirects && await context.statsManager.checkThreshold("redirects", context.config.maxRedirects)) breached = true;
                if (context.config.maxNewUrls && await context.statsManager.checkThreshold("new_urls", context.config.maxNewUrls)) breached = true;

                if (breached) {
                    log.warning("🛑 Legacy Circuit breaker triggered! Stopping crawler.");
                    context.stopReason = "limitErrors"; 
                    await stopCrawler(crawler, "Legacy Circuit breaker triggered");
                    return;
                }
            }
        }

        log.info(`Processing ${url} ( ${request.url} ) ... (HTTP Status: ${response?.status()})`);

        // --- Deduplication & "Double Check" (Redis) ---
        let isDoublon = false;
        const source = request.userData.source || '';
        const isExisting = request.userData.is_existing || (source === 'dataset');

        // Skip Redis check for "Existing" URLs to allow re-verification in Update Mode
        if (context.dedupManager && !isExisting) {
            const isNew = await context.dedupManager.addUrl(url);
            isDoublon = !isNew;
        }
        
        // Removed early increment of "new_urls" here.
        // It is now handled inside the success block (isEnqueuingLinks) to ensure validity.

        // Option A retry-bypass: if Crawlee is retrying this request, run the
        // full extraction logic again regardless of dedup state. DedupManager
        // marked the URL as seen on the first (failed) attempt; without this
        // bypass the retry would short-circuit via the doublon guard and the
        // seed page would yield zero discovered URLs. PushedSet prevents
        // duplicate dataset rows across the retry.
        if (!isDoublon || request.retryCount > 0) {
            // Redis update handled in dedupManager
            // Local file update is heavy, skipped in V3 logic, keeping minimal or periodic in main.ts

            // Cookie consent is now injected pre-navigation in preNavigationHooks (functions.ts)

            // --- REDIRECT LOOP CLOSURE (Important Fix) ---
            // If we ended up at a different URL than requested (redirect), make sure the
            // final URL is also marked as known in Redis to prevent future re-crawling.
            if (context.dedupManager && request.url !== request.loadedUrl) {
                await context.dedupManager.addUrl(request.loadedUrl);
            }

            // --- UPDATE MODE: Redirect tracking via UpdateChecker (no inline stats) ---
            // Legacy redirect tracking is kept for backward compatibility when UpdateChecker is not active
            if (!context.updateChecker && isExisting && context.statsManager) {
                const finalUrl = rightTrimSlash(request.loadedUrl);
                const originalUrl = rightTrimSlash(request.url);
                
                if (finalUrl !== originalUrl) {
                    log.info(`Redirect detected: ${request.url} -> ${request.loadedUrl}`);
                    await context.statsManager.increment("redirects");
                }
            }

            const isMainSite = request.url === site;
            let frenchDetectionMethod: string | Error;
            let isEnqueuingLinks = false;
            let content = "";
            let title = "";

            try {
                title = await page.title();
            } catch (e) {}

            if (isMainSite) {
                // Process normally and store the method
                try {
                    content = await processPage(page, request.loadedUrl, log);
                } catch (e: any) {
                    log.error(`Failed to extract homepage content: ${e.message}`);
                    context.crawlErrorMessage = `Erreur lors de l'extraction du contenu de la page d'accueil`;
                    throw e;
                }

                // Challenge page detection: check if the content is a bot protection page
                // If detected, wait for the challenge to resolve before proceeding
                const challengeService = detectChallengePage(content);
                if (challengeService) {
                    const resolvedContent = await waitForChallengeResolution(
                        page, url, log, challengeService
                    );
                    if (resolvedContent) {
                        content = resolvedContent;
                    } else {
                        // Challenge not resolved — store in error dataset and stop
                        log.error(`Challenge ${challengeService} not resolved for main site ${url}. Aborting crawl.`);
                        let datasetName = context.config.crawleeStorageName ? `error-${context.config.crawleeStorageName}` : `error-${targetDomain}`;
                        let errorDataset = await Dataset.open(datasetName);
                        // PushedSet guard (fail-open). Truth-table equivalent to functions.ts:1635 inverted form.
                        if (!context.pushedSet || (await context.pushedSet.tryClaim(request.url))) {
                            await errorDataset.pushData({
                                id: request.id,
                                url: request.url,
                                errors: [`Challenge page ${challengeService} not resolved after 45s`],
                                proxy_used: maskProxyUrl(proxyUrl ?? undefined),
                                status_code: response?.status() || 0,
                                captcha: challengeService,
                                timestamp: new Date().toISOString()
                            });
                        }
                        context.crawlErrorMessage = `Site protégé par ${challengeService} (challenge non résolu)`;
                        await stopCrawler(crawler, `Challenge ${challengeService} not resolved for main site`);
                        return;
                    }
                }

                try {
                    _timing.detectStartAt = Date.now();
                    const detectResult = await detectionClient.detect(url, content, {
                        mode: "complete",
                        proxyUrl: proxyUrl ?? undefined,
                    });
                    _timing.detectEndAt = Date.now();
                    _detectMethod = detectResult.method;
                    _detectOk = detectResult.ok;

                    if (detectResult.ok) {
                        const primaryMethod = DetectionLangueClient.extractPrimaryMethod(detectResult.method);
                        if (!primaryMethod) {
                            log.error(`API returned ok=true but empty method for ${url}. Cannot store detection method.`);
                        } else {
                            frenchDetectionMethod = manageFrenchDetectionMethod(targetDomain as string, primaryMethod);
                            if (frenchDetectionMethod instanceof Error) {
                                log.error(`Failed to store French detection method: ${frenchDetectionMethod.message}`);
                                await stopCrawler(crawler, "Failed to store French detection method");
                                return;
                            }
                            // For session-based i18n: extract ?lang=fr from start URL
                            // so we can propagate it to discovered internal URLs
                            if (primaryMethod === "pattern_match_query") {
                                context.languageQueryParam = DetectionLangueClient.extractLanguageQueryParam(site);
                                if (context.languageQueryParam) {
                                    log.info(`Stored language query param: ${context.languageQueryParam.key}=${context.languageQueryParam.value} (will propagate to discovered URLs)`);
                                }
                            }
                            isEnqueuingLinks = true;

                            // Regional path exclusion: extract alternative paths to exclude
                            if (detectResult.alternative_urls && detectResult.alternative_urls.length > 0) {
                                // Belt-and-braces gate inside computeExcludedRegionalPaths: only
                                // accept locale-shaped prefixes (e.g. /fr-FR, /en, /de-DE). Rejects
                                // content paths like /nos-realisations that a malformed hreflang
                                // could surface, which would otherwise blanket-block a content
                                // section. Complements the API-side gate in alternative_urls
                                // assembly.
                                const winnerPrefix = DetectionLangueClient.extractPathPrefix(detectResult.url || url);
                                const seedPrefix = DetectionLangueClient.extractPathPrefix(site);
                                const { excluded, rejected } = DetectionLangueClient.computeExcludedRegionalPaths(
                                    detectResult.alternative_urls,
                                    winnerPrefix,
                                    seedPrefix,
                                );

                                for (const r of rejected) {
                                    log.info(`[REGIONAL_EXCLUSION] Rejected non-locale alt prefix: ${r.prefix} (from ${r.sourceUrl})`);
                                }

                                if (excluded.length > 0) {
                                    context.excludedRegionalPaths = excluded;
                                    log.info(`[REGIONAL_EXCLUSION] Excluded ${excluded.length} regional paths: ${excluded.join(", ")}`);
                                    // Persist to disk (re-write {domain}.json with excludedPaths)
                                    // so filtering survives crash/OOM restart
                                    manageFrenchDetectionMethod(targetDomain as string, frenchDetectionMethod as string);
                                }
                            }
                        }
                    } else {
                        // The API returns alternatives sorted by reliability (high > medium > low).
                        // We only use the best one (first element).
                        if (detectResult.alternative_urls && detectResult.alternative_urls.length > 0) {
                            const best = detectResult.alternative_urls[0];
                            log.error(`[ALTERNATIVE_URL] Homepage ${url} is NOT French, but a French alternative was found: ${best.url} (method: ${best.method}, reliability: ${best.reliability}, validated: ${best.validated})`);
                            context.crawlErrorMessage = `Homepage non détectée en Français mais une alternative en Français a été trouvée : ${best.url} (fiabilité: ${best.reliability})`;
                        }

                        // Default error message when no alternative found.
                        // Cleared below if the URL-only fallback (checkUrl) succeeds.
                        if (!context.crawlErrorMessage) {
                            log.error(`[NOT_FRENCH] Homepage ${url} is NOT French and no French alternative was found.`);
                            context.crawlErrorMessage = "Page non détectée en Français";
                        }

                        // Only fall back to URL check if NLP didn't explicitly reject.
                        // When NLP analyzed the content and said "not French", a URL pattern
                        // like .fr TLD should not override that verdict.
                        const nlpRejected = detectResult.method.includes("nlp_not_confirmed")
                            || detectResult.method.includes("nlp_override");

                        if (!nlpRejected) {
                            const checkUrlResult = await detectionClient.checkUrl(url);
                            if (checkUrlResult.ok) {
                                frenchDetectionMethod = manageFrenchDetectionMethod(targetDomain as string, checkUrlResult.method);
                                if (frenchDetectionMethod instanceof Error) {
                                    log.error(`Failed to store French detection method: ${frenchDetectionMethod.message}`);
                                    await stopCrawler(crawler, "Failed to store French detection method");
                                    return;
                                }
                                // For session-based i18n: extract ?lang=fr from start URL
                                if (checkUrlResult.method === "pattern_match_query") {
                                    context.languageQueryParam = DetectionLangueClient.extractLanguageQueryParam(site);
                                    if (context.languageQueryParam) {
                                        log.info(`Stored language query param: ${context.languageQueryParam.key}=${context.languageQueryParam.value} (will propagate to discovered URLs)`);
                                    }
                                }
                                isEnqueuingLinks = true;
                                // Clear alternative_urls error since crawl is proceeding via URL check
                                context.crawlErrorMessage = "";
                            }
                        }
                    }
                } catch (apiError: any) {
                    log.error(`Detection API error for main site ${url}: ${apiError.message}`);
                    context.crawlErrorMessage = `Erreur API de détection pour le site principal ${url}: ${apiError.message}`;
                }

            } else {
                // INTERNAL PAGE LOGIC WITH FALLBACK
                let methodOrError = manageFrenchDetectionMethod(targetDomain as string);

                if (methodOrError instanceof Error) {
                    log.warning(`French detection method not found in storage. Attempting auto-detection on current page.`);

                    // Fallback: Detect on current content via API
                    if (!content) content = await processPage(page, request.loadedUrl, log);

                    // Challenge check on internal page content
                    const internalChallenge1 = content ? detectChallengePage(content) : null;
                    if (internalChallenge1) {
                        const resolved = await waitForChallengeResolution(page, url, log, internalChallenge1);
                        if (resolved) {
                            content = resolved;
                        } else {
                            log.warning(`Challenge ${internalChallenge1} not resolved for internal page ${url}. Skipping.`);
                            isEnqueuingLinks = false;
                        }
                    }

                    try {
                        _timing.detectStartAt = Date.now();
                        const autoCheck = await detectionClient.detect(url, content, {
                            mode: "simple",
                            proxyUrl: proxyUrl ?? undefined,
                        });
                        _timing.detectEndAt = Date.now();
                        _detectMethod = autoCheck.method;
                        _detectOk = autoCheck.ok;

                        if (autoCheck.ok) {
                            const primaryMethod = DetectionLangueClient.extractPrimaryMethod(autoCheck.method);
                            if (primaryMethod) {
                                methodOrError = manageFrenchDetectionMethod(targetDomain as string, primaryMethod);
                                log.info(`Auto-detected and saved method: ${primaryMethod}`);
                            }
                        } else {
                            // Try URL check fallback
                            const checkUrlResult = await detectionClient.checkUrl(url);
                            if (checkUrlResult.ok) {
                                methodOrError = manageFrenchDetectionMethod(targetDomain as string, checkUrlResult.method);
                                log.info(`Auto-detected (URL) and saved method: ${checkUrlResult.method}`);
                            }
                        }
                    } catch (apiError: any) {
                        log.error(`Detection API error during auto-detection for ${url}: ${apiError.message}`);
                    }
                }

                if (methodOrError instanceof Error) {
                    log.error(`Could not determine French detection method for ${url}. Skipping links.`);
                    isEnqueuingLinks = false;
                } else {
                    frenchDetectionMethod = methodOrError as string;

                    if (!content) content = await processPage(page, request.loadedUrl, log);

                    // Challenge check on internal page content
                    const internalChallenge2 = content ? detectChallengePage(content) : null;
                    if (internalChallenge2) {
                        const resolved = await waitForChallengeResolution(page, url, log, internalChallenge2);
                        if (resolved) {
                            content = resolved;
                        } else {
                            log.warning(`Challenge ${internalChallenge2} not resolved for internal page ${url}. Skipping.`);
                            isEnqueuingLinks = false;
                        }
                    }

                    try {
                        const needsNlp = DetectionLangueClient.requiresNlpValidation(frenchDetectionMethod);

                        // When stored method is URL-based or NLP-only, forced_method cannot
                        // validate HTML tags → use NLP to verify actual content instead.
                        // When stored method is HTML-based, use forced_method for fast validation.
                        _timing.detectStartAt = Date.now();
                        const detectResult = await detectionClient.detect(url, content, {
                            forcedMethod: needsNlp ? undefined : frenchDetectionMethod,
                            mode: "simple",
                            useNlpDetection: needsNlp,
                            proxyUrl: proxyUrl ?? undefined,
                        });
                        _timing.detectEndAt = Date.now();
                        _detectMethod = detectResult.method;
                        _detectOk = detectResult.ok;

                        if (detectResult.ok) {
                            isEnqueuingLinks = true;
                        }
                        // No URL fallback after a clean rejection. The forced HTML detect
                        // already analyzed the lang attribute; URL TLD/path signals cannot
                        // override that verdict (aera-sa.fr/de/... leak case). API technical
                        // failures are handled by the surrounding try/catch.
                    } catch (apiError: any) {
                        log.error(`Detection API error for internal page ${url}: ${apiError.message}`);
                    }
                }
            }

            if (isEnqueuingLinks) {
                // === VALIDATED CONTENT BLOCK ===
                
                // --- UPDATE MODE: Delegate to UpdateChecker ---
                if (context.updateChecker && source) {
                    const httpStatus = response?.status() || 200;
                    const result = await context.updateChecker.checkUrl(
                        request.url,
                        request.loadedUrl,
                        source,
                        httpStatus,
                        true // Page is French (since isEnqueuingLinks = true)
                    );
                    log.info(`[UpdateChecker] ${result.action}: ${result.url} (${result.reason || ''})`);
                } else if (context.dedupManager && !isExisting) {
                    // Legacy: Count as NEW URL only if not existing AND passed validation
                    if (context.statsManager) {
                        await context.statsManager.increment("new_urls");
                        
                        // Fail Fast Check for New URLs
                        if (context.config.maxNewUrls && await context.statsManager.checkThreshold("new_urls", context.config.maxNewUrls)) {
                            log.warning("🛑 Max new URLs limit reached during processing. Stopping.");
                            context.stopReason = "limitNewUrls";
                            await stopCrawler(crawler, "Max new URLs limit reached.");
                            return;
                        }
                    }
                }

                // Mirror `?` / `#` counters into StatsManager so they appear in the
                // webhook payload (`filtered_qm` / `filtered_hash`). See qmHashTracker.ts.
                trackQmHashStatsForUrl(url, context.statsManager);

                // Track URLs with '?' and '#' for postNavigationHook limit checks
                if (url.includes('?')) {
                    context.countQuestionMark++;
                    // Tier-1 observer (spec 2026-04-17). Records domain-specific params that survived Tier-0.
                    // No-op when observation disabled (human CLI flag set).
                    recordQuestionMarkObservation(url);
                }
                if (url.includes('#')) {
                    context.countDiez++;
                    // Tier-1 auto-decision engine (spec 2026-04-17).
                    // No-op when context.diezDecisionCommitted is true (persisted decision, CLI flag, or prior commit).
                    recordClassification(url);
                    const outcome = maybeCommitDecision();
                    if (outcome === "skipDiez" && storagePath) {
                        commitSkipDiez(storagePath);
                    } else if (outcome === "bypassDiez" && storagePath) {
                        commitBypassDiez(storagePath);
                    } else if (outcome === "promoteTier2") {
                        console.log(`[diez] Tier 2 promotion triggered (phase 1 no-op). Escalation will fire at MAX_SAMPLES.`);
                    } else if (outcome === "escalate") {
                        console.log(`[diez] Tier 1 inconclusive at ${context.diezClassification.total} samples — existing limitDiez path will fire.`);
                    }
                }

                await routerDefaultHandler(
                    request,
                    requestQueue,
                    url,
                    content,
                    targetDomain,
                    title
                );

                // --- PRE-BATCH DEDUP: Extract links, batch-check Redis, build local Set ---
                // CRITICAL: transformRequestFunction MUST be synchronous (Crawlee API contract).
                // An async version causes minimatch to receive a Promise instead of a Request,
                // crashing with "Cannot read properties of undefined (reading 'split')".
                let knownUrlsOnPage = new Set<string>();

                if (context.dedupManager) {
                    try {
                        // 1. Extract all <a href> links from the page
                        const rawLinks = await page.$$eval('a[href]', (anchors: HTMLAnchorElement[]) =>
                            anchors.map(a => a.href).filter(href => href && href.startsWith('http'))
                        );

                        if (rawLinks.length > 0) {
                            // 2. Batch-check against Redis in a single round-trip
                            knownUrlsOnPage = await context.dedupManager.isKnownBatch(rawLinks);
                        }
                    } catch (e) {
                        // Non-fatal: if link extraction fails, we proceed without pre-filtering
                        // The handler-level dedup (line ~176) will still catch duplicates
                        console.warn(`Pre-batch link extraction failed: ${e}`);
                    }
                }

                await enqueueLinks({
                    strategy: "same-domain",
                    exclude: enqueueLinksExcludePath,
                    transformRequestFunction: (request) => {
                        // 1. Robots Check
                        if (robots && !robots.isAllowed(request.url, "Googlebot")) {
                            logBlocked('robots.txt', request.url);
                            return false;
                        }

                        // 2. Initial CLEANING of the URL (Moved to TOP)
                        // This ensures we strip parameters BEFORE checking forbidden list
                        const { skipQuestionMark, skipDiez, toKeep, toRemove } = context.config;
                        
                        // ALWAYS_REMOVE_PARAMS is defined at module level to avoid
                        // re-instantiation on every discovered link.

                        // Strip empty fragment (#) — "page#" and "page" are identical content
                        if (request.url.endsWith('#')) {
                            request.url = request.url.slice(0, -1);
                        }

                        // Always strip the "Always Remove" list first (skipQuestionMark=false: only remove alwaysRemove params)
                        request.url = processUrl(request.url, false, false, { toRemove: ALWAYS_REMOVE_PARAMS });

                        // Now apply the dynamic config (skipQuestionMark, etc)
                        if (skipQuestionMark || skipDiez) {
                            let parameters = {};
                            if (toKeep && toKeep.length > 0) parameters = { toKeep };
                            if (toRemove && toRemove.length > 0) parameters = { ...parameters, toRemove };
                            
                            request.url = processUrl(
                                request.url,
                                skipQuestionMark,
                                skipDiez,
                                parameters
                            );
                        }

                        // 2b. Session-based i18n: propagate language query param
                        // When the homepage was detected via ?lang=fr (pattern_match_query),
                        // internal URLs often don't carry that param. Append it so the server
                        // serves French content instead of the default language.
                        if (context.languageQueryParam) {
                            try {
                                const reqUrl = new URL(request.url);
                                if (!reqUrl.searchParams.has(context.languageQueryParam.key)) {
                                    reqUrl.searchParams.set(
                                        context.languageQueryParam.key,
                                        context.languageQueryParam.value
                                    );
                                    request.url = reqUrl.toString();
                                }
                            } catch {
                                // Invalid URL — skip param injection
                            }
                        }

                        // 3. Security Checks & Forbidden Params
                        // Now that URL is clean, we check if it still contains forbidden stuff
                        try {
                            const reqUrlObj = new URL(request.url);

                            // Forbidden Params Check
                            for (const param of FORBIDDEN_PARAMS) {
                                if (reqUrlObj.searchParams.has(param) ||
                                    Array.from(reqUrlObj.searchParams.keys()).some(key => key.startsWith(param))) {
                                    logBlocked('forbidden-param', `"${param}": ${request.url}`);
                                    return false;
                                }
                            }

                            // Spider Trap Checks
                            if (request.url.includes('/quotation/cart/') ||
                                request.url.includes('/cart/cart/') ||
                                request.url.includes('/catalog/product_compare/')) {
                                logBlocked('spider-trap', request.url);
                                return false;
                            }

                            // Download Route Checks (extension-less URLs that serve binary content)
                            if (/\/(download|export|print|telecharger|telechargement)\//i.test(request.url)) {
                                logBlocked('download-route', request.url);
                                return false;
                            }

                            if (/\/url\/[a-zA-Z0-9]{20,}/.test(request.url)) {
                                logBlocked('base64-url', request.url);
                                return false;
                            }

                            // External Domain Check: allow URLs matching either domain or site hostname
                            const reqHost = reqUrlObj.hostname;
                            const isReqInternal = (targetDomain && reqHost.includes(targetDomain))
                                || (siteHostname && reqHost.includes(siteHostname));
                            if (!isReqInternal) {
                                logBlocked('external-domain', request.url);
                                return false;
                            }

                        } catch (e) {
                            console.error(`Invalid URL in transformRequestFunction: ${request.url}`);
                            return false;
                        }

                        // Regional variant exclusion: block links to excluded regional paths
                        if (context.excludedRegionalPaths.length > 0 &&
                            DetectionLangueClient.isExcludedRegionalPath(request.url, context.excludedRegionalPaths)) {
                            logBlocked('regional-variant', request.url);
                            return false;
                        }

                        // 4. Pre-Crawl Deduplication (SYNCHRONOUS via pre-built Set)
                        // The Set was populated before enqueueLinks by batch-checking Redis.
                        // This avoids the async trap while still leveraging Redis dedup.
                        if (knownUrlsOnPage.has(request.url)) {
                            return false;
                        }

                        request.userData = { source: 'discovered' };
                        return request;
                    },
                });

                // Post-process blocked URLs for logging (Async Dedup)
                if (context.dedupManager && blockedBuffer.length > 0) {
                     try {
                         const allUrls = blockedBuffer.map(b => b.url);
                         const newUrls = await context.dedupManager.filterNewBlockedBatch(allUrls);
                         const newUrlsSet = new Set(newUrls);
                         
                         const loggedLocal = new Set<string>();
                         for(const item of blockedBuffer) {
                             if(newUrlsSet.has(item.url) && !loggedLocal.has(item.url)) {
                                 console.log(`🚫 [${item.reason}] ${item.url}`);
                                 loggedLocal.add(item.url);
                             }
                         }
                     } catch (e) {
                         console.warn("Failed to log blocked URLs via Redis:", e);
                     }
                }
            } else {
                log.warning(`Le site ${url} n'est pas en Français.`);

                // --- UPDATE MODE: Non-French page = not eligible ---
                if (context.updateChecker && source) {
                    const httpStatus = response?.status() || 200;
                    const result = await context.updateChecker.checkUrl(
                        request.url,
                        request.loadedUrl,
                        source,
                        httpStatus,
                        false // NOT French
                    );
                    log.info(`[UpdateChecker] ${result.action}: ${result.url} (not_french)`);
                }

                if (!content) content = await processPage(page, request.loadedUrl, log);
                let dataset = await Dataset.open("nfr-" + targetDomain);
                // PushedSet guard (fail-open). Truth-table equivalent to functions.ts:1635 inverted form.
                if (!context.pushedSet || (await context.pushedSet.tryClaim(url))) {
                    await dataset.pushData({ url, content });
                }
            }
        } else {
            console.log(`Doublon url : ${url}`);
        }

        // Signal that homepage detection is complete (for update mode two-phase seeding).
        // Must be OUTSIDE the isDoublon check — homepage may be marked as Doublon
        // in update mode (pre-added to DedupManager during Phase 1 seeding).
        if (request.url === site && context.homepageReady) {
            context.homepageReady.resolve();
        }
        } finally {
            // Single exit hook for ALL paths (return, throw, early break). When
            // TIMING_ENABLED=false, context.timingRecorder is undefined and the
            // optional chain is a no-op — zero overhead.
            context.timingRecorder?.recordPage(
                buildTimingEntry(_timing, url, _detectMethod, _detectOk),
            );
            // Drop the per-attempt marker so a Crawlee retry on the same Request
            // does not reuse stale dequeueAt/postNavAt from the previous attempt
            // (T3 review note N-4). preNavigationHook will repopulate.
            try { delete (request.userData as any)._timing; } catch { /* best-effort */ }
        }
    }
);
