import { RequestQueue, RobotsFile } from "crawlee";
import axios from "axios";
import fs from "fs/promises"; // Added for file system operations
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

export let allUrlsCrawled = getUrlsCrawled(domain, isHistorised, dropData ? 'true' : undefined);

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

// Open requestQueue
export const requestQueue = await RequestQueue.open(domain);

if (typeCrawling === "generate_data") {
    // This logic might need adjustment in an API context
    console.log("Data generation mode is not fully supported in API mode. Exiting.");
} else {
    // Reclaim failed request
    await reclaimFailedRequest(domain);

    // Launch the crawler
    await startCrawler(
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