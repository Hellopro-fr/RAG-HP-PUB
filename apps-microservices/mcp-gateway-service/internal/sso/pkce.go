package sso

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
)

// GenerateVerifier returns a cryptographically random PKCE code_verifier as
// base64url-encoded (no padding) over 32 bytes of entropy. Per RFC 7636 the
// verifier must be 43-128 chars from [A-Z][a-z][0-9]-._~. base64url-no-pad
// over 32 bytes lands at 43 chars and uses only allowed characters.
func GenerateVerifier() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", fmt.Errorf("rand: %w", err)
	}
	return base64.RawURLEncoding.EncodeToString(b), nil
}

// S256Challenge computes the SHA-256 / base64url-no-pad challenge for the
// given verifier per RFC 7636 §4.2.
func S256Challenge(verifier string) string {
	sum := sha256.Sum256([]byte(verifier))
	return base64.RawURLEncoding.EncodeToString(sum[:])
}
