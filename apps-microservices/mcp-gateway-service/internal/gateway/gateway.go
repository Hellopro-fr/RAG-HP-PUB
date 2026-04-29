package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/leexiadmin"
	"github.com/hellopro/mcp-gateway/internal/mcp"
	"github.com/hellopro/mcp-gateway/internal/ringoveradmin"
	"github.com/hellopro/mcp-gateway/internal/transport"
)

// BDDTableResolver resolves a bdd_used_tables.id to its (database_id,
// table_name) tuple. The interface keeps the gateway free of any direct
// repository dependency — main.go injects a *repository.BDDUsedRepo (which
// satisfies it) at startup.
type BDDTableResolver interface {
	GetTable(ctx context.Context, id string) (*db.BDDUsedTable, error)
}

// Gateway routes MCP JSON-RPC requests to the appropriate backend servers.
type Gateway struct {
	name          string
	version       string
	registry      *Registry
	leexiAdmin    *leexiadmin.Client    // optional; nil disables Leexi team expansion
	ringoverAdmin *ringoveradmin.Client // optional; nil disables Ringover team expansion
	bddResolver   BDDTableResolver      // optional; nil disables BDD header injection
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

	g.registry.Register(srv)
	log.Printf("[gateway] registered backend: %s (%s %s) [%s] id=%s", url, srv.Name, srv.Version, srv.TransportType, id)
	return nil
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
