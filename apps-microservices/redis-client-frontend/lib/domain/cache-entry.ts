// Domain entity for cache entries
export interface CacheEntry {
  key: string
  value: string
  size: number
  createdAt: Date
  expiresAt?: Date
  ttl?: number
}

export interface CacheMetadata {
  totalKeys: number
  totalSize: number
  lastRefreshed: Date
}
