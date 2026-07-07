import { createClient, RedisClientType } from 'redis';
import fs from 'fs';
import path from 'path';

/**
 * Represents a URL tagged with its origin source for priority-based deduplication.
 */
export interface ConsolidatedUrl {
    url: string;
    source: 'dataset' | 'request_queue' | 'request_url';
}

/**
 * Consolidation counts per source after deduplication.
 */
export interface ConsolidationCounts {
    dataset: number;
    requestQueue: number;
    requestUrl: number;
    duplicatesRemoved: number;
}

/**
 * UrlConsolidator — Loads URLs from 3 sources and deduplicates with strict priority.
 *
 * Priority Order (highest first):
 *   1. Dataset — URLs found here belong exclusively to Dataset
 *   2. Request_queue — Deduplicated against Dataset
 *   3. Request_url — Deduplicated against Dataset AND Request_queue
 *
 * Uses Redis SETs for OOM-safe lookups (no in-memory Set<string>).
 * The Dataset SET persists for the lifetime of the crawl so that
 * UpdateChecker can call isInDataset() during page processing.
 */
export class UrlConsolidator {
    private redis: RedisClientType;
    private datasetKey: string;
    private requestQueueKey: string;
    private requestUrlKey: string;
    private ttl: number;
    private ttlSet: boolean = false;
    private ownsClient: boolean;

    private previousCrawlId: string;
    private domain: string;

    constructor(
        clientOrUrl: RedisClientType | string,
        crawlId: string,
        previousCrawlId: string,
        domain: string,
        ttlSeconds: number = 7 * 24 * 3600
    ) {
        this.datasetKey = `update_dataset:${crawlId}`;
        this.requestQueueKey = `update_rq:${crawlId}`;
        this.requestUrlKey = `update_ru:${crawlId}`;
        this.previousCrawlId = previousCrawlId;
        this.domain = domain;
        this.ttl = ttlSeconds;

        if (typeof clientOrUrl === 'string') {
            // Backward-compatible URL form — UrlConsolidator creates + owns the client.
            this.redis = createClient({ url: clientOrUrl });
            this.ownsClient = true;
            this.redis.on('error', (err: Error) => console.error('Redis UrlConsolidator Error:', err));
        } else {
            // Injected shared client — owner manages connect/disconnect + the 'error' listener.
            this.redis = clientOrUrl;
            this.ownsClient = false;
        }
    }

    async connect(): Promise<void> {
        if (!this.ownsClient) return;   // shared client connected by owner
        if (!this.redis.isOpen) {
            await this.redis.connect();
        }
    }

    async disconnect(): Promise<void> {
        if (!this.ownsClient) return;   // shared client closed by owner
        if (this.redis.isOpen) {
            await this.redis.disconnect();
        }
    }

    private async ensureTtl(): Promise<void> {
        if (this.ttlSet) return;
        this.ttlSet = true; // Set immediately to prevent concurrent calls
        try {
            await this.redis.expire(this.datasetKey, this.ttl);
            await this.redis.expire(this.requestQueueKey, this.ttl);
            await this.redis.expire(this.requestUrlKey, this.ttl);
        } catch (e) {
            this.ttlSet = false; // Reset on failure so it retries
            console.warn(`Failed to set TTL: ${e}`);
        }
    }

    /**
     * Check if a URL belongs to the Dataset source (O(1) via Redis SISMEMBER).
     * Used by UpdateChecker during page processing.
     */
    async isInDataset(url: string): Promise<boolean> {
        try {
            return await this.redis.sIsMember(this.datasetKey, url);
        } catch (e) {
            console.error(`UrlConsolidator isInDataset Error: ${e}`);
            return false;
        }
    }

