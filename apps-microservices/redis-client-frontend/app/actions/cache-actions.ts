// Server actions for cache operations
"use server"

import { cacheRepository } from "@/lib/infrastructure/redis-cache-repository"
import { revalidatePath } from "next/cache"

// S1: validate Redis key format before operations
function isValidKey(key: string): boolean {
  return typeof key === "string" && key.length > 0 && key.length <= 512
}

export async function invalidateCacheEntry(key: string) {
  if (!isValidKey(key)) {
    return { success: false, message: "Invalid key format" }
  }

  try {
    const success = await cacheRepository.deleteEntry(key)
    if (success) {
      revalidatePath("/")
    }
    return { success, message: success ? "Entry deleted" : "Failed to delete" }
  } catch (error) {
    console.error("[redis-client] Error invalidating entry:", error)
    return { success: false, message: "Error deleting entry" }
  }
}

export async function clearAllCache() {
  try {
    const success = await cacheRepository.clearAll()
    if (success) {
      revalidatePath("/")
    }
    return { success, message: success ? "Cache cleared" : "Failed to clear" }
  } catch (error) {
    console.error("[redis-client] Error clearing cache:", error)
    return { success: false, message: "Error clearing cache" }
  }
}

export async function refreshCacheData() {
  try {
    revalidatePath("/")
    return { success: true, message: "Cache refreshed" }
  } catch (error) {
    console.error("[redis-client] Error refreshing cache:", error)
    return { success: false, message: "Error refreshing cache" }
  }
}
