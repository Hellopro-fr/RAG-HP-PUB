package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"syscall"
	"time"

	"github.com/hellopro/mcp-gateway/internal/api"
	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/config"
	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/gateway"
	"github.com/hellopro/mcp-gateway/internal/health"
	"github.com/hellopro/mcp-gateway/internal/mcp"
	"github.com/hellopro/mcp-gateway/internal/ui"
	"github.com/hellopro/mcp-gateway/internal/repository"
	"github.com/hellopro/mcp-gateway/internal/transport"
)

func main() {
	cfg := config.Load()

	log.Printf("[main] starting %s v%s on :%s", cfg.Name, cfg.Version, cfg.Port)

	registry := gateway.NewRegistry()
	gw := gateway.New(cfg.Name, cfg.Version, registry)

	// Connexion MySQL et initialisation du repository
	var repo *repository.ServerRepo
	var healthChecker *health.Checker

	if cfg.MySQLDSN != "" {
		database, err := db.Connect(cfg.MySQLDSN)
		if err != nil {
			log.Fatalf("[main] failed to connect to MySQL: %v", err)
		}

		// Initialise l'encryptor si la clé est fournie
		var encryptor *crypto.Encryptor
		if cfg.EncryptionKey != "" {
			encryptor, err = crypto.NewEncryptor(cfg.EncryptionKey)
			if err != nil {
				log.Fatalf("[main] invalid ENCRYPTION_KEY: %v", err)
			}
			log.Println("[main] encryption enabled for auth_headers")
		}

		repo = repository.NewServerRepo(database, encryptor)

		// Charge les serveurs actifs depuis la base de données
		loadServersFromDB(gw, registry, repo)

		// Démarre le health checker
		healthChecker = health.NewChecker(repo, gw, registry, time.Duration(cfg.HealthCheckInterval)*time.Second)
		healthChecker.Start()
	} else {
		log.Println("[main] MYSQL_DSN not set — running without database (in-memory only)")
	}

	// Backward compat: enregistre les backends configurés par env var
	if len(cfg.BackendServers) > 0 {
		ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		for _, url := range cfg.BackendServers {
			if err := gw.RegisterBackend(ctx, url); err != nil {
				log.Printf("[main] warn: could not register backend %s: %v", url, err)
			}
		}
	}

	mux := http.NewServeMux()

	// Configure auth
	authCfg := auth.Config{
		JWTSecret:   cfg.JWTSecret,
		JWTAlgo:     cfg.JWTAlgo,
		JWTAudience: cfg.JWTAudience,
		AuthURL:     cfg.AuthURL,
		Enabled:     cfg.AuthEnabled,
	}

	// Mount login/logout routes
	if authCfg.Enabled {
		auth.RegisterHandlers(mux, authCfg)
		log.Println("[main] authentication enabled — login at /login")
	}

	// Monte les routes REST API si le repository est disponible
	if repo != nil {
		apiHandler := api.NewHandler(repo, gw, registry)
		apiHandler.Register(mux)
		log.Println("[main] REST API mounted at /api/v1/")
	}

	// Monte l'interface web
	ui.Register(mux)
	log.Println("[main] UI mounted at /ui/")

	// Monte les routes MCP SSE (inchangées)
	sseServer := transport.NewSSEServer(gw)
	sseServer.Register(mux)

	// Monte le transport streamable HTTP (POST /mcp)
	streamableServer := transport.NewStreamableHTTPServer(gw)
	streamableServer.Register(mux)
	log.Println("[main] streamable HTTP mounted at /mcp")

	// Wrap entire mux with auth middleware
	authMiddleware := auth.Middleware(authCfg)
	handler := authMiddleware(mux)

	httpServer := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      handler,
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
	if repo != nil {
		log.Printf("[main] ready — REST API: http://0.0.0.0:%s/api/v1/servers", cfg.Port)
	}

	<-stop
	log.Println("[main] shutting down...")

	if healthChecker != nil {
		healthChecker.Stop()
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := httpServer.Shutdown(shutdownCtx); err != nil {
		log.Printf("[main] shutdown error: %v", err)
	}
	log.Println("[main] stopped")
}

// loadServersFromDB charge tous les serveurs actifs depuis MySQL et les enregistre.
func loadServersFromDB(gw *gateway.Gateway, reg *gateway.Registry, repo *repository.ServerRepo) {
	servers, err := repo.ListActive()
	if err != nil {
		log.Printf("[main] warn: failed to load servers from DB: %v", err)
		return
	}

	log.Printf("[main] loading %d active server(s) from database", len(servers))

	var wg sync.WaitGroup
	for _, srv := range servers {
		wg.Add(1)
		go func(s db.MCPServer) {
			defer wg.Done()

			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()

			// Parse auth headers from DB
			var authHeaders map[string]string
			if len(s.AuthHeaders) > 0 {
				_ = json.Unmarshal(s.AuthHeaders, &authHeaders)
			}
			// Tente la découverte en direct
			if err := gw.DiscoverAndRegister(ctx, s.ID, s.URL, authHeaders); err != nil {
				log.Printf("[main] warn: discovery failed for %s (%s): %v — using cached capabilities", s.Name, s.URL, err)
				_ = repo.UpdateHealth(s.ID, "unhealthy", err.Error())
				// Utilise les capabilities cachées de la DB
				registerFromDBCache(gw, &s)
			} else {
				_ = repo.UpdateHealth(s.ID, "healthy", "")
			}
		}(srv)
	}
	wg.Wait()
}

// registerFromDBCache enregistre un serveur depuis les données cachées en base.
func registerFromDBCache(gw *gateway.Gateway, srv *db.MCPServer) {
	backend := &gateway.BackendServer{
		ID:            srv.ID,
		URL:           srv.URL,
		MessageURL:    srv.MessageURL,
		TransportType: srv.TransportType,
		Name:          srv.ServerName,
		Version:       srv.ServerVersion,
	}

	// Reconstruit les capabilities depuis les données DB
	for _, t := range srv.Tools {
		backend.Tools = append(backend.Tools, mcp.Tool{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: t.InputSchema,
		})
	}
	for _, r := range srv.Resources {
		backend.Resources = append(backend.Resources, mcp.Resource{
			URI:         r.URI,
			Name:        r.Name,
			Description: r.Description,
			MimeType:    r.MimeType,
		})
	}
	for _, p := range srv.Prompts {
		prompt := mcp.Prompt{
			Name:        p.Name,
			Description: p.Description,
		}
		for _, a := range p.Arguments {
			prompt.Arguments = append(prompt.Arguments, mcp.PromptArgument{
				Name:        a.Name,
				Description: a.Description,
				Required:    a.IsRequired,
			})
		}
		backend.Prompts = append(backend.Prompts, prompt)
	}

	// Reconstruit les capabilities depuis le JSON brut
	if len(srv.CapabilitiesRaw) > 0 {
		var caps mcp.ServerCapabilities
		if err := json.Unmarshal(srv.CapabilitiesRaw, &caps); err == nil {
			backend.Capabilities = caps
		}
	}

	gw.RegisterFromCache(backend)
}
