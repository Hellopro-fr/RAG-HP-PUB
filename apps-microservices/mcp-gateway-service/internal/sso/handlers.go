package sso

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/hellopro/mcp-gateway/internal/crypto"
	"github.com/hellopro/mcp-gateway/internal/db"
	"github.com/hellopro/mcp-gateway/internal/repository"
)

// userUpserter abstracts repository.UserRepo's UpsertOnLogin so handlers can
// be tested without spinning up a full GORM stack.
type userUpserter interface {
	UpsertOnLogin(email, displayName string) (*db.GatewayUser, error)
}

// Handlers carries shared dependencies for the /sso/* HTTP routes. Set up
// once at boot and registered via RegisterHandlers.
type Handlers struct {
	client     *Client
	repo       *repository.SSOSessionRepo
	users      userUpserter
	encryptor  *crypto.Encryptor
	stateKey   []byte
	secureCk   bool
}

// NewHandlers builds a Handlers struct. Nil dependencies are tolerated for
// the TDD-gate compile test; production wiring must pass everything.
func NewHandlers(client *Client, repo *repository.SSOSessionRepo, users userUpserter, encryptor *crypto.Encryptor, secureCk bool) *Handlers {
	return &Handlers{client: client, repo: repo, users: users, encryptor: encryptor, secureCk: secureCk}
}

// WithStateKey sets the HMAC key (typically JWT_SECRET) used to sign the
// short-lived gw_sso_pending cookie that round-trips the PKCE verifier.
func (h *Handlers) WithStateKey(key []byte) *Handlers {
	h.stateKey = key
	return h
}

// RegisterHandlers mounts /sso/login, /sso/callback, /logout, and the
// account-service-initiated webhook /api/v1/sso/logout on the supplied mux.
func (h *Handlers) RegisterHandlers(mux *http.ServeMux) {
	mux.HandleFunc("/sso/login", h.handleLogin)
	mux.HandleFunc("/sso/callback", h.handleCallback)
	mux.HandleFunc("/logout", h.handleLogout)
	mux.HandleFunc("/api/v1/sso/logout", h.handleSSOLogoutWebhook)
}

// GET /sso/login — generate verifier+state, set pending cookie, redirect to
// account-service /authorize.
func (h *Handlers) handleLogin(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	verifier, err := GenerateVerifier()
	if err != nil {
		http.Error(w, "failed to init login", http.StatusInternalServerError)
		return
	}
	stateNonce, err := GenerateVerifier()
	if err != nil {
		http.Error(w, "failed to init login", http.StatusInternalServerError)
		return
	}
	returnTo := r.URL.Query().Get("return_to")
	if returnTo == "" || !strings.HasPrefix(returnTo, "/") {
		returnTo = "/"
	}

	pending := PendingState{
		Verifier: verifier,
		State:    stateNonce,
		ReturnTo: returnTo,
		Exp:      time.Now().Add(5 * time.Minute).Unix(),
	}
	cookieVal, err := SignPendingState(h.stateKey, pending)
	if err != nil {
		http.Error(w, "failed to sign state", http.StatusInternalServerError)
		return
	}
	SetPendingCookie(w, cookieVal, h.secureCk)

	authorizeURL, err := h.client.BuildAuthorizeURL(S256Challenge(verifier), stateNonce)
	if err != nil {
		http.Error(w, "failed to build authorize URL", http.StatusInternalServerError)
		return
	}
	http.Redirect(w, r, authorizeURL, http.StatusSeeOther)
}

