// Domain entity for cache entries
export interface CacheEntry {
  key: string
  value: string
  size: number
  // W6: renamed from createdAt — Redis has no native creation timestamp,
  // this is the timestamp when the entry was fetched from Redis
  fetchedAt: Date
  expiresAt?: Date
  ttl?: number
}

// S8: reusable metadata interface
export interface CacheMetadata {
  totalKeys: number
  totalSize: number
  lastRefreshed: Date
}
