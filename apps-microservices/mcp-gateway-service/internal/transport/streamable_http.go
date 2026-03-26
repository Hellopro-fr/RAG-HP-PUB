package transport

import (
	"encoding/json"
	"log"
	"net/http"

	"github.com/hellopro/mcp-gateway/internal/mcp"
)

// StreamableHTTPServer exposes a POST /mcp endpoint that handles
// JSON-RPC requests synchronously (streamable HTTP transport).
type StreamableHTTPServer struct {
	handler Handler
}

func NewStreamableHTTPServer(h Handler) *StreamableHTTPServer {
	return &StreamableHTTPServer{handler: h}
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

	resp := s.handler.Handle(r.Context(), &req)

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("[streamable-http] encode error: %v", err)
	}
}
