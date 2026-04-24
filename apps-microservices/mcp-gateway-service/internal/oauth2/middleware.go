package oauth2

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/hellopro/mcp-gateway/internal/repository"
	"github.com/hellopro/mcp-gateway/internal/scopetoken"
	"github.com/hellopro/mcp-gateway/internal/slack"
)

// notifyUnauthorized fires a Slack alert for a rejected MCP request, gated by
// the per-(ip,endpoint) cooldown so noisy scanners can't flood the channel.
// Safe to call with a nil client (no-op).
func notifyUnauthorized(slackClient *slack.Client, r *http.Request, reason string) {
	if slackClient == nil {
		return
	}
	ip := slack.ClientIP(r)
	endpoint := r.URL.Path
	if !slackClient.AllowAuthAlert(ip, endpoint) {
		return
	}
	slackClient.Notify(slack.UnauthorizedEvent{
		ClientIP: ip,
		Endpoint: endpoint,
		Reason:   reason,
	})
}

// CombinedMiddleware validates either Bearer token or X-MCP-Scope-Token.
// If neither is present, returns 401 with WWW-Authenticate header per MCP spec.
// Both mechanisms inject the same context keys so the ScopedGateway works unchanged.
//
// slackClient is optional; when non-nil it fires an UnauthorizedEvent on every
// 401/403 this middleware emits (with per-(ip,endpoint) cooldown inside the
// client so noisy scanners don't flood Slack).
// instructionRepo is optional — when provided, the Bearer and scope-token
// branches resolve each credential's LLM instructions on cache-miss so the
// MCP initialize response can inject them.
func CombinedMiddleware(
	oauth2Cache *Cache,
	oauth2Repo *repository.OAuth2Repo,
	tokenCache *scopetoken.Cache,
	tokenRepo *repository.TokenRepo,
	instructionRepo *repository.InstructionRepo,
	jwtSecret string,
	publicURL string,
	slackClient *slack.Client,
) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// 1. Check for OAuth2 Bearer token
			authHeader := r.Header.Get("Authorization")
			if strings.HasPrefix(authHeader, "Bearer ") {
				bearerToken := authHeader[7:]
				clientID, err := ValidateAccessToken(bearerToken, jwtSecret)
				if err != nil {
					log.Printf("[oauth2] invalid bearer token: %v", err)
					w.Header().Set("WWW-Authenticate", fmt.Sprintf(`Bearer error="invalid_token", resource_metadata="%s/.well-known/oauth-authorization-server"`, publicURL))
					http.Error(w, `{"error":"invalid_token","error_description":"invalid or expired access token"}`, http.StatusUnauthorized)
					notifyUnauthorized(slackClient, r, "invalid bearer token: "+err.Error())
					return
				}

				cc, ok := oauth2Cache.Get(clientID)
				if !ok {
					client, err := oauth2Repo.FindByID(clientID)
					if err != nil {
						http.Error(w, `{"error":"invalid_token","error_description":"client not found"}`, http.StatusUnauthorized)
						notifyUnauthorized(slackClient, r, "bearer client_id not found")
						return
					}

					serverIDs := make(map[string]bool, len(client.Servers))
					for _, s := range client.Servers {
						serverIDs[s.ServerID] = true
					}

					var allowedTools map[string]map[string]bool
					if len(client.Tools) > 0 {
						allowedTools = make(map[string]map[string]bool)
						for _, t := range client.Tools {
							if allowedTools[t.ServerID] == nil {
								allowedTools[t.ServerID] = make(map[string]bool)
							}
							allowedTools[t.ServerID][t.ToolName] = true
						}
					}

					cc = &CachedClient{
						ID:           client.ID,
						Name:         client.Name,
						ServerIDs:    serverIDs,
						AllowedTools: allowedTools,
						ExpiresAt:    client.ExpiresAt,
						IsActive:     client.IsActive,
						TTL:          client.AccessTokenTTL,
					}

					// Resolve LLM instruction rows on cache-miss (see
					// scopetoken middleware for the equivalent on the
					// X-MCP-Scope-Token path).
					if instructionRepo != nil && len(client.Instructions) > 0 && len(serverIDs) > 0 {
						allowedSlice := make([]string, 0, len(serverIDs))
						for sid := range serverIDs {
							allowedSlice = append(allowedSlice, sid)
						}
						rows, rerr := instructionRepo.ResolveForOAuth2Client(client.ID, allowedSlice)
						if rerr == nil && len(rows) > 0 {
							cc.Instructions = make([]CachedInstruction, 0, len(rows))
							for _, row := range rows {
								cc.Instructions = append(cc.Instructions, CachedInstruction{
									ID: row.ID, Title: row.Title, Body: row.Body,
								})
							}
						} else if rerr != nil {
							log.Printf("[oauth2] resolve instructions for client %s: %v", client.ID, rerr)
						}
					}

					// Decode persisted Leexi filter for runtime header injection.
					cc.LeexiFilterMode = client.LeexiFilterMode
					if len(client.LeexiAllowedUserUUIDs) > 0 {
						_ = json.Unmarshal(client.LeexiAllowedUserUUIDs, &cc.LeexiAllowedUserUUIDs)
					}
					if len(client.LeexiAllowedTeamUUIDs) > 0 {
						_ = json.Unmarshal(client.LeexiAllowedTeamUUIDs, &cc.LeexiAllowedTeamUUIDs)
					}

					oauth2Cache.Set(clientID, cc)
				}

				if !cc.IsActive {
					http.Error(w, `{"error":"invalid_token","error_description":"client is revoked"}`, http.StatusForbidden)
					notifyUnauthorized(slackClient, r, "revoked oauth2 client")
					return
				}
				if cc.ExpiresAt != nil && cc.ExpiresAt.Before(time.Now()) {
					http.Error(w, `{"error":"invalid_token","error_description":"client has expired"}`, http.StatusForbidden)
					notifyUnauthorized(slackClient, r, "expired oauth2 client")
					return
				}

				ctx := context.WithValue(r.Context(), scopetoken.AllowedServersContextKey, cc.ServerIDs)
				if cc.AllowedTools != nil {
					ctx = context.WithValue(ctx, scopetoken.AllowedToolsContextKey, cc.AllowedTools)
				}
				if cc.Name != "" {
					ctx = context.WithValue(ctx, scopetoken.ScopeNameContextKey, cc.Name)
				}
				if len(cc.Instructions) > 0 {
					resolved := make([]scopetoken.ResolvedInstruction, 0, len(cc.Instructions))
					for _, ci := range cc.Instructions {
						resolved = append(resolved, scopetoken.ResolvedInstruction{ID: ci.ID, Title: ci.Title, Body: ci.Body})
					}
					ctx = context.WithValue(ctx, scopetoken.AllowedInstructionsContextKey, resolved)
				}
				if cc.LeexiFilterMode != "" && cc.LeexiFilterMode != "none" {
					ctx = context.WithValue(ctx, scopetoken.LeexiFilterContextKey, &scopetoken.LeexiFilterContext{
						Mode:             cc.LeexiFilterMode,
						AllowedUserUUIDs: cc.LeexiAllowedUserUUIDs,
						AllowedTeamUUIDs: cc.LeexiAllowedTeamUUIDs,
					})
				}
				next.ServeHTTP(w, r.WithContext(ctx))
				return
			}

			// 2. Check for X-MCP-Scope-Token (backward compat)
			scopeTokenHeader := r.Header.Get("X-MCP-Scope-Token")
			if scopeTokenHeader != "" {
				// Delegate to scope token middleware (always required)
				scopeMW := scopetoken.Middleware(tokenCache, tokenRepo, instructionRepo, true, slackClient)
				scopeMW(next).ServeHTTP(w, r)
				return
			}

			// 3. Neither present — return 401 with discovery URL per MCP spec
			metadataURL := publicURL + "/.well-known/oauth-authorization-server"
			if publicURL == "" {
				metadataURL = "/.well-known/oauth-authorization-server"
			}
			w.Header().Set("WWW-Authenticate", fmt.Sprintf(`Bearer resource_metadata="%s"`, metadataURL))
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusUnauthorized)
			w.Write([]byte(`{"error":"unauthorized","error_description":"authentication required"}`))
			notifyUnauthorized(slackClient, r, "no Authorization header or X-MCP-Scope-Token")
		})
	}
}
