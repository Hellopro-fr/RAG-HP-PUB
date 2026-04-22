package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/hellopro/mcp-classification-produit/internal/config"
	"github.com/hellopro/mcp-classification-produit/internal/tools"
	"github.com/hellopro/mcp-classification-produit/internal/transport"
)

func main() {
	cfg := config.Load()

	log.Printf("[main] starting %s v%s on :%s", cfg.Name, cfg.Version, cfg.Port)

	// Create HTTP client for the classification API.
	// 5-minute timeout accounts for slow batch classification requests.
	httpClient := &http.Client{Timeout: 5 * time.Minute}

	clients := &tools.Clients{
		HTTP:    httpClient,
		BaseURL: cfg.ClassificationAPIURL,
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
