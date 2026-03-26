package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

const sessionCookieName = "mcp_session"
const sessionMaxAge = 24 * time.Hour

// SessionData holds the authenticated user's session info.
type SessionData struct {
	DisplayName string `json:"display_name"`
	Email       string `json:"email"`
	Token       string `json:"token"`
	ExpiresAt   int64  `json:"expires_at"`
}

// SetSession writes an HMAC-signed session cookie.
func SetSession(w http.ResponseWriter, secret string, data SessionData) error {
	data.ExpiresAt = time.Now().Add(sessionMaxAge).Unix()
	payload, err := json.Marshal(data)
	if err != nil {
		return err
	}
	signed := signPayload(secret, payload)
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    signed,
		Path:     "/",
		HttpOnly: true,
		SameSite: http.SameSiteLaxMode,
		MaxAge:   int(sessionMaxAge.Seconds()),
	})
	return nil
}

// GetSession reads and validates the session cookie.
func GetSession(r *http.Request, secret string) (*SessionData, error) {
	cookie, err := r.Cookie(sessionCookieName)
	if err != nil {
		return nil, err
	}
	payload, err := verifyPayload(secret, cookie.Value)
	if err != nil {
		return nil, err
	}
	var data SessionData
	if err := json.Unmarshal(payload, &data); err != nil {
		return nil, err
	}
	if time.Now().Unix() > data.ExpiresAt {
		return nil, fmt.Errorf("session expired")
	}
	return &data, nil
}

// ClearSession removes the session cookie.
func ClearSession(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     sessionCookieName,
		Value:    "",
		Path:     "/",
		HttpOnly: true,
		MaxAge:   -1,
	})
}

// signPayload creates base64(payload).base64(hmac-sha256(payload))
func signPayload(secret string, payload []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	sig := mac.Sum(nil)
	return base64.URLEncoding.EncodeToString(payload) + "." + base64.URLEncoding.EncodeToString(sig)
}

// verifyPayload splits, verifies HMAC, and returns the payload.
func verifyPayload(secret string, signed string) ([]byte, error) {
	parts := strings.SplitN(signed, ".", 2)
	if len(parts) != 2 {
		return nil, fmt.Errorf("invalid session format")
	}
	payload, err := base64.URLEncoding.DecodeString(parts[0])
	if err != nil {
		return nil, fmt.Errorf("decode payload: %w", err)
	}
	sig, err := base64.URLEncoding.DecodeString(parts[1])
	if err != nil {
		return nil, fmt.Errorf("decode signature: %w", err)
	}
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(payload)
	expected := mac.Sum(nil)
	if !hmac.Equal(sig, expected) {
		return nil, fmt.Errorf("invalid signature")
	}
	return payload, nil
}