package authserver

import (
	"embed"
	"encoding/json"
	"fmt"
	"html/template"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/mcp-gateway/internal/auth"
	"github.com/hellopro/mcp-gateway/internal/db"
)

//go:embed templates/*.html
var templateFS embed.FS

var (
	loginTmpl   = template.Must(template.ParseFS(templateFS, "templates/login.html"))
	consentTmpl = template.Must(template.ParseFS(templateFS, "templates/consent.html"))
)

type authorizeParams struct {
	ResponseType        string
	ClientID            string
	RedirectURI         string
	CodeChallenge       string
	CodeChallengeMethod string
	State               string
}

func (s *AuthServer) HandleAuthorize(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("X-Frame-Options", "DENY")
	w.Header().Set("Content-Security-Policy", "frame-ancestors 'none'")

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
		case "login":
			s.handleLogin(w, r, client, params)
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
	session, err := auth.GetSession(r, s.jwtSecret)
	if err == nil {
		if _, err := auth.ValidateJWT(session.Token, s.jwtSecret, ""); err == nil {
			s.renderConsent(w, client, params, session.Email)
			return
		}
	}

	loginTmpl.Execute(w, map[string]string{
		"ClientName":          client.Name,
		"ClientID":            params.ClientID,
		"RedirectURI":         params.RedirectURI,
		"CodeChallenge":       params.CodeChallenge,
		"CodeChallengeMethod": params.CodeChallengeMethod,
		"State":               params.State,
		"Error":               "",
		"Username":            "",
	})
}

func (s *AuthServer) handleLogin(w http.ResponseWriter, r *http.Request, client *db.OAuth2Client, params *authorizeParams) {
	username := strings.TrimSpace(r.FormValue("username"))
	password := r.FormValue("password")

	if username == "" || password == "" {
		loginTmpl.Execute(w, map[string]string{
			"ClientName":          client.Name,
			"ClientID":            params.ClientID,
			"RedirectURI":         params.RedirectURI,
			"CodeChallenge":       params.CodeChallenge,
			"CodeChallengeMethod": params.CodeChallengeMethod,
			"State":               params.State,
			"Error":               "Tous les champs sont obligatoires",
			"Username":            username,
		})
		return
	}

	authResp, err := auth.AuthenticateHellopro(s.authURL, username, password)
	if err != nil || !authResp.Success {
		log.Printf("[authserver] login failed for %s", username)
		loginTmpl.Execute(w, map[string]string{
			"ClientName":          client.Name,
			"ClientID":            params.ClientID,
			"RedirectURI":         params.RedirectURI,
			"CodeChallenge":       params.CodeChallenge,
			"CodeChallengeMethod": params.CodeChallengeMethod,
			"State":               params.State,
			"Error":               "Login / Mot de passe invalide",
			"Username":            username,
		})
		return
	}

	token := authResp.Token
	if token == "" {
		claims := auth.Claims{
			Exp:  time.Now().Add(24 * time.Hour).Unix(),
			Iat:  time.Now().Unix(),
			Name: authResp.DisplayName,
		}
		token, _ = auth.SignJWT(s.jwtSecret, claims)
	}
	auth.SetSession(w, s.jwtSecret, auth.SessionData{
		DisplayName: authResp.DisplayName,
		Email:       authResp.Email,
		Token:       token,
	}, s.secureCookie)

	log.Printf("[authserver] user %s logged in for OAuth2 authorize", authResp.Email)
	s.renderConsent(w, client, params, authResp.Email)
}

func (s *AuthServer) renderConsent(w http.ResponseWriter, client *db.OAuth2Client, params *authorizeParams, userEmail string) {
	servers, _ := s.serverRepo.ListActive()

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

	type serverEntry struct {
		ID        string
		Name      string
		ToolCount int
		Checked   bool
	}
	entries := make([]serverEntry, len(servers))
	for i, srv := range servers {
		entries[i] = serverEntry{
			ID:        srv.ID,
			Name:      srv.Name,
			ToolCount: len(srv.Tools),
			Checked:   checkedIDs[srv.ID],
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

	serverIDs := r.Form["server_ids"]
	if len(serverIDs) == 0 {
		http.Error(w, "select at least one server", http.StatusBadRequest)
		return
	}

	scope := ConsentScope{ServerIDs: serverIDs}

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
