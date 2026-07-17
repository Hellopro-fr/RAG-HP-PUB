package scopetoken

import (
	"sync"
	"time"
)

// CachedInstruction is a resolved snapshot of an LLM instruction carried by
// this token. Bodies are held in-memory so `initialize` never triggers an
// extra DB round-trip. Cache TTL (60s) bounds staleness; token/client cache
// is also invalidated explicitly on every instruction edit.
type CachedInstruction struct {
	ID    string
	Title string
	Body  string
}

// CachedToken holds the resolved scope for a token hash.
type CachedToken struct {
	ID           string
	Name         string                     // human-readable token name; surfaced as serverInfo.name
	ServerIDs    map[string]bool            // set of allowed server IDs
	AllowedTools map[string]map[string]bool // server_id → tool_name → true; nil map for a server = all tools
	Instructions []CachedInstruction        // filtered + rendered into initialize.instructions
	ExpiresAt    *time.Time
	IsActive     bool
	FetchedAt    time.Time

	// Leexi participant scope (echoed from the DB row). Resolution from "teams"
	// to user UUIDs is done at request time by the runtime header injector,
	// so team membership changes are reflected without cache invalidation.
	LeexiFilterMode       string   // "none" | "users" | "teams" | "creator"
	LeexiAllowedUserUUIDs []string // for modes "users" and "creator"
	LeexiAllowedTeamUUIDs []string // for mode "teams"

	// Ringover user scope — same semantics as the Leexi fields above, but
	// Ringover identifies users with integer IDs, so the slices hold ints.
	RingoverFilterMode     string // "none" | "users" | "teams" | "creator"
	RingoverAllowedUserIDs []int  // for modes "users" and "creator"
	RingoverAllowedTeamIDs []int  // for mode "teams"

	// BDDAllowedTableIDs holds the bdd_used_tables.id values this token is
	// allowed to surface. Empty slice = no BDD restriction (full access).
	// Resolution to (database_id, table_name) pairs happens at request time
	// in the gateway header injector so deletions propagate immediately.
	BDDAllowedTableIDs []string

	// Zoho ownership scope (echoed from the DB row). See db.ScopeToken.ZohoFilterMode.
	ZohoFilterMode    string   // "none" | "users" | "creator"
	ZohoAllowedEmails []string // for mode "users"
	ZohoCreatorEmail  string   // for mode "creator" — snapshot of CreatedBy at write time
}

// Cache provides an in-memory TTL cache for scope token lookups.
type Cache struct {
	mu      sync.RWMutex
	entries map[string]*CachedToken // keyed by token_hash
	ttl     time.Duration
}

// NewCache creates a cache with the given TTL.
func NewCache(ttl time.Duration) *Cache {
	return &Cache{
		entries: make(map[string]*CachedToken),
		ttl:     ttl,
	}
}

// Get returns a cached token if it exists and hasn't expired from cache.
func (c *Cache) Get(hash string) (*CachedToken, bool) {
	c.mu.RLock()
	defer c.mu.RUnlock()
	ct, ok := c.entries[hash]
	if !ok {
		return nil, false
	}
	if time.Since(ct.FetchedAt) > c.ttl {
		return nil, false
	}
	return ct, true
}

// Set stores a token in the cache.
func (c *Cache) Set(hash string, ct *CachedToken) {
	c.mu.Lock()
	defer c.mu.Unlock()
	ct.FetchedAt = time.Now()
	c.entries[hash] = ct
}

// Invalidate removes a single entry by hash.
func (c *Cache) Invalidate(hash string) {
	c.mu.Lock()
	defer c.mu.Unlock()
	delete(c.entries, hash)
}

// InvalidateAll clears the entire cache.
func (c *Cache) InvalidateAll() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.entries = make(map[string]*CachedToken)
}
