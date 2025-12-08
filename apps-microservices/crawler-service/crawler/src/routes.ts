import { createPlaywrightRouter, Dataset } from "crawlee";
import {
    domain,
    requestQueue,
    baseUrl,
    enqueueLinksIncludePath,
    robots,
    skipquestionmark,
    skipdiez,
    allUrlsCrawled,
    toKeep,
    toRemove,
    site,
} from "./main.js";
import {
    manageFrenchDetectionMethod,
    processPage,
    processUrl,
    routerDefaultHandler,
    stopCrawler,
    updateUrlsCrawled,
} from "./functions.js";
import { DomainFR } from "./class/DomainFR.js";

export const router = createPlaywrightRouter();

const ignoredExtensions = [
    // archives
    "7z",
    "7zip",
    "bz2",
    "rar",
    "tar",
    "tar.gz",
    "xz",
    "zip",
    // images
    "mng",
    "pct",
    "bmp",
    "gif",
    "jpg",
    "jpeg",
    "png",
    "pst",
    "psp",
    "tif",
    "tiff",
    "ai",
    "drw",
    "dxf",
    "eps",
    "ps",
    "svg",
    "cdr",
    "ico",
    "webp",
    // audio
    "mp3",
    "wma",
    "ogg",
    "wav",
    "ra",
    "aac",
    "mid",
    "au",
    "aiff",
    // video
    "3gp",
    "asf",
    "asx",
    "avi",
    "mov",
    "mp4",
    "mpg",
    "qt",
    "rm",
    "swf",
    "wmv",
    "m4a",
    "m4v",
    "flv",
    "webm",
    // office suites
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "pps",
    "doc",
    "docx",
    "odt",
    "ods",
    "odg",
    "odp",
    // other
    "css",
    "pdf",
    "exe",
    "bin",
    "rss",
    "dmg",
    "iso",
    "apk",
    "xml",
].join("|");

const domainFR = new DomainFR("");

