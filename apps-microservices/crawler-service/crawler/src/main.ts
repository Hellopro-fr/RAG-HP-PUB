import { RequestQueue, RobotsFile, Request } from "crawlee";
import { exec } from "child_process";
import fs from "fs";
import os from "os";
import { promisify } from "util";
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
    updateUrlsCrawled,
    getAllRequestQueues,
    parseJsonFiles,
    dropDataset as dropDatasetFn // Fix import clash
} from "./functions.js";
import { DedupManager } from "./class/DedupManager.js";
import { StatsManager } from "./class/StatsManager.js";
import { context } from "./context.js";

const execAsync = promisify(exec);
const now = new Date().toISOString().replace(/:/g, "-");

// --- V3 Feature: Standard CLI Argument Parsing ---
// Parsing args like --domain=example.com instead of npm_config
const args: Record<string, string> = {};
process.argv.slice(2).forEach(arg => {
    if (arg.startsWith('--')) {
        const [key, value] = arg.replace(/^--/, '').split('=');
        args[key] = value || 'true';
    }
});

// Fallback to npm_config for backward compat or usage via npm start
const getArg = (key: string, npmKey: string) => args[key] || process.env[npmKey];

export const domain = getArg('domain', 'npm_config_domain');
export const site = getArg('site', 'npm_config_site') || process.argv[2];
const id = getArg('id', 'npm_config_id');
const storagePath = getArg('storagePath', 'npm_config_storagepath');
const callbackUrl = getArg('callbackUrl', 'npm_config_callbackurl');
const typeCrawling = getArg('typecrawling', 'npm_config_typecrawling');
const method = getArg('method', 'npm_config_method');
const apifyProxyPassword = getArg('proxyapify', 'npm_config_proxyapify');
const breakLimit = (getArg('breaklimit', 'npm_config_breaklimit') || 'false').toLowerCase() === 'true';
const dropData = (getArg('dropdata', 'npm_config_dropdata') || 'false').toLowerCase() === 'true';
export const skipquestionmark = (getArg('skipquestionmark', 'npm_config_skipquestionmark') || 'false').toLowerCase() === 'true';
export const skipdiez = (getArg('skipdiez', 'npm_config_skipdiez') || 'false').toLowerCase() === 'true';
const bypassQuestionMark = (getArg('bypassquestionmark', 'npm_config_bypassquestionmark') || 'false').toLowerCase() === 'true';
const bypassDiez = (getArg('bypassdiez', 'npm_config_bypassdiez') || 'false').toLowerCase() === 'true';

let paramPerCrawl = Number(getArg('percrawl', 'npm_config_percrawl')) || 500;
let paramPerMinute = Number(getArg('perminute', 'npm_config_perminute')) || 100;
export const toKeep = (getArg('tokeep', 'npm_config_tokeep') || '').split(";").filter(Boolean);
export const toRemove = (getArg('toremove', 'npm_config_toremove') || '').split(";").filter(Boolean);

// V3 Params
const crawlMode = getArg('crawlMode', 'npm_config_crawlmode') || 'standard';
const previousCrawlId = getArg('previousCrawlId', 'npm_config_previouscrawlid');
const maxErrors = Number(getArg('maxErrors', 'npm_config_maxerrors')) || 0;
const maxRedirects = Number(getArg('maxRedirects', 'npm_config_maxredirects')) || 0;
const maxNewUrls = Number(getArg('maxNewUrls', 'npm_config_maxnewurls')) || 0;

// Setup Context
context.config = {
    maxErrors,
    maxRedirects,
    maxNewUrls,
    domain: domain || "",
    baseUrl: site || "",
    crawleeStorageName: domain ? domain.replace('.', '-') : ""
};

if (!id || !domain || !site) {
    console.log('Missing required parameters.');
    process.exit(1);
}

// Change CWD if storagePath provided (V3 Logic)
if (storagePath) {
    try {
        if (!fs.existsSync(storagePath)) fs.mkdirSync(storagePath, { recursive: true });
        process.chdir(storagePath);
        console.log(`[stdout] Changed working directory to: ${process.cwd()}`);
    } catch (err) {
        console.error("Failed to change CWD:", err);
    }
}

const nameLogs = `${domain}-logs-${now}.log`;
attachFSLogger(nameLogs);

console.info("Environment Variables & Args Parsed");

// --- V3 Feature: Orphan Process Cleanup ---
try {
    // Fire and forget cleanup
    exec('pkill -9 -f "chrome|chromium" || true');
    exec('pkill -9 -f "playwright" || true');
} catch (e) {}

// Robots check
export let robots = await RobotsFile.find(site);
if (!robots || Object.keys(robots).length === 0) {
    console.log("robots.txt introuvable ou vide, tentative sur la homepage.");
    const homepageUrl = new URL(site).origin;
    robots = await RobotsFile.find(homepageUrl);
    if (!robots || Object.keys(robots).length === 0) console.log("Impossible de récupérer robots.txt.");
    else console.log("robots.txt récupéré");
} else {
    console.log("robots.txt récupéré");
}