    /**
     * Main consolidation method. Loads all 3 sources, deduplicates by priority,
     * and returns a streaming iterator of ConsolidatedUrl objects.
     *
     * Phase 1: Load Dataset URLs → Redis SET `update_dataset:{crawlId}`
     * Phase 2: Load Request_queue URLs → filter against Dataset SET
     * Phase 3: Load Request_url URLs → filter against Dataset SET + Request_queue SET
     */
    async consolidate(
        datasetUrlsGenerator: AsyncGenerator<string>,
        requestUrlsGenerator: AsyncGenerator<string>,
        cleanUrlFn?: (url: string) => string
    ): Promise<{
        datasetKey: string;
        allUrls: AsyncGenerator<ConsolidatedUrl>;
        counts: ConsolidationCounts;
    }> {
        const counts: ConsolidationCounts = {
            dataset: 0,
            requestQueue: 0,
            requestUrl: 0,
            duplicatesRemoved: 0,
        };

        // ── Phase 1: Load Dataset URLs into Redis SET ──
        console.log(`[UrlConsolidator] Phase 1: Loading Dataset URLs...`);
        const datasetBuffer: string[] = [];
        const CHUNK_SIZE = 1000;

        for await (const rawUrl of datasetUrlsGenerator) {
            const url = cleanUrlFn ? cleanUrlFn(rawUrl) : rawUrl;
            datasetBuffer.push(url);

            if (datasetBuffer.length >= CHUNK_SIZE) {
                await this.redis.sAdd(this.datasetKey, datasetBuffer);
                datasetBuffer.length = 0; // Clear buffer efficiently
            }
            counts.dataset++;
        }
        // Flush remaining
        if (datasetBuffer.length > 0) {
            await this.redis.sAdd(this.datasetKey, datasetBuffer);
        }
        await this.ensureTtl();
        console.log(`[UrlConsolidator] Phase 1 complete: ${counts.dataset} Dataset URLs loaded.`);

        // ── Phase 2: Load Request Queue URLs, deduplicate against Dataset ──
        console.log(`[UrlConsolidator] Phase 2: Loading Request Queue URLs...`);
        const rqUrls = this.loadRequestQueueUrls();
        const rqBuffer: string[] = [];

        for await (const rawUrl of rqUrls) {
            const url = cleanUrlFn ? cleanUrlFn(rawUrl) : rawUrl;
            // Check if already in Dataset SET
            const inDataset = await this.redis.sIsMember(this.datasetKey, url);
            if (inDataset) {
                counts.duplicatesRemoved++;
                continue;
            }
            // Check if already seen in this Request Queue batch
            const isNew = await this.redis.sAdd(this.requestQueueKey, url);
            if (isNew === 0) {
                counts.duplicatesRemoved++;
                continue;
            }
            counts.requestQueue++;
        }
        await this.ensureTtl();
        console.log(`[UrlConsolidator] Phase 2 complete: ${counts.requestQueue} Request Queue URLs (${counts.duplicatesRemoved} duplicates removed so far).`);

        // ── Phase 3: Load Request URL history, deduplicate against Dataset + RQ ──
        console.log(`[UrlConsolidator] Phase 3: Loading Request URL history...`);
        let phase3Dupes = 0;

        for await (const rawUrl of requestUrlsGenerator) {
            const url = cleanUrlFn ? cleanUrlFn(rawUrl) : rawUrl;
            // Check if in Dataset
            const inDataset = await this.redis.sIsMember(this.datasetKey, url);
            if (inDataset) {
                phase3Dupes++;
                continue;
            }
            // Check if in Request Queue
            const inRq = await this.redis.sIsMember(this.requestQueueKey, url);
            if (inRq) {
                phase3Dupes++;
                continue;
            }
            // Store in Redis SET so buildAllUrlsIterator can yield them
            await this.redis.sAdd(this.requestUrlKey, url);
            counts.requestUrl++;
        }
        counts.duplicatesRemoved += phase3Dupes;
        console.log(`[UrlConsolidator] Phase 3 complete: ${counts.requestUrl} Request URL URLs (${phase3Dupes} duplicates removed).`);

        // ── Build final consolidated iterator ──
        const self = this;
        async function* buildAllUrlsIterator(): AsyncGenerator<ConsolidatedUrl> {
            // Yield Dataset URLs first (already in Redis SET, scan them)
            let cursor = 0;
            do {
                const result = await self.redis.sScan(self.datasetKey, cursor, { COUNT: 200 });
                cursor = result.cursor;
                for (const url of result.members) {
                    yield { url, source: 'dataset' };
                }
            } while (cursor !== 0);

            // Yield Request Queue URLs (scan the RQ SET)
            cursor = 0;
            do {
                const result = await self.redis.sScan(self.requestQueueKey, cursor, { COUNT: 200 });
                cursor = result.cursor;
                for (const url of result.members) {
                    yield { url, source: 'request_queue' };
                }
            } while (cursor !== 0);

            // Yield Request URL URLs (scan the RU SET)
            cursor = 0;
            do {
                const result = await self.redis.sScan(self.requestUrlKey, cursor, { COUNT: 200 });
                cursor = result.cursor;
                for (const url of result.members) {
                    yield { url, source: 'request_url' };
                }
            } while (cursor !== 0);
        }

        console.log(`\n[UrlConsolidator] ═══════════════════════════════════════`);
        console.log(`[UrlConsolidator] Consolidation Summary:`);
        console.log(`[UrlConsolidator]   Dataset:        ${counts.dataset}`);
        console.log(`[UrlConsolidator]   Request Queue:  ${counts.requestQueue}`);
        console.log(`[UrlConsolidator]   Request URL:    ${counts.requestUrl}`);
        console.log(`[UrlConsolidator]   Duplicates:     ${counts.duplicatesRemoved}`);
        console.log(`[UrlConsolidator]   Total Unique:   ${counts.dataset + counts.requestQueue + counts.requestUrl}`);
        console.log(`[UrlConsolidator] ═══════════════════════════════════════\n`);

        return {
            datasetKey: this.datasetKey,
            allUrls: buildAllUrlsIterator(),
            counts,
        };
    }

