Project Path: crawler

Source Tree:

```txt
crawler
└── src
    ├── class
    │   ├── DomainFR.ts
    │   └── RedirectTracker.ts
    ├── functions.ts
    ├── interfaces
    │   ├── IRedirect.ts
    │   ├── IRedirectResponse.ts
    │   └── queue.ts
    ├── main.ts
    └── routes.ts

```

`src\class\DomainFR.ts`:

```ts
import { RedirectTracker } from "./RedirectTracker.js";

export class DomainFR {
    private _homepage: string;
    private _forcedMethod: string | null;
    private tracker: RedirectTracker;

    constructor(homepage: string, forcedMethod: string | null = null) {
        this._homepage = homepage;
        this._forcedMethod = forcedMethod;
        this.tracker = new RedirectTracker();
    }

    public set homepage(v: string) {
        this._homepage = v;
    }

    private detectLanguage(content: string): any {
        // Base regex for handling conditional comments and HTML tag
        // (?:<!--\[if[^>]*> - Optional IE conditional comment start
        // (?:<!--)?[^<]*    - Optional comment and content
        // <html[^>]*>       - HTML tag with attributes
        // (?:(?:<!--)?<!\[endif\]-->)? - Optional IE conditional comment end
        // (?:<!--\[if[^>]*!\(?ie\)?\]><!-->) - IE specific conditional
        const regexLang = `(?:<!--\\[if[^>]*>(?:<!--)?[^<]*<html[^>]*>(?:(?:<!--)?<!\\[endif\\]-->)?[^<]*)*(?:<!--\\[if[^>]*!\\(?ie\\)?\\]><!-->)`;

        // Match lang attribute in HTML tag
        // \s*<html - HTML tag with optional whitespace
        // [^>]*\slang= - Any attributes followed by lang=
        // ["']?([a-zA-Z-]+)["']? - Language code in quotes (optional)
        const regexHtml = `\\s*<html[^>]*\\s(?:xml:)?lang=["']?([a-zA-Z-]+)["']?`;

        // Combine conditional comments and HTML lang patterns
        let regexLangHtml = new RegExp(`${regexLang}${regexHtml}`, "i");

        // Match Open Graph locale meta tag
        // <meta property="og:locale" content="language_code">
        const regexMetaLang =
            /<meta[^>]*\sproperty=["']og:locale["'][^>]*content=["']([a-zA-Z-]+)["']/i;
        
        // Match meta tag with the property name="language"
        // <meta property="og:locale" content="language_code">
        const regexMetaLanguage =
            /<meta[^>]*\sname=["']LANGUAGE["'][^>]*content=["']([a-zA-Z-]+)["']/i;

        // Match HTTP-EQUIV content language meta tag
        // <meta http-equiv="content-language" content="language_code">
        const regexHttpEquiv =
            /<meta[^>]*\shttp-equiv=["']content-language["'][^>]*content=["']([a-zA-Z-]+)["']/i;

        // Priority 1: Check HTML tag with conditional comments
        let matchHtml = content.match(regexLangHtml);
        if (matchHtml)
            return {
                method: "langHtml",
                value: matchHtml[1].split("-")[0], // Extract primary language code. Ex: "fr-FR" → "fr"
            };

        // Priority 2: Check HTML tag without conditional comments
        regexLangHtml = new RegExp(`${regexLang}?${regexHtml}`, "i");
        matchHtml = content.match(regexLangHtml);
        if (matchHtml)
            return {
                method: "langHtml",
                value: matchHtml[1].split("-")[0], // ex: "fr-FR" → "fr"
            };

        // Priority 3: Check Open Graph locale meta tag
        const matchMeta = content.match(regexMetaLang);
        if (matchMeta)
            return {
                method: "matchMeta",
                value: matchMeta[1].split("-")[0],
            };
        
        // Priority 3.1: Check meta tag with property with="language"
        const matchMetaLanguage = content.match(regexMetaLanguage);
        if (matchMetaLanguage)
            return {
                method: "matchMeta",
                value: matchMetaLanguage[1].split("-")[0],
            };

        // Priority 4: Check HTTP-EQUIV content language
        const matchHttpEquiv = content.match(regexHttpEquiv);
        if (matchHttpEquiv)
            return {
                method: "matchHttpEquiv",
                value: matchHttpEquiv[1].split("-")[0],
            };

        return false;
    }

    public static async checkUrl(
        url: string,
        trackRedirect: boolean = true,
        proxyUrl: string | null = null
    ): Promise<any> {
        try {
            let result: any = false;
            const urlParts = new URL(url);

            if (!urlParts.hostname) {
                return {
                    ok: false,
                    method: "invalid_host",
                };
            }

            const protocol = urlParts.protocol;
            const hostname = urlParts.hostname;
            const path = urlParts.pathname;
            const queryParams = urlParts.searchParams;

            const instance = new this(url);

            // Vérifier le TLD .fr et les sous-domaines indiquant le français
            if (
                hostname.endsWith(".fr") ||
                /^({fr|france|french|francais|français})\./i.test(hostname)
            ) {
                if (!trackRedirect)
                    return {
                        ok: true,
                        method: "direct_match",
                    };

                const newUrl = `${protocol}//${hostname}`;
                const redirections = await instance.handleRedirections(
                    newUrl,
                    url,
                    "",
                    proxyUrl
                );
                if (redirections["ok"])
                    return await instance.recheckUrl(url, redirections["url"]);

                return redirections;
            } // Vérifier les segments de chemin
            else if (
                /\/(fr|france|french|francais|français|fr-fr|fr_fr)(\/|$)/i.test(
                    path
                )
            ) {
                return {
                    ok: true,
                    method: "pattern_match_path",
                };
            } else {
                // Vérifier les paramètres d'URL
                const langParams = ["lang", "locale", "language"];

                langParams.forEach((langParam) => {
                    if (
                        queryParams.get(langParam) &&
                        /^(fr|france|french|francais|français)(-[A-Z]{2})?$/i.test(
                            String(queryParams.get(langParam))
                        )
                    ) {
                        result = {
                            ok: true,
                            method: "pattern_match_query",
                        };
                    }
                });
            }

            return result;
        } catch (error) {
            return {
                ok: false,
                method: "invalid_url",
                error,
            };
        }
    }

    private async recheckUrl(
        originalUrl: string,
        newUrl: string
    ): Promise<any> {
        if (originalUrl === newUrl)
            return {
                ok: true,
                method: "no_redirect",
                url: originalUrl,
            };

        const recheck = await DomainFR.checkUrl(newUrl, false);
        recheck["original_url"] = originalUrl;
        recheck["url"] = newUrl;

        return recheck;
    }

    private async handleRedirections(
        urlToTrack: string,
        url: string | null = null,
        targetContentType: string = "",
        proxyUrl: string | null = null
    ): Promise<any> {
        if (!url) url = urlToTrack;

        try {
            this.tracker.redirects = [];
            this.tracker.finalUrl = null;

            const response = await this.tracker.getUrlRedirection(urlToTrack, proxyUrl);
            const contentType = response.content_type;

            if (response.success && response.status_code === 200) {
                const result = {
                    ok: true,
                    url: response.final_url,
                };

                if (targetContentType) {
                    if (contentType?.includes(targetContentType)) {
                        return result;
                    }
                } else {
                    return result;
                }
            } else {
                throw new Error(
                    JSON.stringify({
                        ok: false,
                        method: "redirect_failed",
                        url,
                        response,
                    })
                );
            }
        } catch (error: any) {
            console.error(
                `Error redirecting with got-scraping for ${url}\n`,
                error
            );

            try {
                const response = await RedirectTracker.getUrlRedirectionPemavor(
                    [urlToTrack]
                );
                const datas = response["data"]["Data"];

                for (const data in datas) {
                    const currentData = datas[data];
                    const value = currentData[currentData.length - 1];
                    const contentType = value?.headers?.["Content-Type"];

                    if (value?.["status_code"] === 200) {
                        if (targetContentType) {
                            if (contentType?.includes(targetContentType)) {
                                return {
                                    ok: true,
                                    url: value["url"],
                                };
                            } else {
                                return {
                                    ok: false,
                                    url: value["url"],
                                    status_code: value["status_code"],
                                    content_type: contentType,
                                };
                            }
                        } else {
                            return {
                                ok: true,
                                url: value["url"],
                            };
                        }
                    } else {
                        return {
                            ok: false,
                            url: value["url"],
                            status_code: value["status_code"],
                        };
                    }
                }
            } catch (pemavorError: any) {
                console.error(
                    `Error redirecting with Pemavor for ${url}\n`,
                    pemavorError
                );
            }

            return {
                ok: false,
                method: "all_redirections_failed",
                url,
            };
        }
    }

    private buildResult(url: string, method: string, isFrench: boolean): any {
        return {
            url,
            method,
            ok: isFrench,
        };
    }

    public async checkPageIfFrench(content: string, isCheckUrl: boolean = true): Promise<any> {
        const url = this._homepage;

        if (!url || !content) return this.buildResult(url, "Info_vide", false);

        if (isCheckUrl) {
            const checkUrl = await DomainFR.checkUrl(url, false);
    
            if (checkUrl["ok"]) return this.buildResult(url, "checkUrl", true);
        }

        // If forced method is set, check it first
        if (this._forcedMethod) {
            const language = this.detectLanguage(content);
            
            // If we find a language and it's French using the forced method
            if (language && language.method === this._forcedMethod && language.value === "fr") {
                return this.buildResult(url, this._forcedMethod, true);
            }
            
            // If forced method didn't work, return false
            return this.buildResult(url, "Check_nok_forced", false);
        }

        const language = this.detectLanguage(content);

        if (!language) return this.buildResult(url, "Check_nok_v1", false);

        if (language && language?.method && language?.value === "fr")
            return this.buildResult(url, language["method"], true);

        return this.buildResult(url, "Check_nok_v2", false);
    }
}

```

`src\class\RedirectTracker.ts`:

```ts
import { ExtendedOptionsOfTextResponseBody, gotScraping } from "got-scraping";
import { IRedirect } from "../interfaces/IRedirect.js";
import { IRedirectResponse } from "../interfaces/IRedirectResponse.js";

export class RedirectTracker {
    private _redirects: IRedirect[];
    private _finalUrl: string | null;

    constructor() {
        this._redirects = [];
        this._finalUrl = null;
    }

    public set redirects(v: any) {
        this._redirects = v;
    }

    public set finalUrl(v: string | null) {
        this._finalUrl = v;
    }

    private getRedirects(): IRedirect[] {
        return this._redirects;
    }

    private getFinalUrl(): string | null {
        return this._finalUrl;
    }

    private getInitialUrl(): string | null {
        return this._redirects.length > 0 ? this._redirects[0].from : null;
    }

    private getRedirectChain(): string[] {
        return this._redirects.map((redirect) => redirect.to);
    }

    public async getUrlRedirection(
        url: string,
        proxyUrl: string | null = null
    ): Promise<IRedirectResponse> {
        try {
            let options: ExtendedOptionsOfTextResponseBody = {
                method: "GET",
                timeout: {
                    request: 5000,
                },
                followRedirect: true,
                maxRedirects: 10,
            };

            if (proxyUrl) options.proxyUrl = proxyUrl;

            const response = await gotScraping(url, options);

            if (response.redirectUrls && response.redirectUrls.length > 0) {
                this._redirects = [];
                let currentUrl = url;

                for (const redirectUrl of response.redirectUrls) {
                    this._redirects.push({
                        from: currentUrl,
                        to: redirectUrl.toString(),
                    });
                    currentUrl = redirectUrl.toString();
                }

                this._finalUrl = response.url;
            } else {
                this._finalUrl = url;
            }

            return {
                success: true,
                initial_url: this.getInitialUrl(),
                final_url: this.getFinalUrl() ?? url,
                redirects: this.getRedirects(),
                redirect_chain: this.getRedirectChain(),
                status_code: response.statusCode,
                content_type: response.headers["content-type"] || "",
            };
        } catch (error: any) {
            throw new Error(
                JSON.stringify({
                    success: false,
                    error: error.message,
                    redirects: this.getRedirects(),
                    redirect_chain: this.getRedirectChain(),
                    status_code: error.response?.statusCode || 0,
                })
            );
        }
    }

    public static async getUrlRedirectionPemavor(
        urls: string[],
        internal: string = "no"
    ): Promise<{
        success: boolean;
        data?: any;
        status_code?: number;
        error?: string;
    }> {
        try {
            // Create form data boundary
            const boundary =
                "geckoformboundary" + crypto.randomUUID().replace(/-/g, "");

            // Construct multipart form data
            const formData = [
                `--${boundary}`,
                'Content-Disposition: form-data; name="url"',
                "",
                JSON.stringify(urls),
                `--${boundary}`,
                'Content-Disposition: form-data; name="internal"',
                "",
                internal,
                `--${boundary}--`,
            ].join("\r\n");

            const options: ExtendedOptionsOfTextResponseBody = {
                method: "POST",
                url: "https://europe-west1-pemavor-free-tools.cloudfunctions.net/HttpStatusCodeChecker",
                headers: {
                    "Content-Type": `multipart/form-data; boundary=${boundary}`,
                },
                body: formData,
            };

            const response = await gotScraping(options);
            const responseData = JSON.parse(response.body);

            return {
                success: true,
                data: responseData,
                status_code: response.statusCode,
            };
        } catch (error: any) {
            throw new Error(
                JSON.stringify({
                    success: false,
                    error: error.message,
                    status_code: error.response?.statusCode || 0,
                })
            );
        }
    }
}

```

`src\functions.ts`:

```ts
import {
    PlaywrightCrawler,
    Log,
    RouterHandler,
    PlaywrightCrawlingContext,
    Dictionary,
    Dataset,
    KeyValueStore,
    RequestQueue,
    StatisticState,
    ProxyConfiguration,
    PlaywrightCrawlerOptions,
    LoadedRequest,
    Request,
    Configuration,
} from "crawlee";
import { Page } from "playwright";
import fs from "fs";
import {
    QueueJsonContent,
    JsonInnerContent,
    UrlParameters,
} from "./interfaces/queue.js";

export let stats: StatisticState;

/**
 * Simulates infinite scroll behavior on a page until no new content loads
 * @param page - Playwright Page object
 * @param url - Current page URL for logging
 * @param log - Logger instance
 * @param maxScrolls - Maximum number of scrolls to perform (default: 100)
 * @param timeoutSecs - Maximum time in seconds to spend scrolling (default: 30)
 */
/**
 * Simulates infinite scroll behavior on a page until no new content loads
 * @param page - Playwright Page object
 * @param url - Current page URL for logging
 * @param log - Logger instance
 * @param maxScrolls - Maximum number of scrolls to perform (default: 100)
 * @param timeoutSecs - Maximum time in seconds to spend scrolling (default: 30)
 */
export const waitAndScroll = async (
    page: Page,
    url: string,
    log: Log,
    maxScrolls: number = 100,
    timeoutSecs: number = 30
) => {
    try {
        // Wait for initial network requests to complete
        await page.waitForLoadState("networkidle");

        // Track page height to detect when scrolling reaches the bottom
        let previousHeight = await page.evaluate("document.body.scrollHeight");
        let newHeight;
        let scrolls = 0;
        const startTime = Date.now();

        do {
            // Check limits
            if (scrolls >= maxScrolls) {
                log.warning(`Max scrolls (${maxScrolls}) reached for ${url}`);
                break;
            }

            if ((Date.now() - startTime) / 1000 > timeoutSecs) {
                log.warning(`Scroll timeout (${timeoutSecs}s) reached for ${url}`);
                break;
            }

            // Scroll to bottom of current page
            await page.evaluate(
                "window.scrollTo(0, document.body.scrollHeight)"
            );

            // Allow time for new content to load
            await page.waitForTimeout(750);

            // Get new page height after potential content load
            newHeight = await page.evaluate("document.body.scrollHeight");

            // If height hasn't changed, we've reached the bottom
            if (newHeight === previousHeight) {
                // log.info(`Reached the end of the page: ${url}`);
                break;
            }

            previousHeight = newHeight;
            scrolls++;
        } while (true);
    } catch (error) {
        // Log any errors that occur during scrolling
        log.error(`Error while scrolling the page: ${url} : ${error}`);
    }
};

/**
 * Process a page by scrolling through all content and returning the HTML
 * @param page - Playwright Page object
 * @param url - Current page URL
 * @param log - Logger instance
 * @param maxScrolls - Maximum number of scrolls to perform (default: 100)
 * @param timeoutSecs - Maximum time in seconds to spend scrolling (default: 30)
 * @returns Promise<string> - Complete page HTML content
 */
export const processPage = async (
    page: Page,
    url: string,
    log: Log,
    maxScrolls: number = 100,
    timeoutSecs: number = 30
) => {
    try {
        // First scroll through all content with safety limits
        await waitAndScroll(page, url, log, maxScrolls, timeoutSecs);
        let content = await page.content();

        // Return the complete page HTML after scrolling
        return content;
    } catch (error) {
        log.error(`Error processPage for ${url}: ${error}`);
        // Return current content even if scrolling failed, to avoid crashing the whole crawl
        try {
            return await page.content();
        } catch (innerError) {
            throw new Error(`Critical error processPage : ${error}`);
        }
    }
};

/**
 * Drops (deletes) an existing dataset by its name
 *
 * @description
 * This function opens an existing dataset and completely removes it from storage.
 * Useful when you need to start fresh before a new crawling session.
 *
 * @param {string} name - The name of the dataset to drop (e.g., 'fp-domain.com')
 * @returns {Promise<void>} A promise that resolves when the dataset is dropped
 *
 * @example
 * ```typescript
 * // Drop a dataset named 'fp-example.com'
 * await dropDataset('fp-example.com');
 * ```
 *
 * @throws Will throw an error if the dataset cannot be opened or dropped
 */
export const dropDataset = async (name: string) => {
    try {
        let datasetToDrop = await Dataset.open(name);
        await datasetToDrop.drop();
    } catch (error) {
        throw new Error(`Error dropDataset : ${error}`);
    }
};

/**
 * Initializes and runs a Playwright crawler with specified configuration
 *
 * @description
 * Creates a new PlaywrightCrawler instance with:
 * - Browser fingerprinting to avoid detection
 * - Session management for maintaining state
 * - Error handling for failed requests
 * - French locale and multiple browser/OS emulation
 *
 * @param {RouterHandler<PlaywrightCrawlingContext<Dictionary>>} router - The router handler for processing different URL patterns
 * @param {Array<string>} startUrl - Array of URLs to start crawling from
 *
 * @returns {Promise<void>} Resolves when crawling is complete
 *
 * @example
 * ```typescript
 * const router = createPlaywrightRouter();
 * router.addDefaultHandler(async ({ request }) => {
 *     // Handle URLs
 * });
 *
 * await startCrawler(router, [
 *     'https://example.com/page1',
 *     'https://example.com/page2'
 * ]);
 * ```
 *
 * @throws Will throw if crawler initialization fails or if any unhandled errors occur during crawling
 */
export const startCrawler = async (
    router: RouterHandler<PlaywrightCrawlingContext<Dictionary>>,
    startUrl: Array<string>,
    domain: string,
    paramPerCrawl: number,
    paramPerMinute: number,
    apifyProxyPassword?: string,
    breakLimit?: boolean,
    bypassQuestionMark?: boolean,
    bypassDiez?: boolean,
    skipquestionmark?: boolean,
    skipdiez?: boolean
) => {
    const requestQueue = await RequestQueue.open(domain);

    // Apify proxy
    const PROXY_HOST = "proxy.apify.com";
    const PROXY_HOST_PORT = 8000;
    const PROXY_USERNAME = "auto";
    const PROXY_USERNAME_FR = "country-FR";
    const PROXY_PASSWORD = apifyProxyPassword;

    const proxyUrl = `http://${PROXY_USERNAME}:${PROXY_PASSWORD}@${PROXY_HOST}:${PROXY_HOST_PORT}`;
    const proxyUrlFR = `http://${PROXY_USERNAME_FR}:${PROXY_PASSWORD}@${PROXY_HOST}:${PROXY_HOST_PORT}`;

    let proxyConfiguration: ProxyConfiguration | undefined;

    // CRITICAL MEMORY OPTIMIZATION: Force Crawlee to use disk instead of RAM

    let configuration = new Configuration({
        maxUsedCpuRatio: 0.95,
        availableMemoryRatio: 0.95,
        persistStorage: true         // Force all storage to disk (not just cache)
    });

    if (PROXY_PASSWORD) {
        proxyConfiguration = new ProxyConfiguration({
            proxyUrls: [proxyUrl],
            // tieredProxyUrls: [[proxyUrlFR], [proxyUrl]],
        });
    }

    let optionsCrawler: PlaywrightCrawlerOptions = {
        // Router to handle different URL patterns and their processing logic
        requestHandler: router,

        // RequestQueue
        requestQueue,

        // headless: true,             // Run browser in headless mode

        // Browser fingerprinting configuration to avoid detection
        browserPoolOptions: {
            // useFingerprints: true, // Enable browser fingerprinting (Invalid property in BrowserPoolOptions)
            fingerprintOptions: {
                fingerprintGeneratorOptions: {
                    browsers: ["firefox", "chrome", "safari"], // Browser types to rotate
                    locales: ["fr-FR"], // Use French locale
                    devices: ["desktop"], // Target device type
                    operatingSystems: ["windows", "macos", "linux"], // OS to emulate
                },
            },
            retireBrowserAfterPageCount: 5, // Aggressive rotation to prevent memory leaks on unstable sites
        },

        // minConcurrency: 1, // Ensure at least one browser is running
        maxConcurrency: 1, // CRITICAL: Reduced to 2 to prevent OOM on CPU-saturated machines (was 15)
        navigationTimeoutSecs: 90, // Increased to 90s to tolerate slow sites (was 60s)
        requestHandlerTimeoutSecs: 120, // Increased to allow for retries and slow processing

        // Session management configuration
        useSessionPool: true, // Enable session pooling
        persistCookiesPerSession: true, // Maintain cookies between requests
        sessionPoolOptions: {
            blockedStatusCodes: [401, 403, 429, 404, 410, 423, 502, 500, 503], // Status codes to mark session as blocked
        },

        // Error handling for failed requests
        failedRequestHandler: async ({ request, log, page }) => {
            log.error(
                `Request ${request.url} failed with error : ${String(
                    request.errorMessages
                )}`
            );

            // Try getting content for analysis
            try {
                let content = await processPage(page, request.loadedUrl, log);

                /**
                 * @description Checking if the page contains CAPTCHA
                 * @todo
                 *  reCAPTCHA V2 : Checking if the page contains the class .g-recaptcha
                 *  reCAPTCHA V3 : Checking if the page contains grecaptcha.execute
                 *  reCAPTCHA V3 Enterprise : Checking if the page contains grecaptcha.enterprise.execute
                 *  Cloudflare Turnstile : Checking if the page contains the class .cf-turnstile
                 *  KeyCAPTCHA : Checking if the page contains s_s_c_user_id, s_s_c_session_id, s_s_c_web_server_sign, s_s_c_web_server_sign2
                 *  Lemin Captcha : Checking if the page contains api.leminnow.com
                 *  DataDome Captcha : Checking if the page contains geo.captcha-delivery.com
                 */
                let captchaDetected = "";
                let checkCaptcha = await page.$(".g-recaptcha");
                if (checkCaptcha) {
                    captchaDetected = "reCAPTCHA V2";
                } else {
                    checkCaptcha = await page.$(".cf-turnstile");
                    if (checkCaptcha) {
                        captchaDetected = "Cloudflare Turnstile";
                    } else {
                        // Continue with the check of content
                        if (
                            content.includes("grecaptcha.execute") ||
                            content.includes("grecaptcha.enterprise.execute")
                        ) {
                            captchaDetected = "reCAPTCHA V3";
                        } else if (content.includes("api.leminnow.com")) {
                            captchaDetected = "Lemin Captcha";
                        } else if (
                            content.includes("geo.captcha-delivery.com")
                        ) {
                            captchaDetected = "DataDome Captcha";
                        } else if (
                            content.includes("s_s_c_user_id") &&
                            content.includes("s_s_c_session_id") &&
                            content.includes("s_s_c_web_server_sign") &&
                            content.includes("s_s_c_web_server_sign2")
                        ) {
                            captchaDetected = "KeyCAPTCHA";
                        }
                    }
                }

                if (captchaDetected) {
                    log.error(
                        `Captcha detected on ${request.url} : ${captchaDetected}`
                    );
                }
            } catch (error) {
                log.error(
                    `Error when processing the page ${request.url} : ${error}`
                );
            }

            let dataset = await Dataset.open(`error-${domain}`);
            await dataset.pushData({
                id: request.id,
                url: request.url,
                errors: request.errorMessages,
            });
        },

        preNavigationHooks: [
            async () => {
                const isStopped = isStoppedManualy(domain, false);
                if (isStopped) {
                    await stopCrawler(
                        crawler,
                        "The crawler has been stopped manually."
                    );
                }

                if (!breakLimit) {
                    // OPTIMIZATION: Use getInfo() to check count without loading data
                    // This avoids loading the entire dataset into memory on every request
                    const dataset = await Dataset.open(domain);
                    const info = await dataset.getInfo();
                    const count = info ? info.itemCount : 0;
                    const limitUrls = 5000;

                    if (count >= limitUrls) {
                        await stopCrawler(
                            crawler,
                            `We have reached the limit of ${limitUrls} entries. The crawler will be stopped.`
                        );
                    }
                }
            },
        ],

        postNavigationHooks: [
            async () => {
                const limitQuestionMarkDiez = 50;

                if (
                    (!bypassQuestionMark && !skipquestionmark) ||
                    (!bypassDiez && !skipdiez)
                ) {
                    // OPTIMIZATION: Load dataset in batches of 1000 instead of loading everything
                    const dataset = await Dataset.open(domain);
                    const info = await dataset.getInfo();
                    const totalItems = info ? info.itemCount : 0;

                    const patternQuestionMark = new RegExp(
                        `(?:/[^?]*)?\\?.*$`
                    );
                    const patternDiez = new RegExp(
                        `(?:/[^#]*)?#.*$`
                    );
                    let countQuestionMark = 0;
                    let countDiez = 0;
                    let offset = 0;
                    const batchSize = 1000;

                    // Iterate through dataset in batches
                    while (offset < totalItems) {
                        const batch = await dataset.getData({
                            offset,
                            limit: batchSize
                        });

                        for (const item of batch.items) {
                            if (patternQuestionMark.test(item.url)) {
                                countQuestionMark++;
                            }

                            if (patternDiez.test(item.url)) {
                                countDiez++;
                            }

                            // Early exit if limit reached
                            if (
                                (!bypassQuestionMark &&
                                    !skipquestionmark &&
                                    countQuestionMark >= limitQuestionMarkDiez) ||
                                (!bypassDiez &&
                                    !skipdiez &&
                                    countDiez >= limitQuestionMarkDiez)
                            ) {
                                break;
                            }
                        }

                        // Check limits after each batch
                        if (
                            !bypassQuestionMark &&
                            !skipquestionmark &&
                            countQuestionMark >= limitQuestionMarkDiez
                        ) {
                            await stopCrawler(
                                crawler,
                                `We have reached the limit of ${limitQuestionMarkDiez} entries with a question mark. The crawler will be stopped.`
                            );
                            break;
                        }

                        if (
                            !bypassDiez &&
                            !skipdiez &&
                            countDiez >= limitQuestionMarkDiez
                        ) {
                            await stopCrawler(
                                crawler,
                                `We have reached the limit of ${limitQuestionMarkDiez} entries with a #. The crawler will be stopped.`
                            );
                            break;
                        }

                        offset += batchSize;
                    }
                }
            },
        ],
    };

    if (paramPerCrawl > 0) {
        optionsCrawler.maxRequestsPerCrawl = paramPerCrawl; // Limit total number of requests
    }

    if (paramPerMinute > 0) {
        optionsCrawler.maxRequestsPerMinute = paramPerMinute; // Limit requests per minute
    }

    if (proxyConfiguration) {
        optionsCrawler.proxyConfiguration = proxyConfiguration;
    }

    const crawler = new PlaywrightCrawler(optionsCrawler, configuration);

    if (await requestQueue.isEmpty()) {
        console.log("RequestQueueEmpty");
        await requestQueue.addRequest({
            url: startUrl[0],
        });
    } else {
        console.log("RequestQueueNotEmpty");
        const queueInfo = await requestQueue.getInfo();
        console.log("Resume crawling : ", JSON.stringify(queueInfo, null, 2));
    }

    await crawler.run();

    stats = crawler.stats.state;

    console.log(
        JSON.stringify(
            {
                CrawlingStats: crawler.stats,
            },
            null,
            2
        )
    );

    return crawler; // Return crawler instance for cleanup hooks
};

/**
 * Verify if a file that indicate the crawler to stop exists , and add a history
 *
 * @param {string} name - The name of the domain
 * @param {boolean} historised - True if the history should be added, false otherwise
 * @returns {boolean} - True if the file exists, false otherwise
 *
 * @description
 * This function checks if a file named "{domaine}.txt" exists in the directory 'stopper'.
 * if the file exists, it indicates that the crawler should stop.
 * It also adds a history of the stop in the file 'history-{domaine}.txt'.
 * And it will remove the file 'stopper/{domaine}.txt' if it exists.
 *
 */
export const isStoppedManualy = (name: string, historised: boolean) => {
    if (fs.existsSync(`stopper/${name}.txt`)) {
        if (historised) {
            console.log("The crawler has been stopped manually.");
            const date = new Date();
            const dateString = date.toISOString();
            fs.appendFileSync(
                `stopper/history-${name}.txt`,
                `- Date arrêt : ${dateString}\n`
            );
            fs.unlinkSync(`stopper/${name}.txt`);
        }
        return true;
    } else {
        return false;
    }
};

/**
 * Retrieves all url scraped from a folder request_urls/{domain}
 *
 * @param {string} name - The name of the domain
 * @param {boolean} historised - True if the file existant should be historised
 * @returns {Array<string>} - list of the urls already crawled
 *
 * @description
 * This function checks if a file named "{domaine}.json" exists in the directory 'request_urls/{domain}'.
 * if the file exists, convert the content as array and be the result return
 * if the file doesn't exists, create the directory 'request_urls/{domain}' if it doesn't exists and then create the file named "{domaine}.json" and return []
 * And if historised is true, create a copy of the file as "YYYY-mm-dd-{domaine}.json"  in the same directory and update the the file named "{domaine}.json" as []
 *
 */

export const getUrlsCrawled = (
    name: string | undefined,
    historised: boolean,
    dropData: string | undefined = undefined
) => {
    // console.log(`name of domaine ${name}`);
    // Since process.chdir(storagePath) has been called, we're already in the job directory
    // So ./request_urls/ will point to /app/storage/{jobId}/request_urls/
    var folderName = `./request_urls/${name}`;
    // console.log(`folderName ${folderName}`);
    try {
        if (!fs.existsSync(folderName)) {
            fs.mkdirSync(folderName, { recursive: true });
        }
    } catch (err) {
        console.error("Couldn't create the folder ");
        console.error(err);
        folderName = "./request_urls";
    }

    var fileUrls = `${folderName}/${name}.json`;

    if (dropData) {
        // If dropData is set, we want to drop the file
        console.log("Droping the file " + fileUrls);
        if (fs.existsSync(fileUrls)) {
            fs.unlinkSync(fileUrls);
        }
    }

    if (fs.existsSync(fileUrls)) {
        let listUrls: Array<string> = [];
        if (historised) {
            console.log("The list of urls crawled have been historised");
            const date = new Date();
            const dateString = date.toISOString();

            const fileHistorised = `${folderName}/${dateString.split("T")[0]
                }-${name}.json`;
            fs.copyFileSync(fileUrls, fileHistorised);

            // update the the file named "{domaine}.json" as []
            fs.writeFileSync(fileUrls, "[]");
        } else {
            // get the content of the file json as array
            const content = fs.readFileSync(fileUrls, "utf8");
            const tempListUrls = JSON.parse(content);
            if (tempListUrls.length > 0) {
                listUrls = tempListUrls;
            }
        }
        return listUrls;
    } else {
        console.log("First creation of the file list urls");
        const fsLog = fs.createWriteStream(fileUrls, {
            flags: "a", // 'a' means appending
        });
        fs.writeFileSync(fileUrls, "[]");
        return [];
    }
};

/**
 * Update the content  of the file named "{domaine}.json" in the folder request_urls/{domain}
 *
 * @param {string} name - The name of the domain
 * @param {Array<string>} listUrls - list of the urls already crawled
 * @returns void
 *
 * @description
 * This function update the content of the file named "{domaine}.json" with the list of the urls already crawled
 *
 */
export const updateUrlsCrawled = (
    name: string | undefined,
    listUrls: Array<string>
) => {
    var folderName = `./storage/request_urls/${name}`;
    var fileUrls = `${folderName}/${name}.json`;
    // console.log("listUrls  : ", JSON.stringify(listUrls));

    if (fs.existsSync(fileUrls)) {
        // console.log("update file ");
        // update the the file named "{domaine}.json" as listUrls
        fs.writeFileSync(fileUrls, JSON.stringify(listUrls));
    }
};

/**
 * Retrieves scraped data from a named dataset with optional pagination
 *
 * @description
 * Opens a dataset by name and retrieves all data or a limited subset.
 * When countArray is specified, results are sorted in descending order.
 * When countArray is 0 or omitted, returns all dataset items.
 *
 * @param {string} name - The name of the dataset to retrieve (e.g., 'fp-domain.com')
 * @param {number} [countArray=0] - Maximum number of items to retrieve. 0 means no limit
 *
 * @returns {Promise<{
 *   items: Array<Dictionary>, // Array of scraped items
 *   total: number,           // Total number of items in dataset
 *   offset: number,          // Starting position of retrieved items
 *   count: number,           // Number of items retrieved
 *   limit: number           // Maximum items that were requested
 * }>} Dataset items and pagination metadata
 *
 * @example
 * // Get all items from dataset
 * const allData = await getScrapingData('fp-example.com');
 *
 * // Get first 10 items from dataset
 * const limitedData = await getScrapingData('fp-example.com', 10);
 *
 * @throws {Error} If dataset cannot be opened
 * @throws {Error} If data retrieval fails
 */
export const getScrapingData = async (name: string, countArray: number = 0) => {
    try {
        let dataset = await Dataset.open(name);

        // Check if dataset exists and has items
        const info = await dataset.getInfo();
        if (!info || info.itemCount === 0) {
            // Return empty structure if dataset is empty or doesn't exist
            return { items: [], total: 0, offset: 0, count: 0, limit: 0 };
        }

        let data;

        if (countArray === 0) {
            data = await dataset.getData();
        } else {
            data = await dataset.getData({
                desc: true,
                limit: countArray,
            });
        }

        return data;
    } catch (error) {
        throw new Error(`Error when getScrapingData : ${error}`);
    }
};

/**
 * Stores scraped data in a KeyValueStore with customizable storage options
 *
 * @description
 * Retrieves data from a dataset by name and stores it in a KeyValueStore.
 * Allows customization of:
 * - Dataset name to retrieve from
 * - Number of items to store
 * - Custom domain for KeyValueStore (defaults to dataset name)
 *
 * @param {string} name - Dataset name to retrieve data from
 * @param {number} [countArray=0] - Maximum number of items to store (0 = unlimited)
 * @param {string} [domain=""] - Custom domain for KeyValueStore (defaults to name if empty)
 *
 * @returns {Promise<void>} Resolves when data is successfully stored in KeyValueStore
 *
 * @example
 * // Store all items from 'products' dataset using same name for KeyValueStore
 * await storeKeyValueStore('products');
 *
 * // Store 10 items from 'fp-products' dataset with custom domain
 * await storeKeyValueStore('fp-products', 10, 'example.com');
 *
 * @throws {Error} If dataset access fails
 * @throws {Error} If KeyValueStore creation/access fails
 * @throws {Error} If data storage operation fails
 */
export const storeKeyValueStore = async (
    name: string,
    countArray: number = 0,
    domain: string = ""
) => {
    try {
        const data = await getScrapingData(name, countArray);

        if (!domain) {
            domain = name;
        }

        if (data.total) {
            const store = await KeyValueStore.open(domain);
            await store.setValue(name, data.items);
        }
    } catch (error) {
        throw new Error(`Error storeKeyValueStore : ${error}`);
    }
};

/**
 * Splits a URL into its base URL and path components, removing query parameters and hash fragments.
 *
 * @param url - The URL string to parse. Can be complete URL, partial URL, or path.
 * @returns Object containing:
 *          - baseUrl: The URL with protocol and host (e.g., 'https://example.com')
 *          - path: Clean path component starting with '/', or empty string if:
 *            - URL has no path
 *            - URL only has query parameters
 *            - URL only has hash fragment
 *
 * @throws Never throws - handles all errors internally with fallback parsing strategies
 *
 * @error-handling
 * 1. Attempts standard URL parsing with provided URL
 *    - Removes query params and hash fragments from pathname
 * 2. If fails, prepends 'http://' and attempts URL parsing again
 *    - Applies same pathname cleaning
 * 3. If all parsing fails, falls back to string splitting
 *    - Splits on '?' or '#' first, then '/'
 *
 * @example
 * // Complete URLs with query params and hash
 * getPathAfterDomain('https://example.com/path?param=1#hash')  // => { baseUrl: 'https://example.com', path: '/path' }
 * getPathAfterDomain('https://site.com/?param=1')             // => { baseUrl: 'https://site.com', path: '' }
 * getPathAfterDomain('https://site.com/page#section')         // => { baseUrl: 'https://site.com', path: '/page' }
 *
 * // Partial or malformed URLs
 * getPathAfterDomain('example.com/path?param=1')              // => { baseUrl: 'http://example.com', path: '/path' }
 * getPathAfterDomain('site.com/#/route')                      // => { baseUrl: 'http://site.com', path: '' }
 */
export const getPathAfterDomain = (
    url: string
): { baseUrl: string; path: string } => {
    try {
        const urlObject = new URL(url);
        const pathWithoutParams = urlObject.pathname
            .split("?")[0]
            .split("#")[0];
        return {
            baseUrl: `${urlObject.protocol}//${urlObject.host}`,
            path: pathWithoutParams.length > 1 ? pathWithoutParams : "",
        };
    } catch (error) {
        try {
            const urlWithProtocol = url.startsWith("http")
                ? url
                : `http://${url}`;
            const urlObject = new URL(urlWithProtocol);
            const pathWithoutParams = urlObject.pathname
                .split("?")[0]
                .split("#")[0];
            return {
                baseUrl: `${urlObject.protocol}//${urlObject.host}`,
                path: pathWithoutParams.length > 1 ? pathWithoutParams : "",
            };
        } catch {
            const parts = url.split(/[?#]/)[0].split("/");
            return {
                baseUrl: `http://${parts[0]}`,
                path: parts.length > 1 ? "/" + parts.slice(1).join("/") : "",
            };
        }
    }
};

export const rightTrimSlash = (str: string) => {
    return str.replace(/\/+$/, "");
};

/**
 * Attaches a file system logger that captures console.log output to both console and file.
 *
 * @param fileName - Name of the log file. File will be created if it doesn't exist.
 *                  If file exists, logs will be appended.
 *
 * @description
 * - Preserves original console.log functionality while adding file logging
 * - Strips ANSI color codes from file output
 * - Uses append mode ('a') to preserve existing log content
 * - Automatically adds newlines between log entries
 *
 * @example
 * // Start logging to file
 * attachFSLogger('./logs/app.log');
 *
 * console.log('Hello');  // Outputs to both console and file
 * console.log('World');  // Multiple calls create separate lines
 *
 * @note
 * This function modifies the global console.log behavior.
 * All subsequent console.log calls will be captured until process ends.
 */
export const attachFSLogger = (fileName: string) => {
    // remember the old log method
    const oldLog = console.log; // remove this line if you only want to log into the file
    const oldInfo = console.info;
    const oldWarn = console.warn;
    const oldError = console.error;
    const oldDebug = console.debug;

    //creer un dossier avec année/mois
    const date = new Date();
    const dateString = date.toISOString().split("T")[0];
    const folderDate =
        dateString.split("-")[0] + "/" + dateString.split("-")[1];

    let folderName = `./logs/` + folderDate;

    try {
        if (!fs.existsSync(folderName)) {
            fs.mkdirSync(folderName, { recursive: true });
        }
    } catch (err) {
        console.error("Couldn't create the folder " + folderName);
        console.error(err);
        folderName = `./logs`;
    }

    // create a write stream for the given folderName + file name
    const fsLog = fs.createWriteStream(folderName + "/" + fileName, {
        flags: "a", // 'a' means appending
    });

    // override console.log
    console.log = (...messages) => {
        // log the console message immediately as usual
        oldLog.apply(console, messages); // remove this line if you only want to log into the file

        // stream message to the file log
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };

    // override console.error
    console.error = (...messages) => {
        // log the console message immediately as usual
        oldError.apply(console, messages); // remove this line if you only want to log into the file

        // stream message to the file log
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };

    // override console.info
    console.info = (...messages) => {
        // log the console message immediately as usual
        oldInfo.apply(console, messages); // remove this line if you only want to log into the file

        // stream message to the file log
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };

    // override console.warn
    console.warn = (...messages) => {
        // log the console message immediately as usual
        oldWarn.apply(console, messages); // remove this line if you only want to log into the file

        // stream message to the file log
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };

    // override console.debug
    console.debug = (...messages) => {
        // log the console message immediately as usual
        oldDebug.apply(console, messages); // remove this line if you only want to log into the file

        // stream message to the file log
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };
};

/**
 * Removes ANSI escape codes from a string or stringifies non-string input.
 *
 * @param str - Input to process. Can be string or any other type.
 * @returns
 * - For strings: Returns string with all ANSI escape codes removed
 * - For non-strings: Returns prettified JSON string representation
 *
 * @description
 * Handles:
 * - ANSI color codes (e.g. \u001b[31m for red)
 * - Other ANSI escape sequences
 * - Non-string inputs via JSON.stringify
 *
 * @example
 * stripAnsi('\u001b[31mRed text\u001b[0m')  // => 'Red text'
 * stripAnsi({ key: 'value' })               // => '{\n  "key": "value"\n}'
 */
const stripAnsi = (str: string) => {
    if (typeof str !== "string") {
        return JSON.stringify(str, null, 2);
    }

    return str.replace(/\u001b\[\d+m/g, "");
};

/**
 * Reclaims failed requests from error dataset for retry processing.
 *
 * @param name - The name of the original request queue and dataset
 *               Error dataset will be prefixed with "error-"
 *
 * @description
 * Process:
 * 1. Retrieves failed requests from error dataset
 * 2. For each failed request:
 *    - Fetches original request from queue
 *    - Resets retry count and error messages
 *    - Clears handled timestamp
 *    - Requeues for processing
 * 3. Drops error dataset after reclaiming
 *
 * @throws {Error} If dataset or queue access fails
 *
 * @example
 * // Reclaim failed requests from 'products' queue
 * await reclaimFailedRequest('products');
 * // Will process requests from 'error-products' dataset
 * // And requeue them in 'products' queue
 */
export const reclaimFailedRequest = async (name: string) => {
    const datasError = await getScrapingData(`error-${name}`);

    for await (const data of datasError.items) {
        const requestID = data["id"];
        const requestQueue = await RequestQueue.open(name);
        let request = await requestQueue.getRequest(requestID);

        if (request) {
            request.retryCount = 0;
            request.errorMessages = [];
            request.handledAt = undefined;

            await requestQueue.reclaimRequest(request);
        }
    }

    await dropDataset(`error-${name}`);
};

export const routerDefaultHandler = async (
    request: LoadedRequest<Request<Dictionary>>,
    requestQueue: RequestQueue,
    url: string,
    content: string,
    domain: string | undefined
) => {
    let results = {
        url,
        content,
    };

    let dataset = await Dataset.open(domain);
    await dataset.pushData(results);

    // Mark request as success
    await requestQueue.markRequestHandled(request);
};

export const stopCrawler = async (crawler: PlaywrightCrawler, message: string) => {
    crawler.log.info(message);
    crawler.autoscaledPool
        ?.pause()
        .then(async () => crawler.autoscaledPool?.abort())
        .then(() =>
            crawler.log.info("The crawler has been gracefully stopped.")
        )
        .catch((error) => {
            crawler.log.error(
                "An error occurred when stopping the crawler : ",
                error
            );
        });
};

export const escapeRegExp = (string: string) => {
    return string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); // $& means the whole matched string
};

/**
 * Gets all JSON files from a specific request queue folder in storage/request_queues
 *
 * @param {string} queueName - The name of the request queue folder to read
 * @returns {Promise<Array<string>>} Array of full paths to JSON files in the queue folder
 *
 * @example
 * ```typescript
 * // Get all JSON files from the 'example.com' request queue
 * const files = await getAllRequestQueues('example.com');
 * console.log(files); // ['storage/request_queues/example.com/000000123.json', ...]
 * ```
 *
 * @throws Will throw an error if accessing request queue folder fails
 */
export const getAllRequestQueues = (queueName: string): string[] => {
    try {
        const requestQueuesPath = `storage/request_queues/${queueName}`;
        if (!fs.existsSync(requestQueuesPath)) {
            return [];
        }

        // Get all files and filter for .json files, then map to full paths
        const queueFiles = fs
            .readdirSync(requestQueuesPath)
            .filter((file) => file.endsWith(".json"))
            .map((file) => `${requestQueuesPath}/${file}`);

        return queueFiles;
    } catch (error) {
        throw new Error(
            `Error getAllRequestQueues for queue ${queueName}: ${error}`
        );
    }
};

/**
 * Process a URL to filter query parameters and remove hash fragments
 *
 * @param {string} url - URL to process
 * @param {boolean} skipQuestionMark - Whether to process URLs with question marks
 * @param {boolean} skipDiez - Whether to process URLs with hash symbols
 * @param {UrlParameters} [parameters] - URL parameters configuration object
 *
 * @returns {string} Processed URL with filtered parameters and/or removed hash
 *
 * @example
 * ```typescript
 * // Keep only specific parameters
 * const url = processUrl('https://example.com?page=1&utm_source=abc', true, true, { toKeep: ['page'] });
 * // Result: https://example.com?page=1
 *
 * // Remove specific parameters and hash
 * const url = processUrl('https://example.com?id=123&utm_source=abc#section', true, true, { toRemove: ['utm_source'] });
 * // Result: https://example.com?id=123
 * ```
 */
export const processUrl = (
    url: string,
    skipQuestionMark: boolean,
    skipDiez: boolean,
    parameters: UrlParameters = {}
): string => {
    // Default parameters
    const defaultParametersToKeep = ["page", "id", "lang"];

    // Validate parameters
    if (parameters.toKeep && parameters.toRemove) {
        throw new Error("Cannot specify both toKeep and toRemove parameters");
    }

    let processedUrl = url;

    // First handle hash if needed
    let baseUrlPart = processedUrl;
    let hashPart = "";

    if (processedUrl.includes("#")) {
        const [base, hash] = processedUrl.split("#");
        baseUrlPart = base;
        hashPart = "#" + hash;
        if (skipDiez) {
            hashPart = "";
        }
    }

    // Process URL if it contains ? and skipQuestionMark is true
    if (skipQuestionMark && baseUrlPart.includes("?")) {
        const [baseUrl, queryString] = baseUrlPart.split("?");
        const params = new URLSearchParams(queryString);
        const filteredParams = new URLSearchParams();

        if (parameters.toKeep || parameters.toRemove) {
            const entries = Array.from(params.entries());

            if (parameters.toKeep) {
                // Keep only specified parameters
                for (const [key, value] of entries) {
                    if (parameters.toKeep.includes(key)) {
                        filteredParams.append(key, value);
                    }
                }
            } else if (parameters.toRemove) {
                // Remove specified parameters
                for (const [key, value] of entries) {
                    if (!parameters.toRemove.includes(key)) {
                        filteredParams.append(key, value);
                    }
                }
            }
        } else {
            // Use default parameters
            const entries = Array.from(params.entries());
            for (const [key, value] of entries) {
                if (defaultParametersToKeep.includes(key)) {
                    filteredParams.append(key, value);
                }
            }
        }

        const newQueryString = filteredParams.toString();
        baseUrlPart = newQueryString ? `${baseUrl}?${newQueryString}` : baseUrl;
    }

    // Combine the parts
    return baseUrlPart + hashPart;
};

/**
 * Parse and modify JSON files from request queues
 *
 * @param {string | string[]} jsonPaths - Single JSON file path or array of paths
 * @param {boolean} skipQuestionMark - Whether to process URLs with question marks
 * @param {boolean} skipDiez - Whether to process URLs with hash symbols
 * @param {UrlParameters} [parameters] - URL parameters configuration object
 *
 * @description
 * Processes JSON files from request queues and modifies URLs based on settings:
 * - Only processes files with non-null orderNo
 * - For URLs with ? (when skipQuestionMark is true):
 *   - If parameters.toKeep is set: keeps only specified parameters
 *   - If parameters.toRemove is set: removes specified parameters
 *   - If neither is set: uses default parameters
 * - For URLs with # (when skipDiez is true):
 *   - Removes everything after and including #
 *
 * @example
 * ```typescript
 * // Process single file, keep only specific parameters
 * await parseJsonFiles('path/to/file.json', true, true, { toKeep: ['page', 'id'] });
 *
 * // Process multiple files, remove specific parameters
 * await parseJsonFiles(['file1.json', 'file2.json'], true, true, { toRemove: ['utm_source', 'utm_medium'] });
 * ```
 */
export const parseJsonFiles = (
    jsonPaths: string | string[],
    skipQuestionMark: boolean,
    skipDiez: boolean,
    parameters: UrlParameters = {}
): void => {
    try {
        const paths = Array.isArray(jsonPaths) ? jsonPaths : [jsonPaths];

        for (const path of paths) {
            // Read and parse the JSON file
            const fileContent = fs.readFileSync(path, "utf-8");
            const jsonContent = JSON.parse(fileContent) as QueueJsonContent;

            // Skip if orderNo is null
            if (!jsonContent.orderNo) continue;

            const processedUrl = processUrl(
                jsonContent.url,
                skipQuestionMark,
                skipDiez,
                parameters
            );

            // If URL was modified, update both the root URL and the URL in the nested JSON
            if (processedUrl !== jsonContent.url) {
                jsonContent.url = processedUrl;

                // Parse and update the nested JSON
                const innerJson = JSON.parse(
                    jsonContent.json
                ) as JsonInnerContent;
                innerJson.url = processedUrl;
                jsonContent.json = JSON.stringify(innerJson);

                // Write the modified JSON back to file
                fs.writeFileSync(path, JSON.stringify(jsonContent, null, 2));
            }
        }
    } catch (error) {
        throw new Error(`Error parsing JSON files: ${error}`);
    }
};

/**
 * Manages French language detection method storage for domains
 *
 * @param {string} name - Domain name
 * @param {string | null} checkFrenchMethod - Method to store (null if retrieving)
 * @returns {string | Error} Stored method or error if not found
 */
export const manageFrenchDetectionMethod = (
    name: string,
    checkFrenchMethod: string | null = null
): string | Error => {
    try {
        const storagePath = `./storage/miscellaneous/${name}`;
        const filePath = `${storagePath}/${name}.json`;

        // If checkFrenchMethod is provided, we want to store it
        if (checkFrenchMethod) {
            // Create directories if they don't exist
            if (!fs.existsSync(storagePath)) {
                fs.mkdirSync(storagePath, { recursive: true });
            }

            // Store new method (overwrite if exists)
            fs.writeFileSync(
                filePath,
                JSON.stringify({ method: checkFrenchMethod }, null, 2)
            );
            return checkFrenchMethod;
        }

        // If no checkFrenchMethod provided, try to read existing file
        if (fs.existsSync(filePath)) {
            const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
            return content.method;
        }

        // If no file and no method provided, return error
        return new Error(
            `No French detection method stored for domain ${name}`
        );
    } catch (error) {
        return new Error(`Error managing French detection method: ${error}`);
    }
};

```

`src\interfaces\IRedirect.ts`:

```ts
export interface IRedirect {
    from: string;
    to: string;
    status_code?: number;
}
```

`src\interfaces\IRedirectResponse.ts`:

```ts
import { IRedirect } from "./IRedirect.js";

export interface IRedirectResponse {
    success: boolean;
    initial_url: string | null;
    final_url: string;
    redirects: Array<IRedirect>;
    redirect_chain: Array<string>;
    status_code: number;
    content_type?: string;
    error?: string;
}
```

`src\interfaces\queue.ts`:

```ts
export interface QueueJsonContent {
    id: string;
    json: string;
    method: string;
    orderNo: number;
    retryCount: number;
    uniqueKey: string;
    url: string;
}

export interface JsonInnerContent {
    id: string;
    url: string;
    uniqueKey: string;
    method: string;
    noRetry: boolean;
    retryCount: number;
    errorMessages: string[];
    headers: Record<string, string>;
    userData: {
        __crawlee: {
            enqueueStrategy: string;
        };
    };
}

export interface UrlParameters {
    toKeep?: string[];
    toRemove?: string[];
}


```

`src\main.ts`:

```ts
import { RequestQueue, RobotsFile } from "crawlee";
import axios from "axios";
import fs from "fs/promises"; // Added for file system operations
import { createClient } from 'redis';
import os from 'os';
import { exec } from 'child_process';
import { promisify } from 'util';
const execAsync = promisify(exec);
import { router } from "./routes.js";
import {
    getPathAfterDomain,
    getScrapingData,
    rightTrimSlash,
    startCrawler,
    storeKeyValueStore,
    attachFSLogger,
    reclaimFailedRequest,
    stats,
    dropDataset,
    isStoppedManualy,
    getUrlsCrawled,
    getAllRequestQueues,
    parseJsonFiles,
} from "./functions.js";

// --- Argument Parsing ---
const args = process.argv.slice(2).reduce((acc, arg) => {
    const [key, value] = arg.split('=');
    acc[key.substring(2)] = value;
    return acc;
}, {} as Record<string, string>);

const now = new Date().toISOString().replace(/:/g, "-");

// --- Required arguments ---
export const domain = args.domain;
export const site = args.site;
const id = args.id;
const storagePath = args.storagePath; // Centralized storage path for this job
const callbackUrl = args.callbackUrl;

// --- Optional arguments ---
const typeCrawling = args.typecrawling;
const method = args.method; // Variable for post-processing logic
const apifyProxyPassword = args.proxyapify;
const breakLimit = args.breaklimit === 'True';
const dropData = args.dropdata === 'True';
export const skipquestionmark = args.skipquestionmark === 'True';
export const skipdiez = args.skipdiez === 'True';
const bypassQuestionMark = args.bypassquestionmark === 'True';
const bypassDiez = args.bypassdiez === 'True';

let paramPerCrawl = Number(args.percrawl) ?? 500;
let paramPerMinute = Number(args.perminute) ?? 100;
export const toKeep = args.tokeep?.split(';') ?? [];
export const toRemove = args.toremove?.split(';') ?? [];

if (!domain || !site || !id || !storagePath || !callbackUrl) {
    console.error('Missing required arguments: --domain, --site, --id, --storagePath, --callbackUrl');
    process.exit(1);
}

// --- Change the current working directory to the unique job storage path ---
// This ensures that all of Crawlee's default storage locations (datasets, request_queues, etc.)
// are created inside the job-specific folder, providing perfect isolation.
try {
    process.chdir(storagePath);
    console.info(`Changed working directory to: ${storagePath}`);
} catch (err) {
    console.error(`Failed to change directory to ${storagePath}:`, err);
    process.exit(1);
}

const nameLogs = `${domain}-logs-${now}.log`;
attachFSLogger(nameLogs); // Logs will now be created inside the job's storagePath

console.info("Crawler starting with arguments:");
console.info(JSON.stringify(args, null, 2));

// --- PRE-FLIGHT CHECKS ---
// 1. Kill orphan processes from previous runs
console.log('🧹 Checking for orphan browser processes...');
try {
    // Kill Chrome/Chromium processes (ignore errors if no processes found)
    await execAsync('pkill -9 -f "chrome|chromium" 2>/dev/null || true', { timeout: 5000 });
    await execAsync('pkill -9 -f "playwright" 2>/dev/null || true', { timeout: 5000 });
    console.log('✅ Orphan processes cleaned.');
} catch (e: any) {
    // Ignore expected errors (no processes found, timeout, SIGKILL)
    if (e.code !== 'ETIMEDOUT' && e.signal !== 'SIGKILL') {
        console.warn('⚠️  Could not clean orphan processes:', e.message);
    } else {
        console.log('✅ No orphan processes found.');
    }
}

// 2. Check available memory (Docker container limits, not host VM)
let totalMem: number;
let freeMem: number;

try {
    // Try to read Docker container memory limit from cgroups v2
    const cgroupMemMax = await fs.readFile('/sys/fs/cgroup/memory.max', 'utf-8').catch(() => null);
    const cgroupMemCurrent = await fs.readFile('/sys/fs/cgroup/memory.current', 'utf-8').catch(() => null);

    if (cgroupMemMax && cgroupMemCurrent && cgroupMemMax.trim() !== 'max') {
        // cgroups v2 (Docker with cgroups v2)
        totalMem = parseInt(cgroupMemMax.trim());
        const usedMem = parseInt(cgroupMemCurrent.trim());
        freeMem = totalMem - usedMem;
    } else {
        // Try cgroups v1 (older Docker versions)
        const cgroupMemLimitV1 = await fs.readFile('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'utf-8').catch(() => null);
        const cgroupMemUsageV1 = await fs.readFile('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'utf-8').catch(() => null);

        if (cgroupMemLimitV1 && cgroupMemUsageV1) {
            totalMem = parseInt(cgroupMemLimitV1.trim());
            const usedMem = parseInt(cgroupMemUsageV1.trim());
            freeMem = totalMem - usedMem;
        } else {
            // Fallback to host memory (not in Docker or cgroups not available)
            totalMem = os.totalmem();
            freeMem = os.freemem();
        }
    }
} catch (e) {
    // Fallback to host memory if cgroup reading fails
    totalMem = os.totalmem();
    freeMem = os.freemem();
}

const usedMem = totalMem - freeMem;
const memPercent = (usedMem / totalMem) * 100;

console.log(`💾 Memory status: ${(usedMem / 1024 / 1024 / 1024).toFixed(2)}GB / ${(totalMem / 1024 / 1024 / 1024).toFixed(2)}GB (${memPercent.toFixed(1)}% used)`);

if (memPercent > 80) {
    console.error(`❌ Memory critically low: ${memPercent.toFixed(1)}% used. Aborting to prevent OOM.`);
    console.error(`   Free memory: ${(freeMem / 1024 / 1024 / 1024).toFixed(2)}GB`);
    process.exit(1);
}

console.log('✅ Pre-flight checks passed. Starting crawler...');
// --- END PRE-FLIGHT CHECKS ---

// --- Heartbeat Mechanism ---
const redisUrl = process.env.REDIS_URL || 'redis://redis:6379';
const redisClient = createClient({ url: redisUrl });
redisClient.on('error', (err) => console.error('Redis Heartbeat Error:', err));

try {
    await redisClient.connect();
    console.log('Connected to Redis for Heartbeat');

    const hostname = os.hostname();
    const numCpus = os.cpus().length;
    let lastCpuUsage = process.cpuUsage();
    let lastTime = Date.now();

    // Helper to get top 3 RAM processes
    const getTopProcesses = async (): Promise<Array<{ name: string, ram: number }>> => {
        try {
            const { execSync } = await import('child_process');
            // Get top 3 processes by RSS (Linux/Mac compatible)
            const output = execSync('ps aux --sort=-rss | head -n 4 | tail -n 3', { encoding: 'utf-8' });
            const lines = output.trim().split('\n');
            return lines.map(line => {
                const parts = line.trim().split(/\s+/);
                const ramKB = parseInt(parts[5]) || 0;
                const command = parts.slice(10).join(' ').substring(0, 30);
                return { name: command, ram: ramKB * 1024 }; // Convert to bytes
            });
        } catch (e) {
            return [];
        }
    };

    setInterval(async () => {
        try {
            // Calculate CPU usage percentage for THIS process
            const currentCpuUsage = process.cpuUsage(lastCpuUsage);
            const currentTime = Date.now();
            const elapsedTime = (currentTime - lastTime) * 1000; // Convert to microseconds

            // CPU usage is in microseconds, convert to percentage
            const cpuPercent = ((currentCpuUsage.user + currentCpuUsage.system) / elapsedTime) / numCpus;

            lastCpuUsage = process.cpuUsage();
            lastTime = currentTime;

            const memoryUsage = process.memoryUsage();
            const topProcesses = await getTopProcesses();

            const heartbeat = {
                type: 'heartbeat',
                replicaId: hostname,
                jobId: id,
                domain: domain,
                cpu: Math.min(cpuPercent, 1), // Cap at 100%
                ram: memoryUsage.rss,
                totalRam: totalMem, // ADDED: Total RAM limit for dynamic percentage calculation
                topProcesses: topProcesses,
                timestamp: Date.now(),
                status: 'running'
            };
            await redisClient.publish('crawler:heartbeat', JSON.stringify(heartbeat));
        } catch (e) {
            console.error('Failed to send heartbeat:', e);
        }
    }, 2000);
} catch (err) {
    console.error('Failed to connect to Redis for Heartbeat:', err);
}
// ---------------------------

// --- Main crawler logic (largely the same, but paths are now relative to the new CWD) ---

export let robots = await RobotsFile.find(site);
if (!robots || Object.keys(robots).length === 0) {
    console.log("robots.txt not found or empty, trying homepage.");
    const homepageUrl = new URL(site).origin;
    robots = await RobotsFile.find(homepageUrl);

    if (!robots || Object.keys(robots).length === 0) {
        console.log("Could not retrieve robots.txt from homepage.");
    } else {
        console.log("robots.txt retrieved from homepage.");
    }
} else {
    console.log("robots.txt retrieved.");
}

// Declare the Glob of URL to include
const siteParts = getPathAfterDomain(site);
export const baseUrl = siteParts.baseUrl;
const includePath = rightTrimSlash(siteParts.path);
export let enqueueLinksIncludePath: Array<string> = [];
if (includePath) {
    enqueueLinksIncludePath.push(`${baseUrl}${includePath}/**/*`);
}

let isHistorised = false;
// Drop the dataset when we have the parameter --dropdata
if (dropData) {
    console.log("Dropping datasets and request queue...");
    const requestQueueToDrop = await RequestQueue.open(domain);
    await requestQueueToDrop.drop();
    await dropDataset(domain);
    await dropDataset(`error-${domain}`);
    await dropDataset(`nfr-${domain}`);

    isHistorised = true;
}

// Load all previously crawled URLs for deduplication
// Note: This loads the full history into RAM, which may cause OOM on large datasets
export let allUrlsCrawled = new Set(
    getUrlsCrawled(domain, isHistorised, 'true')
);

// Open requestQueue FIRST (before any operations)
export const requestQueue = await RequestQueue.open(domain);

// --- QUEUE HEALTH CHECK ---
// Intelligent queue state detection using handled/pending/total counts
const queueInfo = await requestQueue.getInfo();

// Case 1: Crawl completed successfully (all items handled)
if (queueInfo && queueInfo.totalRequestCount > 0 && queueInfo.handledRequestCount === queueInfo.totalRequestCount && queueInfo.pendingRequestCount === 0) {
    console.log(`✅ Crawl already completed: ${queueInfo.handledRequestCount}/${queueInfo.totalRequestCount} items handled.`);
    console.log(`ℹ️  No pending items. Exiting gracefully.`);
    process.exit(0); // Success exit
}

// Case 2: Corrupted/polluted queue (items exist but none are handled or pending)
if (queueInfo && queueInfo.handledRequestCount === 0 && queueInfo.pendingRequestCount === 0 && queueInfo.totalRequestCount > 0) {
    if (breakLimit) {
        // Bypass mode: Log warning but continue
        console.warn(`⚠️  WARNING: Corrupted queue detected for ${domain} but breakLimit=true, bypassing check.`);
        console.warn(`   Total items: ${queueInfo.totalRequestCount}`);
        console.warn(`   Handled: 0, Pending: 0`);
        console.warn(`ℹ️  Crawler will attempt to continue despite locked queue state.`);
    } else {
        // Normal mode: Exit with error
        console.error(`❌ CRITICAL: Corrupted queue detected for ${domain}`);
        console.error(`   Total items: ${queueInfo.totalRequestCount}`);
        console.error(`   Handled: 0, Pending: 0`);
        console.error(`ℹ️  All items are locked/stuck in an invalid state.`);
        console.error(`💡 SOLUTION: Use Monitor Interface > 'Queue Editor' > 'Analyze' then 'Clean Patterns' or 'Drop Queue'.`);
        console.error(`💡 OR: Set breaklimit=True to force bypass this check (not recommended).`);
        process.exit(1); // Error exit
    }
}

// Case 3: Normal operation - items are pending or being processed
if (queueInfo) {
    console.log(`📊 Queue status: ${queueInfo.pendingRequestCount} pending, ${queueInfo.handledRequestCount} handled, ${queueInfo.totalRequestCount} total`);
}
// --------------------------

// URL Filtering (AFTER health check, only if queue is healthy)
if (skipquestionmark || skipdiez) {
    console.log("Filtering URLs in the queue...");
    const requestQueueList = getAllRequestQueues(domain);

    if (requestQueueList.length > 0) {
        let parameters: any = {};
        if (toKeep.length > 0) parameters.toKeep = toKeep;
        if (toRemove.length > 0) parameters.toRemove = toRemove;
        parseJsonFiles(requestQueueList, skipquestionmark, skipdiez, parameters);
    }
}

if (typeCrawling === "generate_data") {
    // This logic might need adjustment in an API context
    console.log("Data generation mode is not fully supported in API mode. Exiting.");
} else {
    // Reclaim failed request
    try {
        await reclaimFailedRequest(domain);
    } catch (error) {
        console.warn(`⚠️ Warning: Failed to reclaim failed requests for ${domain}. The crawler will continue without them. Error: ${error}`);
    }

    // Launch the crawler
    const crawler = await startCrawler(
        router,
        [site],
        domain,
        paramPerCrawl,
        paramPerMinute,
        apifyProxyPassword,
        breakLimit,
        bypassQuestionMark,
        bypassDiez,
        skipquestionmark, // Ensure it's passed as string
        skipdiez
    );

    // CLEANUP HOOKS: Ensure browsers are properly terminated on shutdown
    process.on('SIGTERM', async () => {
        console.log('SIGTERM received, cleaning up browsers...');
        try {
            await crawler.teardown();
        } catch (e) {
            console.error('Error during teardown:', e);
        }
        process.exit(0);
    });

    process.on('SIGINT', async () => {
        console.log('SIGINT received, cleaning up browsers...');
        try {
            await crawler.teardown();
        } catch (e) {
            console.error('Error during teardown:', e);
        }
        process.exit(0);
    });
}

// --- Finalization and Callback ---
let isFinished = 0;
// Ajouter un variable callShell pour conditionner sur le fait de lancer la commande shell
let callShell: boolean = true;

if (await requestQueue.isFinished()) {
    isFinished = 1;
}

if (method === "test") {
    callShell = false;
}

/**
 * List of possible errors :
 *  take account that the crawler is not finished :
 *      - limitCrawl : limit of 5000 URLs reached
 *      - limitQuestionMarkDiez : limit of 20 URLs reached for question mark and # links if not marked to be skipped
 *
 *  do not take into account that the crawler is finished :
 *  - stoppedManually : the crawler was stopped manually
 */
let isError = "";

if (isFinished === 0) {
    // Getting datasets
    const data = await getScrapingData(domain);
    const count = data.total;

    // Checking if the case is the question mark/diez limit
    if (
        (!bypassQuestionMark && !skipquestionmark) ||
        (!bypassDiez && !skipdiez)
    ) {
        // Need to be in sync with the limit in functions.ts/startCrawler() → limitQuestionMarkDiez
        const limitQuestionMarkDiez = 50;
        const patternQuestionMark = new RegExp(
            `(?:/[^?]*)?\\?.*$`
        );
        const patternDiez = new RegExp(
            `(?:/[^#]*)?#.*$`
        );
        let countQuestionMark = 0;
        let countDiez = 0;

        for (const item of data.items) {
            if (patternQuestionMark.test(item.url)) {
                countQuestionMark++;
            }

            if (patternDiez.test(item.url)) {
                countDiez++;
            }

            if (
                !bypassQuestionMark &&
                !skipquestionmark &&
                countQuestionMark >= limitQuestionMarkDiez
            ) {
                isError = "limitQuestionMark";
                break;
            }

            if (
                !bypassDiez &&
                !skipdiez &&
                countDiez >= limitQuestionMarkDiez
            ) {
                isError = "limitDiez";
                break;
            }
        }
    }

    // Checking if the case is the limit of URLs reached
    // Need to be in sync with the limit in functions.ts/startCrawler() → limitUrls
    const limitUrls = 5000;
    if (count >= limitUrls) {
        isError = "limitCrawl";
    }
}

// Checking if the crawler is stopped manually
if (isStoppedManualy(domain, true)) {
    isError = "stoppedManually";
}

// Instead of calling the webhook directly, write a payload file for the manager.
if (callShell) {
    const payload = {
        id_domaine: id,
        success: stats?.requestsFinished ?? 0,
        failed: stats?.requestsFailed ?? 0,
        isFinished: isFinished,
        method: method,
        isError: isError,
        storagePath: storagePath
    };

    try {
        const payloadPath = `${storagePath}/_callback_payload.json`;
        await fs.writeFile(payloadPath, JSON.stringify(payload, null, 2));
        console.info(`Callback payload for manager written to ${payloadPath}`);
    } catch (error: any) {
        console.error(`Failed to write callback payload file: ${error.message}`);
    }
}

// Exit with code 2 to signal graceful completion to the manager
process.exit(2);
```

`src\routes.ts`:

```ts
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

            // SAFETY LIMIT: Prevent unbounded memory growth
            // Clear Set if it exceeds 100k URLs (prevents OOM on very large sites)
            // Crawlee's RequestQueue will continue to handle deduplication
            const MAX_URLS_IN_MEMORY = 100000;
            if (allUrlsCrawled.size > MAX_URLS_IN_MEMORY) {
                log.warning(`⚠️  allUrlsCrawled Set exceeded ${MAX_URLS_IN_MEMORY.toLocaleString()} URLs. Clearing to prevent OOM. Crawlee RequestQueue will handle deduplication.`);
                allUrlsCrawled.clear();
            }

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

                // CRITICAL FIX: Mark request as handled even for non-French pages
                // Without this, handledRequestCount stays at 0, triggering false "corrupted queue" errors
                await requestQueue.markRequestHandled(request);
            }
        } else {
            console.log(`Doublon url : ${url}`);
        }
    }
);

```