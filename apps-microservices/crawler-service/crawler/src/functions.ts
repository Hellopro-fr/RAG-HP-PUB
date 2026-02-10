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
import path from "path";
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

        // Return the complete page HTML after scrolling
        return await page.content();
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
    skipdiez?: boolean,
    containerMemoryMb?: number
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
    // memoryMbytes: Tells Crawlee the real container memory limit (from cgroups).
    // Without this, Crawlee defaults to os.totalmem() which returns the HOST memory,
    // causing the autoscaler to report memInfo.actualRatio: 0 and never throttle concurrency.
    let configOptions: Record<string, any> = {
        maxUsedCpuRatio: 0.95, // V3 allows more CPU usage
        availableMemoryRatio: 0.95,
        persistStorage: true,
    };
    if (containerMemoryMb && containerMemoryMb > 0) {
        configOptions.memoryMbytes = containerMemoryMb;
        console.log(`💾 Crawlee Configuration: memoryMbytes set to ${containerMemoryMb} MB (from container cgroups)`);
    }
    let configuration = new Configuration(configOptions);

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

        // maxConcurrency: 1, // V3 default
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

            // Accumulate error stats ONLY if the URL is from the previous crawl
            // This prevents new/broken URLs from triggering the circuit breaker for "Broken Site"
            if (context.statsManager) {
                if (request.userData.is_existing) {
                    await context.statsManager.increment("errors");
                }
            }

            // Detect Captcha
            let captchaDetected = "";
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

            // Save rich error info
            let datasetName = context.config.crawleeStorageName ? `error-${context.config.crawleeStorageName}` : `error-${domain}`;
            let dataset = await Dataset.open(datasetName);
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
                const isStopped = isStoppedManualy(domain, false);
                if (isStopped) {
                    await stopCrawler(
                        crawler,
                        "The crawler has been stopped manually."
                    );
                }
                
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
                        
                        if (
                            (!bypassQuestionMark &&
                                !skipquestionmark &&
                                countQuestionMark >= limitQuestionMarkDiez) ||
                            (!bypassDiez &&
                                !skipdiez &&
                                countDiez >= limitQuestionMarkDiez)
                        ) break;
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
        console.log("RequestQueueNotEmpty");
        const queueInfo = await requestQueue.getInfo();
        console.log("Resume crawling : ", JSON.stringify(queueInfo, null, 2));
    }

    await crawler.run();

    stats = crawler.stats.state;
    console.log(JSON.stringify({ CrawlingStats: crawler.stats }, null, 2));
    
    return crawler;
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
            const date = new Date().toISOString();
            fs.appendFileSync(`stopper/history-${name}.txt`, `- Date arrêt : ${date}\n`);
            fs.unlinkSync(`stopper/${name}.txt`);
        }
        return true;
    }
    return false;
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
/**
 * @deprecated Use getUrlsCrawledStreaming() for large history files to avoid OOM.
 */
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
        console.error("Couldn't create the folder ");
        console.error(err);
        folderName = "./storage/request_urls";
    }

    var fileUrls = `${folderName}/${name}.json`;

    if (dropData) {
        // If dropData is set, we want to drop the file
        console.log("Droping the file " + fileUrls);
        if (fs.existsSync(fileUrls)) fs.unlinkSync(fileUrls);
    }

    if (fs.existsSync(fileUrls)) {
        let listUrls: Array<string> = [];
        if (historised) {
            console.log("The list of urls crawled have been historised");
            const dateString = new Date().toISOString().split("T")[0];
            const fileHistorised = `${folderName}/${dateString}-${name}.json`;
            fs.copyFileSync(fileUrls, fileHistorised);

            // update the the file named "{domaine}.json" as []
            fs.writeFileSync(fileUrls, "[]");
        } else {
            // get the content of the file json as array
            const content = fs.readFileSync(fileUrls, "utf8");
            const tempListUrls = JSON.parse(content);
            if (tempListUrls.length > 0) listUrls = tempListUrls;
        }
        return listUrls;
    } else {
        console.log("First creation of the file list urls");
        fs.writeFileSync(fileUrls, "[]");
        return [];
    }
};

