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
	"net/url"
	"strings"
	"time"

	"mcp-gateway/internal/crypto"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/repository"
)

// userUpserter abstracts repository.UserRepo's UpsertOnLogin so handlers can
// be tested without spinning up a full GORM stack.
type userUpserter interface {
	UpsertOnLogin(email, displayName string) (*db.GatewayUser, error)
}

// Handlers carries shared dependencies for the /sso/* HTTP routes. Set up
// once at boot and registered via RegisterHandlers.
type Handlers struct {
	client    *Client
	repo      *repository.SSOSessionRepo
	users     userUpserter
	encryptor *crypto.Encryptor
	stateKey  []byte
	secureCk  bool
	// gatewayPublicURL is the externally-reachable base URL of this service
	// (e.g. http://mcp-hellopro.com:8581). Used as post_logout_redirect_uri
	// when bouncing the browser through account-service /logout.
	gatewayPublicURL string
	// slack is the optional dedicated SSO error notifier (LOGIN_SLACK_URL).
	// nil = notifications disabled.
	slack *SlackNotifier
	// authJWTSecret is the HMAC key used by internal/auth.SetSession when the
	// SSO callback runs the OAuth2-authorize flow. Empty disables the OAuth2
	// branch (callback returns 500 if a Purpose=oauth2 pending state arrives
	// without a configured secret).
	authJWTSecret string
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

// WithGatewayPublicURL records this gateway's externally-reachable URL. The
// /logout handler uses it to build a post_logout_redirect_uri that account-
// service can validate against the gateway's registered redirect_uris.
func (h *Handlers) WithGatewayPublicURL(u string) *Handlers {
	h.gatewayPublicURL = strings.TrimRight(u, "/")
	return h
}

// WithSlack attaches a Slack notifier used to forward SSO error events to a
// dedicated webhook (LOGIN_SLACK_URL). Pass nil to disable notifications.
func (h *Handlers) WithSlack(s *SlackNotifier) *Handlers {
	h.slack = s
	return h
}

// WithAuthSession registers the JWT secret used to sign the mcp_session cookie
// when a Purpose=oauth2 callback completes. Wire from cfg.JWTSecret.
func (h *Handlers) WithAuthSession(jwtSecret string) *Handlers {
	h.authJWTSecret = jwtSecret
	return h
}

// notify is a nil-safe shorthand that fills the request-scoped fields on
// the event (path, query, IP, UA) before forwarding to the Slack notifier.
func (h *Handlers) notify(r *http.Request, ev SSOErrorEvent) {
	if h.slack == nil {
		return
	}
	if ev.RequestPath == "" {
		ev.RequestPath = r.URL.Path
	}
	if ev.Query == "" {
		ev.Query = sanitiseQuery(r.URL.RawQuery)
	}
	if ev.ClientIP == "" {
		ev.ClientIP = clientIP(r)
	}
	if ev.UserAgent == "" {
		ev.UserAgent = r.UserAgent()
	}
	h.slack.Notify(ev)
}

// redirectError 303s the browser back to /login with error + error_description
// query params so LoginView can render a user-friendly error UI instead of a
// raw plain-text 4xx page. Used from every error site in /sso/callback.
func (h *Handlers) redirectError(w http.ResponseWriter, r *http.Request, kind, message string) {
	q := url.Values{}
	q.Set("error", kind)
	if message != "" {
		q.Set("error_description", message)
	}
	http.Redirect(w, r, "/login?"+q.Encode(), http.StatusSeeOther)
}

// sanitiseQuery shortens code= / state= / refresh_token= values so they don't
// fill Slack messages with credential-shaped strings. Keeps the prefix as
// evidence the param was present without leaking the full secret.
func sanitiseQuery(raw string) string {
	if raw == "" {
		return ""
	}
	parts := strings.Split(raw, "&")
	for i, p := range parts {
		eq := strings.IndexByte(p, '=')
		if eq < 0 {
			continue
		}
		key := p[:eq]
		val := p[eq+1:]
		switch key {
		case "code", "state", "refresh_token", "access_token", "client_secret", "token":
			if len(val) > 12 {
				val = val[:12] + "…"
			}
			parts[i] = key + "=" + val
		}
	}
	return strings.Join(parts, "&")
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
		h.notify(r, SSOErrorEvent{Kind: "no_pending_login", Reason: err.Error()})
		h.redirectError(w, r, "no_pending_login", "Aucune session de connexion en cours, merci de réessayer.")
		return
	}
	pending, err := VerifyPendingState(h.stateKey, cookieVal)
	if err != nil {
		log.Printf("[sso] callback: pending state invalid: %v", err)
		h.notify(r, SSOErrorEvent{Kind: "pending_state_invalid", Reason: err.Error()})
		h.redirectError(w, r, "pending_state_invalid", "La connexion a expiré ou a été altérée, merci de réessayer.")
		return
	}
	ClearPendingCookie(w, h.secureCk)

	q := r.URL.Query()
	if errCode := q.Get("error"); errCode != "" {
		desc := q.Get("error_description")
		h.notify(r, SSOErrorEvent{
			Kind:   "authorization_error",
			Reason: errCode + ": " + desc,
		})
		h.redirectError(w, r, errCode, desc)
		return
	}
	code := q.Get("code")
	state := q.Get("state")
	if code == "" || state == "" {
		h.notify(r, SSOErrorEvent{Kind: "missing_code_or_state", Reason: "code or state empty"})
		h.redirectError(w, r, "missing_code_or_state", "La réponse d'authentification est incomplète.")
		return
	}
	if state != pending.State {
		log.Printf("[sso] callback: state mismatch (query=%s pending=%s return_to=%s)", state, pending.State, pending.ReturnTo)
		h.notify(r, SSOErrorEvent{
			Kind:   "state_mismatch",
			Reason: "query state did not match pending state",
			ExtraFields: map[string]string{
				"query_state":   state,
				"pending_state": pending.State,
				"return_to":     pending.ReturnTo,
			},
		})
		h.redirectError(w, r, "state_mismatch", "Le jeton d'état ne correspond pas. Merci de réessayer.")
		return
	}

	tok, err := h.client.ExchangeCode(r.Context(), code, pending.Verifier, h.client.RedirectURI)
	if err != nil {
		log.Printf("[sso] callback: token exchange failed: %v", err)
		h.notify(r, SSOErrorEvent{Kind: "token_exchange_failed", Reason: err.Error()})
		h.redirectError(w, r, "token_exchange_failed", "Échange du jeton avec le serveur d'authentification impossible.")
		return
	}

	sub, email, name, err := ParseAccessTokenIdentity(tok.AccessToken)
	if err != nil || email == "" {
		log.Printf("[sso] callback: cannot parse identity from access token: %v", err)
		reason := "missing email claim"
		if err != nil {
			reason = err.Error()
		}
		h.notify(r, SSOErrorEvent{Kind: "invalid_token_payload", Reason: reason})
		h.redirectError(w, r, "invalid_token_payload", "Le jeton d'authentification est invalide.")
		return
	}

	user, err := h.users.UpsertOnLogin(email, name)
	if err != nil {
		log.Printf("[sso] callback: upsert user failed: %v", err)
		h.notify(r, SSOErrorEvent{Kind: "upsert_failed", Reason: err.Error(), UserEmail: email, Sub: sub})
		h.redirectError(w, r, "upsert_failed", "Provisionnement de l'utilisateur impossible.")
		return
	}
	if user != nil && !user.IsAllowed {
		h.notify(r, SSOErrorEvent{
			Kind:      "user_blocked",
			Reason:    "user authenticated but is_allowed=false",
			UserEmail: email,
			Sub:       sub,
		})
		h.redirectError(w, r, "user_blocked", "Accès refusé. Contactez un administrateur.")
		return
	}

	sid, err := NewSessionID()
	if err != nil {
		h.notify(r, SSOErrorEvent{Kind: "session_id_gen_failed", Reason: err.Error(), UserEmail: email})
		h.redirectError(w, r, "session_id_gen_failed", "Erreur interne lors de la création de la session.")
		return
	}
	accessEnc, err := h.encryptor.Encrypt([]byte(tok.AccessToken))
	if err != nil {
		h.notify(r, SSOErrorEvent{Kind: "encrypt_access_failed", Reason: err.Error(), UserEmail: email})
		h.redirectError(w, r, "encrypt_access_failed", "Erreur de chiffrement du jeton d'accès.")
		return
	}
	refreshEnc, err := h.encryptor.Encrypt([]byte(tok.RefreshToken))
	if err != nil {
		h.notify(r, SSOErrorEvent{Kind: "encrypt_refresh_failed", Reason: err.Error(), UserEmail: email})
		h.redirectError(w, r, "encrypt_refresh_failed", "Erreur de chiffrement du jeton de rafraîchissement.")
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
		h.notify(r, SSOErrorEvent{Kind: "session_persist_failed", Reason: err.Error(), UserEmail: email, Sub: sub})
		h.redirectError(w, r, "session_persist_failed", "Erreur lors de la persistance de la session.")
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
// drop the local session row, clear the cookie, then bounce the browser
// through account-service's /logout so its admin-UI session cookie also dies
// (single-sign-out). Account-service redirects back to /sso/login here once
// the cookie is cleared.
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

	logoutURL := h.buildAccountLogoutURL()

	if strings.Contains(r.Header.Get("Accept"), "application/json") {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"ok":true,"logout_url":"` + logoutURL + `"}`))
		return
	}
	http.Redirect(w, r, logoutURL, http.StatusSeeOther)
}

// buildAccountLogoutURL composes the RP-initiated logout URL on account-service.
// post_logout_redirect_uri targets the Vue /login route — the SPA's LoginView
// already runs the same checkSession + /sso/login handoff that /sso/login
// does directly, but lands the user on a URL that matches the gateway's
// "front door" rather than the OAuth back channel.
//
// Source of truth for scheme+host is the registered redirect_uri (which the
// gateway already holds in client.RedirectURI). Account-service validates
// post_logout_redirect_uri against that same host, so deriving from it
// guarantees a match — using GATEWAY_PUBLIC_URL would diverge whenever the
// env var and the DB row drift apart. Falls back to a relative /login when
// the registered redirect_uri is missing or unparsable.
func (h *Handlers) buildAccountLogoutURL() string {
	if h.client == nil || h.client.AccountPublicURL == "" {
		return "/login"
	}
	gatewayBase := schemeHostOf(h.client.RedirectURI)
	if gatewayBase == "" {
		gatewayBase = h.gatewayPublicURL
	}
	if gatewayBase == "" {
		return h.client.AccountPublicURL + "/logout"
	}
	postLogout := strings.TrimRight(gatewayBase, "/") + "/login"
	q := url.Values{}
	q.Set("client_id", h.client.ClientID)
	q.Set("post_logout_redirect_uri", postLogout)
	return h.client.AccountPublicURL + "/logout?" + q.Encode()
}

// schemeHostOf returns "scheme://host[:port]" for an absolute http(s) URL,
// or "" if raw is not absolute. Avoids dragging url.Parse into the hot path
// for what is effectively a prefix slice.
func schemeHostOf(raw string) string {
	const httpsPrefix = "https://"
	const httpPrefix = "http://"
	var prefix string
	switch {
	case strings.HasPrefix(raw, httpsPrefix):
		prefix = httpsPrefix
	case strings.HasPrefix(raw, httpPrefix):
		prefix = httpPrefix
	default:
		return ""
	}
	rest := raw[len(prefix):]
	end := len(rest)
	for i, c := range rest {
		if c == '/' || c == '?' || c == '#' {
			end = i
			break
		}
	}
	if end == 0 {
		return ""
	}
	return prefix + rest[:end]
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
		h.notify(r, SSOErrorEvent{
			Kind:   "webhook_signature_invalid",
			Reason: err.Error(),
		})
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
