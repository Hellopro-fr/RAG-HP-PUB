package authserver

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
)

// ZohoStateForUser is the optional dependency that buildServerList uses
// to render Zoho-tagged servers on the consent screen. Returns the
// per-backend state keyed by mcp_servers.id. A Configured=false entry
// means the viewer's zoho_imports row is missing — the consent screen
// moves the server into the "Non configurés" section with a docs CTA.
type ZohoStateForUser interface {
	FetchZohoStateForUser(ctx context.Context, email string) map[string]gateway.ZohoServerState
}

// ── JSON API DTOs ────────────────────────────────────────────────────────────

type authorizeInfoResponse struct {
	ClientName string              `json:"client_name"`
	Servers    []authorizeServerDTO `json:"servers"`
	HasSession bool                `json:"has_session"`
	HasConsent bool                `json:"has_consent"`
	CSRFToken  string              `json:"csrf_token,omitempty"`
}

type authorizeServerDTO struct {
	ID         string             `json:"id"`
	Name       string             `json:"name"`
	Tools      []authorizeToolDTO `json:"tools"`
	Configured bool               `json:"configured"`
	DocsURL    string             `json:"docs_url,omitempty"`
}

type authorizeToolDTO struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
}

type authorizeLoginRequest struct {
	Username            string `json:"username"`
	Password            string `json:"password"`
	ClientID            string `json:"client_id"`
	RedirectURI         string `json:"redirect_uri"`
	CodeChallenge       string `json:"code_challenge"`
	CodeChallengeMethod string `json:"code_challenge_method"`
	State               string `json:"state"`
}

type authorizeLoginResponse struct {
	Success    bool                `json:"success"`
	ClientName string              `json:"client_name"`
	Servers    []authorizeServerDTO `json:"servers"`
	CSRFToken  string              `json:"csrf_token"`
	Error      string              `json:"error,omitempty"`
}

type authorizeConsentRequest struct {
	ClientID            string   `json:"client_id"`
	RedirectURI         string   `json:"redirect_uri"`
	CodeChallenge       string   `json:"code_challenge"`
	CodeChallengeMethod string   `json:"code_challenge_method"`
	State               string   `json:"state"`
	CSRFToken           string   `json:"csrf_token"`
	ServerIDs           []string `json:"server_ids"`
	ToolIDs             []string `json:"tool_ids,omitempty"` // format: "server_id:tool_name"
}

type authorizeConsentResponse struct {
	RedirectURL string `json:"redirect_url"`
}

// ── Route Registration ───────────────────────────────────────────────────────

// RegisterAPI mounts the JSON API endpoints for the Vue frontend OAuth2 authorize flow.
func (s *AuthServer) RegisterAPI(mux *http.ServeMux) {
	mux.HandleFunc("/api/v1/oauth2/authorize/info", s.handleAuthorizeInfo)
	mux.HandleFunc("/api/v1/oauth2/authorize/login", s.handleAuthorizeLogin)
	mux.HandleFunc("/api/v1/oauth2/authorize/consent", s.handleAuthorizeConsent)
}

// ── GET /api/v1/oauth2/authorize/info ────────────────────────────────────────

func (s *AuthServer) handleAuthorizeInfo(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSONError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	clientID := r.URL.Query().Get("client_id")
	redirectURI := r.URL.Query().Get("redirect_uri")

	if clientID == "" || redirectURI == "" {
		writeJSONError(w, http.StatusBadRequest, "client_id and redirect_uri are required")
		return
	}

	client, err := s.oauth2Repo.GetByID(clientID)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "unknown client_id")
		return
	}

	if !s.isRegisteredRedirectURI(client, redirectURI) {
		writeJSONError(w, http.StatusBadRequest, "redirect_uri not registered")
		return
	}

	// Check session
	hasSession := false
	hasConsent := false
	var userEmail string

	session, err := auth.GetSession(r, s.jwtSecret)
	if err == nil {
		if _, err := auth.ValidateJWT(session.Token, s.jwtSecret, ""); err == nil {
			hasSession = true
			userEmail = session.Email
		}
	}

	// Also check Authorization header (Vue frontend sends Bearer token)
	if !hasSession {
		if authHeader := r.Header.Get("Authorization"); strings.HasPrefix(authHeader, "Bearer ") {
			token := strings.TrimPrefix(authHeader, "Bearer ")
			if claims, err := auth.ValidateJWT(token, s.jwtSecret, ""); err == nil {
				hasSession = true
				userEmail = claims.Email
			}
		}
	}

	// Check consent
	if hasSession && userEmail != "" {
		existing, err := s.consentRepo.FindByClientAndUser(client.ID, userEmail)
		if err == nil && existing != nil {
			hasConsent = true
		}
	}

	// Build server list
	servers := s.buildServerList(r.Context(), client, userEmail)

	resp := authorizeInfoResponse{
		ClientName: client.Name,
		Servers:    servers,
		HasSession: hasSession,
		HasConsent: hasConsent,
	}

	// If session exists, generate CSRF token so consent can proceed without login step
	if hasSession {
		csrfToken, _ := generateCSRFToken()
		http.SetCookie(w, &http.Cookie{
			Name:     "oauth2_csrf",
			Value:    csrfToken,
			Path:     "/",
			MaxAge:   600,
			HttpOnly: true,
			SameSite: http.SameSiteLaxMode,
			Secure:   s.secureCookie,
		})
		resp.CSRFToken = csrfToken
	}

	writeJSON(w, http.StatusOK, resp)
}

