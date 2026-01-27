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
    purgeDefaultStorages,
} from "crawlee";
import { Page } from "playwright";
import fs from "fs";
import {
    QueueJsonContent,
    JsonInnerContent,
    UrlParameters,
} from "./interfaces/queue.js";
import { context } from "./context.js";

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
        try {
            await page.waitForLoadState("networkidle", { timeout: 5000 });
        } catch (e) {
            // Ignore timeout on networkidle, proceed to scroll
        }

        let previousHeight = await page.evaluate("document.body.scrollHeight");
        let newHeight;
        let scrolls = 0;
        const startTime = Date.now();

        do {
            // Check limits
            if (scrolls >= maxScrolls) {
                // log.debug(`Max scrolls (${maxScrolls}) reached for ${url}`);
                break;
            }

            if ((Date.now() - startTime) / 1000 > timeoutSecs) {
                // log.debug(`Scroll timeout (${timeoutSecs}s) reached for ${url}`);
                break;
            }

            // Scroll to bottom of current page
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)");

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
        } catch (innerE) {
            throw new Error(`Critical error processPage : ${innerE}`);
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
    
    let proxyConfiguration: ProxyConfiguration | undefined;

    // V3 Optimization: Persist storage to prevent OOM
    let configuration = new Configuration({
        maxUsedCpuRatio: 0.95, // V3 allows more CPU usage
        availableMemoryRatio: 0.95,
        persistStorage: true,
    });

    if (PROXY_PASSWORD) {
        proxyConfiguration = new ProxyConfiguration({
            proxyUrls: [proxyUrl],
        });
    }

    let optionsCrawler: PlaywrightCrawlerOptions = {
        // Router to handle different URL patterns and their processing logic
        requestHandler: router,

        // RequestQueue
        requestQueue,
        
        // V3 Optimization: Browser Pool settings
        browserPoolOptions: {
            fingerprintOptions: {
                fingerprintGeneratorOptions: {
                    browsers: ["firefox", "chrome", "safari"],
                    locales: ["fr-FR"],
                    devices: ["desktop"],
                    operatingSystems: ["windows", "macos", "linux"],
                },
            },
            retireBrowserAfterPageCount: 25, // Prevent memory leaks in Chrome
        },

        maxConcurrency: 1, // V3 default
        navigationTimeoutSecs: 90,
        requestHandlerTimeoutSecs: 120,
        maxRequestRetries: 5, // V3 resilience

        useSessionPool: true,
        persistCookiesPerSession: true,
        sessionPoolOptions: {
            blockedStatusCodes: [401, 403, 429, 404, 410, 423, 502, 500, 503],
        },

        // V3 Logic: Rich error reporting
        failedRequestHandler: async ({ request, log, page, proxyInfo, response }) => {
            log.error(`Request ${request.url} failed: ${String(request.errorMessages)}`);

            // Accumulate error stats
            if (context.statsManager) {
                await context.statsManager.increment("errors");
            }

            // Detect Captcha
            let captchaDetected = "";
            try {
                if (page) {
                    let content = await page.content();
                    if (await page.$(".g-recaptcha")) captchaDetected = "reCAPTCHA V2";
                    else if (await page.$(".cf-turnstile")) captchaDetected = "Cloudflare Turnstile";
                    else if (content.includes("grecaptcha.execute")) captchaDetected = "reCAPTCHA V3";
                    else if (content.includes("geo.captcha-delivery.com")) captchaDetected = "DataDome Captcha";
                }
            } catch (e) {}

            if (captchaDetected) {
                log.error(`Captcha detected on ${request.url} : ${captchaDetected}`);
            }

            // Save rich error info
            let errorDatasetName = `error-${domain}`;
            let dataset = await Dataset.open(errorDatasetName);
            await dataset.pushData({
                id: request.id,
                url: request.url,
                errors: request.errorMessages,
                proxy_used: proxyInfo?.url || "none",
                status_code: response?.status() || 0,
                captcha: captchaDetected,
                timestamp: new Date().toISOString()
            });
        },

        preNavigationHooks: [
            async () => {
                if (context.stopReason) {
                    await stopCrawler(crawler, `Stopping due to: ${context.stopReason}`);
                }

                if (!breakLimit) {
                    // Optimized check without loading data
                    const dataset = await Dataset.open(domain);
                    const info = await dataset.getInfo();
                    if (info && info.itemCount >= 5000) {
                        context.stopReason = "limitCrawl";
                        await stopCrawler(crawler, "Limit of 5000 entries reached.");
                    }
                }
            },
        ],

        postNavigationHooks: [
            async () => {
                // ... Keep existing logic or optimize if needed. 
                // V3 uses batch processing here but for now keeping V2 logic slightly modified is safer 
                // unless we want to do a full rewrite of this hook.
                // Given the constraints, let's keep it but be aware of memory.
                
                // If skipping is enabled, we check counts.
                if ((!bypassQuestionMark && !skipquestionmark) || (!bypassDiez && !skipdiez)) {
                    // Use batch processing to check limits (V3 Optimization)
                    const limitQuestionMarkDiez = 50;
                    const dataset = await Dataset.open(domain);
                    const info = await dataset.getInfo();
                    const total = info?.itemCount || 0;
                    
                    let countQuestionMark = 0;
                    let countDiez = 0;
                    let offset = 0;
                    const batchSize = 1000;

                    const patternQuestionMark = new RegExp(`(?:/[^?]*)?\\?.*$`);
                    const patternDiez = new RegExp(`(?:/[^#]*)?#.*$`);

                    while (offset < total) {
                        const data = await dataset.getData({ offset, limit: batchSize });
                        for (const item of data.items) {
                            if (patternQuestionMark.test(item.url)) countQuestionMark++;
                            if (patternDiez.test(item.url)) countDiez++;
                        }
                        
                        if (countQuestionMark >= limitQuestionMarkDiez || countDiez >= limitQuestionMarkDiez) break;
                        offset += batchSize;
                    }

                    if (!bypassQuestionMark && !skipquestionmark && countQuestionMark >= limitQuestionMarkDiez) {
                        context.stopReason = "limitQuestionMark";
                        await stopCrawler(crawler, "Limit of 50 question marks reached.");
                    }
                    if (!bypassDiez && !skipdiez && countDiez >= limitQuestionMarkDiez) {
                        context.stopReason = "limitDiez";
                        await stopCrawler(crawler, "Limit of 50 hashes reached.");
                    }
                }
            },
        ],
    };

    if (paramPerCrawl > 0) optionsCrawler.maxRequestsPerCrawl = paramPerCrawl;
    if (paramPerMinute > 0) optionsCrawler.maxRequestsPerMinute = paramPerMinute;
    if (proxyConfiguration) optionsCrawler.proxyConfiguration = proxyConfiguration;

    const crawler = new PlaywrightCrawler(optionsCrawler, configuration);
    context.crawlerInstance = crawler; // Expose instance for stopping

    if (await requestQueue.isEmpty()) {
        console.log("RequestQueueEmpty - Adding seed");
        await requestQueue.addRequest({ url: startUrl[0] });
    } else {
        const queueInfo = await requestQueue.getInfo();
        console.log("Resume crawling : ", JSON.stringify(queueInfo, null, 2));
    }

    await crawler.run();

    stats = crawler.stats.state;
    console.log(JSON.stringify({ CrawlingStats: crawler.stats }, null, 2));
    
    return crawler;
};

