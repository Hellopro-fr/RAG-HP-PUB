package transport

import (
	"context"
	"encoding/json"
	"log"
	"net/http"

	"github.com/hellopro/mcp-gateway/internal/mcp"
)

// AllowedServersFromContext retrieves the set of allowed server IDs
// stored by the scope token middleware. Uses the same plain string key.
func AllowedServersFromContext(ctx context.Context) (map[string]bool, bool) {
	ids, ok := ctx.Value("scope_allowed_servers").(map[string]bool)
	return ids, ok
}

// AllowedToolsFromContext retrieves the per-server tool whitelist
// stored by the scope token middleware. Returns nil if not set (= all tools).
func AllowedToolsFromContext(ctx context.Context) map[string]map[string]bool {
	tools, _ := ctx.Value("scope_allowed_tools").(map[string]map[string]bool)
	return tools
}

// ScopeHandlerFactory creates a scoped handler from the request context. The
// factory is responsible for pulling whatever it needs (allowed server IDs,
// tool whitelist, LLM instructions, etc.) from the ctx values set by the
// scope/OAuth2 middleware. Returning nil means "no scope was present — use
// the unscoped handler".
type ScopeHandlerFactory func(ctx context.Context) Handler

// StreamableHTTPServer exposes a POST /mcp endpoint that handles
// JSON-RPC requests synchronously (streamable HTTP transport).
type StreamableHTTPServer struct {
	handler      Handler
	scopeFactory ScopeHandlerFactory
}

func NewStreamableHTTPServer(h Handler) *StreamableHTTPServer {
	return &StreamableHTTPServer{handler: h}
}

// SetScopeFactory sets the factory for creating scoped handlers.
func (s *StreamableHTTPServer) SetScopeFactory(f ScopeHandlerFactory) {
	s.scopeFactory = f
}

// Register attaches the streamable HTTP route to the given mux.
func (s *StreamableHTTPServer) Register(mux *http.ServeMux) {
	mux.HandleFunc("/mcp", s.handleMCP)
	mux.HandleFunc("/mcp/", s.handleMCP)
}

func (s *StreamableHTTPServer) handleMCP(w http.ResponseWriter, r *http.Request) {
	// CORS preflight
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
	w.Header().Set("Access-Control-Allow-Headers", "Content-Type, Authorization")

	if r.Method == http.MethodOptions {
		w.WriteHeader(http.StatusNoContent)
		return
	}

	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	var req mcp.Request
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		log.Printf("[streamable-http] invalid JSON: %v", err)
		http.Error(w, "invalid JSON body", http.StatusBadRequest)
		return
	}

	log.Printf("[streamable-http] %s id=%s", req.Method, string(req.ID))

	// Use scoped handler when the factory finds a scope in context.
	handler := s.handler
	if s.scopeFactory != nil {
		if scoped := s.scopeFactory(r.Context()); scoped != nil {
			handler = scoped
		}
	}

	// Notifications (no id or null id) must not receive a JSON-RPC response.
	// Per MCP spec, the server returns HTTP 202 Accepted with an empty body.
	if len(req.ID) == 0 || string(req.ID) == "null" {
		w.WriteHeader(http.StatusAccepted)
		return
	}

	resp := handler.Handle(r.Context(), &req)

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("[streamable-http] encode error: %v", err)
	}
}
