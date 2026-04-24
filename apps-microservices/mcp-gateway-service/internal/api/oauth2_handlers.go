package api

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/db"
	oauth2pkg "github.com/hellopro/mcp-gateway/internal/oauth2"
)

// ── OAuth2 Client CRUD handlers ─────────────────────────────────────────────

func (h *Handler) handleOAuth2Clients(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		h.listOAuth2Clients(w, r)
	case http.MethodPost:
		h.createOAuth2Client(w, r)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *Handler) handleOAuth2ClientByID(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/api/v1/oauth2/clients/")
	parts := strings.SplitN(path, "/", 2)
	id := parts[0]

	if len(parts) == 2 && parts[1] == "revoke" && r.Method == http.MethodPost {
		h.revokeOAuth2Client(w, r, id)
		return
	}

	switch r.Method {
	case http.MethodGet:
		h.getOAuth2Client(w, r, id)
	case http.MethodPut:
		h.updateOAuth2Client(w, r, id)
	case http.MethodDelete:
		h.deleteOAuth2Client(w, r, id)
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (h *Handler) listOAuth2Clients(w http.ResponseWriter, r *http.Request) {
	userEmail := auth.UserEmailFromContext(r.Context())
	clients, err := h.oauth2Repo.ListAll(userEmail)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	resp := make([]OAuth2ClientResponse, len(clients))
	for i, c := range clients {
		resp[i] = toOAuth2ClientResponse(c, h.oauth2Repo.DecryptSecret(&c))
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"clients": resp})
}

func (h *Handler) createOAuth2Client(w http.ResponseWriter, r *http.Request) {
	var req CreateOAuth2ClientRequest
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

	clientID, clientSecret, secretHash, secretPrefix, err := oauth2pkg.GenerateCredentials()
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	ttl := 3600
	if req.AccessTokenTTL != nil && *req.AccessTokenTTL > 0 {
		ttl = *req.AccessTokenTTL
	}

	creatorEmail := auth.UserEmailFromContext(r.Context())

	client := db.OAuth2Client{
		ID:              clientID,
		Name:            req.Name,
		Description:     req.Description,
		SecretHash:      secretHash,
		SecretPrefix:    secretPrefix,
		EncryptedSecret: []byte(clientSecret),
		AccessTokenTTL:  ttl,
		IsActive:        true,
		CreatedBy:       creatorEmail,
	}

	// Resolve and validate the optional Leexi ownership filter.
	mode, userUUIDs, teamUUIDs, lerr := resolveLeexiFilterForCreate(
		r.Context(), h.leexiAdmin, req.LeexiFilter, creatorEmail,
	)
	if lerr != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": lerr.Error()})
		return
	}
	client.LeexiFilterMode = mode
	client.LeexiAllowedUserUUIDs = userUUIDs
	client.LeexiAllowedTeamUUIDs = teamUUIDs

	if len(req.RedirectURIs) > 0 {
		redirectJSON, _ := json.Marshal(req.RedirectURIs)
		s := string(redirectJSON)
		client.RedirectURIs = &s
	}
	if len(req.GrantTypes) > 0 {
		grantJSON, _ := json.Marshal(req.GrantTypes)
		s := string(grantJSON)
		client.GrantTypes = &s
	}

	// Parse optional expiry
	if req.ExpiresAt != nil {
		t, err := time.Parse(time.RFC3339, *req.ExpiresAt)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid expires_at format (use RFC3339)"})
			return
		}
		client.ExpiresAt = &t
	}

	// Build server associations
	for _, sid := range req.ServerIDs {
		client.Servers = append(client.Servers, db.OAuth2ClientServer{
			ClientID: client.ID,
			ServerID: sid,
		})
	}

	// Build tool associations (strip prefixes like in token_handlers.go)
	serverPrefixes := h.loadServerPrefixes(req.ServerIDs)
	toolSelectionByServer := make(map[string][]string)
	for _, st := range req.ServerTools {
		toolSelectionByServer[st.ServerID] = st.ToolNames
	}

	for _, sid := range req.ServerIDs {
		toolNames, hasSelection := toolSelectionByServer[sid]
		if !hasSelection || len(toolNames) == 0 {
			continue
		}
		prefix := serverPrefixes[sid]
		for _, toolName := range toolNames {
			client.Tools = append(client.Tools, db.OAuth2ClientTool{
				ClientID: client.ID,
				ServerID: sid,
				ToolName: stripToolPrefix(prefix, toolName),
			})
		}
	}

	if err := h.oauth2Repo.Create(&client); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}

	if h.instructionRepo != nil && len(req.InstructionIDs) > 0 {
		if msg := enforceSingleInstructionPick(req.InstructionIDs); msg != "" {
			_ = h.oauth2Repo.Delete(client.ID)
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": msg})
			return
		}
		invalid, vErr := h.instructionRepo.ValidateForScope(req.InstructionIDs, req.ServerIDs)
		if vErr != nil {
			_ = h.oauth2Repo.Delete(client.ID)
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": vErr.Error()})
			return
		}
		if len(invalid) > 0 {
			_ = h.oauth2Repo.Delete(client.ID)
			writeJSON(w, http.StatusBadRequest, map[string]string{
				"error": "one or more instruction_ids are not linked to any of the client's allowed servers: " + strings.Join(invalid, ","),
			})
			return
		}
		if err := h.instructionRepo.ReplaceOAuth2ClientInstructions(client.ID, req.InstructionIDs); err != nil {
			_ = h.oauth2Repo.Delete(client.ID)
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}

	var expiresStr *string
	if client.ExpiresAt != nil {
		s := client.ExpiresAt.UTC().Format(time.RFC3339)
		expiresStr = &s
	}

	var createRedirectURIs []string
	if client.RedirectURIs != nil && *client.RedirectURIs != "" {
		json.Unmarshal([]byte(*client.RedirectURIs), &createRedirectURIs)
	}
	var createGrantTypes []string
	if client.GrantTypes != nil && *client.GrantTypes != "" {
		json.Unmarshal([]byte(*client.GrantTypes), &createGrantTypes)
	}

	writeJSON(w, http.StatusCreated, CreateOAuth2ClientResponse{
		ID:                    client.ID,
		Name:                  client.Name,
		Description:           client.Description,
		ClientSecret:          clientSecret,
		SecretPrefix:          client.SecretPrefix,
		ServerIDs:             req.ServerIDs,
		ServerTools:           buildOAuth2ServerToolsResponse(client.Tools),
		InstructionIDs:        req.InstructionIDs,
		AccessTokenTTL:        client.AccessTokenTTL,
		IsActive:              client.IsActive,
		CreatedAt:             client.CreatedAt.UTC().Format(time.RFC3339),
		ExpiresAt:             expiresStr,
		RedirectURIs:          createRedirectURIs,
		GrantTypes:            createGrantTypes,
		DynamicallyRegistered: client.DynamicallyRegistered,
		LeexiFilter:           oauth2ClientLeexiFilterToDTO(&client),
	})
}