router.addDefaultHandler(
    async ({ request, page, enqueueLinks, log, proxyInfo, crawler, response }) => {
        const proxyUrl = proxyInfo?.url || null;

        // Block resources to save bandwidth and CPU
        await page.route('**/*', (route) => {
            const request = route.request();
            const resourceType = request.resourceType();
            const url = request.url();

            // Block heavy media and fonts
            if (['image', 'media', 'font', 'stylesheet'].includes(resourceType)) {
                return route.abort();
            }

            // Block download scripts and binary files
            if (url.includes('download.php') || url.includes('imp=1') || url.match(/\.(pdf|zip|rar|doc|docx|xls|xlsx)$/i)) {
                return route.abort();
            }

            return route.continue();
        });

        let url = request.loadedUrl;

        // CRITICAL SECURITY: Check if the loaded URL is still on the target domain
        // This handles cases where a valid internal link redirects to an external site (e.g. Facebook)
        // If we don't check this, the crawler might start crawling the external site.
        const urlObj = new URL(url);
        const targetDomain = domain; // Imported from main.js

        // Check if hostname ends with the target domain (handles subdomains too)
        // e.g. target="myshop.com", loaded="facebook.com" -> BLOCKED
        // e.g. target="myshop.com", loaded="blog.myshop.com" -> ALLOWED
        if (!urlObj.hostname.includes(targetDomain)) {
            log.warning(`Blocked external redirect: ${url} (Target: ${targetDomain})`);
            return;
        }

        let enqueueLinksExcludePath: Array<string> = [
            `**/*.@(${ignoredExtensions}){,\?*}{,\#*}`,

            // === SPIDER TRAPS E-COMMERCE (QUERY STRING PATTERNS) ===
            // FIXED: Patterns now match query strings (?param=value) not just paths
            // Facettes et filtres - Match both ? and & variations
            '**/?*order=*', '**/*?*order=*', '**/*&order=*',
            '**/?*sort=*', '**/*?*sort=*', '**/*&sort=*',
            '**/?*dir=*', '**/*?*dir=*', '**/*&dir=*',
            '**/?*limit=*', '**/*?*limit=*', '**/*&limit=*',
            '**/?*resultsPerPage=*', '**/*?*resultsPerPage=*', '**/*&resultsPerPage=*',
            '**/?*filter=*', '**/*?*filter=*', '**/*&filter=*',
            '**/?*filters[*', '**/*?*filters[*', '**/*&filters[*',
            '**/?*price=*', '**/*?*price=*', '**/*&price=*',
            '**/?*price_min=*', '**/*?*price_min=*', '**/*&price_min=*',
            '**/?*price_max=*', '**/*?*price_max=*', '**/*&price_max=*',
            '**/?*id_category=*', '**/*?*id_category=*', '**/*&id_category=*',
            '**/?*categoryId=*', '**/*?*categoryId=*', '**/*&categoryId=*',
            '**/?*productListView=*', '**/*?*productListView=*', '**/*&productListView=*',

            // Recherche et pagination avancée
            '**/?*q=*', '**/*?*q=*', '**/*&q=*',
            '**/?*search=*', '**/*?*search=*', '**/*&search=*',
            '**/?*query=*', '**/*?*query=*', '**/*&query=*',
            '**/*page=*/**/*page=*', // Double pagination
            '**/?*offset=*', '**/*?*offset=*', '**/*&offset=*',
            '**/?*start=*', '**/*?*start=*', '**/*&start=*',

            // Tris et affichages multiples
            '**/?*view=*', '**/*?*view=*', '**/*&view=*',
            '**/?*mode=*', '**/*?*mode=*', '**/*&mode=*',
            '**/?*display=*', '**/*?*display=*', '**/*&display=*',
            '**/?*per_page=*', '**/*?*per_page=*', '**/*&per_page=*',
            '**/?*items=*', '**/*?*items=*', '**/*&items=*',

            // === AUTHENTIFICATION & COMPTE (CRITICAL FOR OOM) ===
            '**/connexion**', '**/login**', '**/signin**', '**/log-in**',
            '**/register**', '**/signup**', '**/inscription**',
            '**/account**', '**/mon-compte**', '**/my-account**',
            '**/profile**', '**/profil**',
            '**/password**', '**/mot-de-passe**', '**/reset-password**',
            '**/logout**', '**/deconnexion**',
            '**/forgot-password**', '**/oubli-mot-de-passe**',
            '**/customer/account/**', '**/customer/**',

            // === PROCESSUS D'ACHAT (CRITICAL FOR OOM) ===
            '**/panier**', '**/cart**', '**/basket**',
            '**/checkout**', '**/commande**', '**/order**',
            '**/add-to-cart**', '**/addtocart**',
            '**/payment**', '**/paiement**',
            '**/shipping**', '**/livraison**',
            '**/confirmation**',
            '**/quotation/**', '**/devis/**',

            // === ACTIONS UTILISATEUR ===
            '**/wishlist**', '**/liste-envies**', '**/favoris**',
            '**/compare**', '**/comparateur**',
            '**/sendtoafriend**', '**/send-to-friend**',

            // === CALENDRIERS & DATES ===
            '**/?*year=*', '**/*?*year=*', '**/*&year=*',
            '**/?*month=*', '**/*?*month=*', '**/*&month=*',
            '**/?*day=*', '**/*?*day=*', '**/*&day=*',
            '**/?*date=*', '**/*?*date=*', '**/*&date=*',
            '**/?*from=*', '**/*?*from=*', '**/*&from=*',
            '**/?*to=*', '**/*?*to=*', '**/*&to=*',
            '**/calendrier/**', '**/calendar/**',

            // === RÉSEAUX SOCIAUX & PARTAGE (SCOPE LEAK PREVENTION) ===
            '**/*facebook*', '**/*twitter*', '**/*linkedin*',
            '**/*instagram*', '**/*youtube*', '**/*pinterest*',
            '**/*tiktok*', '**/*whatsapp*',
            '**/*share*', '**/*partager*',
            '**/mailto:*', '**/tel:*', '**/*://t.me/*',

            // === TRACKING & ANALYTICS ===
            '**/*redirect*', '**/*track*', '**/*click*',
            '**/?*ref=*', '**/*?*ref=*', '**/*&ref=*',
            '**/?*referrer=*', '**/*?*referrer=*', '**/*&referrer=*',
            '**/?*source=*', '**/*?*source=*', '**/*&source=*',

            // === APIS & TECHNIQUES ===
            '**/api/**', '**/wp-json/**', '**/rest/**',
            '**/feed/**', '**/feeds/**', '**/rss/**',

            // === SPECIFIC SITE EXCLUDES (sellerie-equishop) ===
            '**/PBCPPlayer.asp**',
            '**/popup/**',

            // === SPECIFIC SITE EXCLUDES (promodis.fr) ===
            '**/download.php**',
            '**/*imp=1*',
            '**/dhtml/download.php*',
            '**/*.pdf', '**/*.zip', '**/*.rar', '**/*.doc', '**/*.docx', '**/*.xls', '**/*.xlsx',

            // === SPECIFIC SITE EXCLUDES (SHOPIFY SPIDER TRAPS) ===
            '**/collections/*/*+*',
            '**/collections/*/*%2B*',
            '**/collections/*/*&*',
            '**/*size_*', '**/*taille_*',
            '**/*color_*', '**/*couleur_*',
            '**/*price_*', '**/*prix_*',
            '**/*brand_*', '**/*marque_*',
            '**/*type_*', '**/*vendor_*',
            '**/?*sort_by=*', '**/*?*sort_by=*', '**/*&sort_by=*',
        ];

        // Not useful anymore as we analyze the URL to check which parameters to keep or to remove
        // if (skipquestionmark) {
        //     enqueueLinksExcludePath.push(`${baseUrl}/**/*[?]*`);
        //     enqueueLinksExcludePath.push(`${baseUrl}/**/*[?]*/**`);
        // }
        // if (skipdiez) {
        //     enqueueLinksExcludePath.push(`${baseUrl}/**/*[#]*`);
        //     enqueueLinksExcludePath.push(`${baseUrl}/**/*[#]*/**`);
        // }
        log.info(`Processing ${url} ( ${request.url} ) ... (HTTP Status: ${response?.status()})`);

        // Verify if url is already crawled using Set (O(1))
        const isDoublon = allUrlsCrawled.has(url);

        if (!isDoublon) {
            allUrlsCrawled.add(url);
            // OPTIMIZATION: Removed synchronous disk write on every request (updateUrlsCrawled)
            // This was causing massive CPU/IO overhead with 250k URLs.
            // Persistence is now handled by the Dataset and RequestQueue.

            // Accept Cookies
            await page.context().addCookies([
                {
                    name: "cookieConsent",
                    value: "accepted",
                    domain: domain,
                    path: "/",
                },
            ]);

            // Check if this is the main site URL
            const isMainSite = request.url === site;
            let frenchDetectionMethod: string | Error;
            let isEnqueuingLinks = false;
            let content = "";

            if (isMainSite) {
                // Process normally and store the method
                content = await processPage(page, request.loadedUrl, log);
                domainFR.homepage = url;
                const checkPageIfFrench = await domainFR.checkPageIfFrench(content, false);

                if (checkPageIfFrench["ok"]) {
                    // Store the successful method
                    frenchDetectionMethod = manageFrenchDetectionMethod(domain as string, checkPageIfFrench["method"]);
                    if (frenchDetectionMethod instanceof Error) {
                        log.error(`Failed to store French detection method: ${frenchDetectionMethod.message}`);
                        await stopCrawler(crawler, "Failed to store French detection method");
                        return;
                    }

                    isEnqueuingLinks = true;
                } else {
                    const checkUrl = await DomainFR.checkUrl(url, false, proxyUrl);
                    if (checkUrl["ok"]) {
                        frenchDetectionMethod = manageFrenchDetectionMethod(domain as string, checkUrl["method"]);
                        if (frenchDetectionMethod instanceof Error) {
                            log.error(`Failed to store French detection method: ${frenchDetectionMethod.message}`);
                            await stopCrawler(crawler, "Failed to store French detection method");
                            return;
                        }

                        isEnqueuingLinks = true;
                    }
                }
            } else {
                // Try to get stored method
                frenchDetectionMethod = manageFrenchDetectionMethod(domain as string);
                if (frenchDetectionMethod instanceof Error) {
                    log.error(`Failed to retrieve French detection method: ${frenchDetectionMethod.message}`);
                    await stopCrawler(crawler, "No French detection method found");
                    return;
                }

                // Create new DomainFR instance with forced method
                content = await processPage(page, request.loadedUrl, log);
                const domainFRWithMethod = new DomainFR(url, frenchDetectionMethod as string);
                const checkPageIfFrench = await domainFRWithMethod.checkPageIfFrench(content, false);

                if (checkPageIfFrench["ok"]) {
                    isEnqueuingLinks = true;
                } else {
                    const checkUrl = await DomainFR.checkUrl(url, false, proxyUrl);
                    if (checkUrl["ok"] && checkUrl["method"] === frenchDetectionMethod as string) {
                        isEnqueuingLinks = true;
                    }
                }
            }

            if (isEnqueuingLinks) {
                await routerDefaultHandler(
                    request,
                    requestQueue,
                    url,
                    content,
                    domain
                );

                await enqueueLinks({
                    strategy: "same-domain",
                    globs: enqueueLinksIncludePath, // FIXED: Uncommented to enable URL restrictions
                    exclude: enqueueLinksExcludePath,
                    transformRequestFunction: (request) => {
                        if (
                            robots &&
                            !robots.isAllowed(request.url, "Googlebot")
                        ) {
                            console.log(
                                `Bloqué par robots.txt : ${request.url}`
                            );
                            return null;
                        }

                        // === NEW: PREVENTIVE PARAMETER FILTERING (BEFORE ENQUEUE) ===
                        // This blocks URLs with forbidden query parameters BEFORE they enter the queue
                        // This is MORE RELIABLE than glob patterns for query strings
                        try {
                            const urlObj = new URL(request.url);
                            const forbiddenParams = [
                                'order', 'sort', 'dir', 'limit', 'resultsPerPage',
                                'filter', 'price', 'price_min', 'price_max',
                                'id_category', 'categoryId', 'productListView',
                                'q', 'search', 'query', 'offset', 'start',
                                'view', 'mode', 'display', 'per_page', 'items',
                                'year', 'month', 'day', 'date', 'from', 'to',
                                'ref', 'referrer', 'source', 'sort_by',
                                // Shopify specific
                                'size_', 'taille_', 'color_', 'couleur_',
                                'price_', 'prix_', 'brand_', 'marque_', 'type_', 'vendor_'
                            ];

                            for (const param of forbiddenParams) {
                                if (urlObj.searchParams.has(param) ||
                                    Array.from(urlObj.searchParams.keys()).some(key => key.startsWith(param))) {
                                    console.log(`🚫 Blocked forbidden param "${param}": ${request.url}`);
                                    return null;
                                }
                            }
                        } catch (e) {
                            console.error(`Invalid URL in param check: ${request.url}`);
                            return null;
                        }

                        // PREVENTIVE SPIDER TRAP BLOCKING (Before other checks)
                        // Block nested cart/quotation URLs that create infinite loops
                        if (request.url.includes('/quotation/cart/') ||
                            request.url.includes('/cart/cart/') ||
                            request.url.includes('/catalog/product_compare/')) {
                            console.log(`Blocked spider trap: ${request.url}`);
                            return null;
                        }

                        // Block URLs with long base64-encoded segments (often dynamic/infinite)
                        if (/\/url\/[a-zA-Z0-9]{20,}/.test(request.url)) {
                            console.log(`Blocked base64 URL: ${request.url}`);
                            return null;
                        }

                        // HARD SECURITY: Explicitly block ANY URL that is not on the target domain
                        // This acts as a secondary firewall in case "same-domain" strategy fails or redirects occur
                        try {
                            const reqUrlObj = new URL(request.url);
                            if (!reqUrlObj.hostname.includes(domain)) {
                                console.log(`Blocked external URL: ${request.url}`);
                                return null;
                            }
                        } catch (e) {
                            console.error(`Invalid URL in transformRequestFunction: ${request.url}`);
                            return null;
                        }

                        // List parameters always to remove
                        let toAlwaysRemove = {
                            toRemove: [
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
                            ],
                        };
                        request.url = processUrl(
                            request.url,
                            true, // skip question mark here
                            false,
                            toAlwaysRemove
                        );

                        // If skipquestionmark or skipdiez is true, we need to process the URL
                        if (skipquestionmark || skipdiez) {
                            let parameters = {};
                            if (toKeep.length > 0) {
                                parameters = { toKeep: toKeep };
                            }
                            if (toRemove.length > 0) {
                                parameters = { ...parameters, toRemove: toRemove };
                            }
                            request.url = processUrl(
                                request.url,
                                skipquestionmark,
                                skipdiez,
                                parameters
                            );
                        }

                        return request;
                    },
                });
            } else {
                log.warning(`Le site ${url} n'est pas en Français.`);
                let dataset = await Dataset.open("nfr-" + domain);
                await dataset.pushData({ url, content });
            }
        } else {
            console.log(`Doublon url : ${url}`);
        }
    }
);
