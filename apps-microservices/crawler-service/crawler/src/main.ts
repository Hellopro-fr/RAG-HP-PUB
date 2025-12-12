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

// --- QUEUE HEALTH CHECK ---
// Intelligent queue state detection using handled/pending/total counts
const queueInfo = await requestQueue.getInfo();

// Case 1: Crawl completed successfully (all items handled)
if (queueInfo && queueInfo.handledRequestCount === queueInfo.totalRequestCount && queueInfo.pendingRequestCount === 0) {
    console.log(`✅ Crawl already completed: ${queueInfo.handledRequestCount}/${queueInfo.totalRequestCount} items handled.`);
    console.log(`ℹ️  No pending items. Exiting gracefully.`);
    process.exit(0); // Success exit
}

// Case 2: Corrupted/polluted queue (items exist but none are handled or pending)
if (queueInfo && queueInfo.handledRequestCount === 0 && queueInfo.pendingRequestCount === 0 && queueInfo.totalRequestCount > 0) {
    console.error(`❌ CRITICAL: Corrupted queue detected for ${domain}`);
    console.error(`   Total items: ${queueInfo.totalRequestCount}`);
    console.error(`   Handled: 0, Pending: 0`);
    console.error(`ℹ️  All items are locked/stuck in an invalid state.`);
    console.error(`💡 SOLUTION: Use Monitor Interface > 'Queue Editor' > 'Analyze' then 'Clean Patterns' or 'Drop Queue'.`);
    process.exit(1); // Error exit
}

// Case 3: Normal operation - items are pending or being processed
if (queueInfo) {
    console.log(`📊 Queue status: ${queueInfo.pendingRequestCount} pending, ${queueInfo.handledRequestCount} handled, ${queueInfo.totalRequestCount} total`);
}
// --------------------------

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