import type { RedisClientType } from 'redis';
import type { RedisHealthMonitor } from './RedisHealthMonitor.js';

/**
 * Per-crawl Redis-backed claim set guarding non-idempotent dataset writes.
 *
 * Semantic difference from DedupManager:
 *   - DedupManager.addUrl: "URL has been seen by the crawler" — claim BEFORE
 *     rendering. Used to deduplicate the crawl's link graph.
 *   - PushedSet.tryClaim:  "this URL's row has been written to a dataset" —
 *     claim BEFORE pushData. Used so retry/restart cannot duplicate rows.
 *
 * Fail-open posture: a Redis error during tryClaim returns true (proceed with
 * write). Mirrors DedupManager.addUrl. Trade: a Redis loss may cause a small
 * number of duplicate rows; safer than blocking writes outright.
 */
export interface PushedSetOptions {
    /** Redis TTL on the set key. Default 86400 (24 h). */
    ttlSeconds?: number;
    /** Optional health monitor receiving onSuccess('pushed') / onError('pushed', e). */
    monitor?: RedisHealthMonitor;
}

export class PushedSet {
    private redis: RedisClientType;
    private monitor?: RedisHealthMonitor;
    private key: string;
    private ttlSeconds: number;
    private ttlSetAt: number = 0;

    constructor(
        redisClient: RedisClientType,
        crawlId: string,
        opts?: PushedSetOptions,
    ) {
        this.redis = redisClient;
        this.key = `pushed:${crawlId}`;
        this.ttlSeconds = opts?.ttlSeconds ?? 86400;
        this.monitor = opts?.monitor;
    }

    /**
     * Atomically claim the URL slot for a single dataset write.
     *
     * @returns true  — caller wins the claim. MUST proceed with the write.
     * @returns false — another attempt has already claimed. MUST skip the write.
     *
     * Fail-open: returns true if Redis SADD throws (mirrors
     * DedupManager.addUrl). Logs the error and notifies the monitor.
     */
    async tryClaim(url: string): Promise<boolean> {
        try {
            const isNew = await this.redis.sAdd(this.key, url);
            await this.ensureTtl();
            this.monitor?.onSuccess('pushed');
            return isNew === 1;
        } catch (e) {
            this.monitor?.onError('pushed', e);
            console.error(`PushedSet tryClaim error: ${e}`);
            return true;
        }
    }

    /**
     * Remove URL from the claim set. Used only on explicit rollback paths;
     * not called by default. Claim-before-write semantics treat a failed
     * pushData as accepted residual data loss for that URL.
     */
    async release(url: string): Promise<void> {
        try {
            await this.redis.sRem(this.key, url);
            this.monitor?.onSuccess('pushed');
        } catch (e) {
            this.monitor?.onError('pushed', e);
            console.error(`PushedSet release error: ${e}`);
        }
    }

    /**
     * Delete the entire claim set. Called from main.ts gracefulShutdown
     * alongside DedupManager.cleanup and StatsManager.cleanup. A 24 h
     * TTL safety net evicts orphans if cleanup is skipped (hard crash).
     */
    async cleanup(): Promise<void> {
        try {
            await this.redis.del(this.key);
            this.monitor?.onSuccess('pushed');
            console.log(`Cleaned up pushed set for ${this.key}`);
        } catch (e) {
            this.monitor?.onError('pushed', e);
            console.error(`PushedSet cleanup error: ${e}`);
        }
    }

    /**
     * Rate-limited EXPIRE. Fires at most once per ttlSeconds/2 window so a
     * crawl producing thousands of pushData calls does not hammer Redis with
     * redundant EXPIRE commands.
     */
    private async ensureTtl(): Promise<void> {
        const now = Date.now();
        const halfWindowMs = (this.ttlSeconds * 1000) / 2;
        if (now - this.ttlSetAt < halfWindowMs) return;
        try {
            await this.redis.expire(this.key, this.ttlSeconds);
            this.ttlSetAt = now;
        } catch (e) {
            console.warn(`PushedSet TTL set failed: ${e}`);
        }
    }
}