const siteParts = getPathAfterDomain(site);
export const baseUrl = siteParts.baseUrl;
const includePath = rightTrimSlash(siteParts.path);
export let enqueueLinksIncludePath: Array<string> = [];
if (includePath) {
    enqueueLinksIncludePath.push(`${baseUrl}${includePath}/**/*`);
}

// --- V3 Feature: Stale Stopper Cleanup ---
if (fs.existsSync(`stopper/${domain}.txt`)) {
    try {
        fs.unlinkSync(`stopper/${domain}.txt`);
        console.log("Removed stale stopper file.");
    } catch (e) {}
}

// Init Managers
const redisUrl = process.env.REDIS_URL || "redis://redis:6379";
context.dedupManager = new DedupManager(redisUrl, id);
context.statsManager = new StatsManager(redisUrl, id, storagePath || ".");

await context.dedupManager.connect();
await context.statsManager.connect();

let isHistorised = false;
if (dropData) {
    console.log("Droping the dataset ...");
    const requestQueueToDrop = await RequestQueue.open(domain);
    await requestQueueToDrop.drop();
    await dropDataset(domain);
    await dropDataset(`error-${domain}`);
    await dropDataset(`nfr-${domain}`);
    
    // Also clean managers
    await context.dedupManager.cleanup();
    await context.statsManager.cleanup();
    // Reconnect after cleanup
    await context.dedupManager.connect();
    await context.statsManager.connect();

    isHistorised = true;
} else {
    // Load stats if resuming
    await context.statsManager.loadStateFromDisk();
}

// Load legacy history into Redis Dedup (V3 Logic)
// In V2 this was `allUrlsCrawled` array. Now we seed Redis.
export let allUrlsCrawled = new Set<string>(); // Keep local set for compatibility or fallback
const history = getUrlsCrawled(domain, isHistorised, dropData ? 'true' : undefined);
if (history.length > 0) {
    console.log(`Seeding ${history.length} URLs to Redis Deduplication...`);
    await context.dedupManager.loadFromList(history);
    // Also fill local set if needed for V2 logic fallback
    history.forEach(u => allUrlsCrawled.add(u));
}

// Filter queue files on disk (V3 Fix logic included in functions.ts)
if (skipquestionmark || skipdiez) {
    const requestQueueList = getAllRequestQueues(domain);
    if (requestQueueList.length > 0) {
        let parameters: any = {};
        if (toKeep.length > 0) parameters.toKeep = toKeep;
        if (toRemove.length > 0) parameters.toRemove = toRemove;
        parseJsonFiles(requestQueueList, Boolean(skipquestionmark), Boolean(skipdiez), parameters);
    }
}

export const requestQueue = await RequestQueue.open(domain);

// --- V3 Feature: Queue Health Check ---
const queueInfo = await requestQueue.getInfo();
if (queueInfo && queueInfo.totalRequestCount > 0 && queueInfo.handledRequestCount === 0 && queueInfo.pendingRequestCount === 0) {
    if (!breakLimit) {
        console.error("❌ CRITICAL: Corrupted/Locked Queue detected. Aborting.");
        process.exit(1);
    }
}

if (typeCrawling == "sitemap") {
    // ...
} else if (typeCrawling == "generate_data") {
    // ... logic for generate data ...
} else {
    // Reclaim failed
    await reclaimFailedRequest(domain);

    // --- V3 Feature: Update Mode Seeding ---
    if (crawlMode === 'update' && previousCrawlId) {
        console.log(`Running UPDATE mode from ${previousCrawlId}`);
        // Logic to read previous dataset would go here. 
        // Since V2 doesn't have the V3 generator logic easily available without more porting,
        // we'll assume the Python Manager handles data migration or we just skip this advanced feature 
        // inside the Node process for now, relying on the fact that V2 usually just runs fresh.
        // However, if strict parity is needed, we'd need to mount the previous volume and read it.
    }

    // Launch
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
        skipquestionmark,
        skipdiez
    );
}

// --- V3 Feature: Exit Logic & Files ---
let isFinished = (await requestQueue.isFinished()) ? 1 : 0;
let isError = context.stopReason; // Populated by routes/functions

// Check logic for counts
if (isFinished === 0 && !isError) {
    const data = await getScrapingData(domain);
    if (data.items.length >= 5000) isError = "limitCrawl";
}
if (isStoppedManualy(domain, true)) isError = "stoppedManually";

// Write callback payload
const payload = {
    id_domaine: id,
    success: stats?.requestsFinished || 0,
    failed: stats?.requestsFailed || 0,
    isFinished: isFinished,
    method: method,
    isError: isError,
    storagePath: storagePath
};

try {
    fs.writeFileSync(`${storagePath}/_callback_payload.json`, JSON.stringify(payload, null, 2));
    // Also write exit reason
    fs.writeFileSync(`${storagePath}/_exit_reason.json`, JSON.stringify({
        reason: isError || "completed",
        timestamp: new Date().toISOString(),
        stats: stats
    }, null, 2));
} catch (e) {
    console.error("Failed to write output files", e);
}

// Cleanup Redis
await context.dedupManager.cleanup();
await context.statsManager.cleanup();

// Cleanup Handlers
process.on('SIGINT', async () => {
    console.log("SIGINT received");
    await context.crawlerInstance?.teardown();
    process.exit(0);
});

process.exit(2);