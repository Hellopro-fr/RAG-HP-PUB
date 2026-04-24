package api

import (
	"encoding/json"
	"log"
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
		ServerName:     req.ServerName,
		AllowHTTP:      req.AllowHTTP,
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

	// Resolve and validate the optional Leexi ownership filter.
	mode, userUUIDs, teamUUIDs, lerr := resolveLeexiFilterForCreate(
		r.Context(), h.leexiAdmin, req.LeexiFilter, token.CreatedBy,
	)
	if lerr != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": lerr.Error()})
		return
	}
	token.LeexiFilterMode = mode
	token.LeexiAllowedUserUUIDs = userUUIDs
	token.LeexiAllowedTeamUUIDs = teamUUIDs

	// Build server associations
	for _, sid := range req.ServerIDs {
		token.Servers = append(token.Servers, db.ScopeTokenServer{
			TokenID:  token.ID,
			ServerID: sid,
		})
	}

	// Build tool associations from server_tools.
	// The UI sends prefixed tool names (e.g. "zoho_search") but the registry
	// stores original names (e.g. "search"), so we must strip the prefix before saving.
	serverPrefixes := h.loadServerPrefixes(req.ServerIDs)
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
		prefix := serverPrefixes[sid]
		for _, toolName := range toolNames {
			token.Tools = append(token.Tools, db.ScopeTokenTool{
				TokenID:  token.ID,
				ServerID: sid,
				ToolName: stripToolPrefix(prefix, toolName),
			})
		}
	}

	if err := h.tokenRepo.Create(&token); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	// Persist selected LLM instructions. Server-side validation enforces that
	// every picked instruction has at least one allowed server in common with
	// the token — the UI pre-filters, but we must not trust the client.
	if h.instructionRepo != nil && len(req.InstructionIDs) > 0 {
		if msg := enforceSingleInstructionPick(req.InstructionIDs); msg != "" {
			_ = h.tokenRepo.Delete(token.ID)
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": msg})
			return
		}
		invalid, vErr := h.instructionRepo.ValidateForScope(req.InstructionIDs, req.ServerIDs)
		if vErr != nil {
			_ = h.tokenRepo.Delete(token.ID)
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": vErr.Error()})
			return
		}
		if len(invalid) > 0 {
			_ = h.tokenRepo.Delete(token.ID)
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "one or more instruction_ids are not linked to any of the token's allowed servers: " + strings.Join(invalid, ","),
			})
			return
		}
		if err := h.instructionRepo.ReplaceTokenInstructions(token.ID, req.InstructionIDs); err != nil {
			_ = h.tokenRepo.Delete(token.ID)
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}

	var expiresStr *string
	if token.ExpiresAt != nil {
		s := token.ExpiresAt.UTC().Format(time.RFC3339)
		expiresStr = &s
	}

	writeJSON(w, http.StatusCreated, CreateTokenResponse{
		ID:             token.ID,
		Name:           token.Name,
		Description:    token.Description,
		Token:          rawToken,
		TokenPrefix:    token.TokenPrefix,
		ServerIDs:      req.ServerIDs,
		ServerTools:    buildServerToolsResponse(token.Tools),
		InstructionIDs: req.InstructionIDs,
		MCPCommand:     token.MCPCommand,
		ServerName:     token.ServerName,
		AllowHTTP:      token.AllowHTTP,
		IsActive:       token.IsActive,
		CreatedAt:      token.CreatedAt.UTC().Format(time.RFC3339),
		ExpiresAt:      expiresStr,
		LeexiFilter:    scopeTokenLeexiFilterToDTO(&token),
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
	if req.MCPCommand != nil {
		updates["mcp_command"] = *req.MCPCommand
	}
	if req.ServerName != nil {
		updates["server_name"] = *req.ServerName
	}
	if req.AllowHTTP != nil {
		updates["allow_http"] = *req.AllowHTTP
	}

	// Allow rotating the Leexi ownership filter on an existing token. The
	// creator email is read from the existing row so a non-owner cannot lift
	// or relax the scope.
	if req.LeexiFilter != nil {
		mode, userUUIDs, teamUUIDs, lerr := resolveLeexiFilterForCreate(
			r.Context(), h.leexiAdmin, req.LeexiFilter, existing.CreatedBy,
		)
		if lerr != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": lerr.Error()})
			return
		}
		updates["leexi_filter_mode"] = mode
		updates["leexi_allowed_user_uuids"] = userUUIDs
		updates["leexi_allowed_team_uuids"] = teamUUIDs
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

	// Update instruction selections if provided. Re-validate against the
	// token's effective allowed servers (either the incoming list or, if
	// unchanged on this request, the existing set on the row).
	if req.InstructionIDs != nil && h.instructionRepo != nil {
		if msg := enforceSingleInstructionPick(req.InstructionIDs); msg != "" {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": msg})
			return
		}
		allowed := req.ServerIDs
		if len(allowed) == 0 {
			allowed = make([]string, 0, len(existing.Servers))
			for _, s := range existing.Servers {
				allowed = append(allowed, s.ServerID)
			}
		}
		invalid, vErr := h.instructionRepo.ValidateForScope(req.InstructionIDs, allowed)
		if vErr != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": vErr.Error()})
			return
		}
		if len(invalid) > 0 {
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "one or more instruction_ids are not linked to any of the token's allowed servers: " + strings.Join(invalid, ","),
			})
			return
		}
		if err := h.instructionRepo.ReplaceTokenInstructions(id, req.InstructionIDs); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}

	// Update tool selections if provided
	if req.ServerTools != nil {
		// Collect all server IDs to look up prefixes
		sids := make([]string, 0, len(req.ServerTools))
		for _, st := range req.ServerTools {
			sids = append(sids, st.ServerID)
		}
		prefixes := h.loadServerPrefixes(sids)

		var tools []db.ScopeTokenTool
		for _, st := range req.ServerTools {
			if len(st.ToolNames) == 0 {
				continue
			}
			prefix := prefixes[st.ServerID]
			for _, toolName := range st.ToolNames {
				tools = append(tools, db.ScopeTokenTool{
					TokenID:  id,
					ServerID: st.ServerID,
					ToolName: stripToolPrefix(prefix, toolName),
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

// stripToolPrefix removes the "{prefix}_" from a tool name if present.
// If the name doesn't start with the prefix, it is returned as-is.
func stripToolPrefix(prefix, toolName string) string {
	if prefix == "" {
		return toolName
	}
	pfx := prefix + "_"
	if strings.HasPrefix(toolName, pfx) {
		return toolName[len(pfx):]
	}
	return toolName
}

// loadServerPrefixes fetches the ToolPrefix for the given server IDs from the DB.
func (h *Handler) loadServerPrefixes(serverIDs []string) map[string]string {
	prefixes := make(map[string]string, len(serverIDs))
	for _, sid := range serverIDs {
		srv, err := h.repo.GetByID(sid)
		if err != nil {
			log.Printf("[api] loadServerPrefixes: server %s not found: %v", sid, err)
			continue
		}
		prefixes[sid] = srv.ToolPrefix
	}
	return prefixes
}

func toTokenResponse(t db.ScopeToken, decryptedToken string) TokenResponse {
	serverIDs := make([]string, len(t.Servers))
	for i, s := range t.Servers {
		serverIDs[i] = s.ServerID
	}

	var instructionIDs []string
	if len(t.Instructions) > 0 {
		instructionIDs = make([]string, 0, len(t.Instructions))
		for _, i := range t.Instructions {
			instructionIDs = append(instructionIDs, i.InstructionID)
		}
	}

	var expiresStr *string
	if t.ExpiresAt != nil {
		s := t.ExpiresAt.UTC().Format(time.RFC3339)
		expiresStr = &s
	}

	return TokenResponse{
		ID:             t.ID,
		Name:           t.Name,
		Description:    t.Description,
		Token:          decryptedToken,
		TokenPrefix:    t.TokenPrefix,
		ServerIDs:      serverIDs,
		ServerTools:    buildServerToolsResponse(t.Tools),
		InstructionIDs: instructionIDs,
		MCPCommand:     t.MCPCommand,
		ServerName:     t.ServerName,
		AllowHTTP:      t.AllowHTTP,
		IsActive:       t.IsActive,
		CreatedBy:      t.CreatedBy,
		CreatedAt:      t.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:      t.UpdatedAt.UTC().Format(time.RFC3339),
		ExpiresAt:      expiresStr,
		LeexiFilter:    scopeTokenLeexiFilterToDTO(&t),
	}
}
