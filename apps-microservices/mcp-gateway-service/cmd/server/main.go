// Command mcp-gateway-service is the MCP-protocol gateway + admin REST API
// + OAuth2 Authorization Server. This entry point is intentionally thin:
// load + validate config, hand the wiring to internal/app, then run the
// lifecycle. All dependency assembly, route registration, and helpers live
// in the app package.
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"mcp-gateway/internal/app"
	"mcp-gateway/internal/config"
)

func main() {
	cfg := config.Load()

	if cfg.AuthEnabled && cfg.JWTSecret == "" {
		log.Fatalf("[main] FATAL: JWT_SECRET environment variable must be set when AUTH_ENABLED=true. Generate one with: openssl rand -hex 32")
	}
	if len(cfg.AdminEmails) == 0 {
		log.Fatalf("[main] FATAL: ADMIN_EMAILS environment variable must be set with at least one email address for initial admin access")
	}

	a, err := app.Build(cfg)
	if err != nil {
		log.Fatalf("[main] app build: %v", err)
	}

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	a.Run()
	if cfg.MySQLDSN != "" {
		log.Printf("[main] ready — REST API: http://0.0.0.0:%s/api/v1/servers", cfg.Port)
	}

	sig := <-stop
	log.Printf("[main] shutting down (signal: %s)...", sig)

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	a.Shutdown(shutdownCtx, sig.String())
	log.Println("[main] stopped")
}
