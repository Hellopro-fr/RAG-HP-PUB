package transport

import (
	"encoding/json"
	"log"
	"net/http"

	"github.com/hellopro/mcp-leexi/internal/mcp"
)

// StreamableHTTPServer implements the MCP Streamable HTTP transport.
type StreamableHTTPServer struct {
	handler Handler
}

func NewStreamableHTTPServer(h Handler) *StreamableHTTPServer {
	return &StreamableHTTPServer{handler: h}
}

// Register attaches the /mcp route to the given mux.
func (s *StreamableHTTPServer) Register(mux *http.ServeMux) {
	mux.HandleFunc("/mcp", s.handleMCP)
}

func (s *StreamableHTTPServer) handleMCP(w http.ResponseWriter, r *http.Request) {
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
		writeJSONRPCError(w, nil, mcp.ErrParseError, "invalid JSON body")
		return
	}

	log.Printf("[streamable-http] %s (id=%s)", req.Method, string(req.ID))

	ctx := enrichRequestContext(r)

	if len(req.ID) == 0 || string(req.ID) == "null" {
		_ = s.handler.Handle(ctx, &req)
		w.WriteHeader(http.StatusAccepted)
		return
	}

	resp := s.handler.Handle(ctx, &req)
	if resp == nil {
		w.WriteHeader(http.StatusAccepted)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		log.Printf("[streamable-http] encode error: %v", err)
	}
}

func writeJSONRPCError(w http.ResponseWriter, id json.RawMessage, code int, msg string) {
	resp := &mcp.Response{
		JSONRPC: "2.0",
		ID:      id,
		Error:   &mcp.RPCError{Code: code, Message: msg},
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(resp)
}