/**
 * OOM-safe streaming version of getUrlsCrawled.
 * Yields URLs one-by-one using incremental JSON parsing.
 * 
 * @param {string} name - The name of the domain
 * @param {boolean} historised - Whether to create a dated backup and clear the file
 * @param {string | undefined} dropData - If set, delete the file before reading
 * @returns {AsyncGenerator<string>} Yields URLs one at a time
 */
export async function* getUrlsCrawledStreaming(
    name: string | undefined,
    historised: boolean,
    dropData: string | undefined = undefined
): AsyncGenerator<string> {
    let folderName = `./storage/request_urls/${name}`;
    try {
        if (!fs.existsSync(folderName)) {
            fs.mkdirSync(folderName, { recursive: true });
        }
    } catch (err) {
        console.error("Couldn't create the folder ");
        console.error(err);
        folderName = "./storage/request_urls";
    }

    const fileUrls = `${folderName}/${name}.json`;

    if (dropData) {
        console.log("Dropping the file " + fileUrls);
        if (fs.existsSync(fileUrls)) fs.unlinkSync(fileUrls);
    }

    if (!fs.existsSync(fileUrls)) {
        console.log("First creation of the file list urls");
        fs.writeFileSync(fileUrls, "[]");
        return;
    }

    if (historised) {
        console.log("The list of urls crawled have been historised");
        const dateString = new Date().toISOString().split("T")[0];
        const fileHistorised = `${folderName}/${dateString}-${name}.json`;
        fs.copyFileSync(fileUrls, fileHistorised);
        fs.writeFileSync(fileUrls, "[]");
        return;
    }

    // Stream-parse the JSON array
    // Read file in chunks and extract strings incrementally
    const readStream = fs.createReadStream(fileUrls, { encoding: 'utf8' });
    let buffer = '';
    let inString = false;
    let escapeNext = false;
    let currentString = '';

    for await (const chunk of readStream) {
        buffer += chunk;
        
        for (let i = 0; i < buffer.length; i++) {
            const char = buffer[i];
            
            if (escapeNext) {
                if (inString) currentString += char;
                escapeNext = false;
                continue;
            }
            
            if (char === '\\') {
                escapeNext = true;
                if (inString) currentString += char;
                continue;
            }
            
            if (char === '"') {
                if (inString) {
                    // End of string - yield URL
                    // Decode escape sequences
                    try {
                        yield JSON.parse(`"${currentString}"`);
                    } catch {
                        yield currentString;
                    }
                    currentString = '';
                }
                inString = !inString;
                continue;
            }
            
            if (inString) {
                currentString += char;
            }
        }
        
        buffer = '';
    }
}

/**
 * Update the content  of the file named "{domaine}.json" in the folder request_urls/{domain}
 *
 * @deprecated Use updateUrlsCrawledStreaming() for large URL sets to avoid OOM.
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
    
    // Create folder if it doesn't exist (fix: was missing)
    if (!fs.existsSync(folderName)) {
        fs.mkdirSync(folderName, { recursive: true });
    }
    
    fs.writeFileSync(fileUrls, JSON.stringify(listUrls));
};

/**
 * OOM-safe streaming version of updateUrlsCrawled.
 * Writes URLs to file one-by-one from an async iterator, avoiding full array in memory.
 * Uses atomic write pattern (write to .tmp -> rename) to prevent file corruption on crash.
 *
 * @param {string} name - The name of the domain
 * @param {AsyncGenerator<string>} urlIterator - Async iterator yielding URLs
 * @returns {Promise<number>} Number of URLs written
 */
