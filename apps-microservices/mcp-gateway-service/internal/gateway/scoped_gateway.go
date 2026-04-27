package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strconv"
	"strings"

	"github.com/hellopro/mcp-gateway/internal/leexiadmin"
	"github.com/hellopro/mcp-gateway/internal/mcp"
	"github.com/hellopro/mcp-gateway/internal/ringoveradmin"
	"github.com/hellopro/mcp-gateway/internal/scopetoken"
	"github.com/hellopro/mcp-gateway/internal/transport"
)

// leexiToolPrefix is the convention used when registering the Leexi backend.
// When a backend's ToolPrefix matches this string, the scoped gateway treats
// it as the Leexi backend for the purposes of participant-scope header injection.
const leexiToolPrefix = "leexi"

// ringoverToolPrefix is the ToolPrefix matched to inject the Ringover
// user-scope header onto outbound MCP requests.
const ringoverToolPrefix = "ringover"

// LeexiAllowedParticipantsHeader mirrors the constant defined in mcp-leexi-service
// (transport.AllowedParticipantsHeader). Duplicated here to avoid a cross-module
// import; both sides MUST stay in sync.
const LeexiAllowedParticipantsHeader = "X-Leexi-Allowed-Participants"

// RingoverAllowedUserIDsHeader mirrors the constant defined in
// mcp-ringover-service (transport.AllowedUserIDsHeader). Both sides MUST stay
// in sync.
const RingoverAllowedUserIDsHeader = "X-Ringover-Allowed-User-IDs"

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
// never mutated, and adds X-Leexi-Allowed-Participants when applicable.
func (sg *ScopedGateway) requestHeadersFor(ctx context.Context, backend *BackendServer) map[string]string {
	headers := make(map[string]string, len(backend.AuthHeaders)+1)
	for k, v := range backend.AuthHeaders {
		headers[k] = v
	}
	switch backend.ToolPrefix {
	case leexiToolPrefix:
		sg.injectLeexiHeader(ctx, headers)
	case ringoverToolPrefix:
		sg.injectRingoverHeader(ctx, headers)
	}
	return headers
}

func (sg *ScopedGateway) injectLeexiHeader(ctx context.Context, headers map[string]string) {
	filter, ok := scopetoken.LeexiFilterFromContext(ctx)
	if !ok || filter == nil {
		return
	}
	participants := sg.resolveLeexiParticipants(ctx, filter)
	if len(participants) == 0 {
		// Resolution returned nothing — for "users"/"creator" this means an
		// empty allow-list (deny everything); pass a sentinel the downstream
		// service interprets as "no calls allowed". Sending an empty header
		// would be ambiguous, so we send a clearly invalid UUID.
		log.Printf("[scoped] leexi filter mode=%q resolved to empty allow-list — sending deny sentinel", filter.Mode)
		headers[LeexiAllowedParticipantsHeader] = "00000000-0000-0000-0000-000000000000"
		return
	}
	headers[LeexiAllowedParticipantsHeader] = strings.Join(participants, ",")
}

func (sg *ScopedGateway) injectRingoverHeader(ctx context.Context, headers map[string]string) {
	filter, ok := scopetoken.RingoverFilterFromContext(ctx)
	if !ok || filter == nil {
		return
	}
	ids := sg.resolveRingoverAllowedUsers(ctx, filter)
	if len(ids) == 0 {
		// Deny-all sentinel: "0" is never a real Ringover user_id, so the
		// downstream service treats it as "allow no users".
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
