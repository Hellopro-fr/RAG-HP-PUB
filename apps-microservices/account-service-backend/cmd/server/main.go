package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"gorm.io/gorm"

	"github.com/hellopro/account-service/internal/api"
	"github.com/hellopro/account-service/internal/auth"
	"github.com/hellopro/account-service/internal/authserver"
	"github.com/hellopro/account-service/internal/config"
	"github.com/hellopro/account-service/internal/crypto"
	"github.com/hellopro/account-service/internal/db"
	"github.com/hellopro/account-service/internal/health"
	"github.com/hellopro/account-service/internal/logout"
	"github.com/hellopro/account-service/internal/metrics"
	"github.com/hellopro/account-service/internal/repository"
)

const version = "0.1.0"

type cryptoAdapter struct {
	c *crypto.Cipher
}

func (a cryptoAdapter) Decrypt(in []byte) ([]byte, error) { return a.c.Decrypt(in) }

type dbPinger struct {
	g *gorm.DB
}

func (p dbPinger) Ping() error {
	sqlDB, err := p.g.DB()
	if err != nil {
		return err
	}
	return sqlDB.Ping()
}

type userInfoAdapter struct {
	repo *repository.UserRepo
}

func (a userInfoAdapter) FindByEmail(email string) (api.UserInfo, error) {
	u, err := a.repo.FindByEmail(email)
	if err != nil {
		return api.UserInfo{}, err
	}
	return api.UserInfo{
		Email:       u.Email,
		DisplayName: u.DisplayName,
		IsAdmin:     u.IsAdmin,
		IsAllowed:   u.IsAllowed,
	}, nil
}

type userBroadcastAdapter struct {
	clients *repository.OAuth2ClientRepo
	refresh *repository.RefreshRepo
	bc      *logout.Broadcaster
}

