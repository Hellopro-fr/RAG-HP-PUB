package orchestrator

import (
	"crypto/sha256"
	"encoding/hex"
	"sync"
	"time"
)

// EmbeddingCacheEntry holds a cached embedding vector with expiration.
type EmbeddingCacheEntry struct {
	vector    []float32
	expiresAt time.Time
}

// EmbeddingCache is a thread-safe LRU-like cache for embedding vectors.
type EmbeddingCache struct {
	mu      sync.RWMutex
	entries map[string]*EmbeddingCacheEntry
	maxSize int
	ttl     time.Duration
}

// NewEmbeddingCache creates a new cache with the given max size and TTL.
func NewEmbeddingCache(maxSize int, ttl time.Duration) *EmbeddingCache {
	return &EmbeddingCache{
		entries: make(map[string]*EmbeddingCacheEntry, maxSize),
		maxSize: maxSize,
		ttl:     ttl,
	}
}

// Get returns the cached embedding for the given text, or nil if not found/expired.
func (c *EmbeddingCache) Get(text string) []float32 {
	key := hashKey(text)

	c.mu.RLock()
	entry, ok := c.entries[key]
	c.mu.RUnlock()

	if !ok {
		return nil
	}
	if time.Now().After(entry.expiresAt) {
		c.mu.Lock()
		delete(c.entries, key)
		c.mu.Unlock()
		return nil
	}

	return entry.vector
}

// Set stores an embedding vector for the given text.
func (c *EmbeddingCache) Set(text string, vector []float32) {
	key := hashKey(text)

	c.mu.Lock()
	defer c.mu.Unlock()

	// Evict oldest entries if at capacity
	if len(c.entries) >= c.maxSize {
		c.evictExpired()
		// If still at capacity after evicting expired, remove one arbitrary entry
		if len(c.entries) >= c.maxSize {
			for k := range c.entries {
				delete(c.entries, k)
				break
			}
		}
	}

	c.entries[key] = &EmbeddingCacheEntry{
		vector:    vector,
		expiresAt: time.Now().Add(c.ttl),
	}
}

// Size returns the current number of cached entries.
func (c *EmbeddingCache) Size() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return len(c.entries)
}

func (c *EmbeddingCache) evictExpired() {
	now := time.Now()
	for k, entry := range c.entries {
		if now.After(entry.expiresAt) {
			delete(c.entries, k)
		}
	}
}

func hashKey(text string) string {
	h := sha256.Sum256([]byte(text))
	return hex.EncodeToString(h[:])
}
