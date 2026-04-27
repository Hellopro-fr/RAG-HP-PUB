package transport

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"sync"

	"github.com/hellopro/mcp-ringover/internal/mcp"
)

// Handler is the interface the SSE server uses to dispatch MCP requests.
type Handler interface {
	Handle(ctx context.Context, req *mcp.Request) *mcp.Response
}

// session holds a single client's SSE response channel.
type session struct {
	id string
	ch chan *mcp.Response
}

// SSEServer exposes three HTTP endpoints:
//
//	GET  /sse     - open SSE stream, receive the message endpoint URL
//	POST /message - send a JSON-RPC request (sessionId query param required)
//	GET  /health  - liveness probe
type SSEServer struct {
	handler Handler

	mu       sync.RWMutex
	sessions map[string]*session
}

func NewSSEServer(h Handler) *SSEServer {
	return &SSEServer{
		handler:  h,
		sessions: make(map[string]*session),
	}
}

// Register attaches the HTTP routes to the given mux.
func (s *SSEServer) Register(mux *http.ServeMux) {
	mux.HandleFunc("/sse", s.handleSSE)
	mux.HandleFunc("/message", s.handleMessage)
	mux.HandleFunc("/health", s.handleHealth)
}

// handleSSE opens a new SSE stream for the connecting client.
func (s *SSEServer) handleSSE(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming not supported", http.StatusInternalServerError)
		return
	}

	sessionID := newSessionID()
	sess := &session{id: sessionID, ch: make(chan *mcp.Response, 16)}

	s.mu.Lock()
	s.sessions[sessionID] = sess
	s.mu.Unlock()

	defer func() {
		s.mu.Lock()
		delete(s.sessions, sessionID)
		s.mu.Unlock()
		log.Printf("[sse] session closed: %s", sessionID)
	}()

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("Access-Control-Allow-Origin", "*")

	scheme := "http"
	if r.TLS != nil {
		scheme = "https"
	}
	endpointURL := fmt.Sprintf("%s://%s/message?sessionId=%s", scheme, r.Host, sessionID)
	fmt.Fprintf(w, "event: endpoint\ndata: %s\n\n", endpointURL)
	flusher.Flush()

	log.Printf("[sse] client connected: %s", sessionID)

	for {
		select {
		case <-r.Context().Done():
			return
		case resp, ok := <-sess.ch:
			if !ok {
				return
			}
			b, err := json.Marshal(resp)
			if err != nil {
				log.Printf("[sse] marshal error for session %s: %v", sessionID, err)
				continue
			}
			fmt.Fprintf(w, "event: message\ndata: %s\n\n", b)
			flusher.Flush()
		}
	}
}

// handleMessage receives a JSON-RPC request from the client.
func (s *SSEServer) handleMessage(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	sessionID := r.URL.Query().Get("sessionId")
	if sessionID == "" {
		http.Error(w, "missing sessionId", http.StatusBadRequest)
		return
	}

	s.mu.RLock()
	sess, found := s.sessions[sessionID]
	s.mu.RUnlock()
	if !found {
		http.Error(w, "session not found", http.StatusNotFound)
		return
	}

	var req mcp.Request
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid JSON body", http.StatusBadRequest)
		return
	}

	// Enrich context with the gateway-issued allowed-user-ids scope (if any).
	scopedCtx := enrichRequestContext(r)

	go func() {
		resp := s.handler.Handle(context.WithoutCancel(scopedCtx), &req)
		if resp == nil {
			return
		}
		select {
		case sess.ch <- resp:
		default:
			log.Printf("[sse] session %s: response channel full, dropping message", sessionID)
		}
	}()

	w.WriteHeader(http.StatusAccepted)
}

func (s *SSEServer) handleHealth(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	fmt.Fprint(w, `{"status":"ok"}`)
}

func newSessionID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		panic(fmt.Sprintf("crypto/rand failed: %v", err))
	}
	return hex.EncodeToString(b)
}
