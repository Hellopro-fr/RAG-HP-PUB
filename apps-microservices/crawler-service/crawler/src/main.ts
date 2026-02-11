import { RequestQueue, RobotsFile, Dataset } from "crawlee";
import fs from "fs";
import fsPromises from "fs/promises";
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
    stats as statsFromFunctions,
    dropDataset,
    isStoppedManualy,
    getUrlsCrawledStreaming,
    updateUrlsCrawledStreaming,
    getAllRequestQueues,
    parseJsonFiles,
    loadDatasetUrlsGenerator,
    copyPreviousMethod,
    rehydrateDedupFromDataset,
    generateUpdateReport,
    processUrl,
    getApifyProxyUrl,
} from "./functions.js";
import { DedupManager } from "./class/DedupManager.js";
import { StatsManager } from "./class/StatsManager.js";
import { context } from "./context.js";

const execAsync = promisify(exec);
const now = new Date().toISOString().replace(/:/g, "-");

// --- V3 Feature: Standard CLI Argument Parsing ---
const args: Record<string, string> = {};
process.argv.slice(2).forEach(arg => {
    if (arg.startsWith('--')) {
        const [key, value] = arg.replace(/^--/, '').split('=');
        args[key] = value || 'true';
    }
});

const getArg = (key: string, npmKey: string) => args[key] || process.env[npmKey];

export const domain = getArg('domain', 'npm_config_domain');
export const site = getArg('site', 'npm_config_site') || process.argv[2];
const id = getArg('id', 'npm_config_id');
const storagePath = getArg('storagePath', 'npm_config_storagepath');
const callbackUrl = getArg('callbackUrl', 'npm_config_callbackurl');
const typeCrawling = getArg('typecrawling', 'npm_config_typecrawling');
const method = getArg('method', 'npm_config_method');
const apifyProxyPassword = getArg('proxyapify', 'npm_config_proxyapify');

// Local vars for parsing, stored in context
// const breakLimit = (getArg('breaklimit', 'npm_config_breaklimit') || 'false').toLowerCase() === 'true';
const breakLimit = true; // TODO: Enforce break limit of 5000 URLs to be crawled. Find a more elegant way to handle this
const dropData = (getArg('dropdata', 'npm_config_dropdata') || 'false').toLowerCase() === 'true';
const skipquestionmark = (getArg('skipquestionmark', 'npm_config_skipquestionmark') || 'false').toLowerCase() === 'true';
const skipdiez = (getArg('skipdiez', 'npm_config_skipdiez') || 'false').toLowerCase() === 'true';
const bypassQuestionMark = (getArg('bypassquestionmark', 'npm_config_bypassquestionmark') || 'false').toLowerCase() === 'true';
const bypassDiez = (getArg('bypassdiez', 'npm_config_bypassdiez') || 'false').toLowerCase() === 'true';

let paramPerCrawl = Number(getArg('percrawl', 'npm_config_percrawl')) || 0;
let paramPerMinute = Number(getArg('perminute', 'npm_config_perminute')) || 100;
const toKeep = (getArg('tokeep', 'npm_config_tokeep') || '').split(";").filter(Boolean);
const toRemove = (getArg('toremove', 'npm_config_toremove') || '').split(";").filter(Boolean);

const crawlMode = getArg('crawlMode', 'npm_config_crawlmode') || 'standard';
const previousCrawlId = getArg('previousCrawlId', 'npm_config_previouscrawlid');
const maxErrors = Number(getArg('maxErrors', 'npm_config_maxerrors')) || 0;
const maxRedirects = Number(getArg('maxRedirects', 'npm_config_maxredirects')) || 0;
const maxNewUrls = Number(getArg('maxNewUrls', 'npm_config_maxnewurls')) || 0;

// V1 Circuit Breaker / Update Logic Params (with defaults)
const minSample = Number(getArg('minSample', 'npm_config_minsample')) || 50;
const maxErrorRate = Number(getArg('maxErrorRate', 'npm_config_maxerrorrate')) || 0.15;
const maxRedirectRate = Number(getArg('maxRedirectRate', 'npm_config_maxredirectrate')) || 0.30;
const maxGrowthRate = Number(getArg('maxGrowthRate', 'npm_config_maxgrowthrate')) || 0.50;
const maxAbsErrors = Number(getArg('maxAbsErrors', 'npm_config_maxabserrors')) || 5;
const maxAbsRedirects = Number(getArg('maxAbsRedirects', 'npm_config_maxabsredirects')) || 10;
const maxAbsNew = Number(getArg('maxAbsNew', 'npm_config_maxabsnew')) || 20;

