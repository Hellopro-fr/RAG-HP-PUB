import { RequestQueue, RobotsFile } from "crawlee";
import fs from "fs";
import { createClient } from 'redis';
import os from 'os';
import { exec } from "child_process";
import { promisify } from "util";
import { router } from "./routes.js";
import {
    getPathAfterDomain,
    getScrapingData,
    rightTrimSlash,
    startCrawler,
    attachFSLogger,
    reclaimFailedRequest,
    stats,
    dropDataset,
    isStoppedManualy,
    getUrlsCrawled,
    getAllRequestQueues,
    parseJsonFiles,
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

if (!id || !domain || !site || !storagePath || !callbackUrl) {
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


// Robots check
export let robots = await RobotsFile.find(site);
if (!robots || Object.keys(robots).length === 0) {
    console.log("robots.txt not found or empty, trying homepage.");
    const homepageUrl = new URL(site).origin;
    robots = await RobotsFile.find(homepageUrl);
    if (!robots || Object.keys(robots).length === 0) console.log("Could not retrieve robots.txt from homepage.");
    else console.log("robots.txt retrieved from homepage.");
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
// Drop the dataset when we have the parameter --dropdata
if (dropData) {
    console.log("Dropping datasets and request queue...");
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
// export let allUrlsCrawled = new Set<string>(); // Keep local set for compatibility or fallback
const history = getUrlsCrawled(domain, isHistorised, dropData ? 'true' : undefined);
if (history.length > 0) {
    console.log(`Seeding ${history.length} URLs to Redis Deduplication...`);
    await context.dedupManager.loadFromList(history);
    // Also fill local set if needed for V2 logic fallback
    // history.forEach(u => allUrlsCrawled.add(u));
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

if (typeCrawling == "sitemap") {
    // ...
} else if (typeCrawling == "generate_data") {
    // ... logic for generate data ...
} else {
    // Reclaim failed request
    try {
        await reclaimFailedRequest(domain);
    } catch (error) {
        console.warn(`⚠️ Warning: Failed to reclaim failed requests for ${domain}. The crawler will continue without them. Error: ${error}`);
    }

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
        skipquestionmark,
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

process.exit(2);