package api

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/scopetoken"
)

// ── Token CRUD handlers ──────────────────────────────────────────────────────

func (h *Handler) handleTokens(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.listTokens(w, r)
	case http.MethodPost:
		h.createToken(w, r)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *Handler) handleTokenByID(w http.ResponseWriter, r *http.Request) {
	// Extract ID: /api/v1/tokens/{id}[/action]
	path := strings.TrimPrefix(r.URL.Path, "/api/v1/tokens/")
	parts := strings.SplitN(path, "/", 2)
	id := parts[0]

	if len(parts) == 2 && parts[1] == "revoke" && r.Method == http.MethodPost {
		h.revokeToken(w, r, id)
		return
	}

	switch r.Method {
	case http.MethodGet:
		h.getToken(w, r, id)
	case http.MethodPut:
		h.updateToken(w, r, id)
	case http.MethodDelete:
		h.deleteToken(w, r, id)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *Handler) listTokens(w http.ResponseWriter, r *http.Request) {
	tokens, err := h.tokenRepo.ListAll()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	resp := make([]TokenResponse, len(tokens))
	for i, t := range tokens {
		resp[i] = toTokenResponse(t)
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"tokens": resp})
}

func (h *Handler) createToken(w http.ResponseWriter, r *http.Request) {
	var req CreateTokenRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
		return
	}

	if req.Name == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "name is required"})
		return
	}
	if len(req.ServerIDs) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "server_ids is required (at least one)"})
		return
	}

	rawToken, hash, prefix, err := scopetoken.Generate()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	token := db.ScopeToken{
		ID:          uuid.New().String(),
		Name:        req.Name,
		Description: req.Description,
		TokenHash:   hash,
		TokenPrefix: prefix,
		IsActive:    true,
	}

	// Parse optional expiry
	if req.ExpiresAt != nil {
		t, err := time.Parse(time.RFC3339, *req.ExpiresAt)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid expires_at format (use RFC3339)"})
			return
		}
		token.ExpiresAt = &t
	}

	// Get created_by from session if available
	if sess := sessionFromRequest(r); sess != nil {
		token.CreatedBy = sess.DisplayName
	}

	// Build server associations
	for _, sid := range req.ServerIDs {
		token.Servers = append(token.Servers, db.ScopeTokenServer{
			TokenID:  token.ID,
			ServerID: sid,
		})
	}

	if err := h.tokenRepo.Create(&token); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	var expiresStr *string
	if token.ExpiresAt != nil {
		s := token.ExpiresAt.UTC().Format(time.RFC3339)
		expiresStr = &s
	}

	writeJSON(w, http.StatusCreated, CreateTokenResponse{
		ID:          token.ID,
		Name:        token.Name,
		Description: token.Description,
		Token:       rawToken,
		TokenPrefix: token.TokenPrefix,
		ServerIDs:   req.ServerIDs,
		IsActive:    token.IsActive,
		CreatedAt:   token.CreatedAt.UTC().Format(time.RFC3339),
		ExpiresAt:   expiresStr,
	})
}

func (h *Handler) getToken(w http.ResponseWriter, r *http.Request, id string) {
	token, err := h.tokenRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "token not found"})
		return
	}
	writeJSON(w, http.StatusOK, toTokenResponse(*token))
}

func (h *Handler) updateToken(w http.ResponseWriter, r *http.Request, id string) {
	var req UpdateTokenRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
		return
	}

	updates := make(map[string]interface{})
	if req.Name != nil {
		updates["name"] = *req.Name
	}
	if req.Description != nil {
		updates["description"] = *req.Description
	}

	if len(updates) > 0 {
		if err := h.tokenRepo.Update(id, updates); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}

	if len(req.ServerIDs) > 0 {
		if err := h.tokenRepo.UpdateServers(id, req.ServerIDs); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}

	// Invalidate cache
	if h.tokenCache != nil {
		h.tokenCache.InvalidateAll()
	}

	token, err := h.tokenRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "token not found"})
		return
	}
	writeJSON(w, http.StatusOK, toTokenResponse(*token))
}

func (h *Handler) deleteToken(w http.ResponseWriter, r *http.Request, id string) {
	if err := h.tokenRepo.Delete(id); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	if h.tokenCache != nil {
		h.tokenCache.InvalidateAll()
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) revokeToken(w http.ResponseWriter, r *http.Request, id string) {
	if err := h.tokenRepo.SetActive(id, false); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	if h.tokenCache != nil {
		h.tokenCache.InvalidateAll()
	}
	token, err := h.tokenRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "token not found"})
		return
	}
	writeJSON(w, http.StatusOK, toTokenResponse(*token))
}

// ── helpers ───────────────────────────────────────────────────────────────────

func toTokenResponse(t db.ScopeToken) TokenResponse {
	serverIDs := make([]string, len(t.Servers))
	for i, s := range t.Servers {
		serverIDs[i] = s.ServerID
	}

	var expiresStr *string
	if t.ExpiresAt != nil {
		s := t.ExpiresAt.UTC().Format(time.RFC3339)
		expiresStr = &s
	}

	return TokenResponse{
		ID:          t.ID,
		Name:        t.Name,
		Description: t.Description,
		TokenPrefix: t.TokenPrefix,
		ServerIDs:   serverIDs,
		IsActive:    t.IsActive,
		CreatedBy:   t.CreatedBy,
		CreatedAt:   t.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:   t.UpdatedAt.UTC().Format(time.RFC3339),
		ExpiresAt:   expiresStr,
	}
}

func sessionFromRequest(r *http.Request) *struct{ DisplayName string } {
	// Extract display name from session cookie if available
	// This is a simplified version — the auth middleware already validates
	cookie, err := r.Cookie("mcp_session")
	if err != nil || cookie.Value == "" {
		return nil
	}
	return &struct{ DisplayName string }{DisplayName: ""}
}
