package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/leexiadmin"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/ringoveradmin"
	"mcp-gateway/internal/transport"
)

// BDDTableResolver resolves a bdd_used_tables.id to its (database_id,
// table_name) tuple. The interface keeps the gateway free of any direct
// repository dependency — main.go injects a *repository.BDDUsedRepo (which
// satisfies it) at startup.
type BDDTableResolver interface {
	GetTable(ctx context.Context, id string) (*db.BDDUsedTable, error)
}

// ZohoUserCatalog returns the per-viewer Zoho tool catalog state. The
// implementation MUST resolve the viewer's role first (admin vs non-admin)
// and consult only the appropriate zoho_imports row — there is no admin-row
// fallback for non-admin viewers. Configured == false means the row is
// missing (or has no tools); the consent screen renders this as
// "Non configuré" with a docs CTA.
type ZohoUserCatalog interface {
	StateForEmail(ctx context.Context, email string) ZohoCatalogState
}

// Gateway routes MCP JSON-RPC requests to the appropriate backend servers.
type Gateway struct {
	name          string
	version       string
	registry      *Registry
	leexiAdmin    *leexiadmin.Client    // optional; nil disables Leexi team expansion
	ringoverAdmin *ringoveradmin.Client // optional; nil disables Ringover team expansion
	bddResolver   BDDTableResolver      // optional; nil disables BDD header injection
	gatewayUsers  gatewayUserFinder     // optional; nil disables auto-self admin fallback
	serverAuth    serverAuthorizer      // optional; nil disables Step-0 server-authorization bypass
	zohoCatalog   ZohoUserCatalog       // optional; nil marks all Zoho backends unconfigured
}

func New(name, version string, registry *Registry) *Gateway {
	return &Gateway{
		name:     name,
		version:  version,
		registry: registry,
	}
}

// SetLeexiAdmin attaches the Leexi admin client used by ScopedGateway to
// resolve "teams" filter mode into user UUIDs at request time. Pass nil to
// disable team expansion.
func (g *Gateway) SetLeexiAdmin(c *leexiadmin.Client) {
	g.leexiAdmin = c
}

// SetRingoverAdmin attaches the Ringover admin client used by ScopedGateway
// to resolve "teams" filter mode into user IDs at request time.
func (g *Gateway) SetRingoverAdmin(c *ringoveradmin.Client) {
	g.ringoverAdmin = c
}

// SetGatewayUserFinder registers the user finder used by auto-self override
// to detect gateway admins. Pass *repository.UserRepo at boot.
func (g *Gateway) SetGatewayUserFinder(f gatewayUserFinder) {
	g.gatewayUsers = f
}

// SetServerAuthorizer registers the per-server full-access grant repository
// consulted by the Step-0 bypass in requestHeadersFor. Pass
// *repository.ServerAuthorizationRepo at boot.
func (g *Gateway) SetServerAuthorizer(s serverAuthorizer) {
	g.serverAuth = s
}

// SetZohoUserCatalog wires the persisted per-viewer Zoho catalog source.
// When set, FetchZohoStateForUser asks the implementation whether the
// viewer's zoho_imports row resolves and what its tools are. Pass nil
// to disable per-viewer resolution (every Zoho backend then renders as
// "Non configuré").
func (g *Gateway) SetZohoUserCatalog(c ZohoUserCatalog) {
	g.zohoCatalog = c
}

// SetBDDResolver attaches the BDD used-table resolver consumed by
// ScopedGateway when injecting X-BDD-Allowed-Tables. Pass nil to disable
// the integration; the scoped gateway then sends an empty allow-list when
// a token has a BDD scope (fail-closed).
func (g *Gateway) SetBDDResolver(r BDDTableResolver) {
	g.bddResolver = r
}