// Setup Context immediately
context.config = {
    maxErrors,
    maxRedirects,
    maxNewUrls,
    domain: domain || "",
    baseUrl: site || "",
    crawleeStorageName: domain ? domain.replace('.', '-') : "",
    // Filtering
    skipQuestionMark: skipquestionmark,
    skipDiez: skipdiez,
    bypassQuestionMark: bypassQuestionMark,
    bypassDiez: bypassDiez,
    toKeep: toKeep,
    toRemove: toRemove,
    breakLimit: breakLimit,
    circuitBreaker: {
        enabled: false,
        isMicroMode: false,
        previousTotal: 0,
        minSample: minSample,
        maxErrorRate: maxErrorRate,
        maxRedirectRate: maxRedirectRate,
        maxGrowthRate: maxGrowthRate,
        maxAbsErrors: maxAbsErrors,
        maxAbsRedirects: maxAbsRedirects,
        maxAbsNew: maxAbsNew
    }
};

if (!id || !domain || !site || !storagePath || !callbackUrl) {
    console.log('Missing required parameters.');
    process.exit(1);
}

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
    const cgroupMemMax = await fsPromises.readFile('/sys/fs/cgroup/memory.max', 'utf-8').catch(() => null);
    const cgroupMemCurrent = await fsPromises.readFile('/sys/fs/cgroup/memory.current', 'utf-8').catch(() => null);

    if (cgroupMemMax && cgroupMemCurrent && cgroupMemMax.trim() !== 'max') {
        totalMem = parseInt(cgroupMemMax.trim());
        const usedMem = parseInt(cgroupMemCurrent.trim());
        freeMem = totalMem - usedMem;
    } else {
        // Try cgroups v1 (older Docker versions)
        const cgroupMemLimitV1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'utf-8').catch(() => null);
        const cgroupMemUsageV1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'utf-8').catch(() => null);

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

// --- MEMORY WATCHDOG ---
// Reads container memory from cgroups (same source as pre-flight check) and logs warnings.
// Does NOT stop the crawl — purely diagnostic to capture OOM evidence in log files.
const containerMemoryMb = Math.floor(totalMem / 1024 / 1024);

const readContainerMemory = async (): Promise<{ usedMem: number; totalMem: number } | null> => {
    try {
        const cgroupMemMax = await fsPromises.readFile('/sys/fs/cgroup/memory.max', 'utf-8').catch(() => null);
        const cgroupMemCurrent = await fsPromises.readFile('/sys/fs/cgroup/memory.current', 'utf-8').catch(() => null);

        if (cgroupMemMax && cgroupMemCurrent && cgroupMemMax.trim() !== 'max') {
            return {
                totalMem: parseInt(cgroupMemMax.trim()),
                usedMem: parseInt(cgroupMemCurrent.trim())
            };
        }

        // Fallback to cgroups v1
        const cgroupMemLimitV1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.limit_in_bytes', 'utf-8').catch(() => null);
        const cgroupMemUsageV1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'utf-8').catch(() => null);

        if (cgroupMemLimitV1 && cgroupMemUsageV1) {
            return {
                totalMem: parseInt(cgroupMemLimitV1.trim()),
                usedMem: parseInt(cgroupMemUsageV1.trim())
            };
        }

        // Fallback to OS-level
        return {
            totalMem: os.totalmem(),
            usedMem: os.totalmem() - os.freemem()
        };
    } catch (e) {
        return null;
    }
};

