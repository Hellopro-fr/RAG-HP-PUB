import { RequestQueue, RobotsFile, Dataset, Configuration } from "crawlee";
import path from "path";
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
import { UrlConsolidator } from "./class/UrlConsolidator.js";
import { UpdateChecker } from "./class/UpdateChecker.js";
import { JsonlWriter } from "./class/JsonlWriter.js";
import { DetectionLangueClient } from "./class/DetectionLangueClient.js";
import { context } from "./context.js";
import { isBlanketBlock } from "./robotsTxtGuard.js";

const execAsync = promisify(exec);
const now = new Date().toISOString().replace(/:/g, "-");

// --- V3 Feature: Standard CLI Argument Parsing ---
const args: Record<string, string> = {};
process.argv.slice(2).forEach(arg => {
    if (arg.startsWith('--')) {
        const [key, ...rest] = arg.replace(/^--/, '').split('=');
        args[key] = rest.join('=') || 'true';
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
const breakLimit = (getArg('breaklimit', 'npm_config_breaklimit') || 'true').toLowerCase() === 'true';
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
const camoufoxEnabled = (getArg('camoufox', 'npm_config_camoufox') || 'true').toLowerCase() !== 'false';
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
    siteHostname: site ? new URL(site).hostname : "",
    baseUrl: site || "",
    crawleeStorageName: domain ? domain.replace(/\./g, '-') : "",
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

context.camoufoxEnabled = camoufoxEnabled;
console.log(`🦊 Browser: ${camoufoxEnabled ? 'Camoufox (stealth Firefox)' : 'Playwright (multi-browser rotation)'}`);

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
    console.error(`🔄 Pre-flight OOM: exiting with code 3 (OOM_RELAUNCH) to trigger Python-side auto-restart.`);
    process.exit(3); // OOM_RELAUNCH: trigger Python-side auto-restart
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

// --- Tier 1 Recovery Handler (85-92%) ---
let lastWarningActionTime = 0;
let lastMemPercent = 0; // Track global memory state for persistence guard
let persistenceInterval: ReturnType<typeof setInterval> | undefined;
let isPersisting = false; // Mutex flag to prevent concurrent updateUrlsCrawledStreaming calls
const handleWarningMemory = async (memPercent: number) => {
    const now = Date.now();
    if (now - lastWarningActionTime < 30000) return; // Debounce 30s
    lastWarningActionTime = now;

    console.warn(`⚠️  [Tier 1] Memory Warning (${memPercent.toFixed(1)}%). executing proactive recovery...`);

    // 1. Force GC
    if ((global as any).gc) {
        console.log("   -> Forcing V8 GC");
        (global as any).gc();
    }

    // 2. Retire Browsers (Clear memory leaks in Chrome)
    if (context.crawlerInstance?.browserPool) {
        console.log("   -> Retiring all browsers");
        await context.crawlerInstance.browserPool.retireAllBrowsers();
    }

    // 3. Pause Queue (Cooldown)
    if (context.crawlerInstance?.autoscaledPool) {
        console.log("   -> Pausing request queue for 5s");
        await context.crawlerInstance.autoscaledPool.pause();
        setTimeout(() => context.crawlerInstance?.autoscaledPool?.resume(), 5000);
    }

    // 4. Flush Persistence (REMOVED)
    // We removed emergency persistence here because persistence itself consumes significant memory
    // (Redis streaming -> JSON write). Triggering it during high memory often causes OOM.
    // We rely on the periodic persistence (with logic to skip if mem > 85%) or Phase A emergency.

    // 6. Diagnostics
    const memoryUsage = process.memoryUsage();
    console.log(`   -> RSS: ${(memoryUsage.rss / 1024 / 1024).toFixed(1)}MB, HeapUsed: ${(memoryUsage.heapUsed / 1024 / 1024).toFixed(1)}MB`);
};

// --- Tier 2 Recovery Handler (> 92%) ---
let criticalRecoveryAttempted = false;

const handleCriticalMemory = async (memPercent: number) => {
    if (!criticalRecoveryAttempted) {
        // Phase A: Aggressive Recovery
        console.error(`❌ [Tier 2] Memory CRITICAL (${memPercent.toFixed(1)}%). Initiating Phase A Recovery...`);
        criticalRecoveryAttempted = true;

        // 1. Kill Chrome processes (Forcefully release external memory)
        try {
            console.log("   -> [Phase A] Killing all Chrome/Playwright processes");
            await execAsync('pkill -9 -f "chrome|chromium" 2>/dev/null || true');
        } catch (e) { /* ignore */ }

        // 2. Emergency Persist (Save data before potential crash)
        console.log("   -> [Phase A] Emergency state persistence");
        if (context.dedupManager && !isPersisting) {
            isPersisting = true;
            try {
                const urlIterator = context.dedupManager.getAllUrlsIterator();
                await updateUrlsCrawledStreaming(domain, urlIterator);
            } finally {
                isPersisting = false;
            }
        }
        if (context.statsManager) await context.statsManager.saveStateToDisk();

        // 3. Double GC
        if ((global as any).gc) {
            console.log("   -> [Phase A] Double GC");
            (global as any).gc();
            await new Promise(r => setTimeout(r, 200));
            (global as any).gc();
        }
        
        return; // Return and wait for next poll to see if it helped
    }

    // Phase B: Graceful Shutdown (Recovery failed)
    console.error(`❌ [Tier 2] Memory STILL CRITICAL (${memPercent.toFixed(1)}%) after recovery. Initiating Phase B: Auto-Relaunch...`);
    await gracefulShutdown('OOM_RELAUNCH', 3); // Exit code 3 triggers auto-relaunch in Python
};

setInterval(async () => {
    const memInfo = await readContainerMemory();
    if (!memInfo) return;

    const memPercent = (memInfo.usedMem / memInfo.totalMem) * 100;
    lastMemPercent = memPercent; // Update global tracker

    const usedMB = Math.floor(memInfo.usedMem / 1024 / 1024);
    const totalMB = Math.floor(memInfo.totalMem / 1024 / 1024);

    if (memPercent > 92) {
        await handleCriticalMemory(memPercent);
    } else {
        // Reset Phase A flag if we dropped below critical
        if (criticalRecoveryAttempted) {
             console.log(`✅ Memory recovered to ${memPercent.toFixed(1)}%. Resetting Tier 2 Phase A flag.`);
             criticalRecoveryAttempted = false;
        }

        if (memPercent > 85) {
            await handleWarningMemory(memPercent);
        }
    }
}, 2000); // Poll every 2s (Optimized from 5s)
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

// Detect blanket robots.txt block (Disallow: * or Disallow: /)
if (robots && isBlanketBlock(robots, site)) {
    console.warn(`⚠️ robots.txt blanket block detected (all probe URLs blocked). Bypassing robots.txt for this crawl.`);
    robots = undefined;
    context.robotsTxtBypassed = true;
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
const stopperFile = path.join(storagePath, 'stopper', `${domain}.txt`);
if (fs.existsSync(stopperFile)) {
    try {
        fs.unlinkSync(stopperFile);
        console.log(`Cleaned up leftover stopper file: ${stopperFile}`);
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

    // Rehydrate '?' and '#' counters from dataset (dedup already in Redis)
    if (context.config.crawleeStorageName) {
        for await (const url of rehydrateDedupFromDataset(context.config.crawleeStorageName)) {
            if (url.includes('?')) context.countQuestionMark++;
            if (url.includes('#')) context.countDiez++;
        }
        if (context.countQuestionMark > 0 || context.countDiez > 0) {
            console.log(`Rehydrated counters (hot): ${context.countQuestionMark} URLs with '?', ${context.countDiez} URLs with '#'`);
        }
    }
} else {
    // Cold Start or Drop Data
    console.log("❄️ Cold Start detected (Redis empty). Loading from disk...");
    const urlIterator = getUrlsCrawledStreaming(domain, isHistorised, dropData ? 'true' : undefined);
    await context.dedupManager.loadFromIterator(urlIterator);

    // Rehydrate from dataset if we crashed before saving to history file
    // Also count URLs with '?' and '#' to restore postNavigationHooks counters
    if (context.config.crawleeStorageName) {
        const rehydrateIter = rehydrateDedupFromDataset(context.config.crawleeStorageName);
        let qmCount = 0;
        let diezCount = 0;
        const countingIter = async function*() {
            for await (const url of rehydrateIter) {
                if (url.includes('?')) qmCount++;
                if (url.includes('#')) diezCount++;
                yield url;
            }
        };
        await context.dedupManager.loadFromIterator(countingIter());
        context.countQuestionMark = qmCount;
        context.countDiez = diezCount;
        if (qmCount > 0 || diezCount > 0) {
            console.log(`Rehydrated counters from dataset: ${qmCount} URLs with '?', ${diezCount} URLs with '#'`);
        }
    }
}

// --- PERIODIC PERSISTENCE (Safety Net) ---
const PERSIST_INTERVAL_MS = 10 * 60 * 1000; // Increased to 10 minutes (from 5)
persistenceInterval = setInterval(async () => {
    try {
        // Guard: Skip persistence if memory is already high (>85%) to prevent OOM
        if (lastMemPercent > 85) {
            console.warn(`⚠️ Skipping periodic persistence due to high memory (${lastMemPercent.toFixed(1)}%)`);
            return;
        }

        // Only run if we have a DedupManager and no other persist is in flight
        if (context.dedupManager && !isPersisting) {
            isPersisting = true;
            try {
                const urlIterator = context.dedupManager.getAllUrlsIterator();
                await updateUrlsCrawledStreaming(domain, urlIterator);
            } finally {
                isPersisting = false;
            }
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
// Declared at outer scope so Phase 2 seeding (before startCrawler) can access it
let remainingUrls: { url: string; source: string }[] = [];

if (crawlMode === 'update') {
    if (!previousCrawlId) {
        console.error("Update mode requires --previousCrawlId");
        process.exit(1);
    }
    
    console.log(`Running UPDATE mode. Seeding from previous crawl: ${previousCrawlId}`);
    
    // Copy the detection method to avoid race conditions
    copyPreviousMethod(previousCrawlId, domain);

    // --- URL CONSOLIDATION (Epic 1) ---
    // Load URLs from 3 sources and deduplicate with strict priority:
    // Dataset > Request_queue > Request_url
    const redisUrl = process.env.REDIS_URL || 'redis://redis:6379';
    const consolidator = new UrlConsolidator(redisUrl, id, previousCrawlId, domain);
    await consolidator.connect();
    context.urlConsolidator = consolidator;

    const cleanUrlFn = (rawUrl: string) => processUrl(
        rawUrl, 
        skipquestionmark, 
        skipdiez, 
        { toKeep, toRemove }
    );

    const previousDatasetGenerator = loadDatasetUrlsGenerator(previousCrawlId, domain);
    const previousRequestUrlsGenerator = getUrlsCrawledStreaming(domain, false);

    const { allUrls, counts: consolidationCounts } = await consolidator.consolidate(
        previousDatasetGenerator,
        previousRequestUrlsGenerator,
        cleanUrlFn
    );

    // --- TWO-PHASE SEEDING (Regional Path Exclusion) ---
    // Phase 1: Seed only the homepage so it gets processed first.
    // The homepage handler populates context.excludedRegionalPaths from alternative_urls.
    // Phase 2: After homepage completes, seed remaining URLs with path filtering.

    // Create the homepageReady signal (resolved by homepage handler in routes.ts)
    let resolveHomepage: () => void;
    const homepagePromise = new Promise<void>((resolve) => { resolveHomepage = resolve; });
    context.homepageReady = { resolve: resolveHomepage!, promise: homepagePromise };

    // Phase 1: Seed only the homepage
    await requestQueue.addRequest({
        url: site,
        userData: { source: 'seed' }
    });
    if (context.dedupManager) {
        await context.dedupManager.addUrl(site);
    }

    // Collect remaining URLs for Phase 2 (all consolidated URLs except the homepage)
    for await (const { url: consolidatedUrl, source } of allUrls) {
        if (consolidatedUrl === site) continue; // Already seeded as homepage
        remainingUrls.push({ url: consolidatedUrl, source });
    }

    const totalConsolidated = remainingUrls.length + 1; // +1 for homepage
    console.log(`Consolidated ${totalConsolidated} URLs from ${consolidationCounts.dataset} Dataset + ${consolidationCounts.requestQueue} RQ + ${consolidationCounts.requestUrl} RU.`);

    // Safety net: update mode with 0 URLs means previous crawl data was unavailable
    if (totalConsolidated <= 1) {
        console.error(`❌ Update mode produced 0 URLs from previous crawl '${previousCrawlId}'. No data to compare against. Aborting.`);
        process.exit(4); // Exit code 4 = update mode no data (mapped to failure by orchestrator)
    }

    // --- CONFIGURE CIRCUIT BREAKER ---
    // Based on Dataset count only (not total), as that represents the "previous state"
    const previousTotal = consolidationCounts.dataset;
    context.config.circuitBreaker.enabled = true;
    context.config.circuitBreaker.previousTotal = previousTotal;
    context.config.circuitBreaker.isMicroMode = previousTotal < 50;
    
    console.log(`\n🛡️ Circuit Breaker Configured:`);
    console.log(`   - Previous Total (Dataset): ${previousTotal}`);
    console.log(`   - Mode: ${context.config.circuitBreaker.isMicroMode ? "MICRO (Absolute Limits)" : "STANDARD (Rate Limits)"}`);
    if (context.config.circuitBreaker.isMicroMode) {
        console.log(`   - Limits: MaxErrors=${context.config.circuitBreaker.maxAbsErrors}, MaxRedirects=${context.config.circuitBreaker.maxAbsRedirects}, MaxNew=${context.config.circuitBreaker.maxAbsNew}`);
    } else {
        console.log(`   - Limits: MinSample=${context.config.circuitBreaker.minSample}, ErrorRate=${(context.config.circuitBreaker.maxErrorRate * 100).toFixed(1)}%, RedirectRate=${(context.config.circuitBreaker.maxRedirectRate * 100).toFixed(1)}%, GrowthRate=${(context.config.circuitBreaker.maxGrowthRate * 100).toFixed(1)}%`);
    }
    console.log(`----------------------------------------\n`);

    // --- INSTANTIATE UPDATE CHECKER + JSONL WRITER (Epic 2 + 4) ---
    // JSONL files go in storage/datasets/update-{domain}/ (convention: same as error-{domain})
    if (context.statsManager && context.urlConsolidator) {
        const updateDatasetPath = path.join(storagePath, 'storage', 'datasets', `update-${domain}`);
        const jsonlWriter = new JsonlWriter(updateDatasetPath);
        const { UpdateChecker: UC } = await import("./class/UpdateChecker.js");
        context.updateChecker = new UC(context.urlConsolidator, context.statsManager, jsonlWriter);
        context.jsonlWriter = jsonlWriter;
        console.log(`✅ UpdateChecker + JsonlWriter initialized (output: storage/datasets/update-${domain}/).`);
    }

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
 * Maps internal stopReason/isError codes to human-readable French messages
 * for storage in the database column `message_erreur_crawling` (VARCHAR 250).
 */
const mapStopReasonToMessage = (errorCode: string): string => {
    const ERROR_MAP: Record<string, string> = {
        "OOM_MAX_RESTARTS": "Out Of Memory",
        "OOM_RELAUNCH": "Out Of Memory",
        "limitQuestionMark": "Arrêt sur paramètre (?)",
        "limitDiez": "Arrêt sur ancre (#)",
        "circuitBreaker": "Circuit breaker déclenché",
        "limitErrors": "Trop d'erreurs HTTP rencontrées",
        "limitCrawl": "Limite de 5000 URLs atteinte",
        "limitNewUrls": "Trop de nouvelles URLs détectées",
        "stoppedManually": "Arrêté manuellement",
        "insufficientData": "Données insuffisantes",
        "PAYLOAD_READ_ERROR": "Erreur lecture payload",
    };

    if (!errorCode) return "";
    const mapped = ERROR_MAP[errorCode];
    if (mapped) return mapped;

    // Fallback: truncate to 250 chars for VARCHAR(250)
    return `Erreur inconnue : ${errorCode}`.substring(0, 250);
};

/**
 * Reusable Shutdown Logic
 * Handles persistence and cleanup on both Success and Signals (SIGTERM/SIGINT)
 */
let isShuttingDown = false;
const gracefulShutdown = async (reason: string, exitCode: number = 0) => {
    if (isShuttingDown) return;
    isShuttingDown = true;
    
    // Stop periodic task
    if (persistenceInterval) clearInterval(persistenceInterval);
    
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
    if (isStoppedManualy(domain, true, storagePath)) isError = "stoppedManually";

    // Get stats from instance if available, else usage functions
    const finalStats = context.crawlerInstance?.stats.state || statsFromFunctions;

    // --- Compute message_erreur_crawling ---
    // Priority: context.crawlErrorMessage (set by routes.ts for specific cases) > mapStopReasonToMessage
    let messageErreurCrawling = context.crawlErrorMessage || "";

    if (!messageErreurCrawling && isError) {
        messageErreurCrawling = mapStopReasonToMessage(isError);
    }

    // Special case: OOM_RELAUNCH
    if (reason === 'OOM_RELAUNCH' && !messageErreurCrawling) {
        messageErreurCrawling = "Out Of Memory";
    }

    // Truncate to 250 chars (VARCHAR limit)
    if (messageErreurCrawling.length > 250) {
        messageErreurCrawling = messageErreurCrawling.substring(0, 250);
    }


    // 3. Write Payloads
    const payload = {
        id_domaine: id,
        success: finalStats?.requestsFinished || 0,
        failed: finalStats?.requestsFailed || 0,
        isFinished: isFinished,
        method: method,
        isError: isError,
        storagePath: storagePath,
        message_erreur_crawling: messageErreurCrawling || null,
        robots_txt_bypassed: context.robotsTxtBypassed,
        camoufox_used: context.camoufoxEnabled
    };

    const isOomRelaunch = (reason === 'OOM_RELAUNCH');
    const exitReason = isOomRelaunch ? 'OOM_RELAUNCH' : (isError || reason);

    try {
        fs.writeFileSync(`${storagePath}/_callback_payload.json`, JSON.stringify(payload, null, 2));
        fs.writeFileSync(`${storagePath}/_exit_reason.json`, JSON.stringify({
            reason: exitReason,
            timestamp: new Date().toISOString(),
            stats: finalStats
        }, null, 2));
    } catch (e) {
        console.error("Failed to write output files", e);
    }

    // Final Update Report for Update Mode
    if (crawlMode === 'update') {
        try {
            await generateUpdateReport(domain);
        } catch (e) {
            console.error("Failed to generate update report:", e);
            if (!payload.message_erreur_crawling) {
                payload.message_erreur_crawling = "Erreur lors de la génération du rapport de mise à jour";
                fs.writeFileSync(`${storagePath}/_callback_payload.json`, JSON.stringify(payload, null, 2));
            }
        }
    }

    // 4. Persist Data (Critical Step)
    // 1. Persist URLs from Redis to disk (streaming)
    // Wait for any in-flight persistence to complete before final write
    try {
        if (isPersisting) {
            console.log("Waiting for in-flight persistence to complete...");
            while (isPersisting) {
                await new Promise(r => setTimeout(r, 100));
            }
        }
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

    // 3. Close JSONL streams (flush to disk before Redis cleanup)
    if (context.jsonlWriter) {
        try {
            await context.jsonlWriter.closeAll();
        } catch (e) {
            console.error("Failed to close JSONL streams:", e);
            if (!payload.message_erreur_crawling) {
                payload.message_erreur_crawling = "Erreur lors de l'enregistrement du rapport de mise à jour";
                fs.writeFileSync(`${storagePath}/_callback_payload.json`, JSON.stringify(payload, null, 2));
            }
        }
    }

    // 4. Cleanup Redis connections
    if (context.urlConsolidator) await context.urlConsolidator.cleanup();
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

    // Pre-flight: Configure Global Crawlee Memory Limit
    // This ensures AutoscaledPool sees the REAL container limit, not host memory
    const memInfoPreFlight = await readContainerMemory();
    if (memInfoPreFlight) {
        const containerMb = Math.floor(memInfoPreFlight.totalMem / 1024 / 1024);
        console.log(`🚀 Configuring Global Crawlee Memory Limit: ${containerMb} MB (Environment + Config)`);
        process.env.CRAWLEE_MEMORY_MBYTES = String(containerMb);
        Configuration.getGlobalConfig().set('memoryMbytes', containerMb);
    }

    // Phase 2: Seed remaining URLs after homepage completes (runs concurrently with crawler)
    if (crawlMode === 'update' && context.homepageReady) {
        const seedPhase2 = async () => {
            // If excluded paths were already restored from disk (crash/OOM restart
            // or copied from previous crawl), skip waiting for homepage detection.
            if (context.excludedRegionalPaths.length > 0) {
                console.log(`[PHASE 2] Excluded paths already loaded from disk (${context.excludedRegionalPaths.length} paths). Skipping homepage wait.`);
            } else {
                const HOMEPAGE_TIMEOUT_MS = 120_000;
                const timeout = new Promise<void>((resolve) => setTimeout(resolve, HOMEPAGE_TIMEOUT_MS));
                await Promise.race([context.homepageReady!.promise, timeout]);
            }

            const excluded = context.excludedRegionalPaths;
            if (excluded.length > 0) {
                console.log(`[PHASE 2] Homepage detected ${excluded.length} excluded regional paths: ${excluded.join(", ")}`);
            } else {
                console.log(`[PHASE 2] No regional paths to exclude. Seeding all URLs.`);
            }

            let seedCount = 0;
            let skippedCount = 0;
            for (const { url, source } of remainingUrls) {
                if (excluded.length > 0 && DetectionLangueClient.isExcludedRegionalPath(url, excluded)) {
                    skippedCount++;
                    continue;
                }

                if (context.dedupManager) {
                    await context.dedupManager.addUrl(url);
                }
                await requestQueue.addRequest({
                    url: url,
                    userData: { source: source }
                });
                seedCount++;
                if (seedCount % 1000 === 0) {
                    console.log(`[PHASE 2] Seeded ${seedCount} URLs...`);
                }
            }
            console.log(`[PHASE 2] Finished seeding ${seedCount} URLs (${skippedCount} excluded as regional variants).`);
        };

        // Fire-and-forget: runs concurrently with the crawler
        seedPhase2().catch(err => console.error(`[PHASE 2] Error during seeding: ${err.message}`));
    }

    // Launch
    const crawler = await startCrawler(
        router,
        domain,
        paramPerCrawl,
        paramPerMinute,
        apifyProxyPassword,
        breakLimit,
        bypassQuestionMark,
        bypassDiez,
        skipquestionmark,
        skipdiez,
        containerMemoryMb,
        camoufoxEnabled
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