export const isStoppedManualy = (name: string, historised: boolean) => {
    if (fs.existsSync(`stopper/${name}.txt`)) {
        if (historised) {
            console.log("The crawler has been stopped manually.");
            const date = new Date().toISOString();
            fs.appendFileSync(`stopper/history-${name}.txt`, `- Date arrêt : ${date}\n`);
            fs.unlinkSync(`stopper/${name}.txt`);
        }
        return true;
    }
    return false;
};

// ... keep getUrlsCrawled, updateUrlsCrawled, getScrapingData, storeKeyValueStore, getPathAfterDomain, rightTrimSlash ...
// For brevity, assuming they are unchanged unless specified.
// IMPORTANT: `getUrlsCrawled` uses FS. In V3/V2 migration, we use DedupManager.
// So legacy calls to getUrlsCrawled can remain for backward compat or seeding.

export const getUrlsCrawled = (
    name: string | undefined,
    historised: boolean,
    dropData: string | undefined = undefined
) => {
    // Legacy implementation kept for seeding DedupManager
    var folderName = `./storage/request_urls/${name}`;
    try {
        if (!fs.existsSync(folderName)) {
            fs.mkdirSync(folderName, { recursive: true });
        }
    } catch (err) {
        folderName = "./storage/request_urls";
    }

    var fileUrls = `${folderName}/${name}.json`;

    if (dropData) {
        if (fs.existsSync(fileUrls)) fs.unlinkSync(fileUrls);
    }

    if (fs.existsSync(fileUrls)) {
        let listUrls: Array<string> = [];
        if (historised) {
            const dateString = new Date().toISOString().split("T")[0];
            const fileHistorised = `${folderName}/${dateString}-${name}.json`;
            fs.copyFileSync(fileUrls, fileHistorised);
            fs.writeFileSync(fileUrls, "[]");
        } else {
            const content = fs.readFileSync(fileUrls, "utf8");
            const tempListUrls = JSON.parse(content);
            if (tempListUrls.length > 0) listUrls = tempListUrls;
        }
        return listUrls;
    } else {
        fs.writeFileSync(fileUrls, "[]");
        return [];
    }
};

