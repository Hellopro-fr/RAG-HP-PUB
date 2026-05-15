package authserver

import (
	"embed"
	"encoding/json"
	"fmt"
	"html/template"
	"log"
	"net/http"
	"net/url"
	"time"

	"github.com/google/uuid"
	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/sso"
)

// toServerTools projects a slice of mcp.Tool (live per-user catalog) into
// the db.ServerTool shape so the consent renderer can iterate it through
// the same code path as the cached admin catalog. ServerID is left blank —
// the caller injects the surrounding server context.
func toServerTools(tools []mcp.Tool) []db.ServerTool {
	out := make([]db.ServerTool, 0, len(tools))
	for _, t := range tools {
		out = append(out, db.ServerTool{Name: t.Name, Description: t.Description})
	}
	return out
}

// decideZohoServerEntry tells the consent renderer how to handle a single
// server given the per-viewer Zoho state map. Three outcomes:
//
//   - server is NOT Zoho-tagged → (false, nil) and the caller uses srv.Tools.
//   - server IS Zoho-tagged AND state[srvID].Configured == true → (false, tools)
//     and the caller uses the returned per-user tools.
//   - server IS Zoho-tagged AND state entry is missing OR !Configured →
//     (true, nil) and the caller routes the server into the "Non configurés"
//     section with no tools.
//
// Pure function: callers compose it inside renderConsent's main loop;
// unit tests cover the decision matrix without spinning up AuthServer.
func decideZohoServerEntry(
	srvID string,
	zohoIDs map[string]bool,
	state map[string]gateway.ZohoServerState,
) (unconfigured bool, tools []mcp.Tool) {
	if !zohoIDs[srvID] {
		return false, nil
	}
	st, ok := state[srvID]
	if !ok || !st.Configured {
		return true, nil
	}
	return false, st.Tools
}

//go:embed templates/*.html
var templateFS embed.FS

var consentTmpl = template.Must(template.ParseFS(templateFS, "templates/consent.html"))

type authorizeParams struct {
	ResponseType        string
	ClientID            string
	RedirectURI         string
	CodeChallenge       string
	CodeChallengeMethod string
	State               string
}

