import { DedupManager } from "./class/DedupManager.js";
import { StatsManager } from "./class/StatsManager.js";
import { PlaywrightCrawler } from "crawlee";

export const context = {
    dedupManager: null as DedupManager | null,
    statsManager: null as StatsManager | null,
    crawlerInstance: null as PlaywrightCrawler | null,
    config: {
        maxErrors: 0,
        maxRedirects: 0,
        maxNewUrls: 0,
        domain: "",
        baseUrl: "",
        crawleeStorageName: "",
        // Filtering Options
        skipQuestionMark: false,
        skipDiez: false,
        bypassQuestionMark: false,
        bypassDiez: false,
        toKeep: [] as string[],
        toRemove: [] as string[],
        breakLimit: false
    },
    stopReason: ""
};