    /**
     * Scan request queue files from a previous crawl's storage.
     * Extracts both the original `url` and the `loadedUrl` (redirect target) from each entry.
     */
    private async *loadRequestQueueUrls(): AsyncGenerator<string> {
        // CWD is the current job's storage path (e.g., /app/storage/{currentCrawlId})
        // Previous crawl is at ../{previousCrawlId}/
        const previousJobPath = path.resolve('..', this.previousCrawlId);
        const sanitizedDomain = this.domain.replace(/\./g, '-');

        // Try both original domain and sanitized name
        const possiblePaths = [
            path.join(previousJobPath, 'storage', 'request_queues', this.domain),
            path.join(previousJobPath, 'storage', 'request_queues', sanitizedDomain),
        ];

        let queuePath: string | null = null;
        for (const p of possiblePaths) {
            if (fs.existsSync(p)) {
                queuePath = p;
                break;
            }
        }

        if (!queuePath) {
            console.warn(`[UrlConsolidator] Request queue not found for previous crawl.`);
            return;
        }

        console.log(`[UrlConsolidator] Reading request queue from: ${queuePath}`);

        try {
            const files = await fs.promises.readdir(queuePath);
            for (const file of files) {
                if (!file.endsWith('.json') || file.startsWith('__')) continue;

                try {
                    const filePath = path.join(queuePath, file);
                    const content = await fs.promises.readFile(filePath, 'utf-8');
                    const data = JSON.parse(content);

                    // Extract the URL from the queue entry
                    if (data.url) {
                        yield data.url;
                    }

                    // Also extract the loadedUrl (redirect destination) from the inner JSON
                    // The `json` field contains a stringified JSON with additional data
                    if (data.json) {
                        try {
                            const innerData = JSON.parse(data.json);
                            if (innerData.loadedUrl && innerData.loadedUrl !== data.url) {
                                yield innerData.loadedUrl;
                            }
                        } catch {
                            // Inner JSON parse failed, skip
                        }
                    }
                } catch (e) {
                    // Skip corrupted files
                    console.warn(`[UrlConsolidator] Error reading queue file ${file}: ${e}`);
                }
            }
        } catch (e) {
            console.error(`[UrlConsolidator] Error iterating request queue directory: ${e}`);
        }
    }

    /**
     * Cleanup Redis keys. Call during graceful shutdown.
     * Note: datasetKey is NOT cleaned here because UpdateChecker needs it during the crawl.
     * It will expire via TTL.
     */
    async cleanup(): Promise<void> {
        try {
            await this.redis.del(this.requestQueueKey);
            await this.redis.del(this.requestUrlKey);
            // datasetKey is intentionally kept alive for UpdateChecker.isInDataset()
            // It will auto-expire via TTL
            await this.disconnect();
            console.log(`[UrlConsolidator] Cleaned up temporary Redis keys.`);
        } catch (e) {
            console.error(`[UrlConsolidator] Cleanup Error: ${e}`);
        }
    }

    /**
     * Full cleanup including the dataset key. Call only at final shutdown.
     */
    async fullCleanup(): Promise<void> {
        try {
            await this.redis.del(this.datasetKey);
            await this.redis.del(this.requestQueueKey);
            await this.redis.del(this.requestUrlKey);
            await this.disconnect();
            console.log(`[UrlConsolidator] Full cleanup complete.`);
        } catch (e) {
            console.error(`[UrlConsolidator] Full Cleanup Error: ${e}`);
        }
    }
}
