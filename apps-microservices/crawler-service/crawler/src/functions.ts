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

    let configuration = new Configuration({
        maxUsedCpuRatio: 0.95,
        availableMemoryRatio: 0.95
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

        minConcurrency: 1, // Ensure at least one browser is running
        maxConcurrency: 2, // CRITICAL: Reduced to 2 to prevent OOM on CPU-saturated machines (was 15)
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
                    const data = await getScrapingData(domain);
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
    //verifie if the folder of the domain does exist , if not create it
    var folderName = `./storage/request_urls/${name}`;
    // console.log(`folderName ${folderName}`);
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
