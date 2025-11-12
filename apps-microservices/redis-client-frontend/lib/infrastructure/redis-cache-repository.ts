// Infrastructure layer: Redis repository
import { createClient, type RedisClientType } from "redis"

// Singleton pattern to manage the Redis client connection
let redisClient: RedisClientType | null = null

async function getRedisClient(): Promise<RedisClientType> {
  if (redisClient && redisClient.isOpen) {
    return redisClient
  }

  // Ensure required environment variables are set
  const host = process.env.REDIS_HOST
  const port = process.env.REDIS_PORT
  const password = process.env.REDIS_SECRET

  if (!host || !port || !password) {
    throw new Error("Redis connection details (HOST, PORT, PASSWORD) are not configured in environment variables.")
  }

  const client = createClient({
    url: `redis://:${password}@${host}:${port}`,
  })

  client.on("error", (err) => console.error("[v0] Redis Client Background Error:", err))

  try {
      await client.connect()
  } catch (err) {
      console.error("[v0] FAILED TO CONNECT TO REDIS:", err)
      redisClient = null // Reset client on connection failure to force re-initialization
      throw err // Re-throw the original error
  }
  redisClient = client as RedisClientType
  return redisClient
}

export class RedisCacheRepository {
  private async getClient(): Promise<RedisClientType> {
    return getRedisClient()
  }

  async getAllKeys(): Promise<string[]> {
    try {
      const client = await this.getClient()
      const keys = await client.keys("*")
      return keys
    } catch (error) {
      console.error("[v0] Error fetching keys:", error)
      // Throw a more specific error to be handled by the application layer
      throw new Error("Could not fetch keys from Redis.")
    }
  }

  async getEntry(key: string): Promise<string | null> {
    try {
      const client = await this.getClient()
      return await client.get(key)
    } catch (error) {
      console.error(`[v0] Error fetching entry for key "${key}":`, error)
      return null
    }
  }

  async deleteEntry(key: string): Promise<boolean> {
    try {
      const client = await this.getClient()
      const result = await client.del(key)
      return result > 0
    } catch (error) {
      console.error(`[v0] Error deleting entry for key "${key}":`, error)
      return false
    }
  }

  async clearAll(): Promise<boolean> {
    try {
      const client = await this.getClient()
      await client.flushDb()
      return true
    } catch (error) {
      console.error("[v0] Error clearing cache:", error)
      return false
    }
  }

  async getSize(key: string): Promise<number> {
    try {
      const client = await this.getClient()
      // MEMORY USAGE provides the most accurate size in bytes.
      const size = await client.memoryUsage(key)
      return size || 0
    } catch (error) {
      // Fallback for Redis versions or services where MEMORY USAGE is not available.
      console.warn(`[v0] Could not get memory usage for key "${key}", falling back to string length. Error:`, error)
      try {
        const value = await this.getEntry(key)
        return value ? new Blob([value]).size : 0
      } catch (fallbackError) {
        console.error(`[v0] Error getting size with fallback for key "${key}":`, fallbackError)
        return 0
      }
    }
  }

  async getTTL(key: string): Promise<number | null> {
    try {
      const client = await this.getClient()
      const ttl = await client.ttl(key)
      // node-redis returns -1 for no expiry and -2 if the key doesn't exist.
      return ttl > 0 ? ttl : null
    } catch (error) {
      console.error(`[v0] Error getting TTL for key "${key}":`, error)
      return null
    }
  }
}

export const cacheRepository = new RedisCacheRepository()