import { createClient, RedisClientType } from 'redis';

export class DedupManager {
    private redis: RedisClientType;
    private key: string;
    private ttl: number;
    private ttlSet: boolean = false;

    constructor(redisUrl: string, crawlId: string, ttlSeconds: number = 7 * 24 * 3600) {
        this.redis = createClient({ url: redisUrl });
        this.redis.on('error', (err) => console.error('Redis Dedup Error:', err));
        this.key = `dedup:${crawlId}`;
        this.ttl = ttlSeconds;
    }

    async connect() {
        await this.redis.connect();
    }

    async disconnect() {
        if (this.redis.isOpen) {
            await this.redis.disconnect();
        }
    }

    private async ensureTtl() {
        if (!this.ttlSet) {
            await this.redis.expire(this.key, this.ttl);
            this.ttlSet = true;
        }
    }

    async addUrl(url: string): Promise<boolean> {
        try {
            const isNew = await this.redis.sAdd(this.key, url);
            await this.ensureTtl();
            return isNew === 1; // 1 if added, 0 if existed
        } catch (e) {
            console.error(`Dedup Add Error: ${e}`);
            return true; // Default to true (process it) on error to be safe
        }
    }

    async isKnown(url: string): Promise<boolean> {
        try {
            return await this.redis.sIsMember(this.key, url);
        } catch (e) {
            return false;
        }
    }

    /**
     * Batch-checks multiple URLs against the deduplication set in a single Redis round-trip.
     * Uses SMISMEMBER for O(N) efficiency instead of N individual SISMEMBER calls.
     *
     * @param urls - Array of URLs to check
     * @returns Set of URLs that are already known (exist in Redis)
     */
    async isKnownBatch(urls: string[]): Promise<Set<string>> {
        const knownSet = new Set<string>();
        if (urls.length === 0) return knownSet;

        try {
            // SMISMEMBER returns an array of 0/1 for each member
            const results = await this.redis.smIsMember(this.key, urls);
            for (let i = 0; i < urls.length; i++) {
                if (results[i]) {
                    knownSet.add(urls[i]);
                }
            }
        } catch (e) {
            console.error(`Dedup Batch Check Error: ${e}`);
            // On error, return empty set (process all URLs to be safe)
        }

        return knownSet;
    }

    /**
     * Returns the number of items currently in the deduplication set.
     */
    async getCount(): Promise<number> {
        try {
            return await this.redis.sCard(this.key);
        } catch (e) {
            console.error(`Dedup Count Error: ${e}`);
            return 0;
        }
    }

    /**
     * @deprecated Use getAllUrlsIterator() for memory-efficient streaming.
     * This method loads ALL URLs into memory at once, causing OOM on large sets.
     */
    async getAllUrls(): Promise<string[]> {
        try {
            return await this.redis.sMembers(this.key);
        } catch (e) {
            console.error(`Dedup Get All Error: ${e}`);
            return [];
        }
    }

    /**
     * Memory-efficient iterator using Redis SSCAN.
     * Yields URLs in batches without loading entire set into memory.
     */
    async *getAllUrlsIterator(): AsyncGenerator<string> {
        try {
            let cursor = 0;
            do {
                const result = await this.redis.sScan(this.key, cursor, { COUNT: 1000 });
                cursor = result.cursor;
                for (const member of result.members) {
                    yield member;
                }
            } while (cursor !== 0);
        } catch (e) {
            console.error(`Dedup Scan Error: ${e}`);
        }
    }

    /**
     * @deprecated Use loadFromIterator() for OOM-safe streaming loading.
     */
    async loadFromList(urls: string[]) {
        if (!urls.length) return;
        
        // Chunking to avoid blocking Redis with huge payloads
        const chunkSize = 1000;
        for (let i = 0; i < urls.length; i += chunkSize) {
            const chunk = urls.slice(i, i + chunkSize);
            if (chunk.length > 0) {
                await this.redis.sAdd(this.key, chunk);
            }
        }
        await this.ensureTtl();
        console.log(`Loaded ${urls.length} URLs into deduplication set.`);
    }

    /**
     * OOM-safe streaming loader using async iterator.
     * Buffers URLs and flushes to Redis in batches of 1000.
     */
    async loadFromIterator(urlIterator: AsyncGenerator<string>): Promise<number> {
        const chunkSize = 1000;
        let buffer: string[] = [];
        let totalCount = 0;

        for await (const url of urlIterator) {
            buffer.push(url);
            totalCount++;

            if (buffer.length >= chunkSize) {
                await this.redis.sAdd(this.key, buffer);
                buffer = [];
            }
        }

        // Flush remaining buffer
        if (buffer.length > 0) {
            await this.redis.sAdd(this.key, buffer);
        }

        await this.ensureTtl();
        console.log(`Loaded ${totalCount} URLs into deduplication set (streaming).`);
        return totalCount;
    }

    async cleanup() {
        try {
            await this.redis.del(this.key);
            await this.disconnect();
            console.log(`Cleaned up deduplication set for ${this.key}`);
        } catch (e) {
            console.error(`Dedup Cleanup Error: ${e}`);
        }
    }
}