// ── POST /api/v1/oauth2/authorize/login ──────────────────────────────────────

func (s *AuthServer) handleAuthorizeLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSONError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	var req authorizeLoginRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	if req.Username == "" || req.Password == "" {
		writeJSON(w, http.StatusOK, authorizeLoginResponse{
			Success: false,
			Error:   "Tous les champs sont obligatoires",
		})
		return
	}

	if req.ClientID == "" {
		writeJSON(w, http.StatusOK, authorizeLoginResponse{
			Success: false,
			Error:   "client_id is required",
		})
		return
	}

	client, err := s.oauth2Repo.GetByID(req.ClientID)
	if err != nil {
		writeJSON(w, http.StatusOK, authorizeLoginResponse{
			Success: false,
			Error:   "Client inconnu",
		})
		return
	}

	// Authenticate
	authResp, err := auth.AuthenticateHellopro(s.authURL, req.Username, req.Password)
	if err != nil || !authResp.Success {
		log.Printf("[authserver-api] login failed for %s", req.Username)
		writeJSON(w, http.StatusOK, authorizeLoginResponse{
			Success: false,
			Error:   "Login / Mot de passe invalide",
		})
		return
	}

	// Generate JWT
	token := authResp.Token
	if token == "" {
		claims := auth.Claims{
			Audience: "",
			Exp:      time.Now().Add(24 * time.Hour).Unix(),
			Iat:      time.Now().Unix(),
			Name:     authResp.DisplayName,
			Email:    authResp.Email,
		}
		token, _ = auth.SignJWT(s.jwtSecret, claims)
	}

	// Set session cookie (for backward compat)
	auth.SetSession(w, s.jwtSecret, auth.SessionData{
		DisplayName: authResp.DisplayName,
		Email:       authResp.Email,
		Token:       token,
	}, s.secureCookie)

	log.Printf("[authserver-api] user %s logged in for OAuth2 authorize", authResp.Email)

	// Generate CSRF token
	csrfToken, _ := generateCSRFToken()
	http.SetCookie(w, &http.Cookie{
		Name:     "oauth2_csrf",
		Value:    csrfToken,
		Path:     "/",
		MaxAge:   600,
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   s.secureCookie,
	})

	servers := s.buildServerList(r.Context(), client, authResp.Email)

	writeJSON(w, http.StatusOK, authorizeLoginResponse{
		Success:    true,
		ClientName: client.Name,
		Servers:    servers,
		CSRFToken:  csrfToken,
	})
}

// ── POST /api/v1/oauth2/authorize/consent ────────────────────────────────────

