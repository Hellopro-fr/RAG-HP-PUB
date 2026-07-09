// Server actions for cache operations
"use server"

import { cacheRepository } from "@/lib/infrastructure/redis-cache-repository"
import type { ScanResult } from "@/lib/application/scan-state"

// S1: validate Redis key format before operations
function isValidKey(key: string): boolean {
  return typeof key === "string" && key.length > 0 && key.length <= 512
}

// Paginated key browse. dbSize (Total Keys) is fetched only on the first page (cursor 0).
export async function listCacheKeys(
  { cursor = 0, match = "" }: { cursor?: number; match?: string } = {},
): Promise<ScanResult> {
  const safeCursor = Number.isFinite(cursor) && cursor > 0 ? Math.floor(cursor) : 0
  const safeMatch = typeof match === "string" && match.length > 0 && match.length <= 512 ? match : "*"
  try {
    const { keys, nextCursor } = await cacheRepository.scanKeys(safeCursor, safeMatch)
    const entries = await Promise.all(keys.map((k) => cacheRepository.getKeyMeta(k)))
    const total = safeCursor === 0 ? await cacheRepository.dbSize() : 0
    return { entries, nextCursor, total }
  } catch (error) {
    console.error("[redis-client] Error listing keys:", error)
    return { entries: [], nextCursor: 0, total: 0, error: "Failed to list cache keys" }
  }
}

export async function invalidateCacheEntry(key: string) {
  if (!isValidKey(key)) {
    return { success: false, message: "Invalid key format" }
  }

  try {
    const success = await cacheRepository.deleteEntry(key)
    return { success, message: success ? "Entry deleted" : "Failed to delete" }
  } catch (error) {
    console.error("[redis-client] Error invalidating entry:", error)
    return { success: false, message: "Error deleting entry" }
  }
}

export async function clearAllCache() {
  try {
    const success = await cacheRepository.clearAll()
    return { success, message: success ? "Cache cleared" : "Failed to clear" }
  } catch (error) {
    console.error("[redis-client] Error clearing cache:", error)
    return { success: false, message: "Error clearing cache" }
  }
}
