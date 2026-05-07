// Package app is the composition root for mcp-gateway-service.
//
// cmd/server/main.go stays a tiny entry point (config load, signal handling,
// graceful shutdown) and every dependency — repos, gateway core, health
// checker, SSO, OAuth2 server, REST API, MCP transports, middleware — is
// wired here.
//
// Splitting this out lowers main()'s graphify-flagged centrality (was the
// single bridge connecting every internal/<pkg>) and gives us one place
// where the optional-branching reality of the service (DB optional, SSO
// optional, Leexi/Ringover optional, Google templates optional) can live
// without exploding main.go.
package app

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"runtime/debug"
	"strings"
	"sync"
	"time"

	"gorm.io/gorm"

	"mcp-gateway/internal/api"
	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/authserver"
	"mcp-gateway/internal/bddcatalog"
	"mcp-gateway/internal/config"
	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
	goGoogle "mcp-gateway/internal/google"
	"mcp-gateway/internal/health"
	"mcp-gateway/internal/leexiadmin"
	"mcp-gateway/internal/mcp"
	oauth2pkg "mcp-gateway/internal/oauth2"
	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/ringoveradmin"
	"mcp-gateway/internal/runnerclient"
	"mcp-gateway/internal/scopetoken"
	"mcp-gateway/internal/slack"
	"mcp-gateway/internal/sso"
	"mcp-gateway/internal/transport"
)

// App owns every long-lived dependency built at boot. main() drives Run /
// Shutdown without touching the inner objects.
type App struct {
	cfg           *config.Config
	server        *http.Server
	slack         *slack.Client
	healthChecker *health.Checker
}

// Build assembles every dependency. Does not start listening — callers do
// that via Run, so they own logging and signal handling around the lifecycle.
func Build(cfg *config.Config) (*App, error) {
	log.Printf("[main] starting %s v%s on :%s", cfg.Name, cfg.Version, cfg.Port)

	slackClient := slack.New(cfg.SlackWebhookURL, cfg.SlackEnvLabel, cfg.GatewayPublicURL, cfg.SlackAuthAlertCooldown)

	registry := gateway.NewRegistry()
	gw := gateway.New(cfg.Name, cfg.Version, registry)

	dbStack := buildDBStack(cfg, gw, registry, slackClient)

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

	ssoMiddleware := buildSSO(cfg, mux, dbStack, authCfg, slackClient)

	leexiAdminClient := leexiadmin.NewClient(cfg.LeexiInternalURL, cfg.LeexiAdminToken)
	if leexiAdminClient.Enabled() {
		gw.SetLeexiAdmin(leexiAdminClient)
		log.Println("[main] Leexi admin client configured for ownership-scoped tokens")
	}
	ringoverAdminClient := ringoveradmin.NewClient(cfg.RingoverInternalURL, cfg.RingoverAdminToken)
	if ringoverAdminClient.Enabled() {
		gw.SetRingoverAdmin(ringoverAdminClient)
		log.Println("[main] Ringover admin client configured for ownership-scoped tokens")
	}

	tokenCache := scopetoken.NewCache(60 * time.Second)
	oauth2Cache := oauth2pkg.NewCache(60 * time.Second)
	var instructionRepo *repository.InstructionRepo
	if dbStack.database != nil {
		instructionRepo = repository.NewInstructionRepo(dbStack.database)
	}

	var tokenRepo *repository.TokenRepo
	var oauth2Repo *repository.OAuth2Repo

	if dbStack.repo != nil && dbStack.database != nil {
		tokenRepo = repository.NewTokenRepo(dbStack.database, dbStack.encryptor)
		oauth2Repo = repository.NewOAuth2Repo(dbStack.database, dbStack.encryptor)
		registerRESTAndOAuthServer(cfg, mux, gw, registry, dbStack, tokenRepo, oauth2Repo, tokenCache, oauth2Cache, instructionRepo, leexiAdminClient, ringoverAdminClient, slackClient)
	}

	mux.HandleFunc("/ui/", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/", http.StatusMovedPermanently)
	})
	mux.HandleFunc("/ui", func(w http.ResponseWriter, r *http.Request) {
		http.Redirect(w, r, "/", http.StatusMovedPermanently)
	})

	mountMCPTransports(cfg, mux, gw, oauth2Cache, oauth2Repo, tokenCache, tokenRepo, instructionRepo, slackClient)

	handler := wrapAuthMiddleware(mux, ssoMiddleware, authCfg, dbStack.userRepo)
	if dbStack.auditRepo != nil {
		auditMw := auth.NewAuditMiddleware(dbStack.auditRepo)
		handler = auditMw.Wrap(handler)
	}

	server := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           handler,
		ReadTimeout:       15 * time.Second,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      0,
		IdleTimeout:       60 * time.Second,
		MaxHeaderBytes:    1 << 20,
	}

	return &App{
		cfg:           cfg,
		server:        server,
		slack:         slackClient,
		healthChecker: dbStack.healthChecker,
	}, nil
}

