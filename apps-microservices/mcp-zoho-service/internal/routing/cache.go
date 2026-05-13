package routing

import (
	"sync"
	"time"
)

// Resolution is the cached result of mapping a caller email to an upstream.
type Resolution struct {
	UpstreamURL string
	Headers     map[string]string
}

// cache is a small TTL map keyed by lowercased email.
type cache struct {
	mu      sync.RWMutex
	ttl     time.Duration
	entries map[string]cacheEntry
}

type cacheEntry struct {
	value     *Resolution
	expiresAt time.Time
}

func newCache(ttl time.Duration) *cache {
	return &cache{
		ttl:     ttl,
		entries: make(map[string]cacheEntry),
	}
}

func (c *cache) get(key string) (*Resolution, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	e, ok := c.entries[key]
	if !ok || time.Now().After(e.expiresAt) {
		return nil, false
	}
	return e.value, true
}

func (c *cache) set(key string, value *Resolution) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.entries[key] = cacheEntry{value: value, expiresAt: time.Now().Add(c.ttl)}
}