export const updateUrlsCrawled = (name: string | undefined, listUrls: Array<string>) => {
    var folderName = `./storage/request_urls/${name}`;
    var fileUrls = `${folderName}/${name}.json`;
    if (fs.existsSync(fileUrls)) {
        fs.writeFileSync(fileUrls, JSON.stringify(listUrls));
    }
};

export const getScrapingData = async (name: string, countArray: number = 0) => {
    try {
        let dataset = await Dataset.open(name);
        let data;
        if (countArray === 0) data = await dataset.getData();
        else data = await dataset.getData({ desc: true, limit: countArray });
        return data;
    } catch (error) {
        throw new Error(`Error when getScrapingData : ${error}`);
    }
};

export const storeKeyValueStore = async (name: string, countArray: number = 0, domain: string = "") => {
    try {
        const data = await getScrapingData(name, countArray);
        if (!domain) domain = name;
        if (data.total) {
            const store = await KeyValueStore.open(domain);
            await store.setValue(name, data.items);
        }
    } catch (error) {
        throw new Error(`Error storeKeyValueStore : ${error}`);
    }
};

export const getPathAfterDomain = (url: string): { baseUrl: string; path: string } => {
    try {
        const urlObject = new URL(url);
        const pathWithoutParams = urlObject.pathname.split("?")[0].split("#")[0];
        return {
            baseUrl: `${urlObject.protocol}//${urlObject.host}`,
            path: pathWithoutParams.length > 1 ? pathWithoutParams : "",
        };
    } catch (error) {
        try {
            const urlWithProtocol = url.startsWith("http") ? url : `http://${url}`;
            const urlObject = new URL(urlWithProtocol);
            const pathWithoutParams = urlObject.pathname.split("?")[0].split("#")[0];
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

export const rightTrimSlash = (str: string) => str.replace(/\/+$/, "");

export const attachFSLogger = (fileName: string) => {
    // ... same as before, ensures logs go to file
    const oldLog = console.log;
    const oldInfo = console.info;
    const oldWarn = console.warn;
    const oldError = console.error;
    const oldDebug = console.debug;

    const date = new Date();
    const dateString = date.toISOString().split("T")[0];
    const folderDate = dateString.split("-")[0] + "/" + dateString.split("-")[1];
    let folderName = `./logs/` + folderDate;

    try {
        if (!fs.existsSync(folderName)) fs.mkdirSync(folderName, { recursive: true });
    } catch (err) {
        folderName = `./logs`;
    }

    const fsLog = fs.createWriteStream(folderName + "/" + fileName, { flags: "a" });

    console.log = (...messages) => {
        oldLog.apply(console, messages);
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };
    console.error = (...messages) => {
        oldError.apply(console, messages);
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };
    console.info = (...messages) => {
        oldInfo.apply(console, messages);
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };
    console.warn = (...messages) => {
        oldWarn.apply(console, messages);
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };
    console.debug = (...messages) => {
        oldDebug.apply(console, messages);
        fsLog.write(stripAnsi(messages.join("\n")) + "\n");
    };
};

const stripAnsi = (str: string) => {
    if (typeof str !== "string") return JSON.stringify(str, null, 2);
    return str.replace(/\u001b\[\d+m/g, "");
};

export const reclaimFailedRequest = async (name: string) => {
    const datasError = await getScrapingData(`error-${name}`);
    for (const item of datasError.items) {
        const requestID = item["id"];
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

// Updated: Save title
export const routerDefaultHandler = async (
    request: LoadedRequest<Request<Dictionary>>,
    requestQueue: RequestQueue,
    url: string,
    content: string,
    domain: string | undefined,
    title: string = ""
) => {
    let results = {
        url,
        content,
        title
    };

    let dataset = await Dataset.open(domain);
    await dataset.pushData(results);
    await requestQueue.markRequestHandled(request);
};

export const stopCrawler = async (crawler: PlaywrightCrawler, message: string) => {
    crawler.log.info(message);
    try {
        await crawler.autoscaledPool?.pause();
        await crawler.autoscaledPool?.abort();
        crawler.log.info("The crawler has been gracefully stopped.");
    } catch (error) {
        crawler.log.error("An error occurred when stopping the crawler : ", error);
    }
};

export const escapeRegExp = (string: string) => string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export const getAllRequestQueues = (queueName: string): string[] => {
    try {
        const requestQueuesPath = `storage/request_queues/${queueName}`;
        if (!fs.existsSync(requestQueuesPath)) return [];
        return fs.readdirSync(requestQueuesPath)
            .filter((file) => file.endsWith(".json"))
            .map((file) => `${requestQueuesPath}/${file}`);
    } catch (error) {
        throw new Error(`Error getAllRequestQueues for queue ${queueName}: ${error}`);
    }
};

export const processUrl = (
    url: string,
    skipQuestionMark: boolean,
    skipDiez: boolean,
    parameters: UrlParameters = {}
): string => {
    const defaultParametersToKeep = ["page", "id", "lang"];
    if (parameters.toKeep && parameters.toRemove) throw new Error("Cannot specify both");

    let processedUrl = url;
    let baseUrlPart = processedUrl;
    let hashPart = "";

    if (processedUrl.includes("#")) {
        const [base, hash] = processedUrl.split("#");
        baseUrlPart = base;
        hashPart = "#" + hash;
        if (skipDiez) hashPart = "";
    }

    if (skipQuestionMark && baseUrlPart.includes("?")) {
        const [baseUrl, queryString] = baseUrlPart.split("?");
        const params = new URLSearchParams(queryString);
        const filteredParams = new URLSearchParams();

        if (parameters.toKeep || parameters.toRemove) {
            const entries = Array.from(params.entries());
            if (parameters.toKeep) {
                for (const [key, value] of entries) {
                    if (parameters.toKeep.includes(key)) filteredParams.append(key, value);
                }
            } else if (parameters.toRemove) {
                for (const [key, value] of entries) {
                    if (!parameters.toRemove.includes(key)) filteredParams.append(key, value);
                }
            }
        } else {
            const entries = Array.from(params.entries());
            for (const [key, value] of entries) {
                if (defaultParametersToKeep.includes(key)) filteredParams.append(key, value);
            }
        }
        const newQueryString = filteredParams.toString();
        baseUrlPart = newQueryString ? `${baseUrl}?${newQueryString}` : baseUrl;
    }
    return baseUrlPart + hashPart;
};

// Updated: Fix nested uniqueKey
export const parseJsonFiles = (
    jsonPaths: string | string[],
    skipQuestionMark: boolean,
    skipDiez: boolean,
    parameters: UrlParameters = {}
): void => {
    try {
        const paths = Array.isArray(jsonPaths) ? jsonPaths : [jsonPaths];
        for (const path of paths) {
            const fileContent = fs.readFileSync(path, "utf-8");
            const jsonContent = JSON.parse(fileContent) as QueueJsonContent;

            if (!jsonContent.orderNo) continue;

            const processedUrl = processUrl(jsonContent.url, skipQuestionMark, skipDiez, parameters);

            if (processedUrl !== jsonContent.url) {
                jsonContent.url = processedUrl;
                // V3 Fix: Update uniqueKey at root
                jsonContent.uniqueKey = processedUrl;

                const innerJson = JSON.parse(jsonContent.json) as JsonInnerContent;
                innerJson.url = processedUrl;
                // V3 Fix: Update uniqueKey inside nested json
                innerJson.uniqueKey = processedUrl;
                jsonContent.json = JSON.stringify(innerJson);

                fs.writeFileSync(path, JSON.stringify(jsonContent, null, 2));
            }
        }
    } catch (error) {
        throw new Error(`Error parsing JSON files: ${error}`);
    }
};

export const manageFrenchDetectionMethod = (name: string, checkFrenchMethod: string | null = null): string | Error => {
    try {
        const storagePath = `./storage/miscellaneous/${name}`;
        const filePath = `${storagePath}/${name}.json`;
        if (checkFrenchMethod) {
            if (!fs.existsSync(storagePath)) fs.mkdirSync(storagePath, { recursive: true });
            fs.writeFileSync(filePath, JSON.stringify({ method: checkFrenchMethod }, null, 2));
            return checkFrenchMethod;
        }
        if (fs.existsSync(filePath)) {
            const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
            return content.method;
        }
        return new Error(`No French detection method stored for domain ${name}`);
    } catch (error) {
        return new Error(`Error managing French detection method: ${error}`);
    }
};