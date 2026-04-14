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

	"gorm.io/gorm"

	"github.com/hellopro/mcp-gateway/internal/api"
	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/authserver"
	"github.com/hellopro/mcp-gateway/internal/config"
	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/gateway"
	"github.com/hellopro/mcp-gateway/internal/leexiadmin"
	"github.com/hellopro/mcp-gateway/internal/health"
	"github.com/hellopro/mcp-gateway/internal/mcp"
	oauth2pkg "github.com/hellopro/mcp-gateway/internal/oauth2"
	"github.com/hellopro/mcp-gateway/internal/repository"
	"github.com/hellopro/mcp-gateway/internal/scopetoken"
	"github.com/hellopro/mcp-gateway/internal/transport"
)

func main() {
	cfg := config.Load()

	// Security: JWT_SECRET must be set when authentication is enabled
	if cfg.AuthEnabled && cfg.JWTSecret == "" {
		log.Fatalf("[main] FATAL: JWT_SECRET environment variable must be set when AUTH_ENABLED=true. Generate one with: openssl rand -hex 32")
	}

	// RBAC: ADMIN_EMAILS must be set to bootstrap at least one admin user
	if len(cfg.AdminEmails) == 0 {
		log.Fatalf("[main] FATAL: ADMIN_EMAILS environment variable must be set with at least one email address for initial admin access")
	}

	log.Printf("[main] starting %s v%s on :%s", cfg.Name, cfg.Version, cfg.Port)

	registry := gateway.NewRegistry()
	gw := gateway.New(cfg.Name, cfg.Version, registry)

	// Connexion MySQL et initialisation du repository
	var repo *repository.ServerRepo
	var healthChecker *health.Checker
	var database *gorm.DB
	var encryptor *crypto.Encryptor
	var userRepo *repository.UserRepo
	var auditRepo *repository.AuditRepo

	if cfg.MySQLDSN != "" {
		var err error
		database, err = db.Connect(cfg.MySQLDSN)
		if err != nil {
			log.Fatalf("[main] failed to connect to MySQL: %v", err)
		}

		// Initialise l'encryptor si la clé est fournie
		if cfg.EncryptionKey != "" {
			encryptor, err = crypto.NewEncryptor(cfg.EncryptionKey)
			if err != nil {
				log.Fatalf("[main] invalid ENCRYPTION_KEY: %v", err)
			}
			log.Println("[main] encryption enabled for auth_headers")
		}

		repo = repository.NewServerRepo(database, encryptor)
		userRepo = repository.NewUserRepo(database, cfg.AdminEmails)
		auditRepo = repository.NewAuditRepo(database)

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
		JWTSecret:     cfg.JWTSecret,
		JWTAlgo:       cfg.JWTAlgo,
		JWTAudience:   cfg.JWTAudience,
		AuthURL:       cfg.AuthURL,
		Enabled:       cfg.AuthEnabled,
		SecureCookie:  cfg.SecureCookie,
		FallbackUser:  cfg.FallbackUser,
		FallbackPass:  cfg.FallbackPass,
		FallbackEmail: cfg.FallbackEmail,
	}

	// Mount login/logout routes
	if authCfg.Enabled {
		auth.RegisterHandlers(mux, authCfg, userRepo)
		log.Println("[main] authentication enabled — login at /login")
	}

	// Scope token cache + middleware
	tokenCache := scopetoken.NewCache(60 * time.Second)
	var tokenRepo *repository.TokenRepo

	// OAuth2 cache + repo
	oauth2Cache := oauth2pkg.NewCache(60 * time.Second)
	var oauth2Repo *repository.OAuth2Repo

	// Leexi admin client (used by token/OAuth2 filter UI + runtime header
	// injection). Disabled when env vars are unset; the proxy handlers and
	// scoped gateway tolerate a nil/disabled client gracefully.
	leexiAdminClient := leexiadmin.NewClient(cfg.LeexiInternalURL, cfg.LeexiAdminToken)
	if leexiAdminClient.Enabled() {
		gw.SetLeexiAdmin(leexiAdminClient)
		log.Println("[main] Leexi admin client configured for ownership-scoped tokens")
	}

	// Monte les routes REST API si le repository est disponible
	if repo != nil && database != nil {
		tokenRepo = repository.NewTokenRepo(database, encryptor)
		oauth2Repo = repository.NewOAuth2Repo(database, encryptor)

		apiHandler := api.NewHandler(repo, gw, registry, cfg.AllowInternalURLs)
		apiHandler.SetTokenRepo(tokenRepo, tokenCache)
		apiHandler.SetOAuth2Repo(oauth2Repo, oauth2Cache)
		apiHandler.SetUserRepo(userRepo)
		apiHandler.SetAuditRepo(auditRepo)
		apiHandler.SetLeexiAdmin(leexiAdminClient)
		apiHandler.SetUploadDir(cfg.UploadDir)
		apiHandler.Register(mux)
		log.Println("[main] REST API mounted at /api/v1/")

		// Serve uploaded files (icons, etc.) as static assets
		mux.Handle("/uploads/", http.StripPrefix("/uploads/", http.FileServer(http.Dir(cfg.UploadDir))))
		log.Printf("[main] serving uploads from %s at /uploads/", cfg.UploadDir)

		// OAuth2 Authorization Server (public endpoints: /authorize, /token, /register, /.well-known)
		authCodeRepo := repository.NewAuthCodeRepo(database)
		consentRepo := repository.NewConsentRepo(database)
		refreshRepo := repository.NewRefreshRepo(database)

		authSrv := authserver.NewAuthServer(authserver.AuthServerConfig{
			OAuth2Repo:   oauth2Repo,
			AuthCodeRepo: authCodeRepo,
			ConsentRepo:  consentRepo,
			RefreshRepo:  refreshRepo,
			ServerRepo:   repo,
			JWTSecret:    cfg.JWTSecret,
			PublicURL:    cfg.GatewayPublicURL,
			AuthURL:      cfg.AuthURL,
			SecureCookie: cfg.SecureCookie,
			RefreshTTL:   cfg.OAuth2RefreshTokenTTL,
		})
		authSrv.Register(mux)
		authSrv.RegisterAPI(mux)
		log.Println("[main] OAuth2 Authorization Server mounted at /authorize, /token, /register, /.well-known/")
		log.Println("[main] OAuth2 Authorize API mounted at /api/v1/oauth2/authorize/{info,login,consent}")
	}

	// Legacy UI redirect → Vue frontend handles all UI now
	mux.HandleFunc("/ui/", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/", http.StatusMovedPermanently)
	})
	mux.HandleFunc("/ui", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/", http.StatusMovedPermanently)
	})

	// Scope handler factory: creates a ScopedGateway for filtered access
	scopeFactory := func(allowedIDs map[string]bool, allowedTools map[string]map[string]bool) transport.Handler {
		return gateway.NewScopedGateway(gw, allowedIDs, allowedTools)
	}

	// MCP transport mux (SSE + streamable HTTP) with scope filtering
	mcpMux := http.NewServeMux()
	sseServer := transport.NewSSEServer(gw)
	sseServer.SetScopeFactory(scopeFactory)
	sseServer.Register(mcpMux)
	streamableServer := transport.NewStreamableHTTPServer(gw)
	streamableServer.SetScopeFactory(scopeFactory)
	streamableServer.Register(mcpMux)

	// Wrap MCP routes with combined OAuth2 + scope token middleware
	combinedMW := oauth2pkg.CombinedMiddleware(oauth2Cache, oauth2Repo, tokenCache, tokenRepo, cfg.JWTSecret, cfg.GatewayPublicURL)
	mux.Handle("/sse", combinedMW(mcpMux))
	mux.Handle("/message", combinedMW(mcpMux))
	mux.Handle("/mcp", combinedMW(mcpMux))
	mux.Handle("/mcp/", combinedMW(mcpMux))
	log.Println("[main] streamable HTTP mounted at /mcp (OAuth2 + scope token auth)")

	// Wrap entire mux with auth middleware
	authMiddleware := auth.Middleware(authCfg, userRepo)
	var handler http.Handler = authMiddleware(mux)

	// Wrap with audit middleware if available
	if auditRepo != nil {
		auditMw := auth.NewAuditMiddleware(auditRepo)
		handler = auditMw.Wrap(handler)
	}

	httpServer := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           handler,
		ReadTimeout:       15 * time.Second,
		ReadHeaderTimeout: 5 * time.Second, // Slowloris protection: limit header read phase
		WriteTimeout:      0,               // SSE streams need unlimited write time
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    1 << 20, // 1 MB max header size
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
				// Set tool prefix from DB on the freshly discovered backend
				if s.ToolPrefix != "" {
					reg.SetToolPrefix(s.ID, s.ToolPrefix)
				}
				// Sync tool active states from DB (discovery marks all as active,
				// but some may have been deactivated by the user)
				toolStates := make(map[string]bool, len(s.Tools))
				for _, t := range s.Tools {
					toolStates[t.Name] = t.IsActive
				}
				reg.SyncToolActiveStates(s.ID, toolStates)
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
		ToolPrefix:    srv.ToolPrefix,
	}

	// Reconstruit les capabilities depuis les données DB
	for _, t := range srv.Tools {
		backend.Tools = append(backend.Tools, mcp.Tool{
			Name:        t.Name,
			Description: t.Description,
			InputSchema: t.InputSchema,
			IsActive:    t.IsActive,
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
