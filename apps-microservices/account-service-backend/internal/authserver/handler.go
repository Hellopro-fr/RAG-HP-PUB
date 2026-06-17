package authserver

import (
	"encoding/json"
	"net/http"
	"net/url"
	"time"

	"account-service/internal/auth"
	"account-service/internal/db"
)

type AuthCodeRepo interface {
	Create(c *db.OAuth2AuthorizationCode) error
}

type ClientRepo interface {
	GetByClientID(id string) (*db.OAuth2Client, error)
}

type AuthServerDeps struct {
	ClientRepo    ClientRepo
	AuthCodeRepo  AuthCodeRepo
	UserUpserter  auth.UserUpserter
	AuthURL       string
	JWTSecret     string
	JWTAudience   string
	Issuer        string
	AuthCodeTTL   time.Duration
	SecureCookie  bool
	FallbackUser  string
	FallbackPass  string
	FallbackEmail string
	LoginPath     string
}

type AuthServer struct {
	deps AuthServerDeps
}

func NewAuthServer(d AuthServerDeps) *AuthServer {
	if d.AuthCodeTTL == 0 {
		d.AuthCodeTTL = 10 * time.Minute
	}
	if d.LoginPath == "" {
		d.LoginPath = "/login"
	}
	return &AuthServer{deps: d}
}

func (s *AuthServer) HandleAuthorize(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	p, err := parseAuthorizeParams(r)
	if err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", err.Error())
		return
	}
	client, err := s.deps.ClientRepo.GetByClientID(p.ClientID)
	if err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "unknown client_id")
		return
	}
	if !client.IsActive {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "client inactive")
		return
	}
	if !isRegisteredRedirectURI(client, p.RedirectURI) {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "redirect_uri not registered")
		return
	}

	switch r.Method {
	case http.MethodGet:
		// Already authenticated browser → issue code immediately (skip consent)
		if sess, err := auth.GetSession(r, s.deps.JWTSecret); err == nil {
			s.issueCodeAndRedirect(w, r, client, p, sess.Email)
			return
		}
		// Otherwise bounce to Vue login route, preserving every OAuth2 param
		http.Redirect(w, r, s.deps.LoginPath+"?"+loginRedirectParams(p).Encode(), http.StatusFound)

	case http.MethodPost:
		if r.FormValue("action") != "login" {
			writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "unknown action")
			return
		}
		s.handleLogin(w, r, client, p)

	default:
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
	}
}

// loginRedirectParams rebuilds the OAuth2 query string the Vue login route
// needs to re-render and re-submit the consent form. Shared by the GET bounce
// (unauthenticated browser) and the POST failure bounce (redirectLoginErr).
func loginRedirectParams(p *AuthorizeParams) url.Values {
	q := url.Values{}
	q.Set("response_type", p.ResponseType)
	q.Set("client_id", p.ClientID)
	q.Set("redirect_uri", p.RedirectURI)
	q.Set("code_challenge", p.CodeChallenge)
	q.Set("code_challenge_method", p.CodeChallengeMethod)
	if p.State != "" {
		q.Set("state", p.State)
	}
	return q
}

// redirectLoginErr bounces a failed login back to the Vue login page, keeping
// every OAuth2 param plus a machine-readable error code (the frontend maps it
// to a French message) and the typed username so only the password is re-entered.
func (s *AuthServer) redirectLoginErr(w http.ResponseWriter, r *http.Request, p *AuthorizeParams, errCode string) {
	q := loginRedirectParams(p)
	if username := r.FormValue("username"); username != "" {
		q.Set("username", username)
	}
	q.Set("error", errCode)
	http.Redirect(w, r, s.deps.LoginPath+"?"+q.Encode(), http.StatusFound)
}

func (s *AuthServer) handleLogin(w http.ResponseWriter, r *http.Request, client *db.OAuth2Client, p *AuthorizeParams) {
	username := r.FormValue("username")
	password := r.FormValue("password")
	if username == "" || password == "" {
		s.redirectLoginErr(w, r, p, "missing_credentials")
		return
	}
	resp, err := auth.AuthenticateHellopro(s.deps.AuthURL, username, password)
	if (err != nil || !resp.Success) && s.deps.FallbackUser != "" &&
		username == s.deps.FallbackUser && password == s.deps.FallbackPass {
		resp = &auth.HelloProAuthResponse{
			Success:     true,
			Email:       s.deps.FallbackEmail,
			DisplayName: s.deps.FallbackUser,
		}
		err = nil
	}
	if err != nil || !resp.Success {
		s.redirectLoginErr(w, r, p, "credentials_error")
		return
	}
	u, err := s.deps.UserUpserter.UpsertOnLogin(resp.Email, resp.DisplayName)
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "user upsert failed")
		return
	}
	if !u.IsAllowed {
		s.redirectLoginErr(w, r, p, "user_blocked")
		return
	}
	if !s.userMatchesAllowedRoles(u, client) {
		s.redirectLoginErr(w, r, p, "role_not_allowed")
		return
	}
	_ = auth.SetSession(w, s.deps.JWTSecret, auth.SessionData{
		Email: u.Email, DisplayName: resp.DisplayName,
	}, s.deps.SecureCookie)
	s.issueCodeAndRedirect(w, r, client, p, u.Email)
}

func (s *AuthServer) userMatchesAllowedRoles(u *auth.UpsertedUser, c *db.OAuth2Client) bool {
	if c.AllowedRoles == nil || *c.AllowedRoles == "" || *c.AllowedRoles == "null" || *c.AllowedRoles == "[]" {
		return true
	}
	var roles []string
	if err := json.Unmarshal([]byte(*c.AllowedRoles), &roles); err != nil {
		return true
	}
	if len(roles) == 0 {
		return true
	}
	role := "user"
	if u.IsAdmin {
		role = "admin"
	}
	for _, r := range roles {
		if r == role {
			return true
		}
	}
	return false
}

func (s *AuthServer) issueCodeAndRedirect(w http.ResponseWriter, r *http.Request, c *db.OAuth2Client, p *AuthorizeParams, userEmail string) {
	raw, hash, err := GenerateAuthCode()
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "code gen failed")
		return
	}
	code := &db.OAuth2AuthorizationCode{
		CodeHash:      hash,
		ClientID:      c.ClientID,
		UserEmail:     userEmail,
		RedirectURI:   p.RedirectURI,
		CodeChallenge: p.CodeChallenge,
		Scope:         p.Scope,
		ExpiresAt:     time.Now().Add(s.deps.AuthCodeTTL),
	}
	if err := s.deps.AuthCodeRepo.Create(code); err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "code persist failed")
		return
	}
	u, _ := url.Parse(p.RedirectURI)
	q := u.Query()
	q.Set("code", raw)
	if p.State != "" {
		q.Set("state", p.State)
	}
	u.RawQuery = q.Encode()
	http.Redirect(w, r, u.String(), http.StatusFound)
}

func writeOAuthErr(w http.ResponseWriter, code int, errCode, desc string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"error":             errCode,
		"error_description": desc,
	})
}