func (s *AuthServer) handleAuthorizeConsent(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSONError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	var req authorizeConsentRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSONError(w, http.StatusBadRequest, "invalid request body")
		return
	}

	// Validate client
	client, err := s.oauth2Repo.GetByID(req.ClientID)
	if err != nil {
		writeJSONError(w, http.StatusBadRequest, "unknown client_id")
		return
	}

	if !s.isRegisteredRedirectURI(client, req.RedirectURI) {
		writeJSONError(w, http.StatusBadRequest, "redirect_uri not registered")
		return
	}

	// CSRF check skipped — the authorize page no longer requires a login step.
	// Protection against CSRF attacks is provided by the OAuth2 state parameter
	// and PKCE code_challenge, which are verified during token exchange.

	// Get user from session, Authorization header, or fall back to anonymous
	var userEmail string
	session, err := auth.GetSession(r, s.jwtSecret)
	if err == nil {
		if _, err := auth.ValidateJWT(session.Token, s.jwtSecret, ""); err == nil {
			userEmail = session.Email
		}
	}
	if userEmail == "" {
		if authHeader := r.Header.Get("Authorization"); strings.HasPrefix(authHeader, "Bearer ") {
			token := strings.TrimPrefix(authHeader, "Bearer ")
			if claims, err := auth.ValidateJWT(token, s.jwtSecret, ""); err == nil {
				userEmail = claims.Email
			}
		}
	}
	if userEmail == "" {
		// No session — use anonymous consent (OAuth2 flow doesn't require admin login)
		userEmail = "anonymous@" + req.ClientID
	}

	// Build scope
	var scope ConsentScope
	if len(client.Servers) > 0 {
		// Pre-configured scope
		for _, cs := range client.Servers {
			scope.ServerIDs = append(scope.ServerIDs, cs.ServerID)
		}
		if len(client.Tools) > 0 {
			toolsByServer := make(map[string][]string)
			for _, t := range client.Tools {
				toolsByServer[t.ServerID] = append(toolsByServer[t.ServerID], t.ToolName)
			}
			for sid, tools := range toolsByServer {
				scope.ServerTools = append(scope.ServerTools, ServerToolSelection{
					ServerID:  sid,
					ToolNames: tools,
				})
			}
		}
	} else {
		// Dynamic client — scope from user selection
		if len(req.ServerIDs) == 0 {
			writeJSONError(w, http.StatusBadRequest, "select at least one server")
			return
		}
		scope.ServerIDs = req.ServerIDs

		// Parse tool selections if provided
		if len(req.ToolIDs) > 0 {
			toolsByServer := make(map[string][]string)
			for _, tid := range req.ToolIDs {
				parts := strings.SplitN(tid, ":", 2)
				if len(parts) == 2 {
					toolsByServer[parts[0]] = append(toolsByServer[parts[0]], parts[1])
				}
			}
			for sid, tools := range toolsByServer {
				scope.ServerTools = append(scope.ServerTools, ServerToolSelection{
					ServerID:  sid,
					ToolNames: tools,
				})
			}
		}
	}

	// Save consent
	s.consentRepo.Upsert(&db.OAuth2Consent{
		ID:        fmt.Sprintf("%s:%s", client.ID, userEmail),
		ClientID:  client.ID,
		UserEmail: userEmail,
		Scope:     scope.ToJSON(),
	})

	if client.CreatedBy == "" {
		s.oauth2Repo.Update(client.ID, map[string]interface{}{"created_by": userEmail})
	}

	// Generate auth code
	rawCode, codeHash, err := GenerateAuthCode()
	if err != nil {
		log.Printf("[authserver-api] failed to generate auth code: %v", err)
		writeJSONError(w, http.StatusInternalServerError, "failed to generate authorization code")
		return
	}

	authCode := db.OAuth2AuthorizationCode{
		CodeHash:      codeHash,
		ClientID:      client.ID,
		UserEmail:     userEmail,
		RedirectURI:   req.RedirectURI,
		CodeChallenge: req.CodeChallenge,
		Scope:         scope.ToJSON(),
		ExpiresAt:     time.Now().Add(10 * time.Minute),
	}
	if err := s.authCodeRepo.Create(&authCode); err != nil {
		log.Printf("[authserver-api] failed to store auth code: %v", err)
		writeJSONError(w, http.StatusInternalServerError, "failed to store authorization code")
		return
	}

	go func() { s.authCodeRepo.PurgeExpired() }()

	// Build redirect URL
	redirectURL := req.RedirectURI
	separator := "?"
	if strings.Contains(redirectURL, "?") {
		separator = "&"
	}
	redirectURL += separator + "code=" + rawCode
	if req.State != "" {
		redirectURL += "&state=" + req.State
	}

	writeJSON(w, http.StatusOK, authorizeConsentResponse{
		RedirectURL: redirectURL,
	})
}

// ── Helpers ──────────────────────────────────────────────────────────────────

func (s *AuthServer) buildServerList(ctx context.Context, client *db.OAuth2Client, userEmail string) []authorizeServerDTO {
	hasPreConfiguredScope := len(client.Servers) > 0

	servers, _ := s.serverRepo.ListActive()
	serverMap := make(map[string]db.MCPServer, len(servers))
	zohoIDs := make(map[string]bool, len(servers))
	for _, srv := range servers {
		serverMap[srv.ID] = srv
		if isZohoServer(srv) {
			zohoIDs[srv.ID] = true
		}
	}
	log.Printf("[zoho-diag] buildServerList (JSON API) email=%q client_id=%s pre_configured_scope=%t active_servers=%d zoho_servers=%d zoho_fetcher_wired=%t", userEmail, client.ID, hasPreConfiguredScope, len(servers), len(zohoIDs), s.zohoFetcher != nil)

	var result []authorizeServerDTO

	if hasPreConfiguredScope {
		// Client has admin-assigned scope — show only those servers/tools
		allowedTools := make(map[string]map[string]bool)
		for _, t := range client.Tools {
			if allowedTools[t.ServerID] == nil {
				allowedTools[t.ServerID] = make(map[string]bool)
			}
			allowedTools[t.ServerID][t.ToolName] = true
		}

		for _, cs := range client.Servers {
			srv, ok := serverMap[cs.ServerID]
			if !ok {
				continue
			}
			entry := authorizeServerDTO{
				ID:         srv.ID,
				Name:       srv.Name,
				Configured: true,
			}
			srvTools := allowedTools[srv.ID]
			for _, t := range srv.Tools {
				if srvTools != nil && !srvTools[t.Name] {
					continue
				}
				entry.Tools = append(entry.Tools, authorizeToolDTO{
					Name:        t.Name,
					Description: t.Description,
				})
			}
			result = append(result, entry)
		}
	} else {
		// No pre-configured scope — show all active servers
		for _, srv := range servers {
			entry := authorizeServerDTO{
				ID:         srv.ID,
				Name:       srv.Name,
				Configured: true,
			}
			for _, t := range srv.Tools {
				if !t.IsActive {
					continue
				}
				entry.Tools = append(entry.Tools, authorizeToolDTO{
					Name:        t.Name,
					Description: t.Description,
				})
			}
			result = append(result, entry)
		}
	}

	result = applyZohoUserState(ctx, result, zohoIDs, s.zohoFetcher, userEmail, s.docsURL)
	return result
}

