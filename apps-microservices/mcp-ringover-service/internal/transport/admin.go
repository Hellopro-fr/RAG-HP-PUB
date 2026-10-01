package transport

import (
	"crypto/subtle"
	"encoding/json"
	"log"
	"net/http"

	"github.com/hellopro/mcp-ringover/internal/ringover"
)

// AdminTokenHeader is the HTTP header used to authenticate internal admin
// requests (currently only issued by mcp-gateway-service).
const AdminTokenHeader = "X-Admin-Token"

// AdminServer exposes non-MCP REST endpoints used by the internal admin UI to
// list Ringover users and derive teams. Protected by a shared secret so the
// endpoints are never reachable through misconfiguration.
type AdminServer struct {
	client *ringover.Client
	// token is the shared secret compared in constant-time. When empty, the
	// admin endpoints refuse every request.
	token []byte
}

// NewAdminServer returns an AdminServer bound to the given Ringover client.
// An empty token disables the endpoints entirely.
func NewAdminServer(client *ringover.Client, token string) *AdminServer {
	return &AdminServer{client: client, token: []byte(token)}
}

// Register wires the admin routes on the given mux.
func (s *AdminServer) Register(mux *http.ServeMux) {
	mux.HandleFunc("/admin/users", s.handleUsers)
	mux.HandleFunc("/admin/teams", s.handleTeams)
}

// authorized returns true when the incoming request carries a valid token.
// Constant-time comparison prevents token-length leaks via timing.
func (s *AdminServer) authorized(r *http.Request) bool {
	if len(s.token) == 0 {
		return false
	}
	provided := []byte(r.Header.Get(AdminTokenHeader))
	if len(provided) != len(s.token) {
		return false
	}
	return subtle.ConstantTimeCompare(provided, s.token) == 1
}

func (s *AdminServer) handleUsers(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if !s.authorized(r) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}

	users, err := s.client.FetchAllUsers(r.Context())
	if err != nil {
		log.Printf("[admin] fetch users: %v", err)
		http.Error(w, "upstream error", http.StatusBadGateway)
		return
	}

	writeAdminJSON(w, map[string]any{"users": users, "count": len(users)})
}

func (s *AdminServer) handleTeams(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if !s.authorized(r) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}

	users, err := s.client.FetchAllUsers(r.Context())
	if err != nil {
		log.Printf("[admin] fetch users (for teams): %v", err)
		http.Error(w, "upstream error", http.StatusBadGateway)
		return
	}

	teams := ringover.TeamsFromUsers(users)
	writeAdminJSON(w, map[string]any{"teams": teams, "count": len(teams)})
}

func writeAdminJSON(w http.ResponseWriter, payload any) {
	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(payload); err != nil {
		log.Printf("[admin] encode: %v", err)
	}
}
