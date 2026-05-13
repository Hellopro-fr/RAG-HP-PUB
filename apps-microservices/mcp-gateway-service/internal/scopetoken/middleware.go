package scopetoken

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"time"

	"mcp-gateway/internal/repository"
	"mcp-gateway/internal/slack"
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
		ClientIP:     ip,
		Endpoint:     endpoint,
		Reason:       reason,
		MCPSessionID: r.Header.Get("Mcp-Session-Id"),
		UserAgent:    r.Header.Get("User-Agent"),
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

// RingoverFilterContextKey carries a *RingoverFilterContext describing the
// per-request Ringover user scope. Read by gateway.ScopedGateway when
// forwarding a tools/call to a Ringover-tagged backend.
const RingoverFilterContextKey = "scope_ringover_filter"

// ZohoFilterContextKey carries a *ZohoFilterContext describing the active
// per-token / per-OAuth2-client Zoho ownership scope. Absence of the key
// means no admin filter is configured (Step 2 of requestHeadersFor sees
// nothing and emits no header). When the imported-server Step 1 path
// fires, this context is ignored.
const ZohoFilterContextKey = "scope_zoho_filter"

// ScopeNameContextKey carries the human-readable name of the active scope
// token or OAuth2 client. ScopedGateway reads it to override serverInfo.name
// on the MCP initialize response so clients see the credential label instead
// of the static gateway name.
const ScopeNameContextKey = "scope_name"

// AllowedInstructionsContextKey carries the resolved LLM instructions selected
// into the active token / OAuth2 client, filtered to those whose linked
// servers intersect the token/client's allowed server set. ScopedGateway
// renders them into the MCP initialize response's `instructions` field.
// Value type: []scopetoken.ResolvedInstruction.
const AllowedInstructionsContextKey = "scope_allowed_instructions"

// ResolvedInstruction is the runtime shape of an LLM instruction carried
// through the request context. Mirrors (but doesn't import) the CachedInstruction
// shape of both the scopetoken and oauth2 caches so either middleware can fill
// it without a cross-package dependency.
type ResolvedInstruction struct {
	ID    string
	Title string
	Body  string
}

// AllowedInstructionsFromContext returns the resolved instruction list, if any.
// The boolean return lets callers distinguish "no key set" from "empty list".
func AllowedInstructionsFromContext(ctx context.Context) ([]ResolvedInstruction, bool) {
	v, ok := ctx.Value(AllowedInstructionsContextKey).([]ResolvedInstruction)
	return v, ok
}

// EndUserEmailContextKey carries the authenticated end-user's email captured
// at OAuth2 login time. Only the bearer-token branch of the OAuth2 middleware
// sets this value (authorization_code / refresh_token grants); X-MCP-Scope-Token
// requests and client_credentials grants leave it absent. ScopedGateway reads
// it to resolve filter mode "self" at request time.
const EndUserEmailContextKey = "scope_end_user_email"

// EndUserEmailFromContext returns the end-user email captured during OAuth2
// login, plus a boolean to distinguish "missing" from "explicitly empty". A
// non-string stored value is treated as missing — defensive in depth.
func EndUserEmailFromContext(ctx context.Context) (string, bool) {
	v, ok := ctx.Value(EndUserEmailContextKey).(string)
	if !ok || v == "" {
		return "", false
	}
	return v, true
}

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

// RingoverFilterContext is the runtime view of the persisted Ringover scope.
type RingoverFilterContext struct {
	Mode           string
	AllowedUserIDs []int
	AllowedTeamIDs []int
}

// RingoverFilterFromContext returns the typed Ringover filter info if any was set.
func RingoverFilterFromContext(ctx context.Context) (*RingoverFilterContext, bool) {
	v, ok := ctx.Value(RingoverFilterContextKey).(*RingoverFilterContext)
	return v, ok
}

// ZohoFilterContext is the runtime view of the persisted Zoho scope.
type ZohoFilterContext struct {
	Mode          string   // "none" | "users" | "creator"
	AllowedEmails []string // for mode "users"
	// CreatorEmail is the owning user's email captured at scope-token /
	// OAuth2-client write time. Used only for mode "creator".
	CreatorEmail string
}

// ZohoFilterFromContext returns the typed Zoho filter info if any was set.
func ZohoFilterFromContext(ctx context.Context) (*ZohoFilterContext, bool) {
	v, ok := ctx.Value(ZohoFilterContextKey).(*ZohoFilterContext)
	return v, ok
}

// BDDFilterContextKey carries a []string of bdd_used_tables.id values that
// the active scope token / OAuth2 client is restricted to. ScopedGateway
// reads it and emits X-BDD-Allowed-Tables on outbound MCP requests routed
// to BDD-tagged backends. Absence of the key = no restriction (full access).
const BDDFilterContextKey = "scope_bdd_filter"

// BDDFilterFromContext returns the BDD allow-list if any was set, plus a
// boolean flag distinguishing "no filter" from "filter present but empty".
// An empty slice with ok=true means deny-all (every referenced row was
// deleted); callers must NOT confuse it with no restriction.
func BDDFilterFromContext(ctx context.Context) ([]string, bool) {
	v, ok := ctx.Value(BDDFilterContextKey).([]string)
	return v, ok
}