func (s *AuthServer) HandleAuthorize(w http.ResponseWriter, r *http.Request) {
	params, err := s.parseAuthorizeParams(r)
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"invalid_request","error_description":"%s"}`, err.Error()), http.StatusBadRequest)
		return
	}

	client, err := s.oauth2Repo.GetByID(params.ClientID)
	if err != nil {
		http.Error(w, `{"error":"invalid_request","error_description":"unknown client_id"}`, http.StatusBadRequest)
		return
	}

	if !s.isRegisteredRedirectURI(client, params.RedirectURI) {
		http.Error(w, `{"error":"invalid_request","error_description":"redirect_uri not registered"}`, http.StatusBadRequest)
		return
	}

	switch r.Method {
	case http.MethodGet:
		s.showLoginOrConsent(w, r, client, params)
	case http.MethodPost:
		action := r.FormValue("action")
		switch action {
		case "consent":
			s.handleConsent(w, r, client, params)
		default:
			http.Error(w, "invalid action", http.StatusBadRequest)
		}
	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

func (s *AuthServer) parseAuthorizeParams(r *http.Request) (*authorizeParams, error) {
	getValue := func(key string) string {
		if v := r.FormValue(key); v != "" {
			return v
		}
		return r.URL.Query().Get(key)
	}

	p := &authorizeParams{
		ResponseType:        getValue("response_type"),
		ClientID:            getValue("client_id"),
		RedirectURI:         getValue("redirect_uri"),
		CodeChallenge:       getValue("code_challenge"),
		CodeChallengeMethod: getValue("code_challenge_method"),
		State:               getValue("state"),
	}

	if p.ResponseType != "code" {
		return nil, fmt.Errorf("response_type must be 'code'")
	}
	if p.ClientID == "" {
		return nil, fmt.Errorf("client_id is required")
	}
	if p.RedirectURI == "" {
		return nil, fmt.Errorf("redirect_uri is required")
	}
	if p.CodeChallenge == "" {
		return nil, fmt.Errorf("code_challenge is required (PKCE)")
	}
	if p.CodeChallengeMethod != "S256" {
		return nil, fmt.Errorf("code_challenge_method must be S256")
	}

	return p, nil
}

func (s *AuthServer) isRegisteredRedirectURI(client *db.OAuth2Client, uri string) bool {
	if client.RedirectURIs == nil || *client.RedirectURIs == "" {
		return false
	}
	var uris []string
	if err := json.Unmarshal([]byte(*client.RedirectURIs), &uris); err != nil {
		return false
	}
	for _, registered := range uris {
		if registered == uri {
			return true
		}
	}
	return false
}

func (s *AuthServer) showLoginOrConsent(w http.ResponseWriter, r *http.Request, client *db.OAuth2Client, params *authorizeParams) {
	// Tier 1: existing OAuth2 authserver session — render consent directly.
	session, err := auth.GetSession(r, s.jwtSecret)
	if err == nil {
		if _, err := auth.ValidateJWT(session.Token, s.jwtSecret, ""); err == nil {
			s.renderConsent(w, r, client, params, session.Email)
			return
		}
	}

	// Tier 2: bridge from an active admin SSO session if one exists. Mint a
	// fresh mcp_session so subsequent requests in this OAuth2 flow find the
	// authserver session via tier 1.
	if email, ok := s.bridgeFromSSOSession(r); ok {
		if err := s.mintAuthSession(w, email, ""); err != nil {
			log.Printf("[authserver] bridge mint session: %v", err)
			// Fall through to tier 3 on failure so the user can still log in.
		} else {
			s.renderConsent(w, r, client, params, email)
			return
		}
	}

	// Tier 3: no usable session — redirect to /sso/login with the original
	// authorize URL preserved so the browser lands back here once the cookie
	// is set and tier 1 picks up.
	returnTo := "/authorize?" + r.URL.RawQuery
	q := url.Values{}
	q.Set("return_to", returnTo)
	q.Set("purpose", "oauth2")
	http.Redirect(w, r, "/sso/login?"+q.Encode(), http.StatusSeeOther)
}

// bridgeFromSSOSession returns the email of an authenticated admin user when
// the request carries a valid, non-expired gw_session cookie pointing to an
// sso_sessions row. The boolean distinguishes "no bridge possible" (cookie
// absent / row missing / expired / repo not configured) from "successful
// bridge".
func (s *AuthServer) bridgeFromSSOSession(r *http.Request) (string, bool) {
	if s.ssoSessionRepo == nil {
		return "", false
	}
	sid, err := sso.GetSessionID(r)
	if err != nil {
		return "", false
	}
	row, err := s.ssoSessionRepo.FindByID(sid)
	if err != nil || row == nil {
		return "", false
	}
	if !row.AccessExp.IsZero() && time.Now().After(row.AccessExp) {
		return "", false
	}
	if row.Email == "" {
		return "", false
	}
	return row.Email, true
}

// mintAuthSession writes the mcp_session cookie used by tier 1. The Token
// field stashes a freshly-minted JWT so auth.ValidateJWT in subsequent
// requests passes — the upstream account-service token is not available here,
// and the consent flow only needs the email + a non-empty session.
func (s *AuthServer) mintAuthSession(w http.ResponseWriter, email, displayName string) error {
	claims := auth.Claims{
		Exp:  time.Now().Add(24 * time.Hour).Unix(),
		Iat:  time.Now().Unix(),
		Name: displayName,
	}
	tok, err := auth.SignJWT(s.jwtSecret, claims)
	if err != nil {
		return err
	}
	return auth.SetSession(w, s.jwtSecret, auth.SessionData{
		DisplayName: displayName,
		Email:       email,
		Token:       tok,
	}, s.secureCookie)
}

func (s *AuthServer) renderConsent(w http.ResponseWriter, r *http.Request, client *db.OAuth2Client, params *authorizeParams, userEmail string) {
	// Check if the client has pre-configured server/tool scope (admin-assigned)
	hasPreConfiguredScope := len(client.Servers) > 0

	servers, _ := s.serverRepo.ListActive()

	// Build server lookup for name resolution + identify Zoho-tagged servers
	// so the per-user catalog override can substitute their tools below.
	serverMap := make(map[string]db.MCPServer, len(servers))
	zohoIDs := make(map[string]bool, len(servers))
	for _, srv := range servers {
		serverMap[srv.ID] = srv
		if isZohoServer(srv) {
			zohoIDs[srv.ID] = true
		}
	}

	// Per-viewer Zoho state — fetched once before iterating servers so we
	// can route unconfigured Zoho backends into a dedicated section while
	// keeping configured ones in the main list.
	log.Printf("[zoho-diag] renderConsent (HTML) email=%q client_id=%s pre_configured_scope=%t active_servers=%d zoho_servers=%d zoho_fetcher_wired=%t", userEmail, client.ID, hasPreConfiguredScope, len(servers), len(zohoIDs), s.zohoFetcher != nil)
	var zohoState map[string]gateway.ZohoServerState
	switch {
	case s.zohoFetcher == nil:
		log.Printf("[zoho-diag] renderConsent email=%q: zoho fetcher not wired — every Zoho server stays as cached admin tools", userEmail)
	case userEmail == "":
		log.Printf("[zoho-diag] renderConsent: userEmail is empty — every Zoho server stays as cached admin tools (anonymous browser?)")
	case len(zohoIDs) == 0:
		log.Printf("[zoho-diag] renderConsent email=%q: no Zoho-tagged servers registered — skipping fetch", userEmail)
	default:
		zohoState = s.zohoFetcher.FetchZohoStateForUser(r.Context(), userEmail)
		log.Printf("[zoho-diag] renderConsent email=%q: fetched zoho state entries=%d", userEmail, len(zohoState))
	}

	type toolEntry struct {
		Name        string
		Description string
		ServerID    string
	}
	type serverEntry struct {
		ID        string
		Name      string
		ToolCount int
		Checked   bool
		Tools     []toolEntry
	}

	var entries []serverEntry
	var unconfigured []serverEntry

	if hasPreConfiguredScope {
		// Client has admin-assigned scope — show only those servers/tools (read-only)
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
			entry := serverEntry{
				ID:      srv.ID,
				Name:    srv.Name,
				Checked: true,
			}
			// If specific tools are assigned, list them; otherwise all tools.
			// For Zoho-tagged servers, use the helper to decide whether to
			// show the server in the configured list or route it to the
			// "Non configurés" section.
			srvTools := allowedTools[srv.ID]
			source := srv.Tools
			if zohoIDs[srv.ID] {
				unconf, userTools := decideZohoServerEntry(srv.ID, zohoIDs, zohoState)
				if unconf {
					unconfigured = append(unconfigured, serverEntry{
						ID:        srv.ID,
						Name:      srv.Name,
						ToolCount: 0,
					})
					continue
				}
				source = toServerTools(userTools)
			}
			for _, t := range source {
				if srvTools != nil && !srvTools[t.Name] {
					continue
				}
				entry.Tools = append(entry.Tools, toolEntry{
					Name:        t.Name,
					Description: t.Description,
					ServerID:    srv.ID,
				})
			}
			entry.ToolCount = len(entry.Tools)
			entries = append(entries, entry)
		}
	} else {
		// No pre-configured scope — show all servers with tool picker
		var checkedIDs map[string]bool
		existing, err := s.consentRepo.FindByClientAndUser(client.ID, userEmail)
		if err == nil && existing != nil {
			scope, _ := ParseConsentScope(existing.Scope)
			if scope != nil {
				checkedIDs = make(map[string]bool)
				for _, sid := range scope.ServerIDs {
					checkedIDs[sid] = true
				}
			}
		}

		for _, srv := range servers {
			source := srv.Tools
			if zohoIDs[srv.ID] {
				unconf, userTools := decideZohoServerEntry(srv.ID, zohoIDs, zohoState)
				if unconf {
					unconfigured = append(unconfigured, serverEntry{
						ID:        srv.ID,
						Name:      srv.Name,
						ToolCount: 0,
					})
					continue
				}
				source = toServerTools(userTools)
			}
			entry := serverEntry{
				ID:        srv.ID,
				Name:      srv.Name,
				ToolCount: len(source),
				Checked:   checkedIDs[srv.ID],
			}
			for _, t := range source {
				entry.Tools = append(entry.Tools, toolEntry{
					Name:        t.Name,
					Description: t.Description,
					ServerID:    srv.ID,
				})
			}
			entries = append(entries, entry)
		}
	}

	csrfToken, _ := generateCSRFToken()
	http.SetCookie(w, &http.Cookie{
		Name:     "oauth2_csrf",
		Value:    csrfToken,
		Path:     "/authorize",
		MaxAge:   600,
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		Secure:   s.secureCookie,
	})

	consentTmpl.Execute(w, map[string]interface{}{
		"ClientName":          client.Name,
		"ClientID":            params.ClientID,
		"RedirectURI":         params.RedirectURI,
		"CodeChallenge":       params.CodeChallenge,
		"CodeChallengeMethod": params.CodeChallengeMethod,
		"State":               params.State,
		"CSRFToken":           csrfToken,
		"Servers":             entries,
		"UnconfiguredServers": unconfigured,
		"DocsURL":             s.docsURL,
		"PreConfigured":       hasPreConfiguredScope,
	})
}

func (s *AuthServer) handleConsent(w http.ResponseWriter, r *http.Request, client *db.OAuth2Client, params *authorizeParams) {
	csrfCookie, err := r.Cookie("oauth2_csrf")
	if err != nil || csrfCookie.Value != r.FormValue("csrf_token") {
		http.Error(w, "CSRF validation failed", http.StatusForbidden)
		return
	}
	http.SetCookie(w, &http.Cookie{Name: "oauth2_csrf", Path: "/authorize", MaxAge: -1})

	if r.FormValue("approved") != "true" {
		redirectWithError(w, r, params.RedirectURI, params.State, "access_denied", "user denied the request")
		return
	}

	session, err := auth.GetSession(r, s.jwtSecret)
	if err != nil {
		http.Error(w, "session expired", http.StatusUnauthorized)
		return
	}

	// Build scope: use pre-configured scope if client has admin-assigned servers, else from form
	var scope ConsentScope
	if len(client.Servers) > 0 {
		// Pre-configured scope — use the admin-assigned servers/tools
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
		// Dynamic client — scope from user selection in the form
		serverIDs := r.Form["server_ids"]
		if len(serverIDs) == 0 {
			http.Error(w, "select at least one server", http.StatusBadRequest)
			return
		}
		scope.ServerIDs = serverIDs
	}

	s.consentRepo.Upsert(&db.OAuth2Consent{
		ID:        uuid.New().String(),
		ClientID:  client.ID,
		UserEmail: session.Email,
		Scope:     scope.ToJSON(),
	})

	if client.CreatedBy == "" {
		s.oauth2Repo.Update(client.ID, map[string]interface{}{"created_by": session.Email})
	}

	rawCode, codeHash, err := GenerateAuthCode()
	if err != nil {
		log.Printf("[authserver] failed to generate auth code: %v", err)
		redirectWithError(w, r, params.RedirectURI, params.State, "server_error", "failed to generate code")
		return
	}

	authCode := db.OAuth2AuthorizationCode{
		CodeHash:      codeHash,
		ClientID:      client.ID,
		UserEmail:     session.Email,
		RedirectURI:   params.RedirectURI,
		CodeChallenge: params.CodeChallenge,
		Scope:         scope.ToJSON(),
		ExpiresAt:     time.Now().Add(10 * time.Minute),
	}
	if err := s.authCodeRepo.Create(&authCode); err != nil {
		log.Printf("[authserver] failed to store auth code: %v", err)
		redirectWithError(w, r, params.RedirectURI, params.State, "server_error", "failed to store code")
		return
	}

	go func() { s.authCodeRepo.PurgeExpired() }() //nolint:errcheck

	redirectURL, _ := url.Parse(params.RedirectURI)
	q := redirectURL.Query()
	q.Set("code", rawCode)
	if params.State != "" {
		q.Set("state", params.State)
	}
	redirectURL.RawQuery = q.Encode()

	http.Redirect(w, r, redirectURL.String(), http.StatusFound)
}

func redirectWithError(w http.ResponseWriter, r *http.Request, redirectURI, state, errCode, desc string) {
	u, _ := url.Parse(redirectURI)
	q := u.Query()
	q.Set("error", errCode)
	q.Set("error_description", desc)
	if state != "" {
		q.Set("state", state)
	}
	u.RawQuery = q.Encode()
	http.Redirect(w, r, u.String(), http.StatusFound)
}
