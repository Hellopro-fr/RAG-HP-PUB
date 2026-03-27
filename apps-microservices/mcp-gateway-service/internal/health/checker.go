package health

import (
	"context"
	"encoding/json"
	"log"
	"sync"
	"time"

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
		go func(id, url, prevStatus string, authHeadersRaw []byte) {
			defer wg.Done()
			var authHeaders map[string]string
			if len(authHeadersRaw) > 0 {
				_ = json.Unmarshal(authHeadersRaw, &authHeaders)
			}
			c.checkOne(id, url, prevStatus, authHeaders)
		}(srv.ID, srv.URL, srv.HealthStatus, srv.AuthHeaders)
	}
	wg.Wait()
}

func (c *Checker) checkOne(id, url, prevStatus string, authHeaders map[string]string) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Vérifie si le serveur est joignable en tentant une re-découverte
	err := c.gw.DiscoverAndRegister(ctx, id, url, authHeaders)

	if err != nil {
		// Le serveur n'est pas joignable
		if prevStatus != "unhealthy" {
			log.Printf("[health] server %s (%s) became unhealthy: %v", id, url, err)
		}
		_ = c.repo.UpdateHealth(id, "unhealthy", err.Error())
		return
	}

	// Le serveur est joignable
	if prevStatus == "unhealthy" || prevStatus == "unknown" {
		log.Printf("[health] server %s (%s) is now healthy", id, url)
	}
	_ = c.repo.UpdateHealth(id, "healthy", "")
}
