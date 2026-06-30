import { RequestQueue, RobotsFile, Dataset, Configuration } from "crawlee";
import path from "path";
import fs from "fs";
import fsPromises from "fs/promises";
import os from 'os';
import { router } from "./routes.js";
import { RECOVER_FAILED_ON_RESTART, shouldRunRecovery, resolveStallCountResolved } from "./httpStatusPolicy.js";
import {
    getPathAfterDomain,
    getScrapingData,
    rightTrimSlash,
    startCrawler,
    attachFSLogger,
    reclaimFailedRequest,
    stats as statsFromFunctions,
    dropDataset,
    clearDecisionSidecars,
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
    stopCrawler,
} from "./functions.js";
import { DedupManager } from "./class/DedupManager.js";
import { PushedSet } from "./class/PushedSet.js";
import { RedisHealthMonitor } from "./class/RedisHealthMonitor.js";
import { ProgressMonitor } from "./class/ProgressMonitor.js";
import { StatsManager } from "./class/StatsManager.js";
import { UrlConsolidator } from "./class/UrlConsolidator.js";
import { UpdateChecker } from "./class/UpdateChecker.js";
import { JsonlWriter } from "./class/JsonlWriter.js";
import { DetectionLangueClient } from "./class/DetectionLangueClient.js";
import { ContentExtractorClient } from "./class/ContentExtractorClient.js";
import { TimingRecorder } from "./class/TimingRecorder.js";
import type { PoolSample, TimingSummary } from "./timing/types.js";
import { context } from "./context.js";
import { readPersistedDecision, applyCliFlagGuard, getDiezDecisionMode } from "./diezDecision.js";
import { applyCliFlagGuard as applyQuestionMarkGuard, getQuestionMarkDecisionMode, persistObservations as persistQuestionMarkObservations, readQmPersistedDecision } from "./questionMarkDecision.js";
import { isBlanketBlock } from "./robotsTxtGuard.js";
import { perClassEnabled, stripActionAnchor, actionAnchorStripEnabled } from "./diezClassify.js";
import { killBrowserProcesses } from "./browserKill.js";
import { readUsableMemory } from "./cgroupMemory.js";
import { createSharedRedisClient } from "./redisClient.js";
import { buildHtmlIndex } from "./htmlIndex.js";

const now = new Date().toISOString().replace(/:/g, "-");

// Crawl start timestamp (déclaré ici pour être accessible depuis le handler de fin de crawl
// qui construit la payload — ligne ~985). Mais ASSIGNÉ plus tard, juste avant
// `await startCrawler(...)` (ligne ~1294), pour exclure le temps de bootstrap
// (init Crawlee, Playwright, consolidate URLs, seeding) du décompte.
// Format MySQL DATETIME, alimente crawl_metrics.date_start côté PHP.
let crawlStartTime = '';

// --- V3 Feature: Standard CLI Argument Parsing ---
const args: Record<string, string> = {};
process.argv.slice(2).forEach(arg => {
    if (arg.startsWith('--')) {
        const [key, ...rest] = arg.replace(/^--/, '').split('=');
        args[key] = rest.join('=') || 'true';
    }
});

const getArg = (key: string, npmKey: string) => args[key] || process.env[npmKey];

const parseNumericArg = (key: string, npmKey: string, defaultValue: number): number => {
    const raw = getArg(key, npmKey);
    if (raw === undefined) return defaultValue;
    const parsed = Number(raw);
    return isNaN(parsed) ? defaultValue : parsed;
};

export const domain = getArg('domain', 'npm_config_domain');
export const site = getArg('site', 'npm_config_site') || process.argv[2];
const id = getArg('id', 'npm_config_id');
export const storagePath = getArg('storagePath', 'npm_config_storagepath');
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
const bypassQueue = (getArg('bypassqueue', 'npm_config_bypassqueue') || 'false').toLowerCase() === 'true';
const queueLimit = parseNumericArg('queuelimit', 'npm_config_queuelimit', 2000);

let paramPerCrawl = parseNumericArg('percrawl', 'npm_config_percrawl', 0);
let paramPerMinute = parseNumericArg('perminute', 'npm_config_perminute', 100);
const toKeep = (getArg('tokeep', 'npm_config_tokeep') || '').split(";").filter(Boolean);
const toRemove = (getArg('toremove', 'npm_config_toremove') || '').split(";").filter(Boolean);

const crawlMode = getArg('crawlMode', 'npm_config_crawlmode') || 'standard';
const camoufoxEnabled = (getArg('camoufox', 'npm_config_camoufox') || 'true').toLowerCase() !== 'false';
const previousCrawlId = getArg('previousCrawlId', 'npm_config_previouscrawlid');
const maxErrors = parseNumericArg('maxErrors', 'npm_config_maxerrors', 0);
const maxRedirects = parseNumericArg('maxRedirects', 'npm_config_maxredirects', 0);
const maxNewUrls = parseNumericArg('maxNewUrls', 'npm_config_maxnewurls', 0);

// V1 Circuit Breaker / Update Logic Params (with defaults)
const minSample = parseNumericArg('minSample', 'npm_config_minsample', 50);
const maxErrorRate = parseNumericArg('maxErrorRate', 'npm_config_maxerrorrate', 0.15);
const maxRedirectRate = parseNumericArg('maxRedirectRate', 'npm_config_maxredirectrate', 0.30);
const maxGrowthRate = parseNumericArg('maxGrowthRate', 'npm_config_maxgrowthrate', 0.50);
const maxAbsErrors = parseNumericArg('maxAbsErrors', 'npm_config_maxabserrors', 5);
const maxAbsRedirects = parseNumericArg('maxAbsRedirects', 'npm_config_maxabsredirects', 10);
const maxAbsNew = parseNumericArg('maxAbsNew', 'npm_config_maxabsnew', 20);

