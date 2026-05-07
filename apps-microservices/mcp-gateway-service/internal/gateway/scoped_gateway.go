package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strconv"
	"strings"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/leexiadmin"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/ringoveradmin"
	"mcp-gateway/internal/scopetoken"
	"mcp-gateway/internal/transport"
)

// gatewayUserFinder abstracts the slice of *repository.UserRepo that the
// auto-self override needs (admin-role lookup by email). Defining it as an
// interface lets tests substitute an in-memory fake without spinning up GORM.
type gatewayUserFinder interface {
	GetByEmail(email string) (*db.GatewayUser, error)
}

// serverAuthorizer abstracts repository.ServerAuthorizationRepo. Defining as
// an interface keeps tests in the gateway package free of GORM. nil disables
// Step-0 bypass — the gateway falls through to auto-self override + admin
// config like before.
type serverAuthorizer interface {
	IsAuthorized(serverID, email string) bool
}

// leexiToolPrefix is the convention used when registering the Leexi backend.
// When a backend's ToolPrefix matches this string, the scoped gateway treats
// it as the Leexi backend for the purposes of participant-scope header injection.
const leexiToolPrefix = "leexi"

// ringoverToolPrefix is the ToolPrefix matched to inject the Ringover
// user-scope header onto outbound MCP requests.
const ringoverToolPrefix = "ringover"

// bddToolPrefix is the convention used when registering BDD-tagged backends.
// Mirrors leexiToolPrefix — every backend whose ToolPrefix matches this
// string receives the X-BDD-Allowed-Tables header when the active token /
// OAuth2 client declares a BDD scope.
const bddToolPrefix = "bdd"

// LeexiAllowedParticipantsHeader mirrors the constant defined in mcp-leexi-service
// (transport.AllowedParticipantsHeader). Duplicated here to avoid a cross-module
// import; both sides MUST stay in sync.
const LeexiAllowedParticipantsHeader = "X-Leexi-Allowed-Participants"

// RingoverAllowedUserIDsHeader mirrors the constant defined in
// mcp-ringover-service (transport.AllowedUserIDsHeader). Both sides MUST stay
// in sync.
const RingoverAllowedUserIDsHeader = "X-Ringover-Allowed-User-IDs"

// BDDAllowedTablesHeader is the JSON-encoded allow-list passed downstream to
// BDD-tagged backends. Same duplication caveat as the Leexi header — both
// sides of the contract live in different services and must stay in sync.
const BDDAllowedTablesHeader = "X-BDD-Allowed-Tables"

// ScopedGateway wraps a Gateway but filters results to only the allowed server IDs
// and optionally to specific tools per server.
// It implements the transport.Handler interface.
type ScopedGateway struct {
	name         string
	version      string
	registry     *Registry
	allowedIDs   map[string]bool
	allowedTools map[string]map[string]bool // server_id → tool_name → true; nil = all tools
	// instructions are the LLM instruction snippets the token / OAuth2 client
	// has selected (already filtered by allowed servers upstream). Rendered into
	// the MCP initialize response's `instructions` field.
	instructions []InstructionView
	// leexiAdmin (optional) is used to expand "teams" filter mode to user
	// UUIDs at request time. nil = no team expansion (treat empty list).
	leexiAdmin *leexiadmin.Client
	// ringoverAdmin (optional) — same role as leexiAdmin for Ringover.
	ringoverAdmin *ringoveradmin.Client
	// bddResolver (optional) translates bdd_used_tables.id values into
	// (database_id, table_name) pairs for the X-BDD-Allowed-Tables header.
	// nil = fail-closed: when the token has a BDD scope, an empty allow-list
	// is sent so the backend denies every BDD call.
	bddResolver BDDTableResolver
	// gatewayUsers (optional) is consulted by auto-self override to learn
	// whether an authenticated end-user is a gateway admin. nil disables the
	// admin-fallback branch — non-admin behavior applies to everyone.
	gatewayUsers gatewayUserFinder
	// serverAuth (optional) is consulted by the Step-0 bypass in
	// requestHeadersFor. When the end-user has a full-access grant for the
	// target backend, every filter header is skipped. nil disables Step-0.
	serverAuth serverAuthorizer
}

