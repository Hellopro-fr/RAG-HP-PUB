import { createClient, RedisClientType } from 'redis';
import fs from 'fs/promises';
import path from 'path';

export class StatsManager {
    private redis: RedisClientType;
    private key: string;
    private statsFile: string;
    private ttl: number;
    private ttlSet: boolean = false;

    constructor(redisUrl: string, crawlId: string, storagePath: string, ttlSeconds: number = 7 * 24 * 3600) {
        this.redis = createClient({ url: redisUrl });
        this.redis.on('error', (err) => console.error('Redis Stats Error:', err));
        this.key = `stats:${crawlId}`;
        this.statsFile = path.join(storagePath, 'update_stats.json');
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
        if (this.ttlSet) return;
        this.ttlSet = true; // Set immediately to prevent concurrent calls
        try {
            await this.redis.expire(this.key, this.ttl);
        } catch (e) {
            this.ttlSet = false; // Reset on failure so it retries
            console.warn(`Failed to set TTL: ${e}`);
        }
    }

    async increment(metric: string, by: number = 1): Promise<number> {
        if (by === 0) return await this.getValue(metric);
        try {
            const val = await this.redis.hIncrBy(this.key, metric, by);
            await this.ensureTtl();
            return val;
        } catch (e) {
            console.error(`Stats Increment Error: ${e}`);
            return 0;
        }
    }

    async getValue(metric: string): Promise<number> {
        try {
            const valStr = await this.redis.hGet(this.key, metric);
            return valStr ? parseInt(valStr, 10) : 0;
        } catch (e) {
            console.error(`Stats GetValue Error: ${e}`);
            return 0;
        }
    }

    async checkThreshold(metric: string, limit: number): Promise<boolean> {
        if (!limit || limit <= 0) return false;
        
        try {
            const val = await this.getValue(metric);
            
            if (val >= limit) {
                console.warn(`THRESHOLD BREACHED: ${metric} (${val}) >= limit (${limit})`);
                return true;
            }
        } catch (e) {
            console.error(`Stats Check Error: ${e}`);
        }
        return false;
    }

    async saveStateToDisk() {
        try {
            const data = await this.redis.hGetAll(this.key);
            await fs.writeFile(this.statsFile, JSON.stringify(data, null, 2));
        } catch (e) {
            console.error(`Failed to save stats to disk: ${e}`);
        }
    }

    async loadStateFromDisk() {
        try {
            await fs.access(this.statsFile);
            const content = await fs.readFile(this.statsFile, 'utf-8');
            const data = JSON.parse(content);
            if (Object.keys(data).length > 0) {
                // Redis HSET accepts object in newer versions, or array
                for (const [k, v] of Object.entries(data)) {
                    await this.redis.hSet(this.key, k, v as string);
                }
                console.log(`Loaded existing stats: ${JSON.stringify(data)}`);
            }
        } catch (e) {
            console.warn(`Failed to load stats from disk (starting from zero): ${e}`);
        }
    }

    async cleanup() {
        try {
            await this.redis.del(this.key);
            await this.disconnect();
            console.log(`Cleaned up stats for ${this.key}`);
        } catch (e) {
            console.error(`Stats Cleanup Error: ${e}`);
        }
    }
}