// External-redirect breaker (update mode) — spec 2026-06-09
const externalRedirectBreakerEnabled = (getArg('externalRedirectBreaker', 'npm_config_externalredirectbreaker') || 'true').toLowerCase() === 'true';
const maxExternalRedirectRate = parseNumericArg('maxExternalRedirectRate', 'npm_config_maxexternalredirectrate', 0.90);
const externalRedirectMinSample = parseNumericArg('externalRedirectMinSample', 'npm_config_externalredirectminsample', 10);

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
        maxAbsNew: maxAbsNew,
        externalRedirectBreakerEnabled: externalRedirectBreakerEnabled,
        maxExternalRedirectRate: maxExternalRedirectRate,
        externalRedirectMinSample: externalRedirectMinSample
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

// Clean restart (dropData): delete prior diez/QM decision sidecars from storagePath
// root BEFORE the reads below. storagePath is reused per crawl_id and is NOT cleared
// by the Python relaunch path, and Node's own dataset drop (~L560) runs AFTER these
// reads — so without this, readPersistedDecision/readQmPersistedDecision would inherit
// stale skip/bypass decisions on a "clean" restart. OOM_RELAUNCH (non-dropData) keeps them.
if (storagePath && dropData) {
    const cleared = clearDecisionSidecars(storagePath);
    if (cleared.length) console.log(`[dropData] cleared stale decision sidecars: ${cleared.join(', ')}`);
}

// Tier-1 diez auto-decision bootstrap: load persisted decision (OOM_RELAUNCH) or
// mark as committed if CLI already set skipDiez/bypassDiez (human choice wins, spec §10.1).
if (storagePath) {
    const loaded = readPersistedDecision(storagePath);
    if (!loaded) applyCliFlagGuard();
}

// Tier-1 observer guard: disable observation if CLI already set skipQuestionMark / bypassQuestionMark.
// Human choice wins — spec §9.3.
applyQuestionMarkGuard();
// Phase-2: restore previously committed toRemove params (OOM_RELAUNCH).
if (storagePath) readQmPersistedDecision(storagePath);

const nameLogs = `${domain}-logs-${now}.log`;
attachFSLogger(nameLogs);

console.info("Crawler starting with arguments:");
console.info(JSON.stringify(args, null, 2));

// --- PRE-FLIGHT CHECKS ---
// 1. Kill orphan browser processes from previous runs
console.log('🧹 Checking for orphan browser processes...');
await killBrowserProcesses();
// Reap delay: kernel reclaims anon pages from killed children asynchronously.
// 2s is empirically sufficient on Linux 5.x+ to flush the post-kill cgroup
// state before the threshold check below reads /sys/fs/cgroup/memory.current.
await new Promise((r) => setTimeout(r, 2000));

// 2. Check available memory (Docker container limits, not host VM)
// Page cache is subtracted from used because Linux reclaims it on demand
// before invoking the OOM-killer (Spec-B 2026-05-21).
const gb = (n: number) => (n / 1024 / 1024 / 1024).toFixed(2);
let totalMem: number;

const mem = await readUsableMemory();
if (!mem) {
    // Cannot measure memory. Skip pre-flight — assume OK rather than block startup.
    console.warn('⚠️  Pre-flight: readUsableMemory() returned null. Skipping threshold check.');
    totalMem = os.totalmem();
} else {
    totalMem = mem.totalMem;
    const usablePercent = (mem.usableUsed / mem.totalMem) * 100;
    const rawPercent = (mem.rawCurrent / mem.totalMem) * 100;
    console.log(
        `💾 Memory status: ${gb(mem.usableUsed)}GB usable / ${gb(mem.rawCurrent)}GB raw / ` +
        `${gb(mem.totalMem)}GB limit ` +
        `(${usablePercent.toFixed(1)}% usable, ${rawPercent.toFixed(1)}% raw, ${gb(mem.pageCache)}GB page cache).`
    );
    if (usablePercent > 80) {
        console.error(`❌ Memory critically low: ${usablePercent.toFixed(1)}% usable used. Aborting to prevent OOM.`);
        console.error(`🔄 Pre-flight OOM: exiting with code 3 (OOM_RELAUNCH) to trigger Python-side auto-restart.`);
        process.exit(3);
    }
}

console.log('✅ Pre-flight checks passed. Starting crawler...');
// --- END PRE-FLIGHT CHECKS ---

// --- MEMORY WATCHDOG ---
// Reads container memory from cgroups (same source as pre-flight check) and logs warnings.
// Does NOT stop the crawl — purely diagnostic to capture OOM evidence in log files.
const containerMemoryMb = Math.floor(totalMem / 1024 / 1024);

// Adapter over readUsableMemory(): preserves the {usedMem, totalMem} shape
// expected by Tier 1/2 handlers while shifting `usedMem` semantics from raw
// memory.current to usable used (= memory.current - page cache).
const readContainerMemory = async (): Promise<{ usedMem: number; totalMem: number } | null> => {
    const mem = await readUsableMemory();
    if (!mem) return null;
    return { usedMem: mem.usableUsed, totalMem: mem.totalMem };
};