export const updateUrlsCrawledStreaming = async (
    name: string | undefined,
    urlIterator: AsyncGenerator<string>
): Promise<number> => {
    const folderName = `./storage/request_urls/${name}`;
    const fileUrls = `${folderName}/${name}.json`;
    const tempFile = `${fileUrls}.tmp`; // Atomic Write Pattern
    
    // Create folder if it doesn't exist
    if (!fs.existsSync(folderName)) {
        fs.mkdirSync(folderName, { recursive: true });
    }
    
    // Use streaming write to avoid OOM
    const stream = fs.createWriteStream(tempFile);
    stream.write('[');
    
    let isFirst = true;
    let count = 0;
    
    for await (const url of urlIterator) {
        if (!isFirst) stream.write(',');
        stream.write(JSON.stringify(url));
        isFirst = false;
        count++;
    }
    
    stream.write(']');
    stream.end();
    
    // Wait for stream to finish then rename atomically
    await new Promise<void>((resolve, reject) => {
        stream.on('finish', () => {
            try {
                fs.renameSync(tempFile, fileUrls);
                resolve();
            } catch (err) {
                reject(err);
            }
        });
        stream.on('error', reject);
    });
    
    console.log(`Persisted ${count} URLs to ${fileUrls}`);
    return count;
};

/**
 * Generator that efficiently yields URLs from a previous crawl's dataset.
 * Scans the storage directory structure to find the datasets.
 * 
 * @param {string} previousId - The ID of the previous crawl job
 * @param {string} domain - The domain to load URLs for
 * @returns {AsyncGenerator<string>} Yields URLs one by one
 */
export async function* loadDatasetUrlsGenerator(previousId: string, domain: string): AsyncGenerator<string> {
    // We assume the process is running in storage/{currentId}
    // So we access storage/{previousId} via relative path from CWD
    // CWD is typically set in main.ts to the current job's storage path.
    // So `..` takes us to the parent `storage` dir, then into `{previousId}`.
    
    const previousJobPath = path.resolve('..', previousId);
    
    if (!fs.existsSync(previousJobPath)) {
        console.error(`Previous job storage not found at ${previousJobPath}`);
        return;
    }

    const crawleeBase = path.join(previousJobPath, "storage", "datasets");
    let datasetPath = path.join(crawleeBase, domain);
    
    // Check for original domain name folder
    if (!fs.existsSync(datasetPath)) {
        // Check for sanitized name (dots replaced by hyphens)
        const sanitized = domain.replace(/\./g, '-');
        datasetPath = path.join(crawleeBase, sanitized);
    }
    
    if (!fs.existsSync(datasetPath)) {
        console.error(`Dataset for domain ${domain} not found in ${previousJobPath}`);
        return;
    }

    console.log(`Loading URLs from previous dataset: ${datasetPath}`);

    try {
        const files = await fs.promises.readdir(datasetPath);
        for (const file of files) {
            if (file.endsWith('.json') && !file.startsWith('__')) {
                try {
                    const filePath = path.join(datasetPath, file);
                    const content = await fs.promises.readFile(filePath, 'utf-8');
                    const data = JSON.parse(content);
                    if (data && data.url) {
                        yield data.url;
                    }
                } catch (e) {
                    console.warn(`Error reading dataset file ${file}: ${e}`);
                }
            }
        }
    } catch (e) {
        console.error(`Error iterating dataset directory: ${e}`);
    }
}

/**
 * Scans the current crawl's dataset folder to rehydrate the Deduplication set.
 * Used when restarting a crashed crawl to ensure previously discovered URLs are known.
 * 
 * @param {string} datasetName - The sanitized name of the dataset folder
 * @returns {AsyncGenerator<string>} Yields URLs found in the dataset
 */
export async function* rehydrateDedupFromDataset(datasetName: string): AsyncGenerator<string> {
    const datasetPath = path.join(process.cwd(), "storage", "datasets", datasetName);
    
    if (!fs.existsSync(datasetPath)) {
        // Folder might not exist if no pages were saved yet
        return;
    }

    console.log(`Rehydrating Dedup from current dataset: ${datasetPath}`);

    try {
        const files = await fs.promises.readdir(datasetPath);
        for (const file of files) {
            if (file.endsWith('.json') && !file.startsWith('__')) {
                try {
                    const filePath = path.join(datasetPath, file);
                    const content = await fs.promises.readFile(filePath, 'utf-8');
                    const data = JSON.parse(content);
                    if (data && data.url) {
                        yield data.url;
                    }
                } catch (e) {
                    // Ignore corrupted files from crash
                }
            }
        }
    } catch (e) {
        console.error(`Error iterating dataset directory for rehydration: ${e}`);
    }
}