setInterval(async () => {
    const memInfo = await readContainerMemory();
    if (!memInfo) return;

    const memPercent = (memInfo.usedMem / memInfo.totalMem) * 100;
    const usedMB = Math.floor(memInfo.usedMem / 1024 / 1024);
    const totalMB = Math.floor(memInfo.totalMem / 1024 / 1024);

    if (memPercent > 92) {
        console.error(`❌ CRITICAL: Out of Memory imminent (${memPercent.toFixed(1)}% used — ${usedMB} MB / ${totalMB} MB)`);
    } else if (memPercent > 85) {
        console.warn(`⚠️  WARNING: Memory high (${memPercent.toFixed(1)}% used — ${usedMB} MB / ${totalMB} MB)`);
    }
}, 5000);
// --- END MEMORY WATCHDOG ---

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
                totalRam: totalMem, // Total RAM limit for dynamic percentage calculation
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
export let robots: RobotsFile | undefined;
const hasApifyProxyPassword = Boolean(apifyProxyPassword);

try {
    // Attempt to fetch robots.txt, but don't crash if it fails (e.g. timeout)
    console.log(`Attempting to fetch robots.txt from ${site}...`);
    robots = (hasApifyProxyPassword) ? await RobotsFile.find(site, getApifyProxyUrl(apifyProxyPassword)) : await RobotsFile.find(site);
    
    if (!robots || Object.keys(robots).length === 0) {
        console.log("robots.txt not found or empty, trying homepage.");
        const homepageUrl = new URL(site).origin;
        try {
            robots = (hasApifyProxyPassword) ? await RobotsFile.find(homepageUrl, getApifyProxyUrl(apifyProxyPassword)) : await RobotsFile.find(homepageUrl);
             if (!robots || Object.keys(robots).length === 0) console.log("Could not retrieve robots.txt from homepage.");
             else console.log("robots.txt retrieved from homepage.");
        } catch (e) {
             console.log("Could not retrieve robots.txt from homepage (error).");
        }
    } else {
        console.log("robots.txt retrieved.");
    }
} catch (e: any) {
    console.warn(`⚠️ Warning: Failed to retrieve robots.txt (likely timeout or block). Proceeding without it. Error: ${e.message}`);
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

// --- HYBRID RESUME STRATEGY ---
// Check if Redis already has data (Hot Resume)
const redisCount = await context.dedupManager.getCount();

if (redisCount > 0 && !dropData) {
    console.log(`🔥 Hot Resume detected! Redis has ${redisCount} URLs. Trusting Redis.`);
    // Sync Redis -> Disk immediately to ensure checkpoint is up to date
    console.log("Syncing hot state to disk...");
    const urlIterator = context.dedupManager.getAllUrlsIterator();
    await updateUrlsCrawledStreaming(domain, urlIterator);
} else {
    // Cold Start or Drop Data
    console.log("❄️ Cold Start detected (Redis empty). Loading from disk...");
    const urlIterator = getUrlsCrawledStreaming(domain, isHistorised, dropData ? 'true' : undefined);
    await context.dedupManager.loadFromIterator(urlIterator);

    // Rehydrate from dataset if we crashed before saving to history file
    if (context.config.crawleeStorageName) {
        const rehydrateIter = rehydrateDedupFromDataset(context.config.crawleeStorageName);
        await context.dedupManager.loadFromIterator(rehydrateIter);
    }
}

// --- PERIODIC PERSISTENCE (Safety Net) ---
const PERSIST_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes
const persistenceInterval = setInterval(async () => {
    try {
        // Only run if we have a DedupManager
        if (context.dedupManager) {
            // Note: This operation might be heavy on I/O, but it uses streaming/atomic writes
            const urlIterator = context.dedupManager.getAllUrlsIterator();
            await updateUrlsCrawledStreaming(domain, urlIterator);
        }
        
        // Generate Update Report Periodically
        if (crawlMode === 'update') {
            await generateUpdateReport(domain);
        }
    } catch (e) {
        console.error("Periodic persistence failed:", e);
    }
}, PERSIST_INTERVAL_MS);


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

// --- SEEDING LOGIC (Update Mode Support) ---
if (crawlMode === 'update') {
    if (!previousCrawlId) {
        console.error("Update mode requires --previousCrawlId");
        process.exit(1);
    }
    
    console.log(`Running UPDATE mode. Seeding from previous crawl: ${previousCrawlId}`);
    
    // Copy the detection method to avoid race conditions
    copyPreviousMethod(previousCrawlId, domain);

    const previousDatasetGenerator = loadDatasetUrlsGenerator(previousCrawlId, domain);
    let count = 0;
    let skippedDuplicates = 0;
    
    for await (const url of previousDatasetGenerator) {
        // Ensure even seed URLs are cleaned before processing
        // This handles cases where old data had dirty URLs (e.g. ?order=xxx)
        // We reuse the same config logic passed via CLI
        const cleanUrl = processUrl(
            url, 
            skipquestionmark, 
            skipdiez, 
            { toKeep, toRemove }
        );

        // 1. Add to Redis (Mark as Known) - Returns true if NEW (unique)
        // We use context.dedupManager as the source of truth for uniqueness in this session
        if (context.dedupManager) {
            const isNewUnique = await context.dedupManager.addUrl(cleanUrl);
            
            if (isNewUnique) {
                // 2. Add to Queue (Mark as Existing for Verification) ONLY if it's unique
                await requestQueue.addRequest({
                    url: cleanUrl,
                    userData: { is_existing: true }
                });
                
                count++;
                if (count % 1000 === 0) {
                    console.log(`Seeded ${count} unique URLs from previous crawl...`);
                }
            } else {
                skippedDuplicates++;
            }
        }
    }
    console.log(`Finished seeding ${count} unique URLs from previous crawl. (Skipped ${skippedDuplicates} duplicates)`);

    // --- CONFIGURE CIRCUIT BREAKER ---
    // This logic determines if we use Micro Mode (<50) or Standard Mode (>=50)
    context.config.circuitBreaker.enabled = true;
    context.config.circuitBreaker.previousTotal = count;
    context.config.circuitBreaker.isMicroMode = count < 50;
    
    console.log(`\n🛡️ Circuit Breaker Configured:`);
    console.log(`   - Previous Total: ${count}`);
    console.log(`   - Mode: ${context.config.circuitBreaker.isMicroMode ? "MICRO (Absolute Limits)" : "STANDARD (Rate Limits)"}`);
    if (context.config.circuitBreaker.isMicroMode) {
        console.log(`   - Limits: MaxErrors=${context.config.circuitBreaker.maxAbsErrors}, MaxRedirects=${context.config.circuitBreaker.maxAbsRedirects}, MaxNew=${context.config.circuitBreaker.maxAbsNew}`);
    } else {
        console.log(`   - Limits: MinSample=${context.config.circuitBreaker.minSample}, ErrorRate=${(context.config.circuitBreaker.maxErrorRate * 100).toFixed(1)}%, RedirectRate=${(context.config.circuitBreaker.maxRedirectRate * 100).toFixed(1)}%, GrowthRate=${(context.config.circuitBreaker.maxGrowthRate * 100).toFixed(1)}%`);
    }
    console.log(`----------------------------------------\n`);

} else if (await requestQueue.isEmpty()) {
    console.log("RequestQueueEmpty - Adding standard seed");
    
    // Ensure Start URL is also cleaned using the same logic
    const cleanSite = processUrl(
        site, 
        skipquestionmark, 
        skipdiez, 
        { toKeep, toRemove }
    );

    // Note: Do NOT add the seed URL to Redis dedup here.
    // The handler will add it when processing the page.
    // Pre-adding it causes the homepage to be treated as "Doublon" and skipped entirely.

    await requestQueue.addRequest({ 
        url: cleanSite, 
        userData: { is_existing: false } 
    });
} else {
    console.log("RequestQueueNotEmpty");
}

// --- QUEUE HEALTH CHECK ---
// Intelligent queue state detection using handled/pending/total counts
const queueInfo = await requestQueue.getInfo();

// Case 1: Crawl completed successfully (all items handled)
if (queueInfo && queueInfo.totalRequestCount > 0 && queueInfo.handledRequestCount === queueInfo.totalRequestCount && queueInfo.pendingRequestCount === 0) {
    console.log(`✅ Crawl already completed: ${queueInfo.handledRequestCount}/${queueInfo.totalRequestCount} items handled.`);
    console.log(`ℹ️  No pending items. Exiting gracefully.`);
    process.exit(0); // Success exit
}

// Case 2: Crash Recovery / In-Progress (Updated Logic)
if (queueInfo && queueInfo.handledRequestCount === 0 && queueInfo.pendingRequestCount === 0 && queueInfo.totalRequestCount > 0) {
    console.warn(`⚠️  WARNING: Detected ${queueInfo.totalRequestCount} in-progress items from a previous interrupted run.`);
    console.warn(`ℹ️  Crawler will resume these requests (they will be reclaimed if timed out).`);
    // We proceed instead of exiting
}

// Case 3: Normal operation
if (queueInfo) {
    console.log(`📊 Queue status: ${queueInfo.pendingRequestCount} pending, ${queueInfo.handledRequestCount} handled, ${queueInfo.totalRequestCount} total`);
}
// --------------------------

/**
 * Reusable Shutdown Logic
 * Handles persistence and cleanup on both Success and Signals (SIGTERM/SIGINT)
 */
let isShuttingDown = false;
const gracefulShutdown = async (reason: string, exitCode: number = 0) => {
    if (isShuttingDown) return;
    isShuttingDown = true;
    
    // Stop periodic task
    clearInterval(persistenceInterval);
    
    console.log(`\n🛑 Shutdown initiated: ${reason}`);

    // 1. Stop Crawler if running
    if (context.crawlerInstance) {
        console.log('Aborting crawler...');
        try {
            await context.crawlerInstance.autoscaledPool?.abort();
            await context.crawlerInstance.teardown();
        } catch (e) { 
            console.error('Error stopping crawler:', e); 
        }
    }

    // 2. Determine Final State
    let isFinished = 0;
    try {
        if (requestQueue) isFinished = (await requestQueue.isFinished()) ? 1 : 0;
    } catch (e) {}

    let isError = context.stopReason;
    if (isFinished === 0 && !isError && !breakLimit) {
        try {
            const dataset = await Dataset.open(domain);
            const info = await dataset.getInfo();
            if (info && info.itemCount >= 5000) isError = "limitCrawl";
        } catch (e) {}
    }
    if (isStoppedManualy(domain, true)) isError = "stoppedManually";

    // Get stats from instance if available, else usage functions
    const finalStats = context.crawlerInstance?.stats.state || statsFromFunctions;

    // 3. Write Payloads
    const payload = {
        id_domaine: id,
        success: finalStats?.requestsFinished || 0,
        failed: finalStats?.requestsFailed || 0,
        isFinished: isFinished,
        method: method,
        isError: isError,
        storagePath: storagePath
    };

    try {
        fs.writeFileSync(`${storagePath}/_callback_payload.json`, JSON.stringify(payload, null, 2));
        fs.writeFileSync(`${storagePath}/_exit_reason.json`, JSON.stringify({
            reason: isError || reason,
            timestamp: new Date().toISOString(),
            stats: finalStats
        }, null, 2));
    } catch (e) {
        console.error("Failed to write output files", e);
    }

    // Final Update Report for Update Mode
    if (crawlMode === 'update') {
        await generateUpdateReport(domain);
    }

    // 4. Persist Data (Critical Step)
    // 1. Persist URLs from Redis to disk (streaming)
    try {
        console.log("Persisting crawled URLs history...");
        const urlIterator = context.dedupManager?.getAllUrlsIterator();
        if (urlIterator) {
            await updateUrlsCrawledStreaming(domain, urlIterator);
        }
    } catch (e) {
        console.error("Failed to persist URL history:", e);
    }

    // 2. Save stats state
    try {
        if (context.statsManager) {
            await context.statsManager.saveStateToDisk();
            console.log("Stats saved to update_stats.json");
        }
    } catch (e) {
        console.error("Failed to save stats:", e);
    }

    // 3. Cleanup Redis connections
    if (context.dedupManager) await context.dedupManager.cleanup();
    if (context.statsManager) await context.statsManager.cleanup();

    console.log(`✅ Graceful shutdown complete. Exiting with code ${exitCode}.`);
    process.exit(exitCode);
};

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
        skipdiez,
        containerMemoryMb
    );

    process.on('SIGTERM', async () => {
        await gracefulShutdown('SIGTERM', 0);
    });

    process.on('SIGINT', async () => {
        await gracefulShutdown('SIGINT', 0);
    });
}

// Normal completion
await gracefulShutdown('COMPLETED', 2);