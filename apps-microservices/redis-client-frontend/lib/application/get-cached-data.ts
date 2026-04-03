// Application layer: Use case for retrieving cached data
// W4: removed "use server" — this is a data-fetching function, not a server action

import { cacheRepository } from "@/lib/infrastructure/redis-cache-repository"
import type { CacheEntry, CacheMetadata } from "@/lib/domain/cache-entry"

export async function getCachedData(): Promise<{
  entries: CacheEntry[]
  metadata: CacheMetadata
  error?: string
}> {
  try {
    const keys = await cacheRepository.getAllKeys()

    // C1: fetch all entries in parallel instead of sequential N+1 round-trips
    const entryResults = await Promise.all(
      keys.map(async (key) => {
        const [value, size, ttl] = await Promise.all([
          cacheRepository.getEntry(key),
          cacheRepository.getSize(key),
          cacheRepository.getTTL(key),
        ])
        return { key, value, size, ttl }
      })
    )

    const entries: CacheEntry[] = []
    let totalSize = 0

    for (const { key, value, size, ttl } of entryResults) {
      if (value !== null) {
        entries.push({
          key,
          value,
          size,
          fetchedAt: new Date(),
          ttl: ttl && ttl > 0 ? ttl : undefined,
        })
        totalSize += size
      }
    }

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
    console.error("[redis-client] Error in getCachedData:", error)
    return {
      entries: [],
      metadata: { totalKeys: 0, totalSize: 0, lastRefreshed: new Date() },
      error: "Failed to retrieve cache data",
    }
  }
}
