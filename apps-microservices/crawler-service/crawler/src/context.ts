import { DedupManager } from "./class/DedupManager.js";
import { StatsManager } from "./class/StatsManager.js";
import { UrlConsolidator } from "./class/UrlConsolidator.js";
import { UpdateChecker } from "./class/UpdateChecker.js";
import { JsonlWriter } from "./class/JsonlWriter.js";
import { PlaywrightCrawler } from "crawlee";

export const context = {
    dedupManager: null as DedupManager | null,
    statsManager: null as StatsManager | null,
    urlConsolidator: null as UrlConsolidator | null,
    updateChecker: null as UpdateChecker | null,
    jsonlWriter: null as JsonlWriter | null,
    crawlerInstance: null as PlaywrightCrawler | null,
    // Store detected method in memory to avoid race conditions/disk IO
    frenchDetectionMethod: null as string | null,
    config: {
        maxErrors: 0,
        maxRedirects: 0,
        maxNewUrls: 0,
        domain: "",
        siteHostname: "",
        baseUrl: "",
        crawleeStorageName: "",
        // Filtering
        skipQuestionMark: false,
        skipDiez: false,
        bypassQuestionMark: false,
        bypassDiez: false,
        toKeep: [] as string[],
        toRemove: [] as string[],
        breakLimit: true,
        
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
    stopReason: "",
    robotsTxtBypassed: false,
    camoufoxEnabled: true,
    crawlErrorMessage: "",
    // In-memory counters for URLs containing '?' and '#' pushed to the dataset.
    // Used by postNavigationHooks to avoid O(n²) full-dataset scans.
    countQuestionMark: 0,
    countDiez: 0,
    // Tier-1 auto-decision for limitDiez (see diezDecision.ts + spec 2026-04-17).
    // Counters are in-memory only (not persisted across restarts — §10.2 of spec).
    diezClassification: {
        anchor: 0,
        spa: 0,
        ambiguous: 0,
        total: 0,
        samplesForTier2: [] as string[],  // URLs classified as ambiguous; capped at 50
    },
    // Set to true once a tier-1 commit has happened OR a persisted decision was loaded at startup.
    // When true, recordClassification is a no-op — we already decided.
    diezDecisionCommitted: false,
    // Tier-1 observer for limitQuestionMark (see questionMarkDecision.ts + spec 2026-04-17).
    // Records the domain-specific params that survived Tier-0 stripping. No decisions yet.
    questionMarkObservations: {
        // param name → running count of occurrences across URLs pushed to dataset (post-Tier-0)
        paramFrequency: new Map<string, number>(),
        // param name → list of full URLs carrying that param, capped at 50 samples per param
        samplesByParam: new Map<string, string[]>(),
        // total count of URLs pushed to dataset that STILL contain '?' after Tier-0 processing
        // (differs from context.countQuestionMark which also counts URLs whose '?' survived)
        domainSpecificCount: 0,
    },
    // Becomes false when the human's skipQuestionMark or bypassQuestionMark is set at crawl start.
    // When false, recordQuestionMarkObservation is a no-op (human choice wins).
    questionMarkObservationEnabled: true,
    // Stored language query param for session-based i18n sites (e.g., ?lang=fr)
    // Populated when homepage detection method is pattern_match_query
    languageQueryParam: null as { key: string; value: string } | null,
    // Regional path prefixes to exclude (e.g., ["/fr", "/fr-BE", "/fr-CA"]).
    // Populated from alternative_urls during homepage detection.
    // Read by transformRequestFunction to block discovered regional variant links.
    excludedRegionalPaths: [] as string[],
    // Promise-based signal for update mode two-phase seeding.
    // Created in main.ts (update mode only). Resolved by homepage handler in routes.ts
    // after storing excludedRegionalPaths. Awaited by Phase 2 seeding in main.ts.
    homepageReady: null as { resolve: () => void; promise: Promise<void> } | null,
    // Flag for update mode: prevents crawler from shutting down while Phase 2 is still seeding URLs.
    // Defaults to true (standard mode has no Phase 2). Set to false before Phase 2, true when done.
    phase2SeedingComplete: true
};