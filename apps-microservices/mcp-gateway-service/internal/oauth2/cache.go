package oauth2

import (
	"sync"
	"time"
)

// CachedClient holds the resolved scope for an OAuth2 client.
type CachedClient struct {
	ID           string
	Name         string                     // human-readable client name; surfaced as serverInfo.name
	ServerIDs    map[string]bool            // set of allowed server IDs
	AllowedTools map[string]map[string]bool // server_id -> tool_name -> true; nil = all tools
	ExpiresAt    *time.Time
	IsActive     bool
	TTL          int // access token TTL in seconds
	FetchedAt    time.Time

	// Leexi participant scope — mirrors scopetoken.CachedToken. See that struct
	// for the semantics of each mode.
	LeexiFilterMode       string
	LeexiAllowedUserUUIDs []string
	LeexiAllowedTeamUUIDs []string
}

// Cache provides an in-memory TTL cache for OAuth2 client scope lookups.
type Cache struct {
	mu      sync.RWMutex
	entries map[string]*CachedClient // keyed by client_id
	ttl     time.Duration
}

// NewCache creates a cache with the given TTL.
func NewCache(ttl time.Duration) *Cache {
	return &Cache{
		entries: make(map[string]*CachedClient),
		ttl:     ttl,
	}
}

// Get returns a cached client if it exists and hasn't expired from cache.
func (c *Cache) Get(clientID string) (*CachedClient, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	cc, ok := c.entries[clientID]
	if !ok {
		return nil, false
	}
	if time.Since(cc.FetchedAt) > c.ttl {
		return nil, false
	}
	return cc, true
}

// Set stores a client in the cache.
func (c *Cache) Set(clientID string, cc *CachedClient) {
	c.mu.Lock()
	defer c.mu.Unlock()
	cc.FetchedAt = time.Now()
	c.entries[clientID] = cc
}

// Invalidate removes a single entry by client ID.
func (c *Cache) Invalidate(clientID string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.entries, clientID)
}

// InvalidateAll clears the entire cache.
func (c *Cache) InvalidateAll() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.entries = make(map[string]*CachedClient)
}
