package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	"github.com/hellopro/mcp-normalize-unite/internal/config"
	"github.com/hellopro/mcp-normalize-unite/internal/tools"
	"github.com/hellopro/mcp-normalize-unite/internal/transport"
	normalizationpb "github.com/hellopro/mcp-normalize-unite/proto/gen/graph_normalization"
	unitregistrypb "github.com/hellopro/mcp-normalize-unite/proto/gen/unit_registry"
)

func main() {
	cfg := config.Load()

	log.Printf("[main] starting %s v%s on :%s", cfg.Name, cfg.Version, cfg.Port)

	// Establish the gRPC connection to the normalization backend.
	normalizationConn := mustDial(cfg.NormalizationServiceURL, "normalization")
	defer normalizationConn.Close()
	unitRegistryConn := mustDial(cfg.UnitRegistryAddr, "unit-registry")
	defer unitRegistryConn.Close()
	if cfg.UnitsAdminKey == "" {
		log.Printf("[main] UNITS_ADMIN_KEY is empty: unit write tools will be rejected by unit-registry-service")
	}

	clients := &tools.Clients{
		Normalization: normalizationpb.NewGraphNormalizationServiceClient(normalizationConn),
		Units:         unitregistrypb.NewUnitRegistryServiceClient(unitRegistryConn),
		UnitsAdminKey: cfg.UnitsAdminKey,
		Actor:         "mcp:" + cfg.Name,

		WriteToolsEnabled: cfg.UnitWriteToolsEnabled,
	}
	if cfg.UnitWriteToolsEnabled {
		log.Printf("[main] unit write tools ENABLED (UNIT_WRITE_TOOLS_ENABLED): create/update/deactivate unit + unit type, set_dimension_types")
	} else {
		log.Printf("[main] read-only mode: unit write tools disabled (set UNIT_WRITE_TOOLS_ENABLED=true to expose them)")
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

func mustDial(addr, name string) *grpc.ClientConn {
	log.Printf("[main] connecting to %s at %s", name, addr)
	conn, err := grpc.NewClient(addr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		log.Fatalf("[main] failed to connect to %s service at %s: %v", name, addr, err)
	}
	return conn
}
