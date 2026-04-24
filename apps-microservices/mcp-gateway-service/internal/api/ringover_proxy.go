package api

import (
	"net/http"
)

// handleRingoverUsers exposes the Ringover user list (proxied from
// mcp-ringover-service) to authenticated gateway admins. Used by the token /
// OAuth2 client creation forms to populate the Ringover user picker.
//
//	GET /api/v1/ringover/users
//	Response: { "users": [ {user_id, email, firstname, lastname, team_id, team_name}, ... ] }
//
// 503 is returned when the integration is disabled (env vars unset).
func (h *Handler) handleRingoverUsers(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	if h.ringoverAdmin == nil || !h.ringoverAdmin.Enabled() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"error": "Ringover integration is not configured (set RINGOVER_INTERNAL_URL and RINGOVER_ADMIN_TOKEN)",
		})
		return
	}

	users, err := h.ringoverAdmin.ListUsers(r.Context(), false)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"users": users})
}

// handleRingoverTeams returns the distinct teams derived from the Ringover
// user list. Same auth / disable semantics as handleRingoverUsers.
//
//	GET /api/v1/ringover/teams
//	Response: { "teams": [ {id, name}, ... ] }
func (h *Handler) handleRingoverTeams(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	if h.ringoverAdmin == nil || !h.ringoverAdmin.Enabled() {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{
			"error": "Ringover integration is not configured (set RINGOVER_INTERNAL_URL and RINGOVER_ADMIN_TOKEN)",
		})
		return
	}

	teams, err := h.ringoverAdmin.ListTeams(r.Context(), false)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"teams": teams})
}
