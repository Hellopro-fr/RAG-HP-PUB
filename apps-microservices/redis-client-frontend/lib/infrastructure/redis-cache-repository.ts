// Infrastructure layer: Redis repository
import { createClient, type RedisClientType } from "redis"

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

  // C2: use SCAN instead of KEYS * to avoid blocking the Redis event loop
  async getAllKeys(): Promise<string[]> {
    try {
      const client = await this.getClient()
      const keys: string[] = []
      let cursor = 0

      do {
        const result = await client.scan(cursor, { COUNT: 100 })
        cursor = result.cursor
        keys.push(...result.keys)
      } while (cursor !== 0)

      return keys
    } catch (error) {
      console.error("[redis-client] Error fetching keys:", error)
      throw new Error("Could not fetch keys from Redis.")
    }
  }

  async getEntry(key: string): Promise<string | null> {
    try {
      const client = await this.getClient()
      return await client.get(key)
    } catch (error) {
      console.error(`[redis-client] Error fetching entry for key "${key}":`, error)
      return null
    }
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

  async getSize(key: string): Promise<number> {
    try {
      const client = await this.getClient()
      const size = await client.memoryUsage(key)
      return size || 0
    } catch (error) {
      console.warn(`[redis-client] Could not get memory usage for key "${key}", falling back to string length. Error:`, error)
      try {
        const value = await this.getEntry(key)
        return value ? new Blob([value]).size : 0
      } catch (fallbackError) {
        console.error(`[redis-client] Error getting size with fallback for key "${key}":`, fallbackError)
        return 0
      }
    }
  }

  async getTTL(key: string): Promise<number | null> {
    try {
      const client = await this.getClient()
      const ttl = await client.ttl(key)
      return ttl > 0 ? ttl : null
    } catch (error) {
      console.error(`[redis-client] Error getting TTL for key "${key}":`, error)
      return null
    }
  }
}

export const cacheRepository = new RedisCacheRepository()
