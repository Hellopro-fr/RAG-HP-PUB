package catalog

import (
	"context"
	"log"
	"sync"
	"time"
)

// Refresher holds the live service map and refreshes it periodically from the catalog.
type Refresher struct {
	cli      *Client
	interval time.Duration
	fallback map[string]string
	mu       sync.RWMutex
	current  map[string]string
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
	m, err := r.cli.BuildMap(bctx)
	if err != nil || len(m) == 0 {
		log.Printf("catalog bootstrap: using env fallback (err=%v len=%d)", err, len(m))
		r.set(r.fallback, "env")
		return r.fallback, "env"
	}
	r.set(m, "catalog")
	return m, "catalog"
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
			m, err := r.cli.BuildMap(rctx)
			cancel()
			if err != nil || len(m) == 0 {
				log.Printf("catalog refresh failed; keeping last map (err=%v len=%d)", err, len(m))
				continue
			}
			r.set(m, "catalog")
		}
	}
}

// Snapshot returns a copy of the current service map and its source.
// TODO(catalog): plumb refresher.Snapshot() into proxy handlers so live refreshes
// take effect without a gateway restart.
func (r *Refresher) Snapshot() (map[string]string, string) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.current, r.source
}

func (r *Refresher) set(m map[string]string, src string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.current, r.source = m, src
}
