package oauth2

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"

	"github.com/google/uuid"
)

const secretPrefix = "mcp_oauth_"

// GenerateCredentials creates a new OAuth2 client_id and client_secret.
// Returns (clientID, clientSecret, secretHash, secretDisplayPrefix).
func GenerateCredentials() (clientID, clientSecret, secretHash, displayPrefix string, err error) {
	clientID = uuid.New().String()

	b := make([]byte, 32) // 256 bits of entropy
	if _, err := rand.Read(b); err != nil {
		return "", "", "", "", fmt.Errorf("generate secret: %w", err)
	}
	clientSecret = secretPrefix + hex.EncodeToString(b) // "mcp_oauth_" + 64 hex chars = 74 chars total

	h := sha256.Sum256([]byte(clientSecret))
	secretHash = hex.EncodeToString(h[:])

	displayPrefix = clientSecret[:16]

	return clientID, clientSecret, secretHash, displayPrefix, nil
}

// HashSecret computes the SHA-256 hex digest of a client secret for lookup.
func HashSecret(secret string) string {
	h := sha256.Sum256([]byte(secret))
	return hex.EncodeToString(h[:])
}
