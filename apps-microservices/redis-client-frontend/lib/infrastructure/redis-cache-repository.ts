// Infrastructure layer: Redis repository
import { createClient, type RedisClientType } from "redis"
import type { KeyMeta } from "@/lib/domain/cache-entry"

// Singleton pattern with connection-promise guard to prevent race conditions (W1)
let redisClient: RedisClientType | null = null
let connectingPromise: Promise<RedisClientType> | null = null

async function getRedisClient(): Promise<RedisClientType> {
  if (redisClient && redisClient.isOpen) {
    return redisClient
  }

  // Guard: if a connection attempt is already in flight, await it instead of creating a second one
  if (connectingPromise) {
    return connectingPromise
  }

  const host = process.env.REDIS_HOST
  const port = process.env.REDIS_PORT
  const password = process.env.REDIS_SECRET

  if (!host || !port || !password) {
    throw new Error("Redis connection details (HOST, PORT, PASSWORD) are not configured in environment variables.")
  }

  // W5: pass password as a separate config field to avoid URL-encoding issues
  connectingPromise = (async () => {
    const client = createClient({
      socket: { host, port: Number(port) },
      password,
    })

    client.on("error", (err: Error) => console.error("[redis-client] Redis Client Background Error:", err))

    try {
      await client.connect()
    } catch (err) {
      console.error("[redis-client] FAILED TO CONNECT TO REDIS:", err)
      redisClient = null
      connectingPromise = null
      throw err
    }

    redisClient = client as RedisClientType
    connectingPromise = null
    return redisClient
  })()

  return connectingPromise
}

export class RedisCacheRepository {
  private async getClient(): Promise<RedisClientType> {
    return getRedisClient()
  }

  // Single SCAN step (page). cursor 0 starts iteration; returned nextCursor 0 = complete.
  async scanKeys(cursor: number, match: string, count = 100): Promise<{ keys: string[]; nextCursor: number }> {
    const client = await this.getClient()
    const result = await client.scan(cursor, { MATCH: match || "*", COUNT: count })
    return { keys: result.keys, nextCursor: result.cursor }
  }

  // Per-key metadata WITHOUT reading the value (no GET). Each command degrades independently.
  async getKeyMeta(key: string): Promise<KeyMeta> {
    const client = await this.getClient()
    const [type, ttl, size] = await Promise.all([
      client.type(key).catch(() => "unknown"),
      client.ttl(key).catch(() => -1),
      client.memoryUsage(key).catch(() => 0),
    ])
    return {
      key,
      type: type || "unknown",
      ttl: ttl > 0 ? ttl : undefined,
      size: size || 0,
    }
  }

  async dbSize(): Promise<number> {
    const client = await this.getClient()
    return client.dbSize()
  }

  async deleteEntry(key: string): Promise<boolean> {
    try {
      const client = await this.getClient()
      const result = await client.del(key)
      return result > 0
    } catch (error) {
      console.error(`[redis-client] Error deleting entry for key "${key}":`, error)
      return false
    }
  }

  async clearAll(): Promise<boolean> {
    try {
      const client = await this.getClient()
      await client.flushDb()
      return true
    } catch (error) {
      console.error("[redis-client] Error clearing cache:", error)
      return false
    }
  }
}

export const cacheRepository = new RedisCacheRepository()
