package health

import (
	"context"
	"encoding/json"
	"log"
	"sync"
	"time"

	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/gateway"
	"github.com/hellopro/mcp-gateway/internal/repository"
)

// Checker periodically pings all active MCP backend servers and updates their health status.
type Checker struct {
	repo     *repository.ServerRepo
	gw       *gateway.Gateway
	registry *gateway.Registry
	interval time.Duration
	stop     chan struct{}
}

// NewChecker creates a health checker with the given interval.
func NewChecker(repo *repository.ServerRepo, gw *gateway.Gateway, registry *gateway.Registry, interval time.Duration) *Checker {
	return &Checker{
		repo:     repo,
		gw:       gw,
		registry: registry,
		interval: interval,
		stop:     make(chan struct{}),
	}
}

// Start begins the background health check loop.
func (c *Checker) Start() {
	log.Printf("[health] starting health checker (interval: %s)", c.interval)
	go c.run()
}

// Stop signals the health checker to stop.
func (c *Checker) Stop() {
	close(c.stop)
}

func (c *Checker) run() {
	ticker := time.NewTicker(c.interval)
	defer ticker.Stop()

	for {
		select {
		case <-c.stop:
			log.Println("[health] health checker stopped")
			return
		case <-ticker.C:
			c.checkAll()
		}
	}
}

func (c *Checker) checkAll() {
	active := true
	servers, err := c.repo.ListAll(&active, "", "")
	if err != nil {
		log.Printf("[health] failed to list active servers: %v", err)
		return
	}

	var wg sync.WaitGroup
	for _, srv := range servers {
		wg.Add(1)
		go func(s db.MCPServer) {
			defer wg.Done()
			var authHeaders map[string]string
			if len(s.AuthHeaders) > 0 {
				_ = json.Unmarshal(s.AuthHeaders, &authHeaders)
			}
			c.checkOne(&s, authHeaders)
		}(srv)
	}
	wg.Wait()
}

func (c *Checker) checkOne(srv *db.MCPServer, authHeaders map[string]string) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Vérifie si le serveur est joignable en tentant une re-découverte
	err := c.gw.DiscoverAndRegister(ctx, srv.ID, srv.URL, authHeaders)

	if err != nil {
		// Le serveur n'est pas joignable
		if srv.HealthStatus != "unhealthy" {
			log.Printf("[health] server %s (%s) became unhealthy: %v", srv.ID, srv.URL, err)
		}
		_ = c.repo.UpdateHealth(srv.ID, "unhealthy", err.Error())
		// Keep cached capabilities — they are still valid, the server is just temporarily unreachable.
		// Capabilities get refreshed on the next successful discovery.
		return
	}

	// Restore tool prefix after re-discovery
	if srv.ToolPrefix != "" {
		c.registry.SetToolPrefix(srv.ID, srv.ToolPrefix)
	}

	// Sync tool active states from DB (discovery marks all as active,
	// but some may have been deactivated by the user)
	if len(srv.Tools) > 0 {
		toolStates := make(map[string]bool, len(srv.Tools))
		for _, t := range srv.Tools {
			toolStates[t.Name] = t.IsActive
		}
		c.registry.SyncToolActiveStates(srv.ID, toolStates)
	}

	// Le serveur est joignable
	if srv.HealthStatus == "unhealthy" || srv.HealthStatus == "unknown" {
		log.Printf("[health] server %s (%s) is now healthy", srv.ID, srv.URL)
	}
	_ = c.repo.UpdateHealth(srv.ID, "healthy", "")
}
