import { createClient, RedisClientType } from 'redis';
import type { RedisHealthMonitor } from './RedisHealthMonitor.js';

export class DedupManager {
    private redis: RedisClientType;
    private monitor?: RedisHealthMonitor;
    private key: string;
    private ttl: number;
    private ttlSet: boolean = false;
    private blockedKey: string;

    constructor(redisUrl: string, crawlId: string, ttlSeconds: number = 7 * 24 * 3600,
                monitor?: RedisHealthMonitor) {
        this.redis = createClient({ url: redisUrl });
        this.monitor = monitor;
        this.redis.on('error', (err) => {
            console.error('Redis Dedup Error:', err);
            this.monitor?.onError('dedup', err);
        });
        this.key = `dedup:${crawlId}`;
        this.blockedKey = `blocked_log:${crawlId}`;
        this.ttl = ttlSeconds;
    }

    async connect() {
        try {
            await this.redis.connect();
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            throw e;
        }
    }

    async disconnect() {
        if (this.redis.isOpen) {
            await this.redis.disconnect();
        }
    }

    private async ensureTtl() {
        if (this.ttlSet) return;
        this.ttlSet = true;
        try {
            await this.redis.expire(this.key, this.ttl);
            await this.redis.expire(this.blockedKey, this.ttl);
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.ttlSet = false;
            this.monitor?.onError('dedup', e);
            console.warn(`Failed to set TTL: ${e}`);
        }
    }

    async addUrl(url: string): Promise<boolean> {
        try {
            const isNew = await this.redis.sAdd(this.key, url);
            await this.ensureTtl();
            this.monitor?.onSuccess('dedup');
            return isNew === 1;
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Add Error: ${e}`);
            return true;
        }
    }

    async isKnown(url: string): Promise<boolean> {
        try {
            const result = await this.redis.sIsMember(this.key, url);
            this.monitor?.onSuccess('dedup');
            return result;
        } catch (e) {
            this.monitor?.onError('dedup', e);
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
            const results = await this.redis.smIsMember(this.key, urls);
            for (let i = 0; i < urls.length; i++) {
                if (results[i]) knownSet.add(urls[i]);
            }
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Batch Check Error: ${e}`);
        }
        return knownSet;
    }

    /**
     * Filter a batch of blocked URLs returning only those NOT yet logged.
     * Adds the new ones to the blocked set atomically.
     * @param urls Array of blocked URLs to check
     * @returns Array of URLs that should be logged (were new)
     */
    async filterNewBlockedBatch(urls: string[]): Promise<string[]> {
        if (urls.length === 0) return [];
        const uniqueUrls = [...new Set(urls)];
        const newToLog: string[] = [];
        try {
            const results = await this.redis.smIsMember(this.blockedKey, uniqueUrls);
            const toAdd: string[] = [];
            for (let i = 0; i < uniqueUrls.length; i++) {
                if (!results[i]) {
                    newToLog.push(uniqueUrls[i]);
                    toAdd.push(uniqueUrls[i]);
                }
            }
            if (toAdd.length > 0) {
                await this.redis.sAdd(this.blockedKey, toAdd);
                await this.ensureTtl();
            }
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Blocked Log Batch Error: ${e}`);
            return uniqueUrls;
        }
        return newToLog;
    }

    /**
     * Returns the number of items currently in the deduplication set.
     */
    async getCount(): Promise<number> {
        try {
            const c = await this.redis.sCard(this.key);
            this.monitor?.onSuccess('dedup');
            return c;
        } catch (e) {
            this.monitor?.onError('dedup', e);
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
            const r = await this.redis.sMembers(this.key);
            this.monitor?.onSuccess('dedup');
            return r;
        } catch (e) {
            this.monitor?.onError('dedup', e);
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
                const result = await this.redis.sScan(this.key, cursor, { COUNT: 200 });
                cursor = result.cursor;
                for (const member of result.members) yield member;
            } while (cursor !== 0);
            this.monitor?.onSuccess('dedup');
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Scan Error: ${e}`);
        }
    }

    /**
     * @deprecated Use loadFromIterator() for OOM-safe streaming loading.
     */
    async loadFromList(urls: string[]) {
        if (!urls.length) return;
        const chunkSize = 1000;
        for (let i = 0; i < urls.length; i += chunkSize) {
            const chunk = urls.slice(i, i + chunkSize);
            if (chunk.length > 0) {
                try {
                    await this.redis.sAdd(this.key, chunk);
                    this.monitor?.onSuccess('dedup');
                } catch (e) {
                    this.monitor?.onError('dedup', e);
                    throw e;
                }
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
                try {
                    await this.redis.sAdd(this.key, buffer);
                    this.monitor?.onSuccess('dedup');
                } catch (e) {
                    this.monitor?.onError('dedup', e);
                    throw e;
                }
                buffer = [];
            }
        }

        if (buffer.length > 0) {
            try {
                await this.redis.sAdd(this.key, buffer);
                this.monitor?.onSuccess('dedup');
            } catch (e) {
                this.monitor?.onError('dedup', e);
                throw e;
            }
        }

        await this.ensureTtl();
        console.log(`Loaded ${totalCount} URLs into deduplication set (streaming).`);
        return totalCount;
    }

    async cleanup() {
        try {
            await this.redis.del(this.key);
            await this.redis.del(this.blockedKey);
            await this.disconnect();
            this.monitor?.onSuccess('dedup');
            console.log(`Cleaned up deduplication set for ${this.key}`);
        } catch (e) {
            this.monitor?.onError('dedup', e);
            console.error(`Dedup Cleanup Error: ${e}`);
        }
    }
}
