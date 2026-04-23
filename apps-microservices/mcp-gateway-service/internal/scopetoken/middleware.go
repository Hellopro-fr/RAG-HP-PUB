package scopetoken

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"time"

	"github.com/hellopro/mcp-gateway/internal/repository"
	"github.com/hellopro/mcp-gateway/internal/slack"
)

// notifyUnauthorized alerts Slack (if configured) about a rejected MCP request.
// Cooldown gating lives inside the client.
func notifyUnauthorized(c *slack.Client, r *http.Request, reason string) {
	if c == nil {
		return
	}
	ip := slack.ClientIP(r)
	endpoint := r.URL.Path
	if !c.AllowAuthAlert(ip, endpoint) {
		return
	}
	c.Notify(slack.UnauthorizedEvent{
		ClientIP: ip,
		Endpoint: endpoint,
		Reason:   reason,
	})
}

// AllowedServersContextKey is the context key for scope-allowed server IDs.
// Uses a plain string so both scopetoken and transport packages can read it.
const AllowedServersContextKey = "scope_allowed_servers"

// AllowedToolsContextKey is the context key for scope-allowed tools per server.
// Value is map[string]map[string]bool: server_id → tool_name → true.
// A nil inner map for a server means all tools are allowed.
const AllowedToolsContextKey = "scope_allowed_tools"

// LeexiFilterContextKey carries a *LeexiFilterContext describing the
// per-request Leexi participant scope. Read by gateway.ScopedGateway when
// forwarding a tools/call to a Leexi-tagged backend.
const LeexiFilterContextKey = "scope_leexi_filter"

// ScopeNameContextKey carries the human-readable name of the active scope
// token or OAuth2 client. ScopedGateway reads it to override serverInfo.name
// on the MCP initialize response so clients see the credential label instead
// of the static gateway name.
const ScopeNameContextKey = "scope_name"

// LeexiFilterContext is the runtime view of the persisted scope.
type LeexiFilterContext struct {
	Mode             string
	AllowedUserUUIDs []string
	AllowedTeamUUIDs []string
}

// LeexiFilterFromContext returns the typed filter info if any was set.
func LeexiFilterFromContext(ctx context.Context) (*LeexiFilterContext, bool) {
	v, ok := ctx.Value(LeexiFilterContextKey).(*LeexiFilterContext)
	return v, ok
}

// Middleware returns an HTTP middleware that validates X-MCP-Scope-Token
// and stores the allowed server IDs and tool selections in the request context.
// slackClient is optional; when set, every 401/403 fires an UnauthorizedEvent
// (rate-limited inside the client).
func Middleware(cache *Cache, repo *repository.TokenRepo, required bool, slackClient *slack.Client) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			rawToken := r.Header.Get("X-MCP-Scope-Token")

			if rawToken == "" {
				if required {
					http.Error(w, `{"error":"X-MCP-Scope-Token header required"}`, http.StatusUnauthorized)
					notifyUnauthorized(slackClient, r, "missing X-MCP-Scope-Token")
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
					notifyUnauthorized(slackClient, r, "invalid scope token")
					return
				}
				serverIDs := make(map[string]bool, len(dbToken.Servers))
				for _, s := range dbToken.Servers {
					serverIDs[s.ServerID] = true
				}

				// Build allowed tools map from DB tool rows
				// server_id → tool_name → true; missing server_id key = all tools
				var allowedTools map[string]map[string]bool
				if len(dbToken.Tools) > 0 {
					allowedTools = make(map[string]map[string]bool)
					for _, t := range dbToken.Tools {
						if allowedTools[t.ServerID] == nil {
							allowedTools[t.ServerID] = make(map[string]bool)
						}
						allowedTools[t.ServerID][t.ToolName] = true
					}
				}

				ct = &CachedToken{
					ID:           dbToken.ID,
					Name:         dbToken.Name,
					ServerIDs:    serverIDs,
					AllowedTools: allowedTools,
					ExpiresAt:    dbToken.ExpiresAt,
					IsActive:     dbToken.IsActive,
				}

				// Decode persisted Leexi filter (JSON columns) into typed slices.
				ct.LeexiFilterMode = dbToken.LeexiFilterMode
				if len(dbToken.LeexiAllowedUserUUIDs) > 0 {
					_ = json.Unmarshal(dbToken.LeexiAllowedUserUUIDs, &ct.LeexiAllowedUserUUIDs)
				}
				if len(dbToken.LeexiAllowedTeamUUIDs) > 0 {
					_ = json.Unmarshal(dbToken.LeexiAllowedTeamUUIDs, &ct.LeexiAllowedTeamUUIDs)
				}

				cache.Set(hash, ct)
			}

			// Validate
			if !ct.IsActive {
				http.Error(w, `{"error":"scope token is revoked"}`, http.StatusForbidden)
				notifyUnauthorized(slackClient, r, "revoked scope token")
				return
			}
			if ct.ExpiresAt != nil && ct.ExpiresAt.Before(time.Now()) {
				http.Error(w, `{"error":"scope token has expired"}`, http.StatusForbidden)
				notifyUnauthorized(slackClient, r, "expired scope token")
				return
			}

			// Store allowed server IDs and tool selections in context
			ctx := context.WithValue(r.Context(), AllowedServersContextKey, ct.ServerIDs)
			if ct.AllowedTools != nil {
				ctx = context.WithValue(ctx, AllowedToolsContextKey, ct.AllowedTools)
			}
			if ct.Name != "" {
				ctx = context.WithValue(ctx, ScopeNameContextKey, ct.Name)
			}
			if ct.LeexiFilterMode != "" && ct.LeexiFilterMode != "none" {
				ctx = context.WithValue(ctx, LeexiFilterContextKey, &LeexiFilterContext{
					Mode:             ct.LeexiFilterMode,
					AllowedUserUUIDs: ct.LeexiAllowedUserUUIDs,
					AllowedTeamUUIDs: ct.LeexiAllowedTeamUUIDs,
				})
			}
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