/**
 * Copies the French detection method file from a previous crawl to the current one.
 * Used in Update Mode to ensure the method is available before parallel processing starts.
 * 
 * @param {string} previousId - The ID of the previous crawl job
 * @param {string} domain - The domain being crawled
 * @returns {boolean} True if copy was successful
 */
export const copyPreviousMethod = (previousId: string, domain: string): boolean => {
    try {
        // Resolve paths. CWD is the current storage root (e.g. storage/update-1)
        // Previous ID is relative to parent of CWD (../previousId)
        const previousStoragePath = path.resolve('..', previousId);
        const previousFile = path.join(previousStoragePath, 'storage', 'miscellaneous', domain, `${domain}.json`);

        const currentStoragePath = process.cwd(); // We are already in the storage folder
        const currentFolder = path.join(currentStoragePath, 'storage', 'miscellaneous', domain);
        const currentFile = path.join(currentFolder, `${domain}.json`);

        if (fs.existsSync(previousFile)) {
            if (!fs.existsSync(currentFolder)) {
                fs.mkdirSync(currentFolder, { recursive: true });
            }
            fs.copyFileSync(previousFile, currentFile);
            console.log(`Copied French detection method from previous crawl: ${previousId}`);
            
            // Pre-load into context to avoid race condition on first reads
            const content = JSON.parse(fs.readFileSync(currentFile, 'utf-8'));
            if (content.method) {
                context.frenchDetectionMethod = content.method;
                console.log(`Loaded French detection method into memory: ${content.method}`);
            }
            return true;
        } else {
            console.warn(`Previous French detection method file not found at ${previousFile}`);
        }
    } catch (e) {
        console.error(`Failed to copy previous detection method: ${e}`);
    }
    return false;
}

/**
 * Generates a status report for the Update Mode and saves it to disk.
 * Includes health status, rates, and thresholds used.
 */