// --- Tier 1 Recovery Handler (85-92%) ---
let lastWarningActionTime = 0;
let lastMemPercent = 0; // Track global memory state for persistence guard
let persistenceInterval: ReturnType<typeof setInterval> | undefined;
let progressMonitor: ProgressMonitor | undefined;
let isPersisting = false; // Mutex flag to prevent concurrent updateUrlsCrawledStreaming calls
const handleWarningMemory = async (memPercent: number) => {
    const now = Date.now();
    if (now - lastWarningActionTime < 30000) return; // Debounce 30s
    lastWarningActionTime = now;

    console.warn(`⚠️  [Tier 1] Memory Warning (${memPercent.toFixed(1)}% usable). executing proactive recovery...`);

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
        console.error(`❌ [Tier 2] Memory CRITICAL (${memPercent.toFixed(1)}% usable). Initiating Phase A Recovery...`);
        criticalRecoveryAttempted = true;

        // 1. Kill all browser processes (forcefully release external memory)
        console.log("   -> [Phase A] Killing all browser processes");
        await killBrowserProcesses();

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
    console.error(`❌ [Tier 2] Memory STILL CRITICAL (${memPercent.toFixed(1)}% usable) after recovery. Initiating Phase B: Auto-Relaunch...`);
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
             console.log(`✅ Memory recovered to ${memPercent.toFixed(1)}% usable. Resetting Tier 2 Phase A flag.`);
             criticalRecoveryAttempted = false;
        }

        if (memPercent > 85) {
            await handleWarningMemory(memPercent);
        }
    }
}, 2000); // Poll every 2s (Optimized from 5s)
// --- END MEMORY WATCHDOG ---

// --- Redis Health + Progress Monitors ---
const redisUrl = process.env.REDIS_URL || 'redis://redis:6379';
const parsedRedisLossMs = Number(process.env.REDIS_LOSS_THRESHOLD_MS);
const redisLossThresholdMs = Number.isFinite(parsedRedisLossMs) && parsedRedisLossMs > 0
    ? parsedRedisLossMs
    : 60_000;
const redisMonitor = new RedisHealthMonitor(
    redisLossThresholdMs,
    (reason) => {
        console.error(`[fatal] redis_lost: ${reason}`);
        console.error(JSON.stringify({ event: 'redis_lost', reason, snapshot: redisMonitor.snapshot() }));
        // gracefulShutdown is declared later in the file; safe to forward-reference
        // via the top-level `gracefulShutdown` const because we only call it at fire-time.
        void gracefulShutdown('REDIS_LOST', 5);
    },
);
// Single client identity — heartbeat + dedup multiplex on sharedRedis.
redisMonitor.attach('shared');
redisMonitor.start();

