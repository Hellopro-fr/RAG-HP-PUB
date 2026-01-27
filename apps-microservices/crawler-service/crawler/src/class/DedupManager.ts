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

    async getAllUrls(): Promise<string[]> {
        try {
            return await this.redis.sMembers(this.key);
        } catch (e) {
            console.error(`Dedup Get All Error: ${e}`);
            return [];
        }
    }

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