export const generateUpdateReport = async (domain: string) => {
    try {
        if (!context.statsManager) return;

        const processed = await context.statsManager.getValue("processed");
        const errors = await context.statsManager.getValue("errors");
        const redirects = await context.statsManager.getValue("redirects");
        const newUrls = await context.statsManager.getValue("new_urls");
        
        const cb = context.config.circuitBreaker;
        
        // Calculate rates
        const errorRate = processed > 0 ? errors / processed : 0;
        const redirectRate = processed > 0 ? redirects / processed : 0;
        const growthRate = cb.previousTotal > 0 ? newUrls / cb.previousTotal : 0;

        let status = "HEALTHY";
        let statusMessage = "Update progressing normally.";

        // Determine Health Status
        if (cb.isMicroMode) {
            if (errors >= cb.maxAbsErrors) { status = "CRITICAL"; statusMessage = `Max absolute errors reached (${errors})`; }
            else if (redirects >= cb.maxAbsRedirects) { status = "CRITICAL"; statusMessage = `Max absolute redirects reached (${redirects})`; }
            else if (newUrls >= cb.maxAbsNew) { status = "WARNING"; statusMessage = `High number of new URLs for small site (${newUrls})`; }
        } else {
            if (processed >= cb.minSample) {
                if (errorRate > cb.maxErrorRate) { status = "CRITICAL"; statusMessage = `Error rate too high (${(errorRate*100).toFixed(1)}%)`; }
                else if (redirectRate > cb.maxRedirectRate) { status = "CRITICAL"; statusMessage = `Redirect rate too high (${(redirectRate*100).toFixed(1)}%)`; }
                else if (growthRate > cb.maxGrowthRate) { status = "WARNING"; statusMessage = `Site growth high (${(growthRate*100).toFixed(1)}%)`; }
            } else {
                status = "PENDING_SAMPLE";
                statusMessage = `Waiting for minimum sample (${processed}/${cb.minSample})`;
            }
        }

        if (context.stopReason) {
            status = "ABORTED";
            statusMessage = `Crawler stopped: ${context.stopReason}`;
        }

        const report = {
            timestamp: new Date().toISOString(),
            domain: domain,
            mode: cb.isMicroMode ? "MICRO" : "STANDARD",
            health: status,
            message: statusMessage,
            metrics: {
                processed,
                errors,
                redirects,
                new_urls: newUrls,
                previous_total: cb.previousTotal
            },
            rates: {
                error_rate: parseFloat(errorRate.toFixed(4)),
                redirect_rate: parseFloat(redirectRate.toFixed(4)),
                growth_rate: parseFloat(growthRate.toFixed(4))
            },
            thresholds: {
                min_sample: cb.minSample,
                max_error_rate: cb.maxErrorRate,
                max_redirect_rate: cb.maxRedirectRate,
                max_growth_rate: cb.maxGrowthRate,
                max_abs_errors: cb.maxAbsErrors,
                max_abs_redirects: cb.maxAbsRedirects
            }
        };

        const reportPath = path.join(process.cwd(), "_update_report.json");
        const tempPath = `${reportPath}.tmp`;
        
        await fs.promises.writeFile(tempPath, JSON.stringify(report, null, 2));
        await fs.promises.rename(tempPath, reportPath);

    } catch (e) {
        console.error("Failed to generate update report:", e);
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

        // --- Safety Cap for OOM Prevention ---
        const SAFETY_LIMIT = 100000;
        let finalLimit = countArray;

        if (countArray === 0 && info.itemCount > SAFETY_LIMIT) {
            console.warn(`⚠️ Dataset ${name} is too large (${info.itemCount} items). Truncating load to ${SAFETY_LIMIT} to prevent OOM.`);
            finalLimit = SAFETY_LIMIT;
        }
        // -------------------------------------

        let data;
        if (finalLimit === 0) data = await dataset.getData();
        else data = await dataset.getData({ desc: true, limit: finalLimit });
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
        if (!domain) domain = name;
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
    const oldLog = console.log;
    const oldInfo = console.info;
    const oldWarn = console.warn;
    const oldError = console.error;
    const oldDebug = console.debug;

    //creer un dossier avec année/mois
    const date = new Date();
    const dateString = date.toISOString().split("T")[0];
    const folderDate = dateString.split("-")[0] + "/" + dateString.split("-")[1];
    let folderName = `./logs/` + folderDate;

    try {
        if (!fs.existsSync(folderName)) fs.mkdirSync(folderName, { recursive: true });
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
    if (typeof str !== "string") return JSON.stringify(str, null, 2);
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
    const errorDatasetName = `error-${name}`;
    const dataset = await Dataset.open(errorDatasetName);
    const info = await dataset.getInfo();

    if (!info || info.itemCount === 0) return;

    console.log(`Checking for failed requests in ${errorDatasetName} (${info.itemCount} items)...`);

    // Open queue once
    const requestQueue = await RequestQueue.open(name);
    let reclaimedCount = 0;

    await dataset.forEach(async (item) => {
        const requestID = item["id"];
        if (!requestID) return;

        try {
            const request = await requestQueue.getRequest(requestID);
            if (request) {
                request.retryCount = 0;
                request.errorMessages = [];
                request.handledAt = undefined;
                await requestQueue.reclaimRequest(request);
                reclaimedCount++;
            }
        } catch (e) {
            console.error(`Failed to reclaim request ${requestID}: ${e}`);
        }
    });

    console.log(`Successfully reclaimed ${reclaimedCount} requests.`);
    await dropDataset(errorDatasetName);
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

    // Mark request as success
    await requestQueue.markRequestHandled(request);
};

export const stopCrawler = async (crawler: PlaywrightCrawler, message: string) => {
    crawler.log.info(message);
    try {
        await crawler.autoscaledPool?.pause();
        await crawler.autoscaledPool?.abort();
        crawler.log.info("The crawler has been gracefully stopped.");
    } catch (error) {
        crawler.log.error("An error occurred when stopping the crawler : ", { error: error instanceof Error ? error.message : String(error) });
    }
};

export const escapeRegExp = (string: string) => string.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

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
        if (!fs.existsSync(requestQueuesPath)) return [];
        return fs.readdirSync(requestQueuesPath)
            .filter((file) => file.endsWith(".json"))
            .map((file) => `${requestQueuesPath}/${file}`);
    } catch (error) {
        throw new Error(`Error getAllRequestQueues for queue ${queueName}: ${error}`);
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
    try {
        // Fix: Use native URL API for robust parsing
        const urlObj = new URL(url);
        
        // 1. Always remove hash if skipDiez is true
        if (skipDiez) {
            urlObj.hash = '';
        }

        // 2. Handle Query Parameters if skipQuestionMark is true OR if we have toRemove params (alwaysRemove)
        if (skipQuestionMark || (parameters.toRemove && parameters.toRemove.length > 0)) {
            const params = urlObj.searchParams;
            const keys = Array.from(params.keys());

            // --- Logic: "Always Remove" takes precedence ---
            if (parameters.toRemove) {
                const toRemoveLower = parameters.toRemove.map(p => p.toLowerCase());
                for (const key of keys) {
                    if (toRemoveLower.includes(key.toLowerCase())) {
                        params.delete(key);
                    }
                }
            }

            // --- Logic: "Skip Question Mark" (Whitelist Strategy) ---
            if (skipQuestionMark) {
                // If we are skipping question marks, we generally remove everything...
                // UNLESS there is a 'toKeep' list.
                // If 'toKeep' is provided, we keep ONLY those.
                // If 'toKeep' is NOT provided, we fall back to defaults ["page", "id", "lang"]
                
                const defaultKeep = ["page", "id", "lang"];
                const keepList = parameters.toKeep 
                    ? parameters.toKeep.map(p => p.toLowerCase()) 
                    : defaultKeep;

                // Re-scan keys (some might have been deleted by toRemove already)
                const remainingKeys = Array.from(params.keys());
                
                for (const key of remainingKeys) {
                    if (!keepList.includes(key.toLowerCase())) {
                        params.delete(key);
                    }
                }
            }
        }

        return urlObj.toString();

    } catch (e) {
        // Fallback for invalid URLs
        return url;
    }
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

            const processedUrl = processUrl(jsonContent.url, skipQuestionMark, skipDiez, parameters);

            // If URL was modified, update both the root URL and the URL in the nested JSON
            if (processedUrl !== jsonContent.url) {
                jsonContent.url = processedUrl;

                const innerJson = JSON.parse(jsonContent.json) as JsonInnerContent;
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
        // Sync context if provided
        if (checkFrenchMethod) {
            context.frenchDetectionMethod = checkFrenchMethod;
        }

        // If we have it in context and not writing new one, return it to save disk IO
        if (!checkFrenchMethod && context.frenchDetectionMethod) {
            return context.frenchDetectionMethod;
        }

        const storagePath = `./storage/miscellaneous/${name}`;
        const filePath = `${storagePath}/${name}.json`;

        // If checkFrenchMethod is provided, we want to store it
        if (checkFrenchMethod) {
            // Create directories if they don't exist
            if (!fs.existsSync(storagePath)) fs.mkdirSync(storagePath, { recursive: true });

            // Store new method (overwrite if exists)
            fs.writeFileSync(filePath, JSON.stringify({ method: checkFrenchMethod }, null, 2));
            return checkFrenchMethod;
        }

        // If no checkFrenchMethod provided, try to read existing file
        if (fs.existsSync(filePath)) {
            const content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
            context.frenchDetectionMethod = content.method; // Update cache
            return content.method;
        }

        // If no file and no method provided, return error
        return new Error(`No French detection method stored for domain ${name}`);
    } catch (error) {
        return new Error(`Error managing French detection method: ${error}`);
    }
};