// NewScopedGateway creates a handler that only exposes tools/resources/prompts
// from the given server IDs, optionally filtered to specific tools per server.
// instructions may be nil/empty — the composer then returns an empty string
// and the initialize response omits the `instructions` field.
func NewScopedGateway(gw *Gateway, allowedServerIDs map[string]bool, allowedTools map[string]map[string]bool, instructions []InstructionView) *ScopedGateway {
	return &ScopedGateway{
		name:          gw.name,
		version:       gw.version,
		registry:      gw.registry,
		allowedIDs:    allowedServerIDs,
		allowedTools:  allowedTools,
		instructions:  instructions,
		leexiAdmin:    gw.leexiAdmin,
		ringoverAdmin: gw.ringoverAdmin,
		bddResolver:   gw.bddResolver,
		gatewayUsers:  gw.gatewayUsers,
		serverAuth:    gw.serverAuth,
	}
}

// Handle dispatches a JSON-RPC request with scope filtering.
func (sg *ScopedGateway) Handle(ctx context.Context, req *mcp.Request) *mcp.Response {
	switch req.Method {
	case "initialize":
		return sg.handleInitialize(ctx, req)
	case "tools/list":
		return sg.handleToolsList(req)
	case "tools/call":
		return sg.handleToolsCall(ctx, req)
	case "resources/list":
		return sg.handleResourcesList(req)
	case "resources/read":
		return sg.handleResourcesRead(ctx, req)
	case "prompts/list":
		return sg.handlePromptsList(req)
	case "prompts/get":
		return sg.handlePromptsGet(ctx, req)
	default:
		return errorResp(req.ID, mcp.ErrMethodNotFound, fmt.Sprintf("method not found: %s", req.Method))
	}
}

func (sg *ScopedGateway) handleInitialize(ctx context.Context, req *mcp.Request) *mcp.Response {
	caps := sg.registry.MergedCapabilitiesFiltered(sg.allowedIDs)
	if caps.Tools == nil {
		caps.Tools = &mcp.ToolsCapability{}
	}
	name := sg.name
	if v, ok := ctx.Value(scopetoken.ScopeNameContextKey).(string); ok && v != "" {
		name = v
	}
	result := mcp.InitializeResult{
		ProtocolVersion: mcp.ProtocolVersion,
		Capabilities:    caps,
		ServerInfo:      mcp.Implementation{Name: name, Version: sg.version},
		Instructions:    ComposeInstructions(sg.instructions, name),
	}
	return okResp(req.ID, result)
}

func (sg *ScopedGateway) handleToolsList(req *mcp.Request) *mcp.Response {
	tools := sg.registry.MergedToolsFilteredWithTools(sg.allowedIDs, sg.allowedTools)
	if tools == nil {
		tools = []mcp.Tool{}
	}
	return okResp(req.ID, mcp.ListToolsResult{Tools: tools})
}

func (sg *ScopedGateway) handleToolsCall(ctx context.Context, req *mcp.Request) *mcp.Response {
	var params mcp.CallToolParams
	if err := json.Unmarshal(req.Params, &params); err != nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, "invalid params")
	}

	backend, originalName := sg.registry.FindByToolFilteredWithTools(params.Name, sg.allowedIDs, sg.allowedTools)
	if backend == nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, fmt.Sprintf("unknown tool: %s", params.Name))
	}

	// Compute per-request backend headers, starting from the static auth
	// headers configured at registration. Augment with the Leexi participant-scope
	// header when the request is bound for the Leexi backend AND the active
	// scope token / OAuth2 client declares a participant filter.
	headers := sg.requestHeadersFor(ctx, backend)

	// Forward with the original (unprefixed) tool name to the backend
	backendParams := mcp.CallToolParams{Name: originalName, Arguments: params.Arguments}
	client := transport.NewBackendClientWithEndpoint(backend.MessageURL, headers)
	result, err := client.CallTool(ctx, backendParams)
	if err != nil {
		return errorResp(req.ID, mcp.ErrInternalError, err.Error())
	}
	return okResp(req.ID, result)
}