// --- Shared Redis client (heartbeat + dedup multiplex) ---
const sharedRedis = createSharedRedisClient(redisUrl, { crawlId: id, monitor: redisMonitor });
try {
    await sharedRedis.connect();
    redisMonitor.onSuccess('shared');
    console.log('Connected to Redis (shared client for heartbeat + dedup)');

    const hostname = os.hostname();
    const numCpus = os.cpus().length;
    let lastCpuUsage = process.cpuUsage();
    let lastTime = Date.now();

    // Helper to get top 3 RAM processes
    const getTopProcesses = async (): Promise<Array<{ name: string, ram: number }>> => {
        try {
            const { execSync } = await import('child_process');
            const output = execSync('ps aux --sort=-rss | head -n 4 | tail -n 3', { encoding: 'utf-8' });
            const lines = output.trim().split('\n');
            return lines.map(line => {
                const parts = line.trim().split(/\s+/);
                const ramKB = parseInt(parts[5]) || 0;
                const command = parts.slice(10).join(' ').substring(0, 30);
                return { name: command, ram: ramKB * 1024 };
            });
        } catch (e) {
            return [];
        }
    };

    // Helper to read container-level memory usage from cgroups
    const getContainerMemoryUsage = async (): Promise<number> => {
        try {
            const v2 = await fsPromises.readFile('/sys/fs/cgroup/memory.current', 'utf-8').catch(() => null);
            if (v2) return parseInt(v2.trim());
            const v1 = await fsPromises.readFile('/sys/fs/cgroup/memory/memory.usage_in_bytes', 'utf-8').catch(() => null);
            if (v1) return parseInt(v1.trim());
        } catch (e) { /* fallback below */ }
        return process.memoryUsage().rss;
    };

    // Helper to read container-level CPU usage from cgroups
    const getContainerCpuUsec = async (): Promise<number | null> => {
        try {
            const v2 = await fsPromises.readFile('/sys/fs/cgroup/cpu.stat', 'utf-8').catch(() => null);
            if (v2) {
                const match = v2.match(/usage_usec\s+(\d+)/);
                if (match) return parseInt(match[1]);
            }
            const v1 = await fsPromises.readFile('/sys/fs/cgroup/cpuacct/cpuacct.usage', 'utf-8').catch(() => null);
            if (v1) return parseInt(v1.trim()) / 1000;
        } catch (e) { /* fallback below */ }
        return null;
    };

    let lastContainerCpuUsec = await getContainerCpuUsec();
    let lastContainerCpuTime = Date.now();

    setInterval(async () => {
        try {
            let cpuPercent: number;
            const currentContainerCpuUsec = await getContainerCpuUsec();
            const currentTime = Date.now();

            if (currentContainerCpuUsec !== null && lastContainerCpuUsec !== null) {
                const deltaCpuUsec = currentContainerCpuUsec - lastContainerCpuUsec;
                const deltaWallUsec = (currentTime - lastContainerCpuTime) * 1000;
                cpuPercent = (deltaCpuUsec / deltaWallUsec) / numCpus;
                lastContainerCpuUsec = currentContainerCpuUsec;
                lastContainerCpuTime = currentTime;
            } else {
                const currentCpuUsage = process.cpuUsage(lastCpuUsage);
                const elapsedTime = (currentTime - lastTime) * 1000;
                cpuPercent = ((currentCpuUsage.user + currentCpuUsage.system) / elapsedTime) / numCpus;
                lastCpuUsage = process.cpuUsage();
                lastTime = currentTime;
            }

            const containerRam = await getContainerMemoryUsage();
            const topProcesses = await getTopProcesses();

            const heartbeat = {
                type: 'heartbeat',
                replicaId: hostname,
                jobId: id,
                domain: domain,
                cpu: Math.min(Math.max(cpuPercent, 0), 1),
                ram: containerRam,
                totalRam: totalMem,
                topProcesses: topProcesses,
                timestamp: Date.now(),
                status: 'running'
            };
            try {
                await sharedRedis.publish('crawler:heartbeat', JSON.stringify(heartbeat));
                redisMonitor.onSuccess('shared');
            } catch (e) {
                redisMonitor.onError('shared', e);
                console.error('Failed to send heartbeat:', e);
            }
        } catch (e) {
            console.error('Heartbeat interval error:', e);
        }
    }, 2000);
} catch (err) {
    console.error('Failed to connect shared Redis client:', err);
    redisMonitor.onError('shared', err);
    redisMonitor.stop();
    process.exit(5);
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

// Init Managers — DedupManager reuses the shared Redis client.
context.dedupManager = new DedupManager(sharedRedis, id, undefined, redisMonitor);
// PushedSet guards non-idempotent dataset writes against retry/restart
// duplication. Shares the same Redis client + monitor.
context.pushedSet = new PushedSet(sharedRedis, id, { monitor: redisMonitor });
// Set de claim DÉDIÉ à UpdateChecker.checkUrl. Même client/monitor, mais clé
// `checked:{id}` distincte de `pushed:{id}` : checkUrl ne consomme plus le jeton
// d'écriture dataset, donc routerDefaultHandler peut de nouveau pousser les pages
// « confirmed » en mode update (cf. régression PushedSet du 2026-05-24).
context.checkedSet = new PushedSet(sharedRedis, id, { monitor: redisMonitor, keyPrefix: 'checked' });
context.statsManager = new StatsManager(sharedRedis, id, storagePath || ".");
// No dedupManager.connect() — shared client is already connected above.
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
    if (context.pushedSet) await context.pushedSet.cleanup();
    if (context.checkedSet) await context.checkedSet.cleanup();
    await context.statsManager.cleanup();
    // Shared client survives all manager cleanups (ownsClient=false on dedup,
    // pushed, checked AND now stats), so no reconnect is needed. The
    // statsManager.connect() below is a no-op on the injected path (kept for
    // symmetry with the legacy URL constructor).
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
            console.warn(`⚠️ Skipping periodic persistence due to high memory (${lastMemPercent.toFixed(1)}% usable)`);
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

// --- QUEUE-PAUSE GATE (Machine-time protection) ---
// Dedicated SHORT interval (30s) — NOT the 10-min persistence timer — so an
// oversized site is stopped EARLY (~30-60s after crossing the cap) rather than
// after ~1000 pages. Stop when totalRequestCount (cumulative URLs enqueued)
// exceeds the cap — a hard size limit, NOT the live pending backlog. bypassqueue=1
// is the operator "crawl fully" override; queuelimit<=0 disables the gate entirely.
const QUEUE_PAUSE_INTERVAL_MS = 30 * 1000;
const queuePauseInterval: ReturnType<typeof setInterval> | undefined =
    (!bypassQueue && queueLimit > 0)
        ? setInterval(async () => {
            try {
                const liveQueueInfo = await requestQueue.getInfo();
                if (liveQueueInfo && liveQueueInfo.totalRequestCount > queueLimit) {
                    console.warn(`⚠️ Queue-pause gate triggered: total=${liveQueueInfo.totalRequestCount} > limit=${queueLimit} (limitQueue).`);
                    context.stopReason = "limitQueue";
                    if (context.crawlerInstance) {
                        await stopCrawler(context.crawlerInstance, `Total enqueued URLs (${liveQueueInfo.totalRequestCount}) exceeded limit ${queueLimit} (limitQueue).`);
                    }
                }
            } catch (e) {
                console.error("Queue-pause gate check failed:", e);
            }
        }, QUEUE_PAUSE_INTERVAL_MS)
        : undefined;


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

// --- QUEUE STATS PUBLISHER (live observability) ---
// Always-on (unlike the conditional queue-pause gate): every 30s, snapshot the
// request-queue depth to {storagePath}/_queue_stats.json so the Python /status
// handler can surface total/remaining URL counts to the BO live panel.
const QUEUE_STATS_INTERVAL_MS = 30 * 1000;
const queueStatsInterval = setInterval(async () => {
    try {
        const info = await requestQueue.getInfo();
        if (!info) return;
        const payload = JSON.stringify({
            total_request_count: info.totalRequestCount,
            pending_request_count: info.pendingRequestCount,
            updated_at: new Date().toISOString(),
        });
        await fs.promises.writeFile(path.join(storagePath, '_queue_stats.json'), payload);
    } catch (e) {
        console.error("Queue-stats publisher failed:", e);
    }
}, QUEUE_STATS_INTERVAL_MS);

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
    const consolidator = new UrlConsolidator(sharedRedis, id, previousCrawlId, domain);
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
    let phase1SeedUrl = site;
    if (actionAnchorStripEnabled()) {
        const strippedAa = stripActionAnchor(phase1SeedUrl);
        if (strippedAa !== phase1SeedUrl) {
            phase1SeedUrl = strippedAa;
            context.actionAnchorsStripped++;
        }
    }
    await requestQueue.addRequest({
        url: phase1SeedUrl,
        uniqueKey: phase1SeedUrl,
        userData: { source: 'seed' }
    });
    // Do NOT pre-add the homepage to Redis dedup here (same rule as the standard
    // seed below). The handler claims it on first processing; pre-adding makes the
    // handler see it as a "Doublon" and skip extraction — which also skips homepage
    // detection (regional-path exclusion) in update mode.

    // Collect remaining URLs for Phase 2 (all consolidated URLs except the homepage)
    for await (const { url: consolidatedUrl, source } of allUrls) {
        if (consolidatedUrl === site) continue; // Already seeded as homepage
        remainingUrls.push({ url: consolidatedUrl, source });
    }

    const totalConsolidated = remainingUrls.length + 1; // +1 for homepage
    console.log(`Consolidated ${totalConsolidated} URLs from ${consolidationCounts.dataset} Dataset + ${consolidationCounts.requestQueue} RQ + ${consolidationCounts.requestUrl} RU.`);

    if (context.statsManager && consolidationCounts.duplicatesRemoved > 0) {
        await context.statsManager.increment("filtered_duplicate", consolidationCounts.duplicatesRemoved);
    }

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
    // We will not basing the Circuit Breaker using the number of URL anymore
    // context.config.circuitBreaker.isMicroMode = previousTotal < 50;
    
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
        context.updateChecker = new UC(context.urlConsolidator, context.statsManager, jsonlWriter, context.checkedSet ?? null);
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

    let standardSeedUrl = cleanSite;
    if (actionAnchorStripEnabled()) {
        const strippedAa = stripActionAnchor(standardSeedUrl);
        if (strippedAa !== standardSeedUrl) {
            standardSeedUrl = strippedAa;
            context.actionAnchorsStripped++;
        }
    }
    await requestQueue.addRequest({
        url: standardSeedUrl,
        uniqueKey: standardSeedUrl,
        userData: { is_existing: false }
    });
} else {
    console.log("RequestQueueNotEmpty");
}

