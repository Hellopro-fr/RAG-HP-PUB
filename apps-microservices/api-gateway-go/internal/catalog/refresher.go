package catalog

import (
	"context"
	"log"
	"sync"
	"time"

	auth_pkg "api-gateway-go/internal/auth"
)

// Refresher holds the live service map and auth snapshot, refreshing them periodically from the catalog.
type Refresher struct {
	cli      *Client
	interval time.Duration
	fallback map[string]string
	mu       sync.RWMutex
	routes   map[string]string
	auth     auth_pkg.AuthSnapshot
	source   string // "catalog" | "env"
}

// NewRefresher creates a Refresher with the given client, refresh interval, and env fallback map.
func NewRefresher(cli *Client, interval time.Duration, fallback map[string]string) *Refresher {
	return &Refresher{cli: cli, interval: interval, fallback: fallback}
}

// Bootstrap performs one synchronous fetch with the given dial timeout. On failure or empty
// result it uses the env fallback. Returns (map, source) where source is "catalog" or "env".
func (r *Refresher) Bootstrap(ctx context.Context, dialTimeout time.Duration) (map[string]string, string) {
	bctx, cancel := context.WithTimeout(ctx, dialTimeout)
	defer cancel()
	routes, snap, err := r.cli.BuildMapAndAuthSnapshot(bctx)
	if err != nil || len(routes) == 0 {
		log.Printf("catalog bootstrap: using env fallback (err=%v len=%d)", err, len(routes))
		r.set(r.fallback, auth_pkg.AuthSnapshot{}, "env")
		return r.fallback, "env"
	}
	r.set(routes, snap, "catalog")
	return routes, "catalog"
}

// Run blocks until ctx is cancelled, refreshing the service map every interval.
// On failure the last good map is kept.
func (r *Refresher) Run(ctx context.Context) {
	t := time.NewTicker(r.interval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			rctx, cancel := context.WithTimeout(ctx, 5*time.Second)
			routes, snap, err := r.cli.BuildMapAndAuthSnapshot(rctx)
			cancel()
			if err != nil || len(routes) == 0 {
				log.Printf("catalog refresh failed; keeping last map (err=%v len=%d)", err, len(routes))
				continue
			}
			r.set(routes, snap, "catalog")
		}
	}
}

// Snapshot returns (routes, auth, source).
func (r *Refresher) Snapshot() (map[string]string, auth_pkg.AuthSnapshot, string) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.routes, r.auth, r.source
}

func (r *Refresher) set(routes map[string]string, snap auth_pkg.AuthSnapshot, src string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.routes, r.auth, r.source = routes, snap, src
}
