package scopetoken

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

const tokenPrefix = "mcp_"

// Generate creates a new random scope token and returns (rawToken, sha256Hash, displayPrefix).
func Generate() (raw string, hash string, prefix string, err error) {
	b := make([]byte, 24) // 192 bits of entropy
	if _, err := rand.Read(b); err != nil {
		return "", "", "", fmt.Errorf("generate token: %w", err)
	}
	raw = tokenPrefix + hex.EncodeToString(b) // "mcp_" + 48 hex chars = 52 chars total
	h := sha256.Sum256([]byte(raw))
	return raw, hex.EncodeToString(h[:]), raw[:12], nil
}

// Hash computes the SHA-256 hex digest of a raw token for lookup.
func Hash(rawToken string) string {
	h := sha256.Sum256([]byte(rawToken))
	return hex.EncodeToString(h[:])
}
