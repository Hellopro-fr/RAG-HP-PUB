package auth

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"
)

// Config carries the env-derived knobs the auth package uses. Wired by main.go.
type Config struct {
	AuthURL       string
	JWTSecret     string
	JWTAudience   string
	SecureCookie  bool
	FallbackUser  string
	FallbackPass  string
	FallbackEmail string
}

// UserUpserter is the interface the login handler depends on. The real
// implementation is repository.UserRepo wrapped via UserUpserterFunc.
type UserUpserter interface {
	UpsertOnLogin(email, displayName string) (*UpsertedUser, error)
}

// UserUpserterFunc adapts a free function to the UserUpserter interface.
type UserUpserterFunc func(email, displayName string) (*UpsertedUser, error)

func (f UserUpserterFunc) UpsertOnLogin(email, displayName string) (*UpsertedUser, error) {
	return f(email, displayName)
}

// UpsertedUser is the minimal shape the handler reads back.
type UpsertedUser struct {
	Email     string
	IsAdmin   bool
	IsAllowed bool
}

func NewLoginHandler(cfg Config, repo UserUpserter) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		var body struct {
			Username string `json:"username"`
			Password string `json:"password"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeAuthErr(w, http.StatusBadRequest, "invalid_request", "invalid body")
			return
		}
		username := strings.TrimSpace(body.Username)
		if username == "" || body.Password == "" {
			writeAuthErr(w, http.StatusBadRequest, "invalid_request", "missing fields")
			return
		}

		resp, err := AuthenticateHellopro(cfg.AuthURL, username, body.Password)
		if (err != nil || !resp.Success) && cfg.FallbackUser != "" &&
			username == cfg.FallbackUser && body.Password == cfg.FallbackPass {
			resp = &HelloProAuthResponse{
				Success:     true,
				Email:       cfg.FallbackEmail,
				DisplayName: cfg.FallbackUser,
			}
			err = nil
		}
		if err != nil {
			writeAuthErr(w, http.StatusUnauthorized, "auth_error", "authentication failed")
			return
		}
		if !resp.Success {
			writeAuthErr(w, http.StatusUnauthorized, "invalid_grant", "invalid credentials")
			return
		}

		u, err := repo.UpsertOnLogin(resp.Email, resp.DisplayName)
		if err != nil {
			writeAuthErr(w, http.StatusInternalServerError, "server_error", "user upsert failed")
			return
		}
		if !u.IsAllowed {
			writeAuthErr(w, http.StatusForbidden, "forbidden", "user blocked")
			return
		}

		claims := Claims{
			Sub:     u.Email,
			Email:   u.Email,
			Name:    resp.DisplayName,
			Aud:     cfg.JWTAudience,
			Iat:     time.Now().Unix(),
			Exp:     time.Now().Add(24 * time.Hour).Unix(),
			IsAdmin: u.IsAdmin,
		}
		tok, err := SignJWT(cfg.JWTSecret, claims)
		if err != nil {
			writeAuthErr(w, http.StatusInternalServerError, "server_error", "sign failed")
			return
		}
		_ = SetSession(w, cfg.JWTSecret, SessionData{
			Email: u.Email, DisplayName: resp.DisplayName, Token: tok,
		}, cfg.SecureCookie)

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]interface{}{
			"token":        tok,
			"email":        u.Email,
			"display_name": resp.DisplayName,
			"is_admin":     u.IsAdmin,
		})
	})
}

func NewLogoutHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ClearSession(w)
		w.WriteHeader(http.StatusNoContent)
	})
}

// LogoutRedirectLookup is the interface the redirect-style logout handler
// depends on. Implementations resolve a client_id to its registered
// redirect_uris.
type LogoutRedirectLookup interface {
	GetClientRedirectURIs(clientID string) ([]string, error)
}

// NewLogoutRedirectHandler exposes a browser-friendly GET /logout that clears
// the account_session cookie and 302s the browser back to a caller-supplied
// post_logout_redirect_uri. The redirect target must (1) parse as an absolute
// http(s) URL and (2) share host[:port] with one of the registered redirect_uris
// of the supplied client_id; otherwise the handler falls back to /login. This
// blocks the obvious open-redirect vector and keeps the trust boundary aligned
// with OAuth2's redirect_uri allow-list — there is no separate logout allow-list
// to maintain.
func NewLogoutRedirectHandler(repo LogoutRedirectLookup) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ClearSession(w)

		target := r.URL.Query().Get("post_logout_redirect_uri")
		clientID := r.URL.Query().Get("client_id")
		fallback := "/login"

		if target == "" || clientID == "" || repo == nil {
			http.Redirect(w, r, fallback, http.StatusSeeOther)
			return
		}
		uris, err := repo.GetClientRedirectURIs(clientID)
		if err != nil || len(uris) == 0 {
			http.Redirect(w, r, fallback, http.StatusSeeOther)
			return
		}
		if !sameHostAsAny(target, uris) {
			http.Redirect(w, r, fallback, http.StatusSeeOther)
			return
		}
		http.Redirect(w, r, target, http.StatusSeeOther)
	})
}

func sameHostAsAny(rawURL string, registered []string) bool {
	tHost, tScheme, ok := splitHostScheme(rawURL)
	if !ok {
		return false
	}
	for _, u := range registered {
		rHost, rScheme, ok := splitHostScheme(strings.TrimSpace(u))
		if !ok {
			continue
		}
		if tScheme == rScheme && tHost == rHost {
			return true
		}
	}
	return false
}

// splitHostScheme parses raw and returns (host[:port], scheme, true) for absolute
// http/https URLs. Anything else returns ok=false.
func splitHostScheme(raw string) (string, string, bool) {
	const httpsPrefix = "https://"
	const httpPrefix = "http://"
	var rest, scheme string
	switch {
	case strings.HasPrefix(raw, httpsPrefix):
		scheme = "https"
		rest = raw[len(httpsPrefix):]
	case strings.HasPrefix(raw, httpPrefix):
		scheme = "http"
		rest = raw[len(httpPrefix):]
	default:
		return "", "", false
	}
	end := len(rest)
	for i, c := range rest {
		if c == '/' || c == '?' || c == '#' {
			end = i
			break
		}
	}
	host := rest[:end]
	if host == "" {
		return "", "", false
	}
	return host, scheme, true
}

func writeAuthErr(w http.ResponseWriter, code int, errCode, desc string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"error":             errCode,
		"error_description": desc,
	})
}