// requestHeadersFor returns the set of headers to send to backend on this
// particular tool call. It clones backend.AuthHeaders so the static map is
// never mutated, and adds the per-backend ownership headers when applicable
// (X-Leexi-Allowed-Participants for the Leexi backend, X-BDD-Allowed-Tables
// for BDD-tagged backends).
func (sg *ScopedGateway) requestHeadersFor(ctx context.Context, backend *BackendServer) map[string]string {
	headers := make(map[string]string, len(backend.AuthHeaders)+1)
	for k, v := range backend.AuthHeaders {
		headers[k] = v
	}

	// Step 0 — server-level full-access grant. When the end-user is granted
	// unfiltered access on this specific server, skip every filter header
	// and let the backend treat the call as unrestricted. Per-server (matched
	// by backend.ID) and per-email (from EndUserEmailContextKey).
	if sg.isServerAuthorized(ctx, backend.ID) {
		log.Printf("[scoped] server-authorization bypass for backend %s", backend.ID)
		return headers
	}

	switch backend.ToolPrefix {
	case leexiToolPrefix:
		sg.injectLeexiHeader(ctx, headers)
	case ringoverToolPrefix:
		sg.injectRingoverHeader(ctx, headers)
	case bddToolPrefix:
		sg.injectBDDHeader(ctx, headers)
	}
	return headers
}

// isServerAuthorized returns true when the request's end-user has an explicit
// full-access grant for this server. Returns false when:
//   - serverAuthorizer is not configured (boot-time choice)
//   - no email in context (client_credentials grant — there's no user to
//     match a grant against)
//   - email is in context but no row in server_authorizations
func (sg *ScopedGateway) isServerAuthorized(ctx context.Context, serverID string) bool {
	if sg.serverAuth == nil {
		return false
	}
	email, ok := scopetoken.EndUserEmailFromContext(ctx)
	if !ok {
		return false
	}
	return sg.serverAuth.IsAuthorized(serverID, email)
}

// injectLeexiHeader resolves the active Leexi filter and writes the
// X-Leexi-Allowed-Participants header. Mutates the headers map in place.
//
// Resolution order:
//  1. Auto-self override — when the request carries an end-user email and
//     that email maps to a Leexi user, the request is locked to that user
//     regardless of the admin-configured filter (per-backend independent).
//  2. Admin-configured filter — used when no email is on context (typically
//     a client_credentials grant) OR when the end-user is a gateway admin
//     without a Leexi account.
//  3. Otherwise (email present, no Leexi match, not a gateway admin) —
//     deny-sentinel so the downstream service rejects every call.
func (sg *ScopedGateway) injectLeexiHeader(ctx context.Context, headers map[string]string) {
	// Step 1 — auto-self override (per-backend independent).
	if uuid, denied := sg.tryAutoSelfLeexi(ctx); uuid != "" {
		headers[LeexiAllowedParticipantsHeader] = uuid
		return
	} else if denied {
		log.Printf("[scoped] leexi auto-self denied: end-user has no Leexi match and is not a gateway admin")
		headers[LeexiAllowedParticipantsHeader] = "00000000-0000-0000-0000-000000000000"
		return
	}

	// Step 2 — admin-configured filter (existing path; reached when no email
	// in context OR end-user is a gateway admin without a Leexi account).
	filter, ok := scopetoken.LeexiFilterFromContext(ctx)
	if !ok || filter == nil {
		return
	}
	participants := sg.resolveLeexiParticipants(ctx, filter)
	if len(participants) == 0 {
		log.Printf("[scoped] leexi filter mode=%q resolved to empty allow-list — sending deny sentinel", filter.Mode)
		headers[LeexiAllowedParticipantsHeader] = "00000000-0000-0000-0000-000000000000"
		return
	}
	headers[LeexiAllowedParticipantsHeader] = strings.Join(participants, ",")
}

