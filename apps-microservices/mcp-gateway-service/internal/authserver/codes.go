package authserver

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

// GenerateAuthCode creates a 256-bit random authorization code.
// Returns (rawCode, sha256Hash, error).
func GenerateAuthCode() (string, string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", "", fmt.Errorf("generate auth code: %w", err)
	}
	raw := hex.EncodeToString(b)
	h := sha256.Sum256([]byte(raw))
	return raw, hex.EncodeToString(h[:]), nil
}

// HashAuthCode computes the SHA-256 hex digest of a raw authorization code.
func HashAuthCode(raw string) string {
	h := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(h[:])
}
