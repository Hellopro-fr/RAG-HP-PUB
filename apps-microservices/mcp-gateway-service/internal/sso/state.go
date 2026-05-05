package sso

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
)

// PendingState carries the data we need to remember between /sso/login (which
// builds the upstream /authorize URL) and /sso/callback (which exchanges the
// authorization code at the token endpoint).
//
// Stored in the short-lived HttpOnly gw_sso_pending cookie so the browser
// round-trips it for us; signed with HMAC-SHA256 over the JWT secret so we
// detect tampering.
type PendingState struct {
	Verifier string `json:"v"`
	State    string `json:"s"`
	ReturnTo string `json:"r"`
	Exp      int64  `json:"e"`
}

// SignPendingState encodes the state to a compact "<base64url-payload>.<base64url-mac>"
// string suitable for a cookie value.
func SignPendingState(secret []byte, st PendingState) (string, error) {
	if len(secret) == 0 {
		return "", errors.New("empty secret")
	}
	payload, err := json.Marshal(st)
	if err != nil {
		return "", fmt.Errorf("marshal: %w", err)
	}
	body := base64.RawURLEncoding.EncodeToString(payload)
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(body))
	sig := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	return body + "." + sig, nil
}

// VerifyPendingState parses, MAC-validates and expiry-checks the token.
// Returns ErrPendingExpired for time-based rejection so callers can craft a
// nicer error message; everything else is wrapped as a verification failure.
func VerifyPendingState(secret []byte, token string) (PendingState, error) {
	var zero PendingState
	if len(secret) == 0 {
		return zero, errors.New("empty secret")
	}
	idx := strings.LastIndexByte(token, '.')
	if idx < 0 {
		return zero, errors.New("malformed pending state")
	}
	body, sig := token[:idx], token[idx+1:]
	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(body))
	expected := base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
	if !hmac.Equal([]byte(expected), []byte(sig)) {
		return zero, errors.New("pending state signature mismatch")
	}
	payload, err := base64.RawURLEncoding.DecodeString(body)
	if err != nil {
		return zero, fmt.Errorf("decode payload: %w", err)
	}
	var st PendingState
	if err := json.Unmarshal(payload, &st); err != nil {
		return zero, fmt.Errorf("unmarshal: %w", err)
	}
	if time.Now().Unix() > st.Exp {
		return zero, ErrPendingExpired
	}
	return st, nil
}

// ErrPendingExpired marks expiry-based rejection. /sso/callback handlers can
// surface this with a "Login took too long, please retry" message.
var ErrPendingExpired = errors.New("pending state expired")
