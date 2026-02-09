import { createPlaywrightRouter, Dataset } from "crawlee";
// Removed circular imports from main.js (domain, skipquestionmark etc)
import {
    domain, // Keep basic exports if needed, but prefer context for config
    requestQueue,
    robots,
    site,
} from "./main.js";
import {
    manageFrenchDetectionMethod,
    processPage,
    processUrl,
    rightTrimSlash,
    routerDefaultHandler,
    stopCrawler,
} from "./functions.js";
import { DomainFR } from "./class/DomainFR.js";
import { context } from "./context.js";

export const router = createPlaywrightRouter();

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

// Ported Forbidden Params from V3
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

const domainFR = new DomainFR("");

router.addDefaultHandler(
    async ({ request, page, enqueueLinks, log, proxyInfo, crawler, response }) => {
        const proxyUrl = proxyInfo?.url || null;

        // Resource Blocking (Images, Fonts, etc.)
        await page.route('**/*', (route) => {
            const req = route.request();
            const resourceType = req.resourceType();
            const reqUrl = req.url();

            // Block heavy media and fonts
            if (['image', 'media', 'font', 'stylesheet'].includes(resourceType)) {
                return route.abort();
            }
            // Block download scripts and binary files
            if (reqUrl.includes('download.php') || reqUrl.includes('imp=1') || /\.(pdf|zip|rar|doc|docx|xls|xlsx|exe|bin|iso|dmg)$/i.test(reqUrl)) {
                return route.abort();
            }
            return route.continue();
        });

        let url = request.loadedUrl;

        // CRITICAL SECURITY: Check if the loaded URL is still on the target domain
        // This handles cases where a valid internal link redirects to an external site (e.g. Facebook)
        // If we don't check this, the crawler might start crawling the external site.
        const urlObj = new URL(url);
        const targetDomain = context.config.domain; 

        // Check if hostname ends with the target domain (handles subdomains too)
        // e.g. target="myshop.com", loaded="facebook.com" -> BLOCKED
        // e.g. target="myshop.com", loaded="blog.myshop.com" -> ALLOWED
        if (!targetDomain || !urlObj.hostname.includes(targetDomain)) {
            log.warning(`Blocked external redirect: ${url} (Target: ${targetDomain})`);
            return;
        }

        let enqueueLinksExcludePath: Array<string> = [
            `**/*.@(${ignoredExtensions}){,\?*}{,\#*}`,
        ];

        // Blocked Status Check
        if (response) {
            const status = response.status();
            if ([401, 403, 429, 404, 410, 423, 502, 500, 503].includes(status)) {
                log.error(`🚫 BLOCKED: HTTP ${status} on ${url}`);
                // Increment error stats
                if (context.statsManager && request.userData.is_existing) {
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
                    if (errors >= cb.maxAbsErrors) abortReason = `Too many errors for small site (${errors} >= ${cb.maxAbsErrors})`;
                    else if (redirects >= cb.maxAbsRedirects) abortReason = `Too many redirects for small site (${redirects} >= ${cb.maxAbsRedirects})`;
                    else if (newUrls >= cb.maxAbsNew) abortReason = `Too many new URLs for small site (${newUrls} >= ${cb.maxAbsNew})`;
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
        const isExisting = request.userData.is_existing || false;

        // Skip Redis check for "Existing" URLs to allow re-verification in Update Mode
        if (context.dedupManager && !isExisting) {
            const isNew = await context.dedupManager.addUrl(url);
            isDoublon = !isNew;
        }
        
        // Removed early increment of "new_urls" here.
        // It is now handled inside the success block (isEnqueuingLinks) to ensure validity.

        if (!isDoublon) {
            // Redis update handled in dedupManager
            // Local file update is heavy, skipped in V3 logic, keeping minimal or periodic in main.ts

            // Accept Cookies
            await page.context().addCookies([
                {
                    name: "cookieConsent",
                    value: "accepted",
                    domain: targetDomain,
                    path: "/",
                },
            ]);

            // --- REDIRECT LOOP CLOSURE (Important Fix) ---
            // If we ended up at a different URL than requested (redirect), make sure the 
            // final URL is also marked as known in Redis to prevent future re-crawling.
            if (context.dedupManager && request.url !== request.loadedUrl) {
                const finalUrlClean = rightTrimSlash(request.loadedUrl);
                // We add it to Redis. We don't care if it returns true/false here, just ensuring it's known.
                await context.dedupManager.addUrl(finalUrlClean);
            }

            if (isExisting && context.statsManager) {
                // request.loadedUrl is the final URL after redirects
                // request.url is the queue/original URL
                // Check if they differ (fuzzy matching to ignore trailing slashes)
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
                content = await processPage(page, request.loadedUrl, log);
                domainFR.homepage = url;
                const checkPageIfFrench = await domainFR.checkPageIfFrench(content, false);

                if (checkPageIfFrench["ok"]) {
                    frenchDetectionMethod = manageFrenchDetectionMethod(targetDomain as string, checkPageIfFrench["method"]);
                    if (frenchDetectionMethod instanceof Error) {
                        log.error(`Failed to store French detection method: ${frenchDetectionMethod.message}`);
                        await stopCrawler(crawler, "Failed to store French detection method");
                        return;
                    }
                    isEnqueuingLinks = true;
                } else {
                    const checkUrl = await DomainFR.checkUrl(url, false, proxyUrl);
                    if (checkUrl["ok"]) {
                        frenchDetectionMethod = manageFrenchDetectionMethod(targetDomain as string, checkUrl["method"]);
                        if (frenchDetectionMethod instanceof Error) {
                            log.error(`Failed to store French detection method: ${frenchDetectionMethod.message}`);
                            await stopCrawler(crawler, "Failed to store French detection method");
                            return;
                        }
                        isEnqueuingLinks = true;
                    }
                }
            } else {
                // INTERNAL PAGE LOGIC WITH FALLBACK
                let methodOrError = manageFrenchDetectionMethod(targetDomain as string);
                
                if (methodOrError instanceof Error) {
                    log.warning(`French detection method not found in storage. Attempting auto-detection on current page.`);
                    
                    // Fallback: Detect on current content
                    if (!content) content = await processPage(page, request.loadedUrl, log);
                    
                    // Use global instance (no forced method) to auto-detect
                    domainFR.homepage = url; 
                    const autoCheck = await domainFR.checkPageIfFrench(content, false); 
                    
                    if (autoCheck.ok) {
                        methodOrError = manageFrenchDetectionMethod(targetDomain as string, autoCheck.method);
                        log.info(`Auto-detected and saved method: ${autoCheck.method}`);
                    } else {
                        // Try URL check fallback
                        const checkUrl = await DomainFR.checkUrl(url, false, proxyUrl);
                        if (checkUrl.ok) {
                             methodOrError = manageFrenchDetectionMethod(targetDomain as string, checkUrl.method);
                             log.info(`Auto-detected (URL) and saved method: ${checkUrl.method}`);
                        }
                    }
                }

                if (methodOrError instanceof Error) {
                    log.error(`Could not determine French detection method for ${url}. Skipping links.`);
                    isEnqueuingLinks = false;
                } else {
                    frenchDetectionMethod = methodOrError as string;
                    
                    if (!content) content = await processPage(page, request.loadedUrl, log);
                    const domainFRWithMethod = new DomainFR(url, frenchDetectionMethod);
                    const checkPageIfFrench = await domainFRWithMethod.checkPageIfFrench(content, false);

                    if (checkPageIfFrench["ok"]) {
                        isEnqueuingLinks = true;
                    } else {
                        const checkUrl = await DomainFR.checkUrl(url, false, proxyUrl);
                        if (checkUrl["ok"] && checkUrl["method"] === frenchDetectionMethod) {
                            isEnqueuingLinks = true;
                        }
                    }
                }
            }

            if (isEnqueuingLinks) {
                // === VALIDATED CONTENT BLOCK ===
                
                // Count as NEW URL only if it's not existing AND passed validation (isEnqueuingLinks=True)
                if (context.dedupManager && !isExisting) {
                    if (context.statsManager) {
                        await context.statsManager.increment("new_urls");
                        
                        // Fail Fast Check for New URLs (moved from early check)
                        if (context.config.maxNewUrls && await context.statsManager.checkThreshold("new_urls", context.config.maxNewUrls)) {
                            log.warning("🛑 Max new URLs limit reached during processing. Stopping.");
                            context.stopReason = "limitNewUrls";
                            await stopCrawler(crawler, "Max new URLs limit reached.");
                            return;
                        }
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

                await enqueueLinks({
                    strategy: "same-domain",
                    exclude: enqueueLinksExcludePath,
                    transformRequestFunction: ((async (request: any) => {
                        // 1. Robots Check
                        if (robots && !robots.isAllowed(request.url, "Googlebot")) {
                            console.log(`Bloqué par robots.txt : ${request.url}`);
                            return null;
                        }

                        // 2. Initial CLEANING of the URL (Moved to TOP)
                        // This ensures we strip parameters BEFORE checking forbidden list
                        const { skipQuestionMark, skipDiez, toKeep, toRemove } = context.config;
                        
                        // List parameters always to remove
                        const alwaysRemove = [
                            // === CART & WISHLIST ===
                            "add-to-cart", "add_to_cart", "addtocart",
                            "add-to-compare", "add_to_compare",
                            "add-to-wishlist", "add_to_wishlist", "addtowishlist",
                            "remove_from_wishlist", "remove_wishlist",
                            "remove_compare", "remove_item",
                            "quantity", "qty",

                            // === TRACKING UTM (Marketing) ===
                            "utm_source", "utm_medium", "utm_campaign",
                            "utm_content", "utm_term", "utm_id",
                            "utm_referrer", "utm_name",

                            // === FACEBOOK & META ===
                            "fbclid", "fb_action_ids", "fb_action_types",
                            "fb_source", "fb_ref",

                            // === GOOGLE ADS & ANALYTICS ===
                            "gclid", "gclsrc", "dclid",
                            "srsltid", "utmcct", "utmcsr", "utmcmd", "utmccn",
                            "_ga", "_gid", "_gat",

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

                            // === WORDPRESS ===
                            "_wpnonce", "preview", "preview_id",
                            "preview_nonce", "et_blog",

                            // === PRESTASHOP ===
                            "id_product", "id_category", "pid",
                            "controller", "id_product_attribute",
                            "isolang", "id_lang",

                            // === SHOPIFY ===
                            "pr_prod_strat", "pr_rec_id", "pr_rec_pid",
                            "pr_ref_pid", "pr_seq",
                            "variant", "selling_plan",

                            // === MAGENTO ===
                            "SID", "___store", "___from_store",

                            // === SESSION & TRACKING ===
                            "sessionid", "session_id", "PHPSESSID",
                            "sid", "s_id",
                            "_gl", "ref", "referrer",

                            // === AFFILIATE & MARKETING ===
                            "aff_id", "affiliate", "partner",
                            "coupon", "discount", "promo",
                            "voucher",

                            // === AUTRES TRACKING ===
                            "click_id", "transaction_id",
                            "source", "medium", "campaign",

                            // === FILTRES SOUVENT INUTILES ===
                            "view", "mode", "display",
                            "timestamp", "random", "nocache",
                            "order", "sort", "resultsPerPage", "productListView", // Added for deduplication
                        ];

                        // Always strip the "Always Remove" list first
                        request.url = processUrl(request.url, true, false, { toRemove: alwaysRemove });

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

                        // 3. Security Checks & Forbidden Params
                        // Now that URL is clean, we check if it still contains forbidden stuff
                        try {
                            const reqUrlObj = new URL(request.url);

                            // Forbidden Params Check
                            for (const param of FORBIDDEN_PARAMS) {
                                if (reqUrlObj.searchParams.has(param) ||
                                    Array.from(reqUrlObj.searchParams.keys()).some(key => key.startsWith(param))) {
                                    console.log(`🚫 Blocked forbidden param "${param}": ${request.url}`);
                                    return null;
                                }
                            }

                            // Spider Trap Checks
                            if (request.url.includes('/quotation/cart/') ||
                                request.url.includes('/cart/cart/') ||
                                request.url.includes('/catalog/product_compare/')) {
                                console.log(`Blocked spider trap: ${request.url}`);
                                return null;
                            }

                            if (/\/url\/[a-zA-Z0-9]{20,}/.test(request.url)) {
                                console.log(`Blocked base64 URL: ${request.url}`);
                                return null;
                            }

                            // External Domain Check
                            if (targetDomain && !reqUrlObj.hostname.includes(targetDomain)) {
                                console.log(`Blocked external URL: ${request.url}`);
                                return null;
                            }

                        } catch (e) {
                            console.error(`Invalid URL in transformRequestFunction: ${request.url}`);
                            return null;
                        }

                        // 4. Pre-Crawl Deduplication
                        // Crucial Optimization: Stop the request HERE if we already know about it.
                        // We check against Redis before even creating the Request object fully.
                        // NOTE: In update mode, existing URLs are skipped by this logic implicitly
                        // because we are discovering NEW links here. We assume existing URLs
                        // were already added to Redis during seeding.
                        if (context.dedupManager) {
                            const isNew = await context.dedupManager.addUrl(request.url);
                            if (!isNew) {
                                // Already known, skip it immediately
                                return null;
                            }
                        }

                        request.userData = { is_existing: false };
                        return request;
                    }) as any),
                });
            } else {
                log.warning(`Le site ${url} n'est pas en Français.`);
                let dataset = await Dataset.open("nfr-" + targetDomain);
                await dataset.pushData({ url, content });
                await requestQueue.markRequestHandled(request);
            }
        } else {
            console.log(`Doublon url : ${url}`);
        }
    }
);