// Run blocks on ListenAndServe, panic-trapped via the slack-aware wrapper so
// a server crash posts a synchronous Slack alert before exit.
func (a *App) Run() {
	GoSafeExit(a.slack, "http-server", func() {
		if err := a.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("[main] server error: %v", err)
		}
	})
	log.Printf("[main] ready — SSE: http://0.0.0.0:%s/sse | HTTP: http://0.0.0.0:%s/mcp", a.cfg.Port, a.cfg.Port)
}

// Shutdown gracefully drains the http server and stops the health checker.
// The slack queue is closed inline so any pending events flush.
func (a *App) Shutdown(ctx context.Context, signalName string) {
	a.slack.NotifySync(slack.GatewayShutdownEvent{Signal: signalName})
	if a.healthChecker != nil {
		a.healthChecker.Stop()
	}
	if err := a.server.Shutdown(ctx); err != nil {
		log.Printf("[main] shutdown error: %v", err)
	}
	a.slack.Close()
}

// GoSafeExit runs fn in a goroutine. A panic posts a best-effort Slack alert
// (synchronously, before the process exits) and then terminates via
// log.Fatalf. Used for critical loops whose death would otherwise silently
// take down the service.
func GoSafeExit(slackClient *slack.Client, where string, fn func()) {
	go func() {
		defer func() {
			if rec := recover(); rec != nil {
				stack := string(debug.Stack())
				slackClient.NotifySync(slack.GatewayPanicEvent{Where: where, Err: rec, Stack: stack})
				log.Fatalf("[main] PANIC in %s: %v\n%s", where, rec, stack)
			}
		}()
		fn()
	}()
}

// dbStack bundles every DB-derived object that the rest of Build needs to
// thread through. Built once in buildDBStack so the optional-DB branches
// don't pollute every other wiring step.
type dbStack struct {
	database         *gorm.DB
	encryptor        *crypto.Encryptor
	repo             *repository.ServerRepo
	userRepo         *repository.UserRepo
	auditRepo        *repository.AuditRepo
	installGuideRepo *repository.InstallGuideRepo
	healthChecker    *health.Checker
}

func buildDBStack(cfg *config.Config, gw *gateway.Gateway, registry *gateway.Registry, slackClient *slack.Client) dbStack {
	if cfg.MySQLDSN == "" {
		log.Println("[main] MYSQL_DSN not set — running without database (in-memory only)")
		return dbStack{}
	}
	database, err := db.Connect(cfg.MySQLDSN)
	if err != nil {
		log.Fatalf("[main] failed to connect to MySQL: %v", err)
	}
	var encryptor *crypto.Encryptor
	if cfg.EncryptionKey != "" {
		encryptor, err = crypto.NewEncryptor(cfg.EncryptionKey)
		if err != nil {
			log.Fatalf("[main] invalid ENCRYPTION_KEY: %v", err)
		}
		log.Println("[main] encryption enabled for auth_headers")
	}
	repo := repository.NewServerRepo(database, encryptor)
	userRepo := repository.NewUserRepo(database, cfg.AdminEmails, cfg.AllowedEmails)
	auditRepo := repository.NewAuditRepo(database)
	installGuideRepo := repository.NewInstallGuideRepo(database)

	healthChecker := health.NewChecker(repo, gw, registry, time.Duration(cfg.HealthCheckInterval)*time.Second, slackClient)
	loadServersFromDB(gw, registry, repo, healthChecker)
	healthChecker.Start()

	return dbStack{
		database:         database,
		encryptor:        encryptor,
		repo:             repo,
		userRepo:         userRepo,
		auditRepo:        auditRepo,
		installGuideRepo: installGuideRepo,
		healthChecker:    healthChecker,
	}
}

