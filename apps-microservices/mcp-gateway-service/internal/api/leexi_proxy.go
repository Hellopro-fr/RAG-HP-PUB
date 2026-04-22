package api

import (
	"net/http"
)

// handleLeexiUsers exposes the Leexi user list (proxied from
// mcp-leexi-service) to authenticated gateway admins. Used by the token /
// OAuth2 client creation forms to populate the Leexi user picker.
//
//	GET /api/v1/leexi/users
//	Response: { "users": [ {uuid, email, first_name, last_name, team_uuid, team_name}, ... ] }
//
// 503 is returned when the integration is disabled (env vars unset).
func (h *Handler) handleLeexiUsers(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	if h.leexiAdmin == nil || !h.leexiAdmin.Enabled() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"error": "Leexi integration is not configured (set LEEXI_INTERNAL_URL and LEEXI_ADMIN_TOKEN)",
		})
		return
	}

	users, err := h.leexiAdmin.ListUsers(r.Context(), false)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"users": users})
}

// handleLeexiTeams returns the distinct teams derived from the Leexi user
// list. Same auth/disable semantics as handleLeexiUsers.
//
//	GET /api/v1/leexi/teams
//	Response: { "teams": [ {uuid, name}, ... ] }
func (h *Handler) handleLeexiTeams(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	if h.leexiAdmin == nil || !h.leexiAdmin.Enabled() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"error": "Leexi integration is not configured (set LEEXI_INTERNAL_URL and LEEXI_ADMIN_TOKEN)",
		})
		return
	}

	teams, err := h.leexiAdmin.ListTeams(r.Context(), false)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"teams": teams})
}