// Auto-recover recoverable (infra/transient) failures from a prior run BEFORE the
// queue-health early-exit, so a same-id restart re-crawls proxy/network victims
// instead of exiting "already completed". Default-on; RECOVER_FAILED_ON_RESTART=false
// reverts to the prior behavior. Spec: 2026-06-16-crawler-failure-recovery-design.md
if (shouldRunRecovery(RECOVER_FAILED_ON_RESTART, typeCrawling ?? "")) {
    try {
        await reclaimFailedRequest(domain);
    } catch (e) {
        console.warn(`⚠️ auto-recovery skipped for ${domain}: ${e}`);
    }
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
 * Formats a TimingSummary snapshot as a human-readable console block.
 * Phases are sorted by share-of-total descending so the dominant phase is first.
 */
function formatTimingSummary(s: TimingSummary): string {
    const lines: string[] = [];
    lines.push("=== Timing summary ===");
    lines.push(`Pages: ${s.pages_total} in ${s.duration_s}s ` +
        `(avg ${s.pages_per_min_avg} pages/min, max ${s.pages_per_min_max_sustained} sustained)`);
    lines.push("Phase share of total handler time:");
    const phases: Array<[string, keyof TimingSummary["phases"]]> = [
        ["wait_ms", "wait_ms"],
        ["nav_ms", "nav_ms"],
        ["pre_detect_ms", "pre_detect_ms"],
        ["detect_ms", "detect_ms"],
        ["post_ms", "post_ms"],
    ];
    const sorted = phases.slice().sort((a: [string, keyof TimingSummary["phases"]], b: [string, keyof TimingSummary["phases"]]) =>
        s.phases[b[1]].share_of_total_pct - s.phases[a[1]].share_of_total_pct);
    for (const [label, key] of sorted) {
        const ph = s.phases[key];
        lines.push(`  ${label.padEnd(14)}${ph.share_of_total_pct.toFixed(1)}%  ` +
            `(median ${ph.median}ms, p95 ${ph.p95}ms)`);
    }
    lines.push("Pool:");
    lines.push(`  Crawlee avg concurrency: ${s.pool.crawlee_avg_concurrency} ` +
        `/ max reached: ${s.pool.crawlee_max_concurrency_reached} ` +
        `/ throttled ${s.pool.crawlee_throttle_pct}% of time`);
    lines.push(`  Detect API saturated ${s.pool.detect_saturated_pct}% of time ` +
        `(pending queue non-empty at concurrency cap)`);
    lines.push(`  Memory: avg ratio ${s.pool.memory_avg_ratio}, max ${s.pool.memory_max_ratio}`);
    return lines.join("\n");
}

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
        "interruptedShutdown": "Crawl interrompu lors de l'arrêt du service",
        "limitQueue": "File d'attente d'URLs trop volumineuse",
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
// Hoisted to module scope so gracefulShutdown can flush timing before any
// payload write / Redis cleanup / process.exit. Assigned only inside the
// TIMING_ENABLED block below; remains null when timing is disabled.
let finalizeTimingOnce: (() => Promise<void>) | null = null;
const gracefulShutdown = async (reason: string, exitCode: number = 0) => {
    if (isShuttingDown) return;
    isShuttingDown = true;

    // Stop health monitors first so they cannot fire mid-shutdown.
    try { redisMonitor?.stop(); } catch (e) { /* ignore */ }
    try { progressMonitor?.stop(); } catch (e) { /* ignore */ }

    // Timing instrumentation: stop sampler + flush JSONL/summary before exit.
    // Synchronous-ish: finalize() is fast and fire-and-await before any exit.
    if (typeof finalizeTimingOnce === 'function') {
        await finalizeTimingOnce();
    }

    // Stop periodic tasks
    if (persistenceInterval) clearInterval(persistenceInterval);
    if (queuePauseInterval) clearInterval(queuePauseInterval);
    clearInterval(queueStatsInterval);

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

    // If exiting with unfinished queue and no error, the shutdown interrupted the crawl
    // (e.g., SIGTERM race condition, container restart). Set explicit error code so the BO
    // can handle it properly instead of entering a silent retry loop.
    if (isFinished === 0 && !isError) isError = "interruptedShutdown";

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


    // Timestamp de fin de crawl — capté ici (juste avant le build de la payload) pour refléter
    // la VRAIE fin du crawl côté crawler-service (et non l'heure où PHP reçoit le webhook,
    // qui inclurait la latence Python + le retry du webhook). Format MySQL DATETIME.
    const crawlEndTime = new Date().toISOString().slice(0, 19).replace('T', ' ');

    // Read deperdition counters from StatsManager (defaults to 0 if unavailable)
    async function readStat(metric: string): Promise<number> {
        if (!context.statsManager) return 0;
        try { return await context.statsManager.getValue(metric); } catch { return 0; }
    }
    const filtered_qm = await readStat("filtered_qm");
    const filtered_hash = await readStat("filtered_hash");
    const filtered_ext = await readStat("filtered_ext");
    const filtered_nonfr = await readStat("filtered_nonfr");
    const filtered_duplicate = await readStat("filtered_duplicate");
    const filtered_pdf = await readStat("filtered_pdf");
    const dropped_cb = await readStat("dropped_cb");
    const external_redirects = await readStat("external_redirects");
    const timeout_individual = await readStat("timeout_individual");
    const success_extracted = await readStat("success");

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
        camoufox_used: context.camoufoxEnabled,
        diezDecisionMode: getDiezDecisionMode(isError),
        questionMarkDecisionMode: getQuestionMarkDecisionMode(isError),
        // Observability — deperdition counters (StatsManager / Redis-backed)
        filtered_qm,
        filtered_hash,
        filtered_ext,
        filtered_nonfr,
        filtered_duplicate,
        filtered_pdf,
        dropped_cb,
        external_redirects,
        timeout_individual,
        success_extracted,
        // Observability — timestamps début/fin pour calculer duration_seconds côté PHP
        date_start: crawlStartTime,
        date_end: crawlEndTime,
    };

    const isOomRelaunch = (reason === 'OOM_RELAUNCH');
    const exitReason = isOomRelaunch ? 'OOM_RELAUNCH' : (isError || reason);

    try {
        const payloadPath = `${storagePath}/_callback_payload.json`;
        const exitReasonPath = `${storagePath}/_exit_reason.json`;

        fs.writeFileSync(payloadPath, JSON.stringify(payload, null, 2));
        fs.writeFileSync(exitReasonPath, JSON.stringify({
            reason: exitReason,
            timestamp: new Date().toISOString(),
            stats: finalStats
        }, null, 2));

        // Force OS disk flush so Python manager can read reliably after process.wait()
        const fdPayload = fs.openSync(payloadPath, 'r');
        fs.fsyncSync(fdPayload);
        fs.closeSync(fdPayload);
        const fdExit = fs.openSync(exitReasonPath, 'r');
        fs.fsyncSync(fdExit);
        fs.closeSync(fdExit);
    } catch (e) {
        console.error("Failed to write output files", e);
    }

    // Phase-1.5 sidecar — persist tier-1 observer Maps so offline audits can read
    // per-param frequency without URL replay. Self-contained: own try/catch in the
    // helper, never throws. See questionMarkDecision.ts persistObservations().
    persistQuestionMarkObservations(storagePath);

    // Build the per-domain URL->filename index for the SFPI HTML store (hot tier). Fail-open.
    buildHtmlIndex(storagePath, domain);

    // Final Update Report for Update Mode
    if (crawlMode === 'update') {
        try {
            await generateUpdateReport(domain);
        } catch (e) {
            console.error("Failed to generate update report:", e);
            if (!payload.message_erreur_crawling) {
                payload.message_erreur_crawling = "Erreur lors de la génération du rapport de mise à jour";
                const payloadRewritePath = `${storagePath}/_callback_payload.json`;
                fs.writeFileSync(payloadRewritePath, JSON.stringify(payload, null, 2));
                const fdRw1 = fs.openSync(payloadRewritePath, 'r');
                fs.fsyncSync(fdRw1);
                fs.closeSync(fdRw1);
            }
        }
    }

    // Phase-2: shutdown dataset cleanup — legacy skipDiez blind strip, or content-collision
    // when DIEZ_PERCLASS_ENABLED. Stats captured for the _diez_audit.json sidecar below.
    if (reason === 'COMPLETED' && (context.config.skipDiez || perClassEnabled())) {
        try {
            const { cleanDatasetFragments } = await import("./functions.js");
            context.diezContentCollision = cleanDatasetFragments([domain, `nfr-${domain}`, context.config.crawleeStorageName, `nfr-${context.config.crawleeStorageName}`]);
        } catch (e) {
            console.error("Dataset fragment cleanup failed:", e);
        }
    }

    // Phase-2: per-crawl audit sidecar (collapsed-fragment candidates + content-collision stats).
    if (storagePath && perClassEnabled()) {
        try {
            fs.writeFileSync(
                `${storagePath}/_diez_audit.json`,
                JSON.stringify({
                    collapsed_candidates: context.diezCollapsed,
                    content_collision: context.diezContentCollision,
                }, null, 2),
            );
            if (context.diezCollapsed.length > 0) {
                console.warn(`[diez] route-loss candidates: ${context.diezCollapsed.length} fragment page(s) collapsed onto an existing base — see _diez_audit.json (re-crawl to confirm).`);
            }
        } catch (e) {
            console.error("Diez audit sidecar write failed:", e);
        }
    }

    // Phase-2 QM audit sidecar (spec 2026-06-29): committed params + their pair stats +
    // collapsed-param route-loss candidates. Mirrors _diez_audit.json.
    if (storagePath && (context.qmTier2.addedToRemove.length > 0 || context.qmCollapsed.length > 0)) {
        try {
            const pairStats: Record<string, { same: number; different: number; unusable: number }> = {};
            for (const [p, s] of context.qmTier2.tally) pairStats[p] = s;
            fs.writeFileSync(
                `${storagePath}/_questionmark_audit.json`,
                JSON.stringify({
                    collapsed_candidates: context.qmCollapsed,
                    committed: context.qmTier2.addedToRemove,
                    pair_stats: pairStats,
                }, null, 2),
            );
            if (context.qmCollapsed.length > 0) {
                console.warn(`[questionmark] route-loss candidates: ${context.qmCollapsed.length} ?param= page(s) collapsed onto an existing base — see _questionmark_audit.json (re-crawl to confirm).`);
            }
        } catch (e) {
            console.error("QM audit sidecar write failed:", e);
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
                const payloadRewritePath2 = `${storagePath}/_callback_payload.json`;
                fs.writeFileSync(payloadRewritePath2, JSON.stringify(payload, null, 2));
                const fdRw2 = fs.openSync(payloadRewritePath2, 'r');
                fs.fsyncSync(fdRw2);
                fs.closeSync(fdRw2);
            }
        }
    }

    // 4. Cleanup Redis connections
    if (context.urlConsolidator) await context.urlConsolidator.cleanup();
    if (context.dedupManager) await context.dedupManager.cleanup();
    if (context.pushedSet) await context.pushedSet.cleanup();
    if (context.checkedSet) await context.checkedSet.cleanup();
    if (context.statsManager) await context.statsManager.cleanup();

    // Disconnect the shared Redis client (heartbeat + dedup multiplexed on it).
    // Owner-managed — DedupManager.cleanup() left this open by design.
    try {
        if (sharedRedis && sharedRedis.isOpen) await sharedRedis.disconnect();
    } catch (e) {
        console.error('Shared Redis disconnect error:', e);
    }

    if (context.actionAnchorsStripped > 0) {
        console.log(`[diez] stripped ${context.actionAnchorsStripped} action-anchor fragment(s)`);
    }
    console.log(`✅ Graceful shutdown complete. Exiting with code ${exitCode}.`);
    process.exit(exitCode);
};

