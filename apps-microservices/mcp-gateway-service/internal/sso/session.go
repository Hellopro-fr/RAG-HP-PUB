package sso

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"net/http"
)

// CookieName is the HttpOnly cookie that carries the opaque sso_sessions.id.
// Pending-state (PKCE verifier + return_to) lives in PendingCookieName during
// the brief window between /sso/login and /sso/callback.
const (
	CookieName        = "gw_session"
	PendingCookieName = "gw_sso_pending"
)

// NewSessionID returns a 64-char hex string (32 random bytes). Stored as the
// primary key of sso_sessions and as the cookie value.
func NewSessionID() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("rand: %w", err)
	}
	return hex.EncodeToString(b), nil
}

// SetSessionCookie writes the gw_session cookie. secure=true requires HTTPS;
// keep secure=false for local dev (matches the SECURE_COOKIE config knob used
// by internal/auth).
func SetSessionCookie(w http.ResponseWriter, id string, secure bool) {
	http.SetCookie(w, &http.Cookie{
		Name:     CookieName,
		Value:    id,
		Path:     "/",
		HttpOnly: true,
		Secure:   secure,
		SameSite: http.SameSiteLaxMode,
	})
}

// SetPendingCookie writes the short-lived (5 min) signed state cookie used
// across the /sso/login → /sso/callback round trip.
func SetPendingCookie(w http.ResponseWriter, value string, secure bool) {
	http.SetCookie(w, &http.Cookie{
		Name:     PendingCookieName,
		Value:    value,
		Path:     "/sso",
		HttpOnly: true,
		Secure:   secure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   300,
	})
}

// GetSessionID reads the gw_session cookie. Returns ErrNoSession if absent so
// callers can distinguish "no cookie" from "cookie but invalid format".
func GetSessionID(r *http.Request) (string, error) {
	c, err := r.Cookie(CookieName)
	if err != nil {
		return "", ErrNoSession
	}
	if c.Value == "" {
		return "", ErrNoSession
	}
	return c.Value, nil
}

// GetPendingCookie reads the gw_sso_pending cookie value.
func GetPendingCookie(r *http.Request) (string, error) {
	c, err := r.Cookie(PendingCookieName)
	if err != nil {
		return "", ErrNoSession
	}
	return c.Value, nil
}

// ClearSessionCookie expires the gw_session cookie client-side.
func ClearSessionCookie(w http.ResponseWriter, secure bool) {
	http.SetCookie(w, &http.Cookie{
		Name:     CookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		Secure:   secure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
	})
}

// ClearPendingCookie expires the gw_sso_pending cookie after /sso/callback consumes it.
func ClearPendingCookie(w http.ResponseWriter, secure bool) {
	http.SetCookie(w, &http.Cookie{
		Name:     PendingCookieName,
		Value:    "",
		Path:     "/sso",
		HttpOnly: true,
		Secure:   secure,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   -1,
	})
}

// ErrNoSession indicates the request carried no session cookie. Callers
// should redirect to /sso/login or return 401 depending on the route.
var ErrNoSession = errors.New("no session cookie")