// tryAutoSelfLeexi runs the auto-self override for the Leexi backend. Return
// values:
//   - (uuid, false) — override succeeded, caller should inject the UUID.
//   - ("", true)    — email present, no Leexi match, end-user is not a
//     gateway admin → caller should inject deny-sentinel.
//   - ("", false)   — no email OR end-user is a gateway admin → caller should
//     fall through to the admin-configured filter.
func (sg *ScopedGateway) tryAutoSelfLeexi(ctx context.Context) (string, bool) {
	email, ok := scopetoken.EndUserEmailFromContext(ctx)
	if !ok {
		return "", false
	}
	if sg.leexiAdmin == nil || !sg.leexiAdmin.Enabled() {
		return "", false
	}
	user, err := sg.leexiAdmin.FindUserByEmail(ctx, email)
	if err == nil {
		return user.UUID, false
	}
	if sg.isGatewayAdmin(email) {
		return "", false
	}
	return "", true
}

// isGatewayAdmin returns true when the email belongs to a gateway_users row
// with Role=admin. Returns false when the repo isn't configured, the row is
// missing, or the role is anything else.
func (sg *ScopedGateway) isGatewayAdmin(email string) bool {
	if sg.gatewayUsers == nil {
		return false
	}
	user, err := sg.gatewayUsers.GetByEmail(email)
	if err != nil || user == nil {
		return false
	}
	return user.Role == auth.RoleAdmin
}

// injectRingoverHeader is the Ringover-side mirror of injectLeexiHeader:
// auto-self override first, admin-configured filter second, deny-sentinel
// for non-admin end-users without a Ringover match. See injectLeexiHeader
// for the full resolution-order rationale.
func (sg *ScopedGateway) injectRingoverHeader(ctx context.Context, headers map[string]string) {
	// Step 1 — auto-self override (per-backend independent).
	if id, denied := sg.tryAutoSelfRingover(ctx); id != "" {
		headers[RingoverAllowedUserIDsHeader] = id
		return
	} else if denied {
		log.Printf("[scoped] ringover auto-self denied: end-user has no Ringover match and is not a gateway admin")
		headers[RingoverAllowedUserIDsHeader] = "0"
		return
	}

	// Step 2 — admin-configured filter (existing path).
	filter, ok := scopetoken.RingoverFilterFromContext(ctx)
	if !ok || filter == nil {
		return
	}
	ids := sg.resolveRingoverAllowedUsers(ctx, filter)
	if len(ids) == 0 {
		log.Printf("[scoped] ringover filter mode=%q resolved to empty allow-list — sending deny sentinel", filter.Mode)
		headers[RingoverAllowedUserIDsHeader] = "0"
		return
	}
	parts := make([]string, len(ids))
	for i, id := range ids {
		parts[i] = strconv.Itoa(id)
	}
	headers[RingoverAllowedUserIDsHeader] = strings.Join(parts, ",")
}

// tryAutoSelfRingover mirrors tryAutoSelfLeexi for the Ringover backend.
func (sg *ScopedGateway) tryAutoSelfRingover(ctx context.Context) (string, bool) {
	email, ok := scopetoken.EndUserEmailFromContext(ctx)
	if !ok {
		return "", false
	}
	if sg.ringoverAdmin == nil || !sg.ringoverAdmin.Enabled() {
		return "", false
	}
	user, err := sg.ringoverAdmin.FindUserByEmail(ctx, email)
	if err == nil {
		return strconv.Itoa(user.UserID), false
	}
	if sg.isGatewayAdmin(email) {
		return "", false
	}
	return "", true
}

