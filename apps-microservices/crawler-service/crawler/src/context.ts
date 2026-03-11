import { DedupManager } from "./class/DedupManager.js";
import { StatsManager } from "./class/StatsManager.js";
import { UrlConsolidator } from "./class/UrlConsolidator.js";
import { PlaywrightCrawler } from "crawlee";

export const context = {
    dedupManager: null as DedupManager | null,
    statsManager: null as StatsManager | null,
    urlConsolidator: null as UrlConsolidator | null,
    crawlerInstance: null as PlaywrightCrawler | null,
    // Store detected method in memory to avoid race conditions/disk IO
    frenchDetectionMethod: null as string | null,
    config: {
        maxErrors: 0,
        maxRedirects: 0,
        maxNewUrls: 0,
        domain: "",
        baseUrl: "",
        crawleeStorageName: "",
        // Filtering
        skipQuestionMark: false,
        skipDiez: false,
        bypassQuestionMark: false,
        bypassDiez: false,
        toKeep: [] as string[],
        toRemove: [] as string[],
        breakLimit: false,
        
        // V1 Update Logic: Dual-Mode Circuit Breaker
        circuitBreaker: {
            enabled: false,
            isMicroMode: false,
            previousTotal: 0,
            
            // Standard Mode Settings (> 50 URLs)
            minSample: 50,
            maxErrorRate: 0.15,     // 15%
            maxRedirectRate: 0.30,  // 30%
            maxGrowthRate: 0.50,    // 50%
            
            // Micro Mode Settings (<= 50 URLs)
            maxAbsErrors: 5,
            maxAbsRedirects: 10,
            maxAbsNew: 20
        }
    },
    stopReason: ""
};