func (a userBroadcastAdapter) BroadcastForUser(email string) {
	rows, err := a.refresh.ListByUser(email)
	if err != nil {
		return
	}
	clientIDs := map[string]struct{}{}
	for _, r := range rows {
		clientIDs[r.ClientID] = struct{}{}
	}
	clients := make([]db.OAuth2Client, 0, len(clientIDs))
	for cid := range clientIDs {
		c, err := a.clients.GetByClientID(cid)
		if err != nil {
			continue
		}
		clients = append(clients, *c)
	}
	a.bc.Broadcast(email, "", clients)
}

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		logger.Error("config load", "err", err)
		os.Exit(1)
	}

	gormDB, err := db.Connect(cfg.MySQLDSN)
	if err != nil {
		logger.Error("db connect", "err", err)
		os.Exit(1)
	}
	if err := db.AutoMigrate(gormDB); err != nil {
		logger.Error("auto migrate", "err", err)
		os.Exit(1)
	}

	cipher, err := crypto.New(cfg.EncryptionKey)
	if err != nil {
		logger.Error("crypto", "err", err)
		os.Exit(1)
	}

	userRepo := repository.NewUserRepo(gormDB, cfg.AdminEmails)
	oauthRepo := repository.NewOAuth2ClientRepo(gormDB)
	authCodeRepo := repository.NewAuthCodeRepo(gormDB)
	refreshRepo := repository.NewRefreshRepo(gormDB)
	logoutEvtRepo := repository.NewLogoutEventRepo(gormDB)
	auditRepo := repository.NewAuditRepo(gormDB)

	upsertAdapter := auth.UserUpserterFunc(func(email, name string) (*auth.UpsertedUser, error) {
		u, err := userRepo.UpsertOnLogin(email, name)
		if err != nil {
			return nil, err
		}
		return &auth.UpsertedUser{Email: u.Email, IsAdmin: u.IsAdmin, IsAllowed: u.IsAllowed}, nil
	})

	deliv := logout.NewDeliverer(logout.DelivererConfig{
		Timeout:     time.Duration(cfg.WebhookTimeoutS) * time.Second,
		MaxAttempts: cfg.WebhookRetries,
	})
	pool := logout.NewWorkerPool(logout.WorkerConfig{
		Workers:    cfg.LogoutWorkers,
		BufferSize: 256,
		Deliverer:  deliv,
		Repo:       logoutEvtRepo,
	})
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	pool.Start(ctx)

	broadcaster := logout.NewBroadcaster(logout.BroadcasterDeps{
		Decrypter: cryptoAdapter{cipher},
		Repo:      logoutEvtRepo,
		Pool:      pool,
		Issuer:    cfg.PublicURL,
	})

	authSrv := authserver.NewAuthServer(authserver.AuthServerDeps{
		ClientRepo:    oauthRepo,
		AuthCodeRepo:  authCodeRepo,
		UserUpserter:  upsertAdapter,
		AuthURL:       cfg.AuthURL,
		JWTSecret:     cfg.JWTSecret,
		JWTAudience:   cfg.JWTAudience,
		Issuer:        cfg.PublicURL,
		AuthCodeTTL:   time.Duration(cfg.AuthCodeTTL) * time.Second,
		SecureCookie:  cfg.SecureCookie,
		FallbackUser:  cfg.FallbackUser,
		FallbackPass:  cfg.FallbackPass,
		FallbackEmail: cfg.FallbackEmail,
	})
	tokenEP := authserver.NewTokenEndpoint(authserver.TokenEndpointDeps{
		ClientRepo:     oauthRepo,
		AuthCodeRepo:   authCodeRepo,
		RefreshRepo:    refreshRepo,
		RefreshRotator: refreshRepo,
		Decrypt:        cipher.Decrypt,
		JWTSecret:      cfg.JWTSecret,
		Issuer:         cfg.PublicURL,
	})

	mux := http.NewServeMux()

	// Public OAuth2 endpoints
	mux.Handle("GET /.well-known/oauth-authorization-server", authserver.NewMetadataHandler(cfg.PublicURL))
	mux.HandleFunc("/authorize", authSrv.HandleAuthorize)
	mux.Handle("POST /token", tokenEP)
	mux.Handle("POST /token/revoke", authserver.NewRevokeHandler(authserver.RevokeDeps{
		ClientRepo: oauthRepo, Rotator: refreshRepo, Revoker: refreshRepo, Decrypt: cipher.Decrypt,
	}))
	mux.Handle("POST /introspect", authserver.NewIntrospectHandler(authserver.IntrospectDeps{
		ClientRepo: oauthRepo, Rotator: refreshRepo, Decrypt: cipher.Decrypt,
		JWTSecret: cfg.JWTSecret, Issuer: cfg.PublicURL,
	}))
	mux.Handle("GET /authorize/branding/{client_id}", authserver.NewBrandingHandler(oauthRepo))

	// Internal: admin-token-gated credentials lookup by service name.
	// Consumed by libs/common-utils/sso + libs/account-client-go so services
	// registered in the admin UI can fetch their client_id + client_secret
	// programmatically without a DB connection or the AES key.
	mux.Handle("GET /internal/credentials/{name}", api.NewInternalCredentialsHandler(api.InternalCredentialsDeps{
		Repo:       oauthRepo,
		Decrypt:    cipher.Decrypt,
		AdminToken: cfg.InternalAdminToken,
	}))

	// Admin UI session endpoints
	loginHandler := auth.NewLoginHandler(auth.Config{
		AuthURL: cfg.AuthURL, JWTSecret: cfg.JWTSecret, JWTAudience: cfg.JWTAudience,
		SecureCookie: cfg.SecureCookie, FallbackUser: cfg.FallbackUser,
		FallbackPass: cfg.FallbackPass, FallbackEmail: cfg.FallbackEmail,
	}, upsertAdapter)
	mux.Handle("POST /api/v1/login", loginHandler)
	mux.Handle("POST /api/v1/logout", auth.NewLogoutHandler())

	// Admin guard
	resolver := func(email string) (bool, bool) {
		u, err := userRepo.FindByEmail(email)
		if err != nil {
			return false, false
		}
		return u.IsAllowed, u.IsAdmin
	}
	requireAdmin := auth.RequireAdmin(cfg.JWTSecret, resolver)
	requireAuth := auth.RequireAuth(cfg.JWTSecret)

	mux.Handle("GET /api/v1/me", requireAuth(api.NewMeHandler(userInfoAdapter{userRepo})))
	// Services CRUD: open to any authenticated user (full access).
	mux.Handle("/api/v1/admin/services", requireAuth(api.NewAdminServiceHandler(api.AdminServiceDeps{Repo: oauthRepo, Encrypt: cipher.Encrypt})))
	mux.Handle("/api/v1/admin/services/{id}", requireAuth(api.NewAdminServiceDetailHandler(api.AdminServiceDetailDeps{Repo: oauthRepo, Encrypt: cipher.Encrypt})))
	mux.Handle("/api/v1/admin/services/{id}/{op}", requireAuth(api.NewAdminServiceDetailHandler(api.AdminServiceDetailDeps{Repo: oauthRepo, Encrypt: cipher.Encrypt})))
	mux.Handle("GET /api/v1/admin/users", requireAdmin(api.NewAdminUserHandler(api.AdminUserDeps{
		Repo:        userRepo,
		RevokeAll:   refreshRepo,
		Broadcaster: userBroadcastAdapter{oauthRepo, refreshRepo, broadcaster},
	})))
	mux.Handle("POST /api/v1/admin/users/{email}/{op}", requireAdmin(api.NewAdminUserHandler(api.AdminUserDeps{
		Repo:        userRepo,
		RevokeAll:   refreshRepo,
		Broadcaster: userBroadcastAdapter{oauthRepo, refreshRepo, broadcaster},
	})))
	mux.Handle("GET /api/v1/admin/users/{email}/sessions", requireAdmin(api.NewSessionsHandler(api.SessionsDeps{Repo: refreshRepo})))
	mux.Handle("POST /api/v1/admin/sessions/{sid}/revoke", requireAdmin(api.NewSessionsHandler(api.SessionsDeps{Repo: refreshRepo})))
	mux.Handle("GET /api/v1/admin/audit", requireAdmin(api.NewAuditHandler(api.AuditDeps{Repo: auditRepo})))

	// Health + metrics
	mux.Handle("GET /health", health.NewHandler(version, dbPinger{gormDB}))
	mux.Handle("GET /metrics", metrics.Handler())

	// Top-level middleware chain
	root := api.RequestLog(api.Recover(mux))

	srv := &http.Server{
		Addr:              ":" + strconv.Itoa(cfg.Port),
		Handler:           root,
		ReadHeaderTimeout: 5 * time.Second,
	}

	stopChan := make(chan os.Signal, 1)
	signal.Notify(stopChan, os.Interrupt, syscall.SIGTERM)
	go func() {
		logger.Info("listening", "addr", srv.Addr, "version", version)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Error("listen", "err", err)
			os.Exit(1)
		}
	}()
	<-stopChan
	logger.Info("shutdown signal received")
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()
	_ = srv.Shutdown(shutdownCtx)
	cancel()
	pool.Wait()
	logger.Info("clean shutdown")
}
