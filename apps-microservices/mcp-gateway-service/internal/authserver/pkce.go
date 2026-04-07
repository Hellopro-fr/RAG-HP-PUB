package authserver

import (
	"crypto/sha256"
	"encoding/base64"
	"errors"
)

var ErrPKCEMismatch = errors.New("PKCE code_verifier does not match code_challenge")

// GenerateS256Challenge computes BASE64URL(SHA256(verifier)) per RFC 7636.
func GenerateS256Challenge(verifier string) string {
	h := sha256.Sum256([]byte(verifier))
	return base64.RawURLEncoding.EncodeToString(h[:])
}

// VerifyPKCE verifies that BASE64URL(SHA256(verifier)) == challenge.
func VerifyPKCE(challenge, verifier string) error {
	computed := GenerateS256Challenge(verifier)
	if computed != challenge {
		return ErrPKCEMismatch
	}
	return nil
}
