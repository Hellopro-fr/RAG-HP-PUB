package tools

import (
	"context"
	"encoding/json"
	"log"

	"github.com/hellopro/mcp-classification-produit/internal/mcp"
)

// MCPHandler implements the transport.Handler interface for MCP requests.
type MCPHandler struct {
	name     string
	version  string
	registry *Registry
}

func NewMCPHandler(name, version string, registry *Registry) *MCPHandler {
	return &MCPHandler{
		name:     name,
		version:  version,
		registry: registry,
	}
}

// Handle dispatches an MCP JSON-RPC request and returns a response.
func (h *MCPHandler) Handle(ctx context.Context, req *mcp.Request) *mcp.Response {
	switch req.Method {
	case "initialize":
		return h.handleInitialize(req)
	case "notifications/initialized":
		return nil
	case "tools/list":
		return h.handleToolsList(req)
	case "tools/call":
		return h.handleToolsCall(ctx, req)
	default:
		return h.errorResponse(req.ID, mcp.ErrMethodNotFound, "method not found: "+req.Method)
	}
}

func (h *MCPHandler) handleInitialize(req *mcp.Request) *mcp.Response {
	result := mcp.InitializeResult{
		ProtocolVersion: mcp.ProtocolVersion,
		Capabilities: mcp.ServerCapabilities{
			Tools: &mcp.ToolsCapability{},
		},
		ServerInfo: mcp.Implementation{
			Name:    h.name,
			Version: h.version,
		},
	}

	return h.successResponse(req.ID, result)
}

func (h *MCPHandler) handleToolsList(req *mcp.Request) *mcp.Response {
	result := mcp.ListToolsResult{
		Tools: h.registry.ListTools(),
	}
	return h.successResponse(req.ID, result)
}

func (h *MCPHandler) handleToolsCall(ctx context.Context, req *mcp.Request) *mcp.Response {
	var params mcp.CallToolParams
	if err := json.Unmarshal(req.Params, &params); err != nil {
		return h.errorResponse(req.ID, mcp.ErrInvalidParams, "invalid tool call params")
	}

	log.Printf("[handler] tools/call: %s", params.Name)
	result := h.registry.CallTool(ctx, &params)

	return h.successResponse(req.ID, result)
}

func (h *MCPHandler) successResponse(id json.RawMessage, result any) *mcp.Response {
	b, err := json.Marshal(result)
	if err != nil {
		return h.errorResponse(id, mcp.ErrInternalError, "failed to marshal result")
	}
	return &mcp.Response{
		JSONRPC: "2.0",
		ID:      id,
		Result:  b,
	}
}

func (h *MCPHandler) errorResponse(id json.RawMessage, code int, msg string) *mcp.Response {
	return &mcp.Response{
		JSONRPC: "2.0",
		ID:      id,
		Error:   &mcp.RPCError{Code: code, Message: msg},
	}
}