// buildSSO returns the SSO middleware when cfg.SSOEnabled, else nil. Side-
// effects: mounts /sso/* handlers on mux and starts the session reaper. When
// SSOEnabled is false the legacy auth.RegisterHandlers path is mounted
// instead so /login / /logout still work.
func buildSSO(cfg *config.Config, mux *http.ServeMux, dbs dbStack, authCfg auth.Config, slackClient *slack.Client) *sso.Middleware {
	if !cfg.SSOEnabled {
		if authCfg.Enabled {
			auth.RegisterHandlers(mux, authCfg, dbs.userRepo, slackClient)
			log.Println("[main] authentication enabled — login at /login")
		}
		return nil
	}
	if dbs.database == nil || dbs.encryptor == nil {
		log.Fatalf("[main] FATAL: SSO_ENABLED=true requires MYSQL_DSN and ENCRYPTION_KEY")
	}
	if cfg.AccountPublicURL == "" {
		log.Fatalf("[main] FATAL: SSO_ENABLED=true requires ACCOUNT_PUBLIC_URL")
	}

	clientID, clientSecret := cfg.SSOClientID, cfg.SSOClientSecret
	var fetchedRedirects []string
	if clientID == "" || clientSecret == "" {
		fetchCtx, fetchCancel := context.WithTimeout(context.Background(), 10*time.Second)
		creds, err := sso.FetchCredentialsFromAPI(fetchCtx, cfg.SSOClientName, cfg.AccountInternalURL, cfg.AccountInternalToken)
		fetchCancel()
		if err != nil {
			log.Fatalf("[main] FATAL: failed to fetch SSO client credentials for %q: %v", cfg.SSOClientName, err)
		}
		clientID, clientSecret = creds.ClientID, creds.ClientSecret
		fetchedRedirects = creds.RedirectURIs
		log.Printf("[main] SSO client credentials fetched for %q (redirect_uris=%d)", cfg.SSOClientName, len(fetchedRedirects))
	}

	redirectURI := cfg.SSORedirectURI
	if redirectURI == "" && len(fetchedRedirects) > 0 {
		redirectURI = fetchedRedirects[0]
	}
	if redirectURI == "" {
		redirectURI = strings.TrimRight(cfg.GatewayPublicURL, "/") + "/sso/callback"
	}

	ssoClient := &sso.Client{
		ClientID:           clientID,
		ClientSecret:       clientSecret,
		AccountPublicURL:   cfg.AccountPublicURL,
		AccountInternalURL: cfg.AccountInternalURL,
		RedirectURI:        redirectURI,
		Scope:              "openid profile email",
	}
	ssoRepo := repository.NewSSOSessionRepo(dbs.database)
	ssoSlack := sso.NewSlackNotifier(cfg.LoginSlackURL, cfg.SlackEnvLabel, cfg.GatewayPublicURL)
	if cfg.LoginSlackURL != "" {
		log.Printf("[main] SSO error notifications → LOGIN_SLACK_URL")
	}
	ssoHandlers := sso.NewHandlers(ssoClient, ssoRepo, dbs.userRepo, dbs.encryptor, cfg.SecureCookie).
		WithStateKey([]byte(cfg.JWTSecret)).
		WithGatewayPublicURL(cfg.GatewayPublicURL).
		WithSlack(ssoSlack).
		WithAuthSession(cfg.JWTSecret)
	ssoHandlers.RegisterHandlers(mux)
	ssoMiddleware := sso.NewMiddleware(ssoClient, ssoRepo, dbs.userRepo, cfg.SecureCookie).
		WithEncryptor(dbs.encryptor).
		WithSlack(ssoSlack)

	GoSafeExit(slackClient, "sso-reaper", func() {
		t := time.NewTicker(time.Hour)
		defer t.Stop()
		for range t.C {
			if n, err := ssoRepo.ReapExpired(24 * time.Hour); err != nil {
				log.Printf("[sso] reaper error: %v", err)
			} else if n > 0 {
				log.Printf("[sso] reaped %d expired session(s)", n)
			}
		}
	})

	log.Printf("[main] SSO mode enabled — /sso/login → %s/authorize (client_id=%s)", cfg.AccountPublicURL, clientID)
	return ssoMiddleware
}