// Middleware returns an HTTP middleware that validates X-MCP-Scope-Token
// and stores the allowed server IDs, tool selections, and resolved LLM
// instructions in the request context. slackClient is optional; when set,
// every 401/403 fires an UnauthorizedEvent (rate-limited inside the client).
// instructionRepo may be nil — scoping works without it; only the MCP
// initialize `instructions` field is empty in that case.
func Middleware(cache *Cache, repo *repository.TokenRepo, instructionRepo *repository.InstructionRepo, required bool, slackClient *slack.Client) func(http.Handler) http.Handler {
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

				// Resolve LLM instruction rows once per cache-miss. The
				// repo flattens the token's picked pages into rows and filters
				// each row by its own server scope, so the cache only ever
				// holds renderable content.
				if instructionRepo != nil && len(dbToken.Instructions) > 0 && len(serverIDs) > 0 {
					allowedSlice := make([]string, 0, len(serverIDs))
					for sid := range serverIDs {
						allowedSlice = append(allowedSlice, sid)
					}
					rows, err := instructionRepo.ResolveForToken(dbToken.ID, allowedSlice)
					if err == nil && len(rows) > 0 {
						ct.Instructions = make([]CachedInstruction, 0, len(rows))
						for _, row := range rows {
							ct.Instructions = append(ct.Instructions, CachedInstruction{
								ID: row.ID, Title: row.Title, Body: row.Body,
							})
						}
					} else if err != nil {
						log.Printf("[scope] resolve instructions for token %s: %v", dbToken.ID, err)
					}
				}

				// Decode persisted Leexi filter (JSON columns) into typed slices.
				ct.LeexiFilterMode = dbToken.LeexiFilterMode
				if len(dbToken.LeexiAllowedUserUUIDs) > 0 {
					_ = json.Unmarshal(dbToken.LeexiAllowedUserUUIDs, &ct.LeexiAllowedUserUUIDs)
				}
				if len(dbToken.LeexiAllowedTeamUUIDs) > 0 {
					_ = json.Unmarshal(dbToken.LeexiAllowedTeamUUIDs, &ct.LeexiAllowedTeamUUIDs)
				}

				// Decode persisted Ringover filter (JSON columns of ints).
				ct.RingoverFilterMode = dbToken.RingoverFilterMode
				if len(dbToken.RingoverAllowedUserIDs) > 0 {
					_ = json.Unmarshal(dbToken.RingoverAllowedUserIDs, &ct.RingoverAllowedUserIDs)
				}
				if len(dbToken.RingoverAllowedTeamIDs) > 0 {
					_ = json.Unmarshal(dbToken.RingoverAllowedTeamIDs, &ct.RingoverAllowedTeamIDs)
				}

				// Decode persisted Zoho filter for runtime header injection.
				ct.ZohoFilterMode = dbToken.ZohoFilterMode
				if len(dbToken.ZohoAllowedEmails) > 0 {
					_ = json.Unmarshal(dbToken.ZohoAllowedEmails, &ct.ZohoAllowedEmails)
				}
				if ct.ZohoFilterMode == "creator" {
					ct.ZohoCreatorEmail = dbToken.CreatedBy
				}

				// BDD scope: flatten the join rows into a flat slice of IDs.
				// Empty slice = no restriction; the runtime injector keys off
				// the presence of the slice (len > 0), see ScopedGateway.
				if len(dbToken.BDDTables) > 0 {
					ct.BDDAllowedTableIDs = make([]string, 0, len(dbToken.BDDTables))
					for _, b := range dbToken.BDDTables {
						ct.BDDAllowedTableIDs = append(ct.BDDAllowedTableIDs, b.UsedTableID)
					}
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
			if len(ct.Instructions) > 0 {
				resolved := make([]ResolvedInstruction, 0, len(ct.Instructions))
				for _, ci := range ct.Instructions {
					resolved = append(resolved, ResolvedInstruction{ID: ci.ID, Title: ci.Title, Body: ci.Body})
				}
				ctx = context.WithValue(ctx, AllowedInstructionsContextKey, resolved)
			}
			if ct.LeexiFilterMode != "" && ct.LeexiFilterMode != "none" {
				ctx = context.WithValue(ctx, LeexiFilterContextKey, &LeexiFilterContext{
					Mode:             ct.LeexiFilterMode,
					AllowedUserUUIDs: ct.LeexiAllowedUserUUIDs,
					AllowedTeamUUIDs: ct.LeexiAllowedTeamUUIDs,
				})
			}
			if ct.RingoverFilterMode != "" && ct.RingoverFilterMode != "none" {
				ctx = context.WithValue(ctx, RingoverFilterContextKey, &RingoverFilterContext{
					Mode:           ct.RingoverFilterMode,
					AllowedUserIDs: ct.RingoverAllowedUserIDs,
					AllowedTeamIDs: ct.RingoverAllowedTeamIDs,
				})
			}
			if ct.ZohoFilterMode != "" && ct.ZohoFilterMode != "none" {
				ctx = context.WithValue(ctx, ZohoFilterContextKey, &ZohoFilterContext{
					Mode:          ct.ZohoFilterMode,
					AllowedEmails: ct.ZohoAllowedEmails,
					CreatorEmail:  ct.ZohoCreatorEmail,
				})
			}
			if len(ct.BDDAllowedTableIDs) > 0 {
				ctx = context.WithValue(ctx, BDDFilterContextKey, ct.BDDAllowedTableIDs)
			}
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}