func (h *Handler) getOAuth2Client(w http.ResponseWriter, r *http.Request, id string) {
	client, err := h.oauth2Repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "client not found"})
		return
	}
	if !h.isOAuth2ClientOwner(r, client) {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "not your client"})
		return
	}
	writeJSON(w, http.StatusOK, toOAuth2ClientResponse(*client, h.oauth2Repo.DecryptSecret(client)))
}

func (h *Handler) updateOAuth2Client(w http.ResponseWriter, r *http.Request, id string) {
	existing, err := h.oauth2Repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "client not found"})
		return
	}
	if !h.isOAuth2ClientOwner(r, existing) {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "not your client"})
		return
	}

	var req UpdateOAuth2ClientRequest
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

	if len(req.RedirectURIs) > 0 {
		redirectJSON, _ := json.Marshal(req.RedirectURIs)
		s := string(redirectJSON)
		updates["redirect_uris"] = &s
	}
	if len(req.GrantTypes) > 0 {
		grantJSON, _ := json.Marshal(req.GrantTypes)
		s := string(grantJSON)
		updates["grant_types"] = &s
	}

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
		if err := h.oauth2Repo.Update(id, updates); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}

	if len(req.ServerIDs) > 0 {
		if err := h.oauth2Repo.UpdateServers(id, req.ServerIDs); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}

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
				"error": "one or more instruction_ids are not linked to any of the client's allowed servers: " + strings.Join(invalid, ","),
			})
			return
		}
		if err := h.instructionRepo.ReplaceOAuth2ClientInstructions(id, req.InstructionIDs); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}

	if req.ServerTools != nil {
		sids := make([]string, 0, len(req.ServerTools))
		for _, st := range req.ServerTools {
			sids = append(sids, st.ServerID)
		}
		prefixes := h.loadServerPrefixes(sids)

		var tools []db.OAuth2ClientTool
		for _, st := range req.ServerTools {
			if len(st.ToolNames) == 0 {
				continue
			}
			prefix := prefixes[st.ServerID]
			for _, toolName := range st.ToolNames {
				tools = append(tools, db.OAuth2ClientTool{
					ClientID: id,
					ServerID: st.ServerID,
					ToolName: stripToolPrefix(prefix, toolName),
				})
			}
		}
		if err := h.oauth2Repo.UpdateTools(id, tools); err != nil {
			writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
			return
		}
	}

	// Invalidate OAuth2 cache
	if h.oauth2Cache != nil {
		h.oauth2Cache.InvalidateAll()
	}

	client, err := h.oauth2Repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "client not found"})
		return
	}
	writeJSON(w, http.StatusOK, toOAuth2ClientResponse(*client, h.oauth2Repo.DecryptSecret(client)))
}