// registerRESTAndOAuthServer wires the REST API handler (with all its
// optional setters) plus the OAuth2 Authorization Server. Only called when
// the DB is present — without a DB the gateway is in MCP-only relay mode.
func registerRESTAndOAuthServer(
	cfg *config.Config,
	mux *http.ServeMux,
	gw *gateway.Gateway,
	registry *gateway.Registry,
	dbs dbStack,
	tokenRepo *repository.TokenRepo,
	oauth2Repo *repository.OAuth2Repo,
	tokenCache *scopetoken.Cache,
	oauth2Cache *oauth2pkg.Cache,
	instructionRepo *repository.InstructionRepo,
	leexiAdminClient *leexiadmin.Client,
	ringoverAdminClient *ringoveradmin.Client,
	slackClient *slack.Client,
) {
	templateRepo := repository.NewTemplateRepo(dbs.database)
	instanceRepo := repository.NewInstanceRepo(dbs.database, dbs.encryptor)

	var runnerClient *runnerclient.Client
	if cfg.GoogleTemplatesRunnerURL != "" && cfg.GoogleTemplatesRunnerAdminToken != "" {
		runnerClient = runnerclient.New(cfg.GoogleTemplatesRunnerURL, cfg.GoogleTemplatesRunnerAdminToken)
		log.Printf("[main] google-templates runner: %s", cfg.GoogleTemplatesRunnerURL)
	} else {
		log.Println("[main] google-templates runner: DISABLED (env vars not set)")
	}

	apiHandler := api.NewHandler(dbs.repo, gw, registry, cfg.AllowInternalURLs, templateRepo, instanceRepo, runnerClient, cfg)
	apiHandler.SetTokenRepo(tokenRepo, tokenCache)
	apiHandler.SetOAuth2Repo(oauth2Repo, oauth2Cache)
	apiHandler.SetUserRepo(dbs.userRepo)
	apiHandler.SetAuditRepo(dbs.auditRepo)
	apiHandler.SetLeexiAdmin(leexiAdminClient)
	apiHandler.SetRingoverAdmin(ringoverAdminClient)
	apiHandler.SetUploadDir(cfg.UploadDir)
	apiHandler.SetInstallGuideRepo(dbs.installGuideRepo)
	apiHandler.SetSlack(slackClient)
	apiHandler.SetInstructionRepo(instructionRepo)

	bddUsedRepo := repository.NewBDDUsedRepo(dbs.database)
	bddCatalogClient := bddcatalog.New(cfg.BDDCatalogBaseURL, cfg.BDDCatalogToken)
	apiHandler.SetBDDUsedRepo(bddUsedRepo)
	apiHandler.SetBDDCatalog(bddCatalogClient)
	gw.SetBDDResolver(bddUsedRepo)
	if bddCatalogClient.Enabled() {
		log.Println("[main] BDD catalog client configured (read-only proxy enabled)")
	}

	if cfg.GoogleClientID != "" && cfg.GoogleClientSecret != "" {
		redirectURL := strings.TrimRight(cfg.GatewayPublicURL, "/") + "/api/v1/google/callback"
		googleOAuth := goGoogle.NewOAuthClient(cfg.GoogleClientID, cfg.GoogleClientSecret, redirectURL)
		googleTokenRepo := repository.NewGoogleTokenRepo(dbs.database, dbs.encryptor)
		apiHandler.SetGoogleTokenRepo(googleTokenRepo, googleOAuth)
		log.Printf("[main] Google Sheets import enabled (redirect: %s)", redirectURL)
	}

	apiHandler.Register(mux)
	log.Println("[main] REST API mounted at /api/v1/")

	mux.Handle("/uploads/", http.StripPrefix("/uploads/", http.FileServer(http.Dir(cfg.UploadDir))))
	log.Printf("[main] serving uploads from %s at /uploads/", cfg.UploadDir)

	authCodeRepo := repository.NewAuthCodeRepo(dbs.database)
	consentRepo := repository.NewConsentRepo(dbs.database)
	refreshRepo := repository.NewRefreshRepo(dbs.database)
	// Wire the SSO bridge for /authorize so an authenticated admin browser
	// (gw_session cookie) skips the legacy login form. Constructing the repo
	// here keeps buildSSO focused on its own wiring.
	ssoSessionRepo := repository.NewSSOSessionRepo(dbs.database)

	authSrv := authserver.NewAuthServer(authserver.AuthServerConfig{
		OAuth2Repo:     oauth2Repo,
		AuthCodeRepo:   authCodeRepo,
		ConsentRepo:    consentRepo,
		RefreshRepo:    refreshRepo,
		ServerRepo:     dbs.repo,
		SSOSessionRepo: ssoSessionRepo,
		JWTSecret:      cfg.JWTSecret,
		PublicURL:      cfg.GatewayPublicURL,
		AuthURL:        cfg.AuthURL,
		SecureCookie:   cfg.SecureCookie,
		RefreshTTL:     cfg.OAuth2RefreshTokenTTL,
	})
	authSrv.Register(mux)
	authSrv.RegisterAPI(mux)
	log.Println("[main] OAuth2 Authorization Server mounted at /authorize, /token, /register, /.well-known/")
	log.Println("[main] OAuth2 Authorize API mounted at /api/v1/oauth2/authorize/{info,login,consent}")
}

