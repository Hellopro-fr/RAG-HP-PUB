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

func writeAuthErr(w http.ResponseWriter, code int, errCode, desc string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(map[string]string{
		"error":             errCode,
		"error_description": desc,
	})
}