// injectBDDHeader resolves the active BDD allow-list (a slice of
// bdd_used_tables.id values) into a JSON array of {database_id, table_name}
// pairs and writes the X-BDD-Allowed-Tables header. Behaviour:
//   - No BDD scope on the request → no header (full access).
//   - Filter set, every referenced ID resolves successfully → header with the
//     full list.
//   - Filter set, some/all IDs absent from the registry (deleted upstream)
//     → header with whatever resolved; if nothing resolved, an empty JSON
//     array is sent so the backend denies every call (fail-closed).
//   - bddResolver not configured but filter set → empty array (also fail-closed).
func (sg *ScopedGateway) injectBDDHeader(ctx context.Context, headers map[string]string) {
	ids, ok := scopetoken.BDDFilterFromContext(ctx)
	if !ok {
		return
	}
	pairs := sg.resolveBDDPairs(ctx, ids)
	encoded, err := json.Marshal(pairs)
	if err != nil {
		// json.Marshal of []bddTablePair never fails in practice. Log and
		// fall back to a safe deny-all so we never accidentally lift the
		// scope on a transient error.
		log.Printf("[scoped] marshal bdd allow-list: %v", err)
		headers[BDDAllowedTablesHeader] = "[]"
		return
	}
	headers[BDDAllowedTablesHeader] = string(encoded)
	if len(pairs) == 0 {
		log.Printf("[scoped] bdd filter resolved to empty allow-list — sending deny-all (header=[])")
	}
}

// bddTablePair is the wire shape for a single entry in X-BDD-Allowed-Tables.
// Mirrors the contract documented in the task brief: numeric database id +
// catalog table name, no other metadata.
type bddTablePair struct {
	DatabaseID int    `json:"database_id"`
	TableName  string `json:"table_name"`
}

// resolveBDDPairs translates a slice of bdd_used_tables.id values into the
// corresponding (database_id, table_name) tuples. Missing rows (deleted
// in the registry between cache load and this call) are skipped silently —
// the caller decides what an empty result means.
func (sg *ScopedGateway) resolveBDDPairs(ctx context.Context, ids []string) []bddTablePair {
	if sg.bddResolver == nil {
		return nil
	}
	out := make([]bddTablePair, 0, len(ids))
	for _, id := range ids {
		row, err := sg.bddResolver.GetTable(ctx, id)
		if err != nil {
			log.Printf("[scoped] bdd resolve id=%s: %v (skipped)", id, err)
			continue
		}
		out = append(out, bddTablePair{DatabaseID: row.DatabaseID, TableName: row.Name})
	}
	return out
}

// resolveLeexiParticipants turns a (mode, allowed-users, allowed-teams) tuple
// into a flat list of participant UUIDs to authorise. For "teams" mode it
// consults the leexiadmin client cache; for the other modes it simply returns
// the stored user UUIDs.
func (sg *ScopedGateway) resolveLeexiParticipants(ctx context.Context, f *scopetoken.LeexiFilterContext) []string {
	switch f.Mode {
	case "users", "creator":
		return f.AllowedUserUUIDs
	case "teams":
		if sg.leexiAdmin == nil || !sg.leexiAdmin.Enabled() {
			log.Printf("[scoped] leexi filter mode=teams but leexiadmin client is not configured")
			return nil
		}
		uuids, err := sg.leexiAdmin.ResolveTeamMembers(ctx, f.AllowedTeamUUIDs)
		if err != nil {
			log.Printf("[scoped] resolve team members: %v", err)
			return nil
		}
		return uuids
	case "self":
		email, ok := scopetoken.EndUserEmailFromContext(ctx)
		if !ok {
			log.Printf("[scoped] leexi filter mode=self but no end-user email on context (likely client_credentials grant) — deny-all")
			return nil
		}
		if sg.leexiAdmin == nil || !sg.leexiAdmin.Enabled() {
			log.Printf("[scoped] leexi filter mode=self but leexiadmin client is not configured")
			return nil
		}
		user, err := sg.leexiAdmin.FindUserByEmail(ctx, email)
		if err != nil {
			log.Printf("[scoped] leexi self-mode: email %q not found: %v", email, err)
			return nil
		}
		return []string{user.UUID}
	default:
		return nil
	}
}