// DiscoverAndRegister connects to a backend MCP server, performs the handshake,
// discovers capabilities, and registers it in the in-memory registry.
// authHeaders are forwarded on every HTTP request to this backend.
func (g *Gateway) DiscoverAndRegister(ctx context.Context, id string, url string, authHeaders map[string]string) error {
	client := transport.NewBackendClient(url, authHeaders)

	if err := client.Connect(ctx); err != nil {
		return fmt.Errorf("connect to backend %s: %w", url, err)
	}

	gatewayInfo := mcp.Implementation{Name: g.name, Version: g.version}
	initResult, err := client.Initialize(ctx, gatewayInfo)
	if err != nil {
		return fmt.Errorf("initialize backend %s: %w", url, err)
	}

	srv := &BackendServer{
		ID:            id,
		URL:           url,
		MessageURL:    client.MessageURL(),
		TransportType: client.TransportType(),
		Name:          initResult.ServerInfo.Name,
		Version:       initResult.ServerInfo.Version,
		Capabilities:  initResult.Capabilities,
		AuthHeaders:   authHeaders,
	}

	// Récupère les outils si supportés.
	if initResult.Capabilities.Tools != nil {
		tools, err := client.ListTools(ctx)
		if err != nil {
			log.Printf("[gateway] warn: list tools from %s: %v", url, err)
		} else {
			// Mark all discovered tools as active by default
			for i := range tools {
				tools[i].IsActive = true
			}
			srv.Tools = tools
		}
	}

	// Récupère les ressources si supportées.
	if initResult.Capabilities.Resources != nil {
		resources, err := client.ListResources(ctx)
		if err != nil {
			log.Printf("[gateway] warn: list resources from %s: %v", url, err)
		} else {
			srv.Resources = resources
		}
	}

	// Récupère les prompts si supportés.
	if initResult.Capabilities.Prompts != nil {
		prompts, err := client.ListPrompts(ctx)
		if err != nil {
			log.Printf("[gateway] warn: list prompts from %s: %v", url, err)
		} else {
			srv.Prompts = prompts
		}
	}

	// Preserve metadata that lives on the registry but wasn't fetched from
	// the upstream init result: TemplateSlug, CreatedBy, Tags. Health-checker
	// re-discovery would otherwise wipe them every probe cycle.
	if prev := g.registry.FindByID(id); prev != nil {
		if srv.TemplateSlug == "" {
			srv.TemplateSlug = prev.TemplateSlug
		}
		if srv.CreatedBy == "" {
			srv.CreatedBy = prev.CreatedBy
		}
		if len(srv.Tags) == 0 {
			srv.Tags = prev.Tags
		}
		if srv.ToolPrefix == "" {
			srv.ToolPrefix = prev.ToolPrefix
		}
	}

	g.registry.Register(srv)
	log.Printf("[gateway] registered backend: %s (%s %s) [%s] id=%s tags=%v", url, srv.Name, srv.Version, srv.TransportType, id, srv.Tags)
	return nil
}

// FetchZohoStateForUser returns the per-viewer Zoho state keyed by
// mcp_servers.id for every registered Zoho-tagged (or zoho-prefixed)
// backend. Each entry's Configured flag indicates whether the viewer
// has a usable zoho_imports row resolved (admin row for admins, user
// row for non-admins). Returns nil only when email is empty or no
// Zoho backend is registered.
//
// When SetZohoUserCatalog has been wired, state comes from the
// persisted zoho_import_tools table via the adapter. Otherwise the
// gateway returns a map where every Zoho backend is marked
// Configured=false (the live HTTP fallback is intentionally removed
// from the consent path — the persisted catalog is the only source
// of truth).
func (g *Gateway) FetchZohoStateForUser(ctx context.Context, email string) map[string]ZohoServerState {
	if email == "" {
		return nil
	}

	var zohoBackends []*BackendServer
	for _, srv := range g.registry.All() {
		if srv.HasTag("zoho") || srv.ToolPrefix == "zoho" {
			zohoBackends = append(zohoBackends, srv)
		}
	}
	if len(zohoBackends) == 0 {
		return nil
	}

	out := make(map[string]ZohoServerState, len(zohoBackends))
	if g.zohoCatalog == nil {
		for _, srv := range zohoBackends {
			out[srv.ID] = ZohoServerState{Configured: false}
		}
		log.Printf("[gateway] consent zoho catalog unwired email=%s — marking all backends unconfigured", email)
		return out
	}

	st := g.zohoCatalog.StateForEmail(ctx, email)
	for _, srv := range zohoBackends {
		out[srv.ID] = ZohoServerState{
			Tools:      st.Tools,
			Configured: st.Configured,
		}
	}
	if st.Configured {
		log.Printf("[gateway] consent zoho catalog email=%s configured=true tool_count=%d", email, len(st.Tools))
	} else {
		log.Printf("[gateway] consent zoho catalog email=%s configured=false — docs CTA", email)
	}
	return out
}

// RegisterFromCache registers a backend from cached DB data (no network call).
func (g *Gateway) RegisterFromCache(srv *BackendServer) {
	g.registry.Register(srv)
	log.Printf("[gateway] registered backend from cache: %s (%s) id=%s", srv.URL, srv.Name, srv.ID)
}

