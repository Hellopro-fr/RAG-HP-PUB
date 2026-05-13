package transport

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"time"

	mcperr "mcp-zoho-service/internal/mcp"
	"mcp-zoho-service/internal/proxy"
	"mcp-zoho-service/internal/routing"
)

// Server bundles the resolver and runtime config used by POST /mcp.
type Server struct {
	Resolver        *routing.Resolver
	UpstreamTimeout time.Duration
	GatewayToken    string
}

// Routes returns the chained HTTP handler covering /mcp + /health.
func (s *Server) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", s.health)
	mux.HandleFunc("/mcp", s.handleMCP)

	chain := http.Handler(mux)
	chain = adminTokenMiddleware(s.GatewayToken)(chain)
	chain = recoveryMiddleware(chain)
	chain = loggingMiddleware(chain)
	return chain
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write([]byte(`{"status":"ok"}`))
}

// requestEnvelope is the shape used only for ID extraction. Other fields are
// forwarded verbatim to the upstream — we never re-serialise the body.
type requestEnvelope struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
}

func (s *Server) handleMCP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, `{"error":"method_not_allowed"}`, http.StatusMethodNotAllowed)
		return
	}

	// X-End-User-Email is optional: when absent (gateway discovery / health
	// probe), the resolver routes to the admin Zoho row so initialize and
	// tools/list succeed without per-user context. When present, per-user
	// routing takes effect.
	email := r.Header.Get("X-End-User-Email")
	login := r.Header.Get("X-End-User-Login")

	rawBody, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, `{"error":"read_body"}`, http.StatusBadRequest)
		return
	}

	var env requestEnvelope
	_ = json.Unmarshal(rawBody, &env) // ID extraction is best-effort

	log.Printf("[mcp-zoho-service] /mcp method=%s email=%q login=%q body_bytes=%d", env.Method, email, login, len(rawBody))

	res, err := s.Resolver.Resolve(r.Context(), email, login)
	if err != nil {
		log.Printf("[mcp-zoho-service] /mcp method=%s email=%q resolve_error=%v", env.Method, email, err)
		s.writeResolverError(w, env.ID, email, err)
		return
	}

	log.Printf("[mcp-zoho-service] /mcp method=%s email=%q routing_to=%s", env.Method, email, res.UpstreamURL)

	upstream, perr := proxy.ForwardJSONRPC(r.Context(), res.UpstreamURL, res.Headers, bytes.NewReader(rawBody), s.UpstreamTimeout)
	if perr != nil {
		log.Printf("[mcp-zoho-service] upstream error for %s: %v", email, perr)
		body := mcperr.WriteRPCError(rawID(env.ID), mcperr.CodeInternalError, "upstream Zoho error", map[string]string{
			"end_user_email": email,
			"category":       "upstream_error",
			"detail":         perr.Error(),
		})
		writeJSONRPC(w, body)
		return
	}
	defer upstream.Close()

	w.Header().Set("Content-Type", "application/json")
	_, _ = io.Copy(w, upstream)
}

func (s *Server) writeResolverError(w http.ResponseWriter, id json.RawMessage, email string, err error) {
	switch {
	case errors.Is(err, routing.ErrInvalidIdentity):
		http.Error(w, `{"error":"missing_end_user_email"}`, http.StatusBadRequest)
	case errors.Is(err, routing.ErrMisconfigured):
		http.Error(w, `{"error":"misconfigured_admin_row"}`, http.StatusServiceUnavailable)
	case errors.Is(err, routing.ErrNoAdminZohoConfigured):
		body := mcperr.WriteRPCError(rawID(id), mcperr.CodeNoZohoConfigured, "no admin Zoho server configured", map[string]string{
			"end_user_email": email,
			"category":       "no_admin_zoho_configured",
		})
		writeJSONRPC(w, body)
	case errors.Is(err, routing.ErrNoZohoConfigured):
		body := mcperr.WriteRPCError(rawID(id), mcperr.CodeNoZohoConfigured, "no Zoho server configured for "+email, map[string]string{
			"end_user_email": email,
			"category":       "no_zoho_configured",
		})
		writeJSONRPC(w, body)
	default:
		log.Printf("[mcp-zoho-service] resolver error for %s: %v", email, err)
		body := mcperr.WriteRPCError(rawID(id), mcperr.CodeInternalError, "internal resolver error", nil)
		writeJSONRPC(w, body)
	}
}

func writeJSONRPC(w http.ResponseWriter, body []byte) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(body)
}

// rawID converts the inbound id RawMessage into something json.Marshal handles
// inside the error envelope. nil-or-empty rawMessage becomes nil → JSON null.
func rawID(raw json.RawMessage) interface{} {
	if len(raw) == 0 {
		return nil
	}
	return raw
}

// MustListen builds an http.Server on addr with the routes chain installed.
func (s *Server) MustListen(addr string) *http.Server {
	return &http.Server{
		Addr:              addr,
		Handler:           s.Routes(),
		ReadHeaderTimeout: 10 * time.Second,
	}
}
