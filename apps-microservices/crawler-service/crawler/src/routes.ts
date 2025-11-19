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

        let url = request.loadedUrl;
        let enqueueLinksExcludePath: Array<string> = [
            `**/*.@(${ignoredExtensions}){,\?*}{,\#*}`,
            // === SPIDER TRAPS E-COMMERCE ===
            // Facettes et filtres
            '**/*order=*', '**/*sort=*', '**/*dir=*', '**/*limit=*',
            '**/*resultsPerPage=*', '**/*filter=*', '**/*filters[*',
            '**/*price=*', '**/*price_min=*', '**/*price_max=*',
            '**/*id_category=*', '**/*categoryId=*',

            // Recherche et pagination avancée
            '**/*q=*', '**/*search=*', '**/*query=*',
            '**/*page=*/**/*page=*', // Double pagination
            '**/*offset=*', '**/*start=*',

            // Tris et affichages multiples
            '**/*view=*', '**/*mode=*', '**/*display=*',
            '**/*per_page=*', '**/*items=*',

            // === AUTHENTIFICATION & COMPTE ===
            '**/connexion**', '**/login**', '**/signin**', '**/log-in**',
            '**/register**', '**/signup**', '**/inscription**',
            '**/account**', '**/mon-compte**', '**/my-account**',
            '**/profile**', '**/profil**',
            '**/password**', '**/mot-de-passe**', '**/reset-password**',
            '**/logout**', '**/deconnexion**',
            '**/forgot-password**', '**/oubli-mot-de-passe**',

            // === PROCESSUS D'ACHAT ===
            '**/panier**', '**/cart**', '**/basket**',
            '**/checkout**', '**/commande**', '**/order**',
            '**/add-to-cart**', '**/addtocart**',
            '**/payment**', '**/paiement**',
            '**/shipping**', '**/livraison**',
            '**/confirmation**',

            // === ACTIONS UTILISATEUR ===
            '**/wishlist**', '**/liste-envies**', '**/favoris**',
            '**/compare**', '**/comparateur**',
            '**/sendtoafriend**', '**/send-to-friend**',
            '**/avis**', '**/review**', '**/reviews**',
            '**/comment**', '**/comments**',
            '**/rating**', '**/noter**',

             // === FONCTIONNALITÉS DYNAMIQUES ===
            '**/*action=*', '**/*do=*', '**/*task=*',
            '**/*ajax=*', '**/*xhr=*',
            '**/*popup=*', '**/*modal=*',
            '**/*print=*', '**/*impression=*',

            // === CALENDRIERS & DATES (Spider traps classiques) ===
            '**/*year=*', '**/*month=*', '**/*day=*',
            '**/*date=*', '**/*from=*', '**/*to=*',
            '**/calendrier/**', '**/calendar/**',

            // === RÉSEAUX SOCIAUX & PARTAGE ===
            '**/*facebook*', '**/*twitter*', '**/*linkedin*',
            '**/*instagram*', '**/*youtube*', '**/*pinterest*',
            '**/*tiktok*', '**/*whatsapp*',
            '**/*share*', '**/*partager*',
            '**/mailto:*', '**/tel:*', '**/*://t.me/*',

            // === TRACKING & ANALYTICS ===
            '**/*redirect*', '**/*track*', '**/*click*',
            '**/*ref=*', '**/*referrer=*', '**/*source=*',

            // === APIS & TECHNIQUES ===
            '**/api/**', '**/wp-json/**', '**/rest/**',
            '**/feed/**', '**/feeds/**', '**/rss/**',


            // `${baseUrl}/**/*[?#]*`,
            // `${baseUrl}/**/*[?#]*/**`,
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

        let isDoublon = false;

        //verify if url is already crawled
        allUrlsCrawled.forEach((item: string) => {
            if (item === url) {
                isDoublon = true;
            }
        });

        if (!isDoublon) {
            allUrlsCrawled.push(url);
            updateUrlsCrawled(domain, allUrlsCrawled);

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
                    // globs: enqueueLinksIncludePath,
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
