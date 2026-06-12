// Package app is the composition root for account-service-backend.
//
// It exists to keep cmd/server/main.go down to ~30 lines (config load,
// signal handling, ListenAndServe, graceful shutdown) while every dependency
// — repos, crypto, logout fan-out, OAuth2 server, REST API, middleware — is
// wired in this package's Build / registerRoutes.
//
// graphify centrality analysis flagged the original main() as a 19-community
// bridge with betweenness 0.409, the highest in the graph. Splitting the
// dependency wiring out lowers main()'s reach while preserving the single
// entry point.
package app

import (
	"context"
	"fmt"
	"net/http"
	"strconv"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"gorm.io/gorm"

	"account-service/internal/api"
	"account-service/internal/auth"
	"account-service/internal/config"
	"account-service/internal/crypto"
	"account-service/internal/db"
	"account-service/internal/gatewaysync"
	"account-service/internal/logout"
	"account-service/internal/repository"
)

// App owns every long-lived dependency built at boot. main() drives Run /
// Shutdown without touching the inner objects.
type App struct {
	cfg       *config.Configuration
	server    *http.Server
	pool      *logout.WorkerPool
	bcgCancel context.CancelFunc
}

// Build assembles every dependency the service needs. It does NOT start the
// http listener nor the worker-pool goroutines — those happen in Run so the
// caller can wire its own logging and signal handling around the lifecycle.
//
// Returning a single *App + the routed http.Handler keeps the public surface
// of this package small (just Build, Run, Shutdown).
func Build(cfg *config.Configuration, version string) (*App, error) {
	gormDB, err := db.Connect(cfg.MySQLDSN)
	if err != nil {
		return nil, err
	}
	if err := db.AutoMigrate(gormDB); err != nil {
		return nil, err
	}
	cipher, err := crypto.New(cfg.EncryptionKey)
	if err != nil {
		return nil, err
	}

	repos := BuildRepos(gormDB, cfg.AdminEmails)

	upsert := newUserUpserter(repos.User)
	pool, broadcaster, bcgCancel := buildLogoutPipeline(cfg, cipher, repos.Logout)

	// Wire the API Catalog gRPC client when the backend address is configured.
	// Leave catCli nil when the env var is absent so the service starts without
	// the catalog backend (handlers return 503 from gRPC Unavailable).
	var catCli api.CatalogClientIface
	var catAudit api.CatalogAuditFn
	if cfg.APICatalogGRPC != "" {
		conn, err := grpc.NewClient(cfg.APICatalogGRPC, grpc.WithTransportCredentials(insecure.NewCredentials()))
		if err != nil {
			return nil, fmt.Errorf("dial api-catalog: %w", err)
		}
		catCli = api.NewCatalogClient(conn, cfg.CatalogAdminKey)
	}
	if repos.Audit != nil {
		catAudit = func(ctx context.Context, actor, action, target string) {
			_ = repos.Audit.Insert(&db.AuditLog{
				Event:       action,
				ActorEmail:  actor,
				TargetEmail: target,
			})
		}
	}

	// MCP gateway user sync — nil when MCP_GATEWAY_INTERNAL_URL is unset so
	// the sync routes return 503 instead of dialing nowhere.
	var mcpSync api.McpSyncer
	if cfg.MCPGatewayInternalURL != "" {
		mcpSync = gatewaysync.New(cfg.MCPGatewayInternalURL, cfg.InternalAdminToken)
	}

	mux := http.NewServeMux()
	registerRoutes(mux, routeDeps{
		cfg:          cfg,
		repos:        repos,
		cipher:       cipher,
		upsert:       upsert,
		broadcaster:  broadcaster,
		dbPing:       dbPinger{g: gormDB},
		version:      version,
		catalog:      catCli,
		catalogAudit: catAudit,
		mcpSync:      mcpSync,
	})

	root := api.RequestLog(api.Recover(mux))

	server := &http.Server{
		Addr:              ":" + strconv.Itoa(cfg.Port),
		Handler:           root,
		ReadHeaderTimeout: 5 * time.Second,
	}

	return &App{
		cfg:       cfg,
		server:    server,
		pool:      pool,
		bcgCancel: bcgCancel,
	}, nil
}

// Run blocks until the http server exits. The returned error is the
// ListenAndServe error (nil on graceful Shutdown).
func (a *App) Run() error {
	if err := a.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return err
	}
	return nil
}

// Addr returns the listening address — useful for logging at boot.
func (a *App) Addr() string { return a.server.Addr }

// Shutdown drains the http server, the logout worker pool, and any
// background goroutines started by Build. Safe to call multiple times.
func (a *App) Shutdown(ctx context.Context) error {
	err := a.server.Shutdown(ctx)
	a.bcgCancel()
	a.pool.Wait()
	return err
}

// newUserUpserter adapts repository.UserRepo to auth.UserUpserter so the
// adapter doesn't have to live in routes.go.
func newUserUpserter(repo *repository.UserRepo) auth.UserUpserter {
	return auth.UserUpserterFunc(func(email, name string) (*auth.UpsertedUser, error) {
		u, err := repo.UpsertOnLogin(email, name)
		if err != nil {
			return nil, err
		}
		return &auth.UpsertedUser{Email: u.Email, IsAdmin: u.IsAdmin, IsAllowed: u.IsAllowed}, nil
	})
}

// buildLogoutPipeline wires the logout fan-out: webhook deliverer → worker
// pool with retry persistence → broadcaster fed by the encrypted logout_events
// table. Returns the pool (so callers can Wait), the broadcaster (so admin
// handlers can fire events), and a cancel that drains the pool's context.
func buildLogoutPipeline(cfg *config.Configuration, cipher *crypto.Cipher, repo *repository.LogoutEventRepo) (*logout.WorkerPool, *logout.Broadcaster, context.CancelFunc) {
	deliv := logout.NewDeliverer(logout.DelivererConfig{
		Timeout:     time.Duration(cfg.WebhookTimeoutS) * time.Second,
		MaxAttempts: cfg.WebhookRetries,
	})
	pool := logout.NewWorkerPool(logout.WorkerConfig{
		Workers:    cfg.LogoutWorkers,
		BufferSize: 256,
		Deliverer:  deliv,
		Repo:       repo,
	})
	ctx, cancel := context.WithCancel(context.Background())
	pool.Start(ctx)

	bcst := logout.NewBroadcaster(logout.BroadcasterDeps{
		Decrypter: cryptoAdapter{c: cipher},
		Repo:      repo,
		Pool:      pool,
		Issuer:    cfg.PublicURL,
	})

	// gormDB is not needed downstream once Repos is built.
	_ = gorm.DB{}
	return pool, bcst, cancel
}