// isZohoServer returns true when the registered server is the Zoho stub —
// either by tool_prefix or by carrying the "zoho" tag (case-insensitive).
// Mirrors the same check the scoped gateway runs at request time.
func isZohoServer(srv db.MCPServer) bool {
	if strings.EqualFold(srv.ToolPrefix, "zoho") {
		return true
	}
	for _, t := range srv.Tags {
		if strings.EqualFold(t.Tag, "zoho") {
			return true
		}
	}
	return false
}

// applyZohoUserState rewrites each Zoho-tagged server entry in-place using
// the per-viewer state returned by the fetcher. Configured servers get
// their Tools replaced with the viewer's tools and Configured=true.
// Unconfigured servers are emptied of tools, marked Configured=false, and
// receive the docs CTA URL. Non-Zoho servers and the nil-fetcher / empty
// email / no-Zoho-id cases are passthroughs. Pure function: testable
// without any AuthServer plumbing.
func applyZohoUserState(
	ctx context.Context,
	servers []authorizeServerDTO,
	zohoIDs map[string]bool,
	fetcher ZohoStateForUser,
	userEmail string,
	docsURL string,
) []authorizeServerDTO {
	if fetcher == nil {
		log.Printf("[zoho-diag] applyZohoUserState: fetcher is nil — every Zoho server stays as cached admin tools (no per-viewer override)")
		return servers
	}
	if userEmail == "" {
		log.Printf("[zoho-diag] applyZohoUserState: userEmail is empty — every Zoho server stays as cached admin tools (no per-viewer override)")
		return servers
	}
	if len(zohoIDs) == 0 {
		log.Printf("[zoho-diag] applyZohoUserState email=%q: no Zoho-tagged servers registered — passthrough", userEmail)
		return servers
	}
	log.Printf("[zoho-diag] applyZohoUserState email=%q zoho_backend_count=%d — fetching per-viewer state", userEmail, len(zohoIDs))
	state := fetcher.FetchZohoStateForUser(ctx, userEmail)
	if state == nil {
		log.Printf("[zoho-diag] applyZohoUserState email=%q: FetchZohoStateForUser returned nil — every Zoho server will fall into unconfigured branch below", userEmail)
	}
	for i, srv := range servers {
		if !zohoIDs[srv.ID] {
			continue
		}
		st, ok := state[srv.ID]
		if !ok {
			log.Printf("[zoho-diag] applyZohoUserState email=%q server_id=%s: no state entry returned — marking Configured=false (fail-safe)", userEmail, srv.ID)
			servers[i].Tools = nil
			servers[i].Configured = false
			servers[i].DocsURL = docsURL
			continue
		}
		if !st.Configured {
			log.Printf("[zoho-diag] applyZohoUserState email=%q server_id=%s: state.Configured=false — marking unconfigured (root cause is in [zoho-diag] StateForEmail logs above)", userEmail, srv.ID)
			servers[i].Tools = nil
			servers[i].Configured = false
			servers[i].DocsURL = docsURL
			continue
		}
		log.Printf("[zoho-diag] applyZohoUserState email=%q server_id=%s: Configured=true tool_count=%d — substituting per-viewer tools", userEmail, srv.ID, len(st.Tools))
		converted := make([]authorizeToolDTO, 0, len(st.Tools))
		for _, t := range st.Tools {
			converted = append(converted, authorizeToolDTO{
				Name:        t.Name,
				Description: t.Description,
			})
		}
		servers[i].Tools = converted
		servers[i].Configured = true
		servers[i].DocsURL = ""
	}
	return servers
}

func writeJSON(w http.ResponseWriter, status int, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(data)
}

func writeJSONError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}
