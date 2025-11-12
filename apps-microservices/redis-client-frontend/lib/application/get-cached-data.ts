// Application layer: Use case for retrieving cached data
"use server"

import { cacheRepository } from "@/lib/infrastructure/redis-cache-repository"
import type { CacheEntry } from "@/lib/domain/cache-entry"

export async function getCachedData(): Promise<{
  entries: CacheEntry[]
  metadata: { totalKeys: number; totalSize: number; lastRefreshed: Date }
  error?: string
}> {
  try {
    const keys = await cacheRepository.getAllKeys()
    const entries: CacheEntry[] = []
    let totalSize = 0

    for (const key of keys) {
      const value = await cacheRepository.getEntry(key)
      const size = await cacheRepository.getSize(key)
      const ttl = await cacheRepository.getTTL(key)

      if (value !== null) {
        entries.push({
          key,
          value,
          size,
          createdAt: new Date(),
          ttl: ttl && ttl > 0 ? ttl : undefined,
        })
        totalSize += size
      }
    }

    // Sort by key name
    entries.sort((a, b) => a.key.localeCompare(b.key))

    return {
      entries,
      metadata: {
        totalKeys: entries.length,
        totalSize,
        lastRefreshed: new Date(),
      },
    }
  } catch (error) {
    console.error("[v0] Specific error in getCachedData:", error)
    return {
      entries: [],
      metadata: { totalKeys: 0, totalSize: 0, lastRefreshed: new Date() },
      error: "Failed to retrieve cache data",
    }
  }
}
