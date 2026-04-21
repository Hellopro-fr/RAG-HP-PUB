package auth

import (
	"context"
	"log"
	"net/http"
	"net/url"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/db"
)

// UserRepo is the interface for user lookup used by the auth middleware.
type UserRepo interface {
	GetByEmail(email string) (*db.GatewayUser, error)
}

// contextKey is an unexported type for context keys in this package.
type contextKey string

const (
	// ContextKeyUserEmail is the context key for the authenticated user's email.
	ContextKeyUserEmail contextKey = "user_email"
	// ContextKeyUserName is the context key for the authenticated user's display name.
	ContextKeyUserName contextKey = "user_display_name"
)

// UserEmailFromContext extracts the authenticated user's email from the request context.
// Returns empty string if not set (e.g., auth disabled).
func UserEmailFromContext(ctx context.Context) string {
	if v, ok := ctx.Value(ContextKeyUserEmail).(string); ok {
		return v
	}
	return ""
}

// UserNameFromContext extracts the authenticated user's display name from the request context.
// Returns empty string if not set.
func UserNameFromContext(ctx context.Context) string {
	if v, ok := ctx.Value(ContextKeyUserName).(string); ok {
		return v
	}
	return ""
}

// Config holds JWT/auth configuration.
type Config struct {
	JWTSecret     string
	JWTAlgo       string // always HS256
	JWTAudience   string
	AuthURL       string // hellopro.fr auth endpoint
	Enabled       bool
	SecureCookie  bool   // Secure flag on session cookie (true when behind TLS)
	FallbackUser  string // optional fallback username (env FALLBACK_USER)
	FallbackPass  string   // optional fallback password (env FALLBACK_PASS)
	FallbackEmail string   // optional fallback email (env FALLBACK_EMAIL)
}

// publicPaths that don't require authentication.
var publicExact = map[string]bool{
	"/login":  true,
	"/logout": true,
	"/health": true,
}

var publicPrefixes = []string{
	"/static",
	"/favicon",
	"/sse",          // MCP SSE transport (machine-to-machine)
	"/mcp",          // MCP streamable HTTP transport (machine-to-machine)
	"/openapi.json",
	"/authorize",                  // OAuth2 authorization endpoint
	"/token",                      // OAuth2 token endpoint
	"/api/v1/oauth2/authorize",    // OAuth2 authorize API (Vue frontend)
	// "/register" intentionally NOT public — requires admin session to prevent abuse
	"/.well-known",        // OAuth2 server metadata
	"/api/v1/public/",     // Public docs endpoints
	"/uploads/",           // Uploaded static files (icons)
	"/api/v1/internal/",   // Internal machine-to-machine (X-Admin-Token on handler)
}

// Middleware returns an HTTP middleware that enforces authentication.
// userRepo is optional: when non-nil, the user's role is looked up from the DB
// and injected into the context. If the user is not found, role defaults to config-only.
func Middleware(cfg Config, userRepo UserRepo) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		if !cfg.Enabled {
			return next
		}
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			path := r.URL.Path

			// Public exact match
			if publicExact[path] {
				next.ServeHTTP(w, r)
				return
			}

			// Public prefix match
			for _, prefix := range publicPrefixes {
				if strings.HasPrefix(path, prefix) {
					next.ServeHTTP(w, r)
					return
				}
			}

			// Try Authorization: Bearer header first (Vue frontend sends this)
			if authHeader := r.Header.Get("Authorization"); strings.HasPrefix(authHeader, "Bearer ") {
				token := strings.TrimPrefix(authHeader, "Bearer ")
				claims, err := ValidateJWT(token, cfg.JWTSecret, cfg.JWTAudience)
				if err == nil {
					ctx := r.Context()
					ctx = context.WithValue(ctx, ContextKeyUserEmail, claims.Email)
					ctx = context.WithValue(ctx, ContextKeyUserName, claims.Name)
					ctx = injectRole(ctx, claims.Email, userRepo)
					next.ServeHTTP(w, r.WithContext(ctx))
					return
				}
				log.Printf("[auth] invalid bearer token for %s: %v", path, err)
			}

			// Fall back to session cookie
			session, err := GetSession(r, cfg.JWTSecret)
			if err != nil {
				log.Printf("[auth] no valid session for %s: %v", path, err)
				if strings.HasPrefix(path, "/api/") {
					w.Header().Set("Content-Type", "application/json")
					w.WriteHeader(http.StatusUnauthorized)
					w.Write([]byte(`{"error":"not authenticated"}`))
				} else {
					http.Redirect(w, r, "/login?redirect="+url.QueryEscape(r.URL.RequestURI()), http.StatusSeeOther)
				}
				return
			}

			// Validate JWT token in session cookie
			_, err = ValidateJWT(session.Token, cfg.JWTSecret, cfg.JWTAudience)
			if err != nil {
				log.Printf("[auth] invalid session token for %s: %v", path, err)
				ClearSession(w)
				if strings.HasPrefix(path, "/api/") {
					w.Header().Set("Content-Type", "application/json")
					w.WriteHeader(http.StatusUnauthorized)
					w.Write([]byte(`{"error":"not authenticated"}`))
				} else {
					http.Redirect(w, r, "/login?redirect="+url.QueryEscape(r.URL.RequestURI()), http.StatusSeeOther)
				}
				return
			}

			// Inject user identity from session cookie
			ctx := r.Context()
			ctx = context.WithValue(ctx, ContextKeyUserEmail, session.Email)
			ctx = context.WithValue(ctx, ContextKeyUserName, session.DisplayName)
			ctx = injectRole(ctx, session.Email, userRepo)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

// injectRole looks up the user role from the DB and injects it into the context.
// If userRepo is nil or the user is not found, the role defaults to config-only.
func injectRole(ctx context.Context, email string, userRepo UserRepo) context.Context {
	role := RoleConfigOnly
	if userRepo != nil && email != "" {
		user, err := userRepo.GetByEmail(email)
		if err == nil && user != nil {
			role = user.Role
		}
	}
	return context.WithValue(ctx, ContextKeyUserRole, role)
}