// resolveRingoverAllowedUsers is the Ringover-side mirror of
// resolveLeexiParticipants. Returns the user-id set to inject into the
// outbound header.
func (sg *ScopedGateway) resolveRingoverAllowedUsers(ctx context.Context, f *scopetoken.RingoverFilterContext) []int {
	switch f.Mode {
	case "users", "creator":
		return f.AllowedUserIDs
	case "teams":
		if sg.ringoverAdmin == nil || !sg.ringoverAdmin.Enabled() {
			log.Printf("[scoped] ringover filter mode=teams but ringoveradmin client is not configured")
			return nil
		}
		ids, err := sg.ringoverAdmin.ResolveTeamMembers(ctx, f.AllowedTeamIDs)
		if err != nil {
			log.Printf("[scoped] resolve ringover team members: %v", err)
			return nil
		}
		return ids
	case "self":
		email, ok := scopetoken.EndUserEmailFromContext(ctx)
		if !ok {
			log.Printf("[scoped] ringover filter mode=self but no end-user email on context (likely client_credentials grant) — deny-all")
			return nil
		}
		if sg.ringoverAdmin == nil || !sg.ringoverAdmin.Enabled() {
			log.Printf("[scoped] ringover filter mode=self but ringoveradmin client is not configured")
			return nil
		}
		user, err := sg.ringoverAdmin.FindUserByEmail(ctx, email)
		if err != nil {
			log.Printf("[scoped] ringover self-mode: email %q not found: %v", email, err)
			return nil
		}
		return []int{user.UserID}
	default:
		return nil
	}
}

func (sg *ScopedGateway) handleResourcesList(req *mcp.Request) *mcp.Response {
	resources := sg.registry.MergedResourcesFiltered(sg.allowedIDs)
	if resources == nil {
		resources = []mcp.Resource{}
	}
	return okResp(req.ID, mcp.ListResourcesResult{Resources: resources})
}

func (sg *ScopedGateway) handleResourcesRead(ctx context.Context, req *mcp.Request) *mcp.Response {
	var params mcp.ReadResourceParams
	if err := json.Unmarshal(req.Params, &params); err != nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, "invalid params")
	}

	backend := sg.registry.FindByResourceFiltered(params.URI, sg.allowedIDs)
	if backend == nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, fmt.Sprintf("unknown resource: %s", params.URI))
	}

	client := transport.NewBackendClientWithEndpoint(backend.MessageURL, backend.AuthHeaders)
	result, err := client.ReadResource(ctx, params)
	if err != nil {
		return errorResp(req.ID, mcp.ErrInternalError, err.Error())
	}
	return okResp(req.ID, result)
}

func (sg *ScopedGateway) handlePromptsList(req *mcp.Request) *mcp.Response {
	prompts := sg.registry.MergedPromptsFiltered(sg.allowedIDs)
	if prompts == nil {
		prompts = []mcp.Prompt{}
	}
	return okResp(req.ID, mcp.ListPromptsResult{Prompts: prompts})
}

func (sg *ScopedGateway) handlePromptsGet(ctx context.Context, req *mcp.Request) *mcp.Response {
	var params mcp.GetPromptParams
	if err := json.Unmarshal(req.Params, &params); err != nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, "invalid params")
	}

	backend := sg.registry.FindByPromptFiltered(params.Name, sg.allowedIDs)
	if backend == nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, fmt.Sprintf("unknown prompt: %s", params.Name))
	}

	client := transport.NewBackendClientWithEndpoint(backend.MessageURL, backend.AuthHeaders)
	result, err := client.GetPrompt(ctx, params)
	if err != nil {
		return errorResp(req.ID, mcp.ErrInternalError, err.Error())
	}
	return okResp(req.ID, result)
}