// mountMCPTransports wires the SSE + streamable-HTTP MCP transports behind
// the combined OAuth2-bearer + scope-token middleware. Pulled out of Build
// so the dependency-flow at the top of Build remains readable.
func mountMCPTransports(
	cfg *config.Config,
	mux *http.ServeMux,
	gw *gateway.Gateway,
	oauth2Cache *oauth2pkg.Cache,
	oauth2Repo *repository.OAuth2Repo,
	tokenCache *scopetoken.Cache,
	tokenRepo *repository.TokenRepo,
	instructionRepo *repository.InstructionRepo,
	slackClient *slack.Client,
) {
	scopeFactory := func(ctx context.Context) transport.Handler {
		allowedIDs, ok := transport.AllowedServersFromContext(ctx)
		if !ok {
			return nil
		}
		allowedTools := transport.AllowedToolsFromContext(ctx)
		var instructions []gateway.InstructionView
		if resolved, ok := scopetoken.AllowedInstructionsFromContext(ctx); ok {
			instructions = make([]gateway.InstructionView, 0, len(resolved))
			for _, ri := range resolved {
				instructions = append(instructions, gateway.InstructionView{
					ID: ri.ID, Title: ri.Title, Body: ri.Body,
				})
			}
		}
		return gateway.NewScopedGateway(gw, allowedIDs, allowedTools, instructions)
	}

	mcpMux := http.NewServeMux()
	sseServer := transport.NewSSEServer(gw)
	sseServer.SetScopeFactory(scopeFactory)
	sseServer.Register(mcpMux)
	streamableServer := transport.NewStreamableHTTPServer(gw)
	streamableServer.SetScopeFactory(scopeFactory)
	streamableServer.Register(mcpMux)

	combinedMW := oauth2pkg.CombinedMiddleware(oauth2Cache, oauth2Repo, tokenCache, tokenRepo, instructionRepo, cfg.JWTSecret, cfg.GatewayPublicURL, slackClient)
	mux.Handle("/sse", combinedMW(mcpMux))
	mux.Handle("/message", combinedMW(mcpMux))
	mux.Handle("/mcp", combinedMW(mcpMux))
	mux.Handle("/mcp/", combinedMW(mcpMux))
	log.Println("[main] streamable HTTP mounted at /mcp (OAuth2 + scope token auth)")
}

// wrapAuthMiddleware picks the right middleware for the active mode. SSO
// mode swaps in sso.Middleware which loads identity from sso_sessions rows;
// legacy mode keeps the JWT/hellopro.fr cookie path.
func wrapAuthMiddleware(mux *http.ServeMux, ssoMW *sso.Middleware, authCfg auth.Config, userRepo *repository.UserRepo) http.Handler {
	if ssoMW != nil {
		return ssoMW.Handler(mux)
	}
	authMiddleware := auth.Middleware(authCfg, userRepo)
	return authMiddleware(mux)
}

// loadServersFromDB charge tous les serveurs actifs depuis MySQL et les
// enregistre. Transitions (healthy↔unhealthy) are routed through
// healthChecker.ApplyHealthResult so Slack sees them.
func loadServersFromDB(gw *gateway.Gateway, reg *gateway.Registry, repo *repository.ServerRepo, checker *health.Checker) {
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

			var authHeaders map[string]string
			if len(s.AuthHeaders) > 0 {
				_ = json.Unmarshal(s.AuthHeaders, &authHeaders)
			}
			if err := gw.DiscoverAndRegister(ctx, s.ID, s.URL, authHeaders); err != nil {
				log.Printf("[main] warn: discovery failed for %s (%s): %v — using cached capabilities", s.Name, s.URL, err)
				checker.ApplyHealthResult(&s, err)
				registerFromDBCache(gw, &s)
			} else {
				if s.ToolPrefix != "" {
					reg.SetToolPrefix(s.ID, s.ToolPrefix)
				}
				toolStates := make(map[string]bool, len(s.Tools))
				for _, t := range s.Tools {
					toolStates[t.Name] = t.IsActive
				}
				reg.SyncToolActiveStates(s.ID, toolStates)
				checker.ApplyHealthResult(&s, nil)
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
	if len(srv.CapabilitiesRaw) > 0 {
		var caps mcp.ServerCapabilities
		if err := json.Unmarshal(srv.CapabilitiesRaw, &caps); err == nil {
			backend.Capabilities = caps
		}
	}
	gw.RegisterFromCache(backend)
}
