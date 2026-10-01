package app

import (
	"net/http"
	"time"

	"account-service/internal/api"
	"account-service/internal/auth"
	"account-service/internal/authserver"
	"account-service/internal/config"
	"account-service/internal/crypto"
	"account-service/internal/health"
	"account-service/internal/logout"
	"account-service/internal/metrics"
)

// routeDeps is the closed set of values registerRoutes needs. Bundling the
// dependencies here keeps the function arity sane and lets each subsystem
// (oauth2, sessions, admin, broadcast) get a coherent slice of state.
type routeDeps struct {
	cfg          *config.Configuration
	repos        Repos
	cipher       *crypto.Cipher
	upsert       auth.UserUpserter
	broadcaster  *logout.Broadcaster
	dbPing       health.Pinger
	version      string
	catalog      api.CatalogClientIface
	catalogAudit api.CatalogAuditFn
	mcpSync      api.McpSyncer
}

// registerRoutes mounts every route on mux. Split out of main() so the entry
// point has zero knowledge of the URL surface — adding or removing an endpoint
// no longer touches main.go.
func registerRoutes(mux *http.ServeMux, d routeDeps) {
	cfg := d.cfg
	r := d.repos
	cipher := d.cipher

	// Public OAuth2 endpoints — no admin auth, MCP-spec compliant.
	mux.Handle("GET /.well-known/oauth-authorization-server", authserver.NewMetadataHandler(cfg.PublicURL))

	authSrv := authserver.NewAuthServer(authserver.AuthServerDeps{
		ClientRepo:    r.OAuth2,
		AuthCodeRepo:  r.AuthCode,
		UserUpserter:  d.upsert,
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
	mux.HandleFunc("/authorize", authSrv.HandleAuthorize)
	mux.Handle("GET /authorize/branding/{client_id}", authserver.NewBrandingHandler(r.OAuth2))

	tokenEP := authserver.NewTokenEndpoint(authserver.TokenEndpointDeps{
		ClientRepo:     r.OAuth2,
		AuthCodeRepo:   r.AuthCode,
		RefreshRepo:    r.Refresh,
		RefreshRotator: r.Refresh,
		Decrypt:        cipher.Decrypt,
		JWTSecret:      cfg.JWTSecret,
		Issuer:         cfg.PublicURL,
	})
	mux.Handle("POST /token", tokenEP)
	mux.Handle("POST /token/revoke", authserver.NewRevokeHandler(authserver.RevokeDeps{
		ClientRepo: r.OAuth2, Rotator: r.Refresh, Revoker: r.Refresh, Decrypt: cipher.Decrypt,
	}))
	mux.Handle("POST /introspect", authserver.NewIntrospectHandler(authserver.IntrospectDeps{
		ClientRepo: r.OAuth2, Rotator: r.Refresh, Decrypt: cipher.Decrypt,
		JWTSecret: cfg.JWTSecret, Issuer: cfg.PublicURL,
	}))

	// Internal admin-token-gated credential lookup.
	mux.Handle("GET /internal/credentials/{name}", api.NewInternalCredentialsHandler(api.InternalCredentialsDeps{
		Repo:       r.OAuth2,
		Decrypt:    cipher.Decrypt,
		AdminToken: cfg.InternalAdminToken,
	}))

	// Admin-UI session endpoints.
	loginHandler := auth.NewLoginHandler(auth.Config{
		AuthURL: cfg.AuthURL, JWTSecret: cfg.JWTSecret, JWTAudience: cfg.JWTAudience,
		SecureCookie: cfg.SecureCookie, FallbackUser: cfg.FallbackUser,
		FallbackPass: cfg.FallbackPass, FallbackEmail: cfg.FallbackEmail,
	}, d.upsert)
	mux.Handle("POST /api/v1/login", loginHandler)
	mux.Handle("POST /api/v1/logout", auth.NewLogoutHandler())
	// Browser-friendly RP-initiated logout (clears account_session, validates
	// post_logout_redirect_uri against the registered redirect_uris of
	// ?client_id, then 303s back to it).
	mux.Handle("GET /logout", auth.NewLogoutRedirectHandler(logoutRedirectLookup{repo: r.OAuth2}))

	// Auth gates — closures keep RequireAdmin/RequireAuth wired to this app's
	// JWT secret + user repo without leaking those into every handler.
	resolver := func(email string) (bool, bool) {
		u, err := r.User.FindByEmail(email)
		if err != nil {
			return false, false
		}
		return u.IsAllowed, u.IsAdmin
	}
	requireAdmin := auth.RequireAdmin(cfg.JWTSecret, resolver)
	requireAuth := auth.RequireAuth(cfg.JWTSecret)

	// Authenticated REST API.
	mux.Handle("GET /api/v1/me", requireAuth(api.NewMeHandler(userInfoAdapter{repo: r.User})))

	// Services CRUD: open to any authenticated user.
	servicesDeps := api.AdminServiceDeps{Repo: r.OAuth2, Encrypt: cipher.Encrypt}
	servicesDetailDeps := api.AdminServiceDetailDeps{Repo: r.OAuth2, Encrypt: cipher.Encrypt}
	mux.Handle("/api/v1/admin/services", requireAuth(api.NewAdminServiceHandler(servicesDeps)))
	mux.Handle("/api/v1/admin/services/{id}", requireAuth(api.NewAdminServiceDetailHandler(servicesDetailDeps)))
	mux.Handle("/api/v1/admin/services/{id}/{op}", requireAuth(api.NewAdminServiceDetailHandler(servicesDetailDeps)))

	// Admin-only user management + sessions + audit.
	adminUserDeps := api.AdminUserDeps{
		Repo:        r.User,
		RevokeAll:   r.Refresh,
		Broadcaster: userBroadcastAdapter{clients: r.OAuth2, refresh: r.Refresh, bc: d.broadcaster},
		McpSync:     d.mcpSync,
	}
	mux.Handle("GET /api/v1/admin/users", requireAdmin(api.NewAdminUserHandler(adminUserDeps)))
	// Literal segment — Go 1.22 mux prefers it over the {email}/{op} wildcard.
	mux.Handle("POST /api/v1/admin/users/sync-mcp", requireAdmin(api.NewAdminUserMcpSyncAllHandler(adminUserDeps)))
	mux.Handle("POST /api/v1/admin/users/{email}/{op}", requireAdmin(api.NewAdminUserHandler(adminUserDeps)))
	sessionsDeps := api.SessionsDeps{Repo: r.Refresh}
	mux.Handle("GET /api/v1/admin/users/{email}/sessions", requireAdmin(api.NewSessionsHandler(sessionsDeps)))
	mux.Handle("POST /api/v1/admin/sessions/{sid}/revoke", requireAdmin(api.NewSessionsHandler(sessionsDeps)))
	mux.Handle("GET /api/v1/admin/audit", requireAdmin(api.NewAuditHandler(api.AuditDeps{Repo: r.Audit})))

	// API Catalog — proxy to api-catalog-service via gRPC.
	// A nil client (APICatalogGRPC unset) is fine: the handler returns 503 from gRPC Unavailable.
	catalogHandler := api.NewAPICatalogHandler(api.APICatalogDeps{
		Client: d.catalog,
		Audit:  d.catalogAudit,
	})
	// Any authenticated user may create/update/rescan API entries; delete stays admin-only.
	mux.Handle("GET /api/v1/admin/api", requireAuth(catalogHandler))
	mux.Handle("POST /api/v1/admin/api", requireAuth(catalogHandler))
	// Explicit rescan-all before the wildcard {id} routes so Go mux picks the more specific pattern.
	mux.Handle("POST /api/v1/admin/api/rescan", requireAuth(catalogHandler))
	mux.Handle("GET /api/v1/admin/api/{id}", requireAuth(catalogHandler))
	mux.Handle("PUT /api/v1/admin/api/{id}", requireAuth(catalogHandler))
	mux.Handle("DELETE /api/v1/admin/api/{id}", requireAdmin(catalogHandler))
	mux.Handle("POST /api/v1/admin/api/{id}/{op}", requireAuth(catalogHandler))
	mux.Handle("PUT /api/v1/admin/api/{id}/endpoints/{endpoint_id}", requireAuth(catalogHandler))

	// Health + Prometheus metrics.
	mux.Handle("GET /health", health.NewHandler(d.version, d.dbPing))
	mux.Handle("GET /metrics", metrics.Handler())
}