if (typeCrawling == "sitemap") {
    // ...
} else if (typeCrawling == "generate_data") {
    // ... logic for generate data ...
} else {
    // Failed-request recovery now runs earlier (before the queue-health check) so it
    // is reachable for completed crawls — see the RECOVER_FAILED_ON_RESTART block above.

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

                // Do NOT pre-add to Redis dedup before queueing. The page handler
                // claims each URL on first processing (routes.ts). Pre-adding here
                // made every non-dataset seed (request_queue / request_url) self-mark
                // as "Doublon" and get skipped before reaching UpdateChecker.
                let seedUrl = url;
                if (actionAnchorStripEnabled()) {
                    const strippedAa = stripActionAnchor(seedUrl);
                    if (strippedAa !== seedUrl) {
                        seedUrl = strippedAa;
                        context.actionAnchorsStripped++;
                    }
                }
                await requestQueue.addRequest({
                    url: seedUrl,
                    userData: { source: source }
                });
                seedCount++;
                if (seedCount % 1000 === 0) {
                    console.log(`[PHASE 2] Seeded ${seedCount} URLs...`);
                }
            }
            console.log(`[PHASE 2] Finished seeding ${seedCount} URLs (${skippedCount} excluded as regional variants).`);
            context.phase2SeedingComplete = true;
        };

        // Fire-and-forget: runs concurrently with the crawler
        context.phase2SeedingComplete = false;
        seedPhase2().catch(err => {
            console.error(`[PHASE 2] Error during seeding: ${err.message}`);
            context.phase2SeedingComplete = true; // Unblock crawler on error
        });

        // Safety timeout: force completion flag after 5 minutes if Phase 2 hangs
        setTimeout(() => {
            if (!context.phase2SeedingComplete) {
                console.warn("[PHASE 2] Timeout: seeding not complete after 5 minutes. Forcing completion flag.");
                context.phase2SeedingComplete = true;
            }
        }, 5 * 60 * 1000);
    }

    // --- SHARED DETECTION CLIENT ---
    // Constructed unconditionally so routes.ts and the (optional) timing
    // sampler share the SAME p-limit queue. With a per-module instance in
    // routes.ts, the sampler's `limiter.pendingCount/activeCount` would have
    // observed an empty queue while the real workload ran on the routes
    // instance — masking detect-API saturation.
    context.detectionClient = new DetectionLangueClient();
    // Phase-2 tier-2 content comparison. Constructed unconditionally; only used
    // when DIEZ_TIER2_ENABLED and the diez engine activates.
    context.contentExtractorClient = new ContentExtractorClient();

    // --- TIMING INSTRUMENTATION ---
    // When TIMING_ENABLED=false (the default), this entire block is a no-op:
    // no recorder is constructed, no sampler is started, and no signal
    // listeners are registered. Routes/hooks observe `context.timingRecorder`
    // and short-circuit when it is undefined.
    const TIMING_ENABLED = (process.env.TIMING_ENABLED ?? "false").toLowerCase() === "true";
    const TIMING_SAMPLE_INTERVAL_MS = parseInt(process.env.TIMING_SAMPLE_INTERVAL_MS ?? "5000");

    if (TIMING_ENABLED) {
        console.log(`[TIMING] enabled — outputDir=${storagePath} sampleIntervalMs=${TIMING_SAMPLE_INTERVAL_MS}`);
    } else {
        console.log("[TIMING] disabled — set TIMING_ENABLED=true to write timing.jsonl + timing-summary.json to the crawl folder");
    }

    let timingSampler: NodeJS.Timeout | null = null;

    if (TIMING_ENABLED) {
        const detectionClient = context.detectionClient;

        const recorder = new TimingRecorder({
            crawlId: String(id),
            outputDir: storagePath,
            detectMaxConcurrency: detectionClient.maxConcurrency,
        });
        context.timingRecorder = recorder;

        let lastSampleAt = Date.now();
        let pagesAtLastSample = 0;

        timingSampler = setInterval(() => {
            try {
                const crawlerInstance = context.crawlerInstance;
                const pool = (crawlerInstance as any)?.autoscaledPool;
                const memUsedBytes = process.memoryUsage().rss;
                const budgetBytes = ((crawlerInstance as any)?.config?.memoryMbytes ?? 0) * 1024 * 1024;
                const handled = (crawlerInstance as any)?.stats?.state?.requestsFinished ?? 0;
                const elapsedMs = Date.now() - lastSampleAt;
                const ppm = elapsedMs > 0 ? Math.round(((handled - pagesAtLastSample) / elapsedMs) * 60000) : 0;
                lastSampleAt = Date.now();
                pagesAtLastSample = handled;

                const sample: PoolSample = {
                    t: Date.now(),
                    crawlee: {
                        currentConcurrency: pool?.currentConcurrency ?? 0,
                        desiredConcurrency: pool?.desiredConcurrency ?? 0,
                        maxConcurrency: pool?.maxConcurrency ?? 0,
                    },
                    detect: {
                        pendingCount: detectionClient.limiter.pendingCount,
                        activeCount: detectionClient.limiter.activeCount,
                    },
                    memory: {
                        used_mb: Math.round(memUsedBytes / (1024 * 1024)),
                        budget_mb: Math.round(budgetBytes / (1024 * 1024)),
                        ratio: budgetBytes > 0 ? memUsedBytes / budgetBytes : 0,
                    },
                    rolling: { pages_per_min: ppm },
                };
                recorder.recordPoolSample(sample);
            } catch (err) {
                console.error(`[TIMING] sampler error: ${(err as Error).message}`);
            }
        }, TIMING_SAMPLE_INTERVAL_MS);

        finalizeTimingOnce = (() => {
            let done = false;
            return async () => {
                if (done) return;
                done = true;
                if (timingSampler) {
                    clearInterval(timingSampler);
                    timingSampler = null;
                }
                await recorder.finalize();
                console.log(formatTimingSummary(recorder.snapshot()));
            };
        })();

        // SIGINT/SIGTERM are handled exclusively by gracefulShutdown (declared
        // at module scope above), which now invokes finalizeTimingOnce as its
        // first step. Registering duplicate listeners here would race with
        // process.exit and lose the JSONL flush. Keep beforeExit for natural
        // exit (loop empty → no signal fires → gracefulShutdown still runs
        // via the COMPLETED path, but beforeExit acts as belt-and-braces).
        process.on("beforeExit", () => { void finalizeTimingOnce!(); });
    }
    // --- END TIMING INSTRUMENTATION ---

    // Capture du timestamp de démarrage RÉEL du crawl, juste avant l'invocation de
    // startCrawler() qui appelle crawler.run() (cf functions.ts:755). Tout le setup
    // précédent (bootstrap modules, init Crawlee, Playwright, consolidate URLs,
    // two-phase seeding) est EXCLU du décompte de duration_seconds.
    crawlStartTime = new Date().toISOString().slice(0, 19).replace('T', ' ');

    // Progress stall monitor — fires gracefulShutdown(exit 6) if requestsFinished
    // does not advance for PROGRESS_STALL_THRESHOLD_MS (default 10 min).
    const parsedProgressStallMs = Number(process.env.PROGRESS_STALL_THRESHOLD_MS);
    const progressStallThresholdMs = Number.isFinite(parsedProgressStallMs) && parsedProgressStallMs > 0
        ? parsedProgressStallMs
        : 600_000;
    progressMonitor = new ProgressMonitor(
        () => {
            const st = (context.crawlerInstance as any)?.stats?.state;
            const finished = st?.requestsFinished ?? 0;
            if (!resolveStallCountResolved(process.env.STALL_COUNT_RESOLVED)) return finished;
            return finished + (st?.requestsFailed ?? 0);
        },
        progressStallThresholdMs,
        (reason) => {
            console.error(`[fatal] progress_stalled: ${reason}`);
            console.error(JSON.stringify({ event: 'progress_stalled', reason }));
            void gracefulShutdown('PROGRESS_STALL', 6);
        },
        30_000,
    );
    progressMonitor.start();

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

// Normal completion. fatalExitCode is set by an in-handler fatal breaker
// (e.g. domainChanged -> 7) so the run terminates as a failure; otherwise 2 (success).
await gracefulShutdown('COMPLETED', context.fatalExitCode ?? 2);