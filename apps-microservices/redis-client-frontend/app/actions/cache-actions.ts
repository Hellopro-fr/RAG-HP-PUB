// Server actions for cache operations
"use server"

import { cacheRepository } from "@/lib/infrastructure/redis-cache-repository"
import { revalidatePath } from "next/cache"

export async function invalidateCacheEntry(key: string) {
  try {
    const success = await cacheRepository.deleteEntry(key)
    if (success) {
      revalidatePath("/")
    }
    return { success, message: success ? "Entry deleted" : "Failed to delete" }
  } catch (error) {
    console.error("[v0] Error invalidating entry:", error)
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
    console.error("[v0] Error clearing cache:", error)
    return { success: false, message: "Error clearing cache" }
  }
}

export async function refreshCacheData() {
  try {
    revalidatePath("/")
    return { success: true, message: "Cache refreshed" }
  } catch (error) {
    console.error("[v0] Error refreshing cache:", error)
    return { success: false, message: "Error refreshing cache" }
  }
}
