// Package crypto provides AES-256-GCM decryption for sensitive blobs stored
// in the gateway's MySQL (mcp_servers.auth_headers). The algorithm mirrors
// mcp-gateway-service/internal/crypto so the same ciphertext round-trips.
package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"encoding/hex"
	"fmt"
)

// Decryptor wraps an AES-256-GCM AEAD primed with a fixed key.
type Decryptor struct {
	gcm cipher.AEAD
}

// NewDecryptor parses a hex-encoded 32-byte key and returns a Decryptor.
// Returns an error if the key is not valid hex or not 32 bytes long.
func NewDecryptor(hexKey string) (*Decryptor, error) {
	key, err := hex.DecodeString(hexKey)
	if err != nil {
		return nil, fmt.Errorf("decode hex key: %w", err)
	}
	if len(key) != 32 {
		return nil, fmt.Errorf("key must be 32 bytes (got %d)", len(key))
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, fmt.Errorf("create cipher: %w", err)
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, fmt.Errorf("create GCM: %w", err)
	}
	return &Decryptor{gcm: gcm}, nil
}

// Decrypt undoes Encryptor.Encrypt on the gateway side. The input is the
// raw ciphertext as stored in MySQL: nonce || sealed_payload.
func (d *Decryptor) Decrypt(ciphertext []byte) ([]byte, error) {
	nonceSize := d.gcm.NonceSize()
	if len(ciphertext) < nonceSize {
		return nil, fmt.Errorf("ciphertext too short")
	}
	nonce, ct := ciphertext[:nonceSize], ciphertext[nonceSize:]
	pt, err := d.gcm.Open(nil, nonce, ct, nil)
	if err != nil {
		return nil, fmt.Errorf("decrypt: %w", err)
	}
	return pt, nil
}
