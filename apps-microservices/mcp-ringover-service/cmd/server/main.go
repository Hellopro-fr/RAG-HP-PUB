package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/hellopro/mcp-ringover/internal/config"
	"github.com/hellopro/mcp-ringover/internal/ringover"
	"github.com/hellopro/mcp-ringover/internal/tools"
	"github.com/hellopro/mcp-ringover/internal/transport"
)

func main() {
	cfg := config.Load()

	log.Printf("[main] starting %s v%s on :%s", cfg.Name, cfg.Version, cfg.Port)

	if cfg.RingoverAPIKey == "" {
		log.Println("[main] WARNING: RINGOVER_API_KEY is not set — API calls will fail")
	}

	// Create Ringover HTTP client.
	ringoverClient := ringover.NewClient(cfg.RingoverAPIBaseURL, cfg.RingoverAPIKey)

	clients := &tools.Clients{
		Ringover: ringoverClient,
	}

	// Set up MCP tool registry and handler.
	registry := tools.NewRegistry(clients)
	handler := tools.NewMCPHandler(cfg.Name, cfg.Version, registry)

	// Start the SSE + Streamable HTTP server.
	mux := http.NewServeMux()
	sseServer := transport.NewSSEServer(handler)
	sseServer.Register(mux)
	streamableServer := transport.NewStreamableHTTPServer(handler)
	streamableServer.Register(mux)

	// Internal admin endpoints (users/teams listing for the MCP gateway UI).
	// Disabled when no admin token is set to avoid accidental exposure.
	if cfg.AdminToken == "" {
		log.Println("[main] MCP_RINGOVER_ADMIN_TOKEN not set — /admin/users and /admin/teams are disabled")
	} else {
		adminServer := transport.NewAdminServer(ringoverClient, cfg.AdminToken)
		adminServer.Register(mux)
		log.Println("[main] admin endpoints registered: GET /admin/users, GET /admin/teams")
	}

	httpServer := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      mux,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 0, // SSE streams need unlimited write time
		IdleTimeout:  60 * time.Second,
	}

	// Graceful shutdown on SIGINT / SIGTERM.
	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[main] server error: %v", err)
		}
	}()

	log.Printf("[main] ready — SSE: http://0.0.0.0:%s/sse | HTTP: http://0.0.0.0:%s/mcp", cfg.Port, cfg.Port)

	<-stop
	log.Println("[main] shutting down...")

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		log.Printf("[main] shutdown error: %v", err)
	}
	log.Println("[main] stopped")
}