// RegisterBackend is the legacy method for backward compat with env var backends.
// It generates a deterministic ID from the URL.
func (g *Gateway) RegisterBackend(ctx context.Context, url string) error {
	// Utilise l'URL comme ID pour les backends configurés par env var
	return g.DiscoverAndRegister(ctx, "env:"+url, url, nil)
}

// Handle dispatches a JSON-RPC request and returns a response.
func (g *Gateway) Handle(ctx context.Context, req *mcp.Request) *mcp.Response {
	switch req.Method {
	case "initialize":
		return g.handleInitialize(req)
	case "tools/list":
		return g.handleToolsList(req)
	case "tools/call":
		return g.handleToolsCall(ctx, req)
	case "resources/list":
		return g.handleResourcesList(req)
	case "resources/read":
		return g.handleResourcesRead(ctx, req)
	case "prompts/list":
		return g.handlePromptsList(req)
	case "prompts/get":
		return g.handlePromptsGet(ctx, req)
	default:
		return errorResp(req.ID, mcp.ErrMethodNotFound, fmt.Sprintf("method not found: %s", req.Method))
	}
}

func (g *Gateway) handleInitialize(req *mcp.Request) *mcp.Response {
	caps := g.registry.MergedCapabilities()
	// Always advertise at least an empty tools capability so clients know to ask.
	if caps.Tools == nil {
		caps.Tools = &mcp.ToolsCapability{}
	}

	result := mcp.InitializeResult{
		ProtocolVersion: mcp.ProtocolVersion,
		Capabilities:    caps,
		ServerInfo:      mcp.Implementation{Name: g.name, Version: g.version},
	}
	return okResp(req.ID, result)
}

func (g *Gateway) handleToolsList(req *mcp.Request) *mcp.Response {
	tools := g.registry.MergedTools()
	if tools == nil {
		tools = []mcp.Tool{}
	}
	return okResp(req.ID, mcp.ListToolsResult{Tools: tools})
}

func (g *Gateway) handleToolsCall(ctx context.Context, req *mcp.Request) *mcp.Response {
	var params mcp.CallToolParams
	if err := json.Unmarshal(req.Params, &params); err != nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, "invalid params")
	}

	backend, originalName := g.registry.FindByTool(params.Name)
	if backend == nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, fmt.Sprintf("unknown tool: %s", params.Name))
	}

	// Forward with the original (unprefixed) tool name to the backend
	backendParams := mcp.CallToolParams{Name: originalName, Arguments: params.Arguments}
	client := transport.NewBackendClientWithEndpoint(backend.MessageURL, backend.AuthHeaders)
	result, err := client.CallTool(ctx, backendParams)
	if err != nil {
		return errorResp(req.ID, mcp.ErrInternalError, err.Error())
	}
	return okResp(req.ID, result)
}

func (g *Gateway) handleResourcesList(req *mcp.Request) *mcp.Response {
	resources := g.registry.MergedResources()
	if resources == nil {
		resources = []mcp.Resource{}
	}
	return okResp(req.ID, mcp.ListResourcesResult{Resources: resources})
}

func (g *Gateway) handleResourcesRead(ctx context.Context, req *mcp.Request) *mcp.Response {
	var params mcp.ReadResourceParams
	if err := json.Unmarshal(req.Params, &params); err != nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, "invalid params")
	}

	backend := g.registry.FindByResource(params.URI)
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

func (g *Gateway) handlePromptsList(req *mcp.Request) *mcp.Response {
	prompts := g.registry.MergedPrompts()
	if prompts == nil {
		prompts = []mcp.Prompt{}
	}
	return okResp(req.ID, mcp.ListPromptsResult{Prompts: prompts})
}

func (g *Gateway) handlePromptsGet(ctx context.Context, req *mcp.Request) *mcp.Response {
	var params mcp.GetPromptParams
	if err := json.Unmarshal(req.Params, &params); err != nil {
		return errorResp(req.ID, mcp.ErrInvalidParams, "invalid params")
	}

	backend := g.registry.FindByPrompt(params.Name)
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

// ── helpers ───────────────────────────────────────────────────────────────────

func okResp(id json.RawMessage, result any) *mcp.Response {
	b, _ := json.Marshal(result)
	return &mcp.Response{JSONRPC: "2.0", ID: id, Result: b}
}

func errorResp(id json.RawMessage, code int, message string) *mcp.Response {
	return &mcp.Response{
		JSONRPC: "2.0",
		ID:      id,
		Error:   &mcp.RPCError{Code: code, Message: message},
	}
}
