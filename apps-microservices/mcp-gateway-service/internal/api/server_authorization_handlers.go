package api

import (
	"encoding/json"
	"net/http"
	"strings"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
)

// handleListServerAuthorizations handles GET /api/v1/server-authorizations[?server_id=...].
func (h *Handler) handleListServerAuthorizations(w http.ResponseWriter, r *http.Request) {
	if h.serverAuthRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "server-authorizations not configured"})
		return
	}
	serverID := r.URL.Query().Get("server_id")
	var rows []db.ServerAuthorization
	var err error
	if serverID != "" {
		rows, err = h.serverAuthRepo.ListByServer(serverID)
	} else {
		rows, err = h.serverAuthRepo.List()
	}
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "list failed: " + err.Error()})
		return
	}
	resp := make([]ServerAuthorizationResponse, 0, len(rows))
	for _, row := range rows {
		resp = append(resp, ServerAuthorizationResponse{
			ServerID:  row.ServerID,
			Email:     row.Email,
			CreatedBy: row.CreatedBy,
			CreatedAt: row.CreatedAt.Format("2006-01-02T15:04:05Z07:00"),
		})
	}
	writeJSON(w, http.StatusOK, resp)
}

// handleCreateServerAuthorization handles POST /api/v1/server-authorizations.
func (h *Handler) handleCreateServerAuthorization(w http.ResponseWriter, r *http.Request) {
	if h.serverAuthRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "server-authorizations not configured"})
		return
	}
	var req CreateServerAuthorizationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "invalid JSON: " + err.Error()})
		return
	}
	req.ServerID = strings.TrimSpace(req.ServerID)
	req.Email = strings.TrimSpace(req.Email)
	if req.ServerID == "" || req.Email == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "server_id and email are required"})
		return
	}

	// Validate the server exists so the admin can't create dangling grants.
	if _, err := h.repo.GetByID(req.ServerID); err != nil {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "unknown server_id"})
		return
	}

	row := &db.ServerAuthorization{
		ServerID:  req.ServerID,
		Email:     req.Email,
		CreatedBy: auth.UserEmailFromContext(r.Context()),
	}
	if err := h.serverAuthRepo.Create(row); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "create failed: " + err.Error()})
		return
	}
	writeJSON(w, http.StatusCreated, ServerAuthorizationResponse{
		ServerID:  row.ServerID,
		Email:     row.Email,
		CreatedBy: row.CreatedBy,
		CreatedAt: row.CreatedAt.Format("2006-01-02T15:04:05Z07:00"),
	})
}

// handleDeleteServerAuthorization handles
// DELETE /api/v1/server-authorizations/{server_id}/{email}.
func (h *Handler) handleDeleteServerAuthorization(w http.ResponseWriter, r *http.Request) {
	if h.serverAuthRepo == nil {
		writeJSON(w, http.StatusServiceUnavailable, ErrorResponse{Error: "server-authorizations not configured"})
		return
	}
	rest := strings.TrimPrefix(r.URL.Path, "/api/v1/server-authorizations/")
	parts := strings.SplitN(rest, "/", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		writeJSON(w, http.StatusBadRequest, ErrorResponse{Error: "expected /server-authorizations/{server_id}/{email}"})
		return
	}
	if err := h.serverAuthRepo.Delete(parts[0], parts[1]); err != nil {
		writeJSON(w, http.StatusInternalServerError, ErrorResponse{Error: "delete failed: " + err.Error()})
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