// GET /sso/callback — verify pending cookie, exchange code, persist session, redirect.
func (h *Handlers) handleCallback(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	cookieVal, err := GetPendingCookie(r)
	if err != nil {
		http.Error(w, "no pending login", http.StatusBadRequest)
		return
	}
	pending, err := VerifyPendingState(h.stateKey, cookieVal)
	if err != nil {
		log.Printf("[sso] callback: pending state invalid: %v", err)
		http.Error(w, "login expired or tampered, please retry", http.StatusBadRequest)
		return
	}
	ClearPendingCookie(w, h.secureCk)

	q := r.URL.Query()
	if errCode := q.Get("error"); errCode != "" {
		desc := q.Get("error_description")
		http.Error(w, fmt.Sprintf("authorization failed: %s — %s", errCode, desc), http.StatusUnauthorized)
		return
	}
	code := q.Get("code")
	state := q.Get("state")
	if code == "" || state == "" {
		http.Error(w, "missing code or state", http.StatusBadRequest)
		return
	}
	if state != pending.State {
		log.Printf("[sso] callback: state mismatch")
		http.Error(w, "state mismatch", http.StatusBadRequest)
		return
	}

	tok, err := h.client.ExchangeCode(r.Context(), code, pending.Verifier, h.client.RedirectURI)
	if err != nil {
		log.Printf("[sso] callback: token exchange failed: %v", err)
		http.Error(w, "token exchange failed", http.StatusBadGateway)
		return
	}

	sub, email, name, err := ParseAccessTokenIdentity(tok.AccessToken)
	if err != nil || email == "" {
		log.Printf("[sso] callback: cannot parse identity from access token: %v", err)
		http.Error(w, "invalid token payload", http.StatusBadGateway)
		return
	}

	user, err := h.users.UpsertOnLogin(email, name)
	if err != nil {
		log.Printf("[sso] callback: upsert user failed: %v", err)
		http.Error(w, "failed to provision user", http.StatusInternalServerError)
		return
	}
	if user != nil && !user.IsAllowed {
		http.Error(w, "Access denied. Contact an administrator.", http.StatusForbidden)
		return
	}

	sid, err := NewSessionID()
	if err != nil {
		http.Error(w, "session error", http.StatusInternalServerError)
		return
	}
	accessEnc, err := h.encryptor.Encrypt([]byte(tok.AccessToken))
	if err != nil {
		http.Error(w, "encryption error", http.StatusInternalServerError)
		return
	}
	refreshEnc, err := h.encryptor.Encrypt([]byte(tok.RefreshToken))
	if err != nil {
		http.Error(w, "encryption error", http.StatusInternalServerError)
		return
	}

	accessExp := time.Now().Add(time.Duration(tok.ExpiresIn) * time.Second)
	refreshExp := time.Now().Add(30 * 24 * time.Hour)
	if tok.RefreshExpiresIn > 0 {
		refreshExp = time.Now().Add(time.Duration(tok.RefreshExpiresIn) * time.Second)
	}

	row := &db.SSOSession{
		ID:           sid,
		UserID:       user.ID,
		Sub:          sub,
		Email:        email,
		AccessToken:  accessEnc,
		RefreshToken: refreshEnc,
		AccessExp:    accessExp,
		RefreshExp:   refreshExp,
		LastSeenAt:   time.Now(),
		UserAgent:    truncate(r.UserAgent(), 255),
		ClientIP:     truncate(clientIP(r), 45),
	}
	if err := h.repo.Create(row); err != nil {
		log.Printf("[sso] callback: persist session failed: %v", err)
		http.Error(w, "session error", http.StatusInternalServerError)
		return
	}

	SetSessionCookie(w, sid, h.secureCk)
	target := pending.ReturnTo
	if target == "" {
		target = "/"
	}
	http.Redirect(w, r, target, http.StatusSeeOther)
}

// POST /logout — user-initiated logout. Best-effort revoke at account-service,
// then drop the row + clear cookie, then redirect.
func (h *Handlers) handleLogout(w http.ResponseWriter, r *http.Request) {
	sid, err := GetSessionID(r)
	if err == nil {
		if sess, err := h.repo.FindByID(sid); err == nil && sess != nil {
			if refresh, err := h.encryptor.Decrypt(sess.RefreshToken); err == nil {
				ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
				_ = h.client.Revoke(ctx, string(refresh), "refresh_token")
				cancel()
			}
			_ = h.repo.Delete(sid)
		}
	}
	ClearSessionCookie(w, h.secureCk)

	if strings.Contains(r.Header.Get("Accept"), "application/json") {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true}`))
		return
	}
	http.Redirect(w, r, "/sso/login", http.StatusSeeOther)
}

// POST /api/v1/sso/logout — back-channel webhook from account-service. HMAC-
// signed body identifies the user/session to invalidate.
func (h *Handlers) handleSSOLogoutWebhook(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, 4096))
	if err != nil {
		http.Error(w, "read body", http.StatusBadRequest)
		return
	}
	sig := r.Header.Get("X-Account-Signature")
	if err := VerifyWebhookSignature([]byte(h.client.ClientSecret), body, sig); err != nil {
		log.Printf("[sso] webhook signature rejected: %v", err)
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	var payload struct {
		Sub string `json:"sub"`
		Sid string `json:"sid,omitempty"`
	}
	if err := json.Unmarshal(body, &payload); err != nil {
		http.Error(w, "bad json", http.StatusBadRequest)
		return
	}
	if payload.Sid != "" {
		_ = h.repo.Delete(payload.Sid)
	} else if payload.Sub != "" {
		_, _ = h.repo.DeleteBySub(payload.Sub)
	} else {
		http.Error(w, "missing sub or sid", http.StatusBadRequest)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// ParseAccessTokenIdentity decodes the JWT payload (no signature check — we
// trust account-service since we just received the token from it over a
// client-secret-authenticated TLS exchange) and returns sub, email, and best-
// effort display name. Returns error if the token isn't a JWT or lacks payload.
func ParseAccessTokenIdentity(token string) (sub, email, name string, err error) {
	parts := strings.Split(token, ".")
	if len(parts) < 2 {
		return "", "", "", errors.New("not a JWT")
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		// Tolerate padded variant
		payload, err = base64.URLEncoding.DecodeString(parts[1])
		if err != nil {
			return "", "", "", fmt.Errorf("decode payload: %w", err)
		}
	}
	var claims struct {
		Sub   string `json:"sub"`
		Email string `json:"email"`
		Name  string `json:"name"`
		PreferredName string `json:"preferred_username"`
	}
	if err := json.Unmarshal(payload, &claims); err != nil {
		return "", "", "", fmt.Errorf("parse claims: %w", err)
	}
	displayName := claims.Name
	if displayName == "" {
		displayName = claims.PreferredName
	}
	return claims.Sub, claims.Email, displayName, nil
}

func clientIP(r *http.Request) string {
	if v := r.Header.Get("X-Forwarded-For"); v != "" {
		if i := strings.Index(v, ","); i >= 0 {
			return strings.TrimSpace(v[:i])
		}
		return strings.TrimSpace(v)
	}
	if v := r.Header.Get("X-Real-IP"); v != "" {
		return v
	}
	return r.RemoteAddr
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}
