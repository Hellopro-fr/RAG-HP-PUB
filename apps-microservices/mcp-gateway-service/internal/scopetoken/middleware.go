package scopetoken

import (
	"context"
	"log"
	"net/http"
	"time"

	"github.com/hellopro/mcp-gateway/internal/repository"
)

// AllowedServersContextKey is the context key for scope-allowed server IDs.
// Uses a plain string so both scopetoken and transport packages can read it.
const AllowedServersContextKey = "scope_allowed_servers"

// Middleware returns an HTTP middleware that validates X-MCP-Scope-Token
// and stores the allowed server IDs in the request context.
func Middleware(cache *Cache, repo *repository.TokenRepo, required bool) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			rawToken := r.Header.Get("X-MCP-Scope-Token")

			if rawToken == "" {
				if required {
					http.Error(w, `{"error":"X-MCP-Scope-Token header required"}`, http.StatusUnauthorized)
					return
				}
				// No token, no scope restriction — full access (backward compat)
				next.ServeHTTP(w, r)
				return
			}

			hash := Hash(rawToken)

			// Cache lookup
			ct, ok := cache.Get(hash)
			if !ok {
				// DB lookup
				if repo == nil {
					http.Error(w, `{"error":"scope tokens not configured"}`, http.StatusServiceUnavailable)
					return
				}
				dbToken, err := repo.FindByHash(hash)
				if err != nil {
					log.Printf("[scope] invalid token: %s...", hash[:8])
					http.Error(w, `{"error":"invalid scope token"}`, http.StatusUnauthorized)
					return
				}
				serverIDs := make(map[string]bool, len(dbToken.Servers))
				for _, s := range dbToken.Servers {
					serverIDs[s.ServerID] = true
				}
				ct = &CachedToken{
					ID:        dbToken.ID,
					ServerIDs: serverIDs,
					ExpiresAt: dbToken.ExpiresAt,
					IsActive:  dbToken.IsActive,
				}
				cache.Set(hash, ct)
			}

			// Validate
			if !ct.IsActive {
				http.Error(w, `{"error":"scope token is revoked"}`, http.StatusForbidden)
				return
			}
			if ct.ExpiresAt != nil && ct.ExpiresAt.Before(time.Now()) {
				http.Error(w, `{"error":"scope token has expired"}`, http.StatusForbidden)
				return
			}

			// Store allowed server IDs in context
			ctx := context.WithValue(r.Context(), AllowedServersContextKey, ct.ServerIDs)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
