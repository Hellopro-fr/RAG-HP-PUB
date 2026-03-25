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

	"github.com/hellopro/mcp-api-recherche/internal/config"
	"github.com/hellopro/mcp-api-recherche/internal/orchestrator"
	"github.com/hellopro/mcp-api-recherche/internal/tools"
	"github.com/hellopro/mcp-api-recherche/internal/transport"
	databasepb "github.com/hellopro/mcp-api-recherche/proto/gen/database"
	embeddingpb "github.com/hellopro/mcp-api-recherche/proto/gen/embedding"
	llmpb "github.com/hellopro/mcp-api-recherche/proto/gen/llm"
	rerankingpb "github.com/hellopro/mcp-api-recherche/proto/gen/reranking"
)

func main() {
	cfg := config.Load()

	log.Printf("[main] starting %s v%s on :%s", cfg.Name, cfg.Version, cfg.Port)

	// Establish gRPC connections to backend services.
	embeddingConn := mustDial(cfg.EmbeddingServiceURL, "embedding")
	databaseConn := mustDial(cfg.DatabaseServiceURL, "database")
	rerankingConn := mustDial(cfg.RerankingServiceURL, "reranking")
	llmConn := mustDial(cfg.LLMServiceURL, "llm")

	defer embeddingConn.Close()
	defer databaseConn.Close()
	defer rerankingConn.Close()
	defer llmConn.Close()

	// Create gRPC clients.
	clients := &tools.Clients{
		Embedding: embeddingpb.NewEmbeddingServiceClient(embeddingConn),
		Database:  databasepb.NewDatabaseSearchServiceClient(databaseConn),
		Reranking: rerankingpb.NewRerankingServiceClient(rerankingConn),
		LLM:       llmpb.NewLLMServiceClient(llmConn),
	}

	// Initialize the search orchestrator.
	schemaCache := orchestrator.NewSchemaCache(1 * time.Hour)
	filterBuilder := orchestrator.NewFilterBuilder(clients.Database, schemaCache)
	searchOrch := orchestrator.NewSearchOrchestrator(
		clients.Embedding, clients.Database, clients.Reranking, filterBuilder,
	)
	tools.SetSearchOrchestrator(searchOrch)

	// Set up MCP tool registry and handler.
	registry := tools.NewRegistry(clients)
	handler := tools.NewMCPHandler(cfg.Name, cfg.Version, registry)

	// Start the SSE server.
	mux := http.NewServeMux()
	sseServer := transport.NewSSEServer(handler)
	sseServer.Register(mux)

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

	log.Printf("[main] ready — SSE endpoint: http://0.0.0.0:%s/sse", cfg.Port)

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
