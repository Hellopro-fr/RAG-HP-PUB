package api

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/auth"
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
	userEmail := auth.UserEmailFromContext(r.Context())
	tokens, err := h.tokenRepo.ListAll(userEmail)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	resp := make([]TokenResponse, len(tokens))
	for i, t := range tokens {
		resp[i] = toTokenResponse(t, h.tokenRepo.DecryptToken(&t))
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
	if req.MCPCommand == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "mcp_command is required"})
		return
	}

	rawToken, hash, prefix, err := scopetoken.Generate()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	token := db.ScopeToken{
		ID:             uuid.New().String(),
		Name:           req.Name,
		Description:    req.Description,
		TokenHash:      hash,
		TokenPrefix:    prefix,
		MCPCommand:     req.MCPCommand,
		EncryptedToken: []byte(rawToken),
		IsActive:       true,
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

	// Get created_by from session (use email for ownership checks)
	token.CreatedBy = auth.UserEmailFromContext(r.Context())

	// Build server associations
	for _, sid := range req.ServerIDs {
		token.Servers = append(token.Servers, db.ScopeTokenServer{
			TokenID:  token.ID,
			ServerID: sid,
		})
	}

	// Build tool associations from server_tools
	// Index request tool selections by server_id for quick lookup
	toolSelectionByServer := make(map[string][]string)
	for _, st := range req.ServerTools {
		toolSelectionByServer[st.ServerID] = st.ToolNames
	}

	for _, sid := range req.ServerIDs {
		toolNames, hasSelection := toolSelectionByServer[sid]
		if !hasSelection || len(toolNames) == 0 {
			// No explicit selection → all tools allowed (no rows = all)
			continue
		}
		for _, toolName := range toolNames {
			token.Tools = append(token.Tools, db.ScopeTokenTool{
				TokenID:  token.ID,
				ServerID: sid,
				ToolName: toolName,
			})
		}
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
		ServerTools: buildServerToolsResponse(token.Tools),
		MCPCommand:  token.MCPCommand,
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
	if !h.isTokenOwner(r, token) {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "not your token"})
		return
	}
	writeJSON(w, http.StatusOK, toTokenResponse(*token, h.tokenRepo.DecryptToken(token)))
}

func (h *Handler) updateToken(w http.ResponseWriter, r *http.Request, id string) {
	existing, err := h.tokenRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "token not found"})
		return
	}
	if !h.isTokenOwner(r, existing) {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "not your token"})
		return
	}

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

	// Update tool selections if provided
	if req.ServerTools != nil {
		var tools []db.ScopeTokenTool
		for _, st := range req.ServerTools {
			if len(st.ToolNames) == 0 {
				// No explicit selection → all tools (no rows)
				continue
			}
			for _, toolName := range st.ToolNames {
				tools = append(tools, db.ScopeTokenTool{
					TokenID:  id,
					ServerID: st.ServerID,
					ToolName: toolName,
				})
			}
		}
		if err := h.tokenRepo.UpdateTools(id, tools); err != nil {
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
	writeJSON(w, http.StatusOK, toTokenResponse(*token, h.tokenRepo.DecryptToken(token)))
}

func (h *Handler) deleteToken(w http.ResponseWriter, r *http.Request, id string) {
	existing, err := h.tokenRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "token not found"})
		return
	}
	if !h.isTokenOwner(r, existing) {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "not your token"})
		return
	}
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
	existing, err := h.tokenRepo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "token not found"})
		return
	}
	if !h.isTokenOwner(r, existing) {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "not your token"})
		return
	}
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
	writeJSON(w, http.StatusOK, toTokenResponse(*token, h.tokenRepo.DecryptToken(token)))
}

// ── helpers ───────────────────────────────────────────────────────────────────

// isTokenOwner checks if the current user owns the token (or if the token has no owner).
func (h *Handler) isTokenOwner(r *http.Request, token *db.ScopeToken) bool {
	if token.CreatedBy == "" {
		return true // legacy tokens with no owner are accessible to everyone
	}
	userEmail := auth.UserEmailFromContext(r.Context())
	return userEmail == token.CreatedBy
}

// buildServerToolsResponse converts db tool rows into the API response format.
func buildServerToolsResponse(tools []db.ScopeTokenTool) []ServerToolSelection {
	if len(tools) == 0 {
		return nil
	}
	// Group tools by server_id
	grouped := make(map[string][]string)
	for _, t := range tools {
		grouped[t.ServerID] = append(grouped[t.ServerID], t.ToolName)
	}
	result := make([]ServerToolSelection, 0, len(grouped))
	for sid, names := range grouped {
		result = append(result, ServerToolSelection{
			ServerID:  sid,
			ToolNames: names,
		})
	}
	return result
}

func toTokenResponse(t db.ScopeToken, decryptedToken string) TokenResponse {
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
		Token:       decryptedToken,
		TokenPrefix: t.TokenPrefix,
		ServerIDs:   serverIDs,
		ServerTools: buildServerToolsResponse(t.Tools),
		MCPCommand:  t.MCPCommand,
		IsActive:    t.IsActive,
		CreatedBy:   t.CreatedBy,
		CreatedAt:   t.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:   t.UpdatedAt.UTC().Format(time.RFC3339),
		ExpiresAt:   expiresStr,
	}
}