func (h *Handler) deleteOAuth2Client(w http.ResponseWriter, r *http.Request, id string) {
	existing, err := h.oauth2Repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "client not found"})
		return
	}
	if !h.isOAuth2ClientOwner(r, existing) {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "not your client"})
		return
	}
	if err := h.oauth2Repo.Delete(id); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	if h.oauth2Cache != nil {
		h.oauth2Cache.InvalidateAll()
	}
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handler) revokeOAuth2Client(w http.ResponseWriter, r *http.Request, id string) {
	existing, err := h.oauth2Repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "client not found"})
		return
	}
	if !h.isOAuth2ClientOwner(r, existing) {
		writeJSON(w, http.StatusForbidden, map[string]string{"error": "not your client"})
		return
	}
	if err := h.oauth2Repo.SetActive(id, false); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	if h.oauth2Cache != nil {
		h.oauth2Cache.InvalidateAll()
	}
	client, err := h.oauth2Repo.GetByID(id)
	if err != nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"error": "client not found"})
		return
	}
	writeJSON(w, http.StatusOK, toOAuth2ClientResponse(*client, h.oauth2Repo.DecryptSecret(client)))
}

// ── helpers ───────────────────────────────────────────────────────────────────

func (h *Handler) isOAuth2ClientOwner(r *http.Request, client *db.OAuth2Client) bool {
	if client.CreatedBy == "" {
		return true
	}
	userEmail := auth.UserEmailFromContext(r.Context())
	return userEmail == client.CreatedBy
}

func buildOAuth2ServerToolsResponse(tools []db.OAuth2ClientTool) []ServerToolSelection {
	if len(tools) == 0 {
		return nil
	}
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

func toOAuth2ClientResponse(c db.OAuth2Client, decryptedSecret string) OAuth2ClientResponse {
	serverIDs := make([]string, len(c.Servers))
	for i, s := range c.Servers {
		serverIDs[i] = s.ServerID
	}

	var instructionIDs []string
	if len(c.Instructions) > 0 {
		instructionIDs = make([]string, 0, len(c.Instructions))
		for _, i := range c.Instructions {
			instructionIDs = append(instructionIDs, i.InstructionID)
		}
	}

	var expiresStr *string
	if c.ExpiresAt != nil {
		s := c.ExpiresAt.UTC().Format(time.RFC3339)
		expiresStr = &s
	}

	var redirectURIs []string
	if c.RedirectURIs != nil && *c.RedirectURIs != "" {
		json.Unmarshal([]byte(*c.RedirectURIs), &redirectURIs)
	}
	var grantTypes []string
	if c.GrantTypes != nil && *c.GrantTypes != "" {
		json.Unmarshal([]byte(*c.GrantTypes), &grantTypes)
	}

	return OAuth2ClientResponse{
		ID:                    c.ID,
		Name:                  c.Name,
		Description:           c.Description,
		ClientSecret:          decryptedSecret,
		SecretPrefix:          c.SecretPrefix,
		ServerIDs:             serverIDs,
		ServerTools:           buildOAuth2ServerToolsResponse(c.Tools),
		InstructionIDs:        instructionIDs,
		AccessTokenTTL:        c.AccessTokenTTL,
		IsActive:              c.IsActive,
		CreatedBy:             c.CreatedBy,
		CreatedAt:             c.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:             c.UpdatedAt.UTC().Format(time.RFC3339),
		ExpiresAt:             expiresStr,
		RedirectURIs:          redirectURIs,
		GrantTypes:            grantTypes,
		DynamicallyRegistered: c.DynamicallyRegistered,
		LeexiFilter:           oauth2ClientLeexiFilterToDTO(&c),
	}
}
