package crypto

import (
	"bytes"
	"crypto/aes"
	cryptocipher "crypto/cipher"
	"crypto/rand"
	"encoding/hex"
	"io"
	"testing"
)

// gatewayEncrypt mirrors mcp-gateway-service/internal/crypto.Encryptor.Encrypt.
// Kept verbatim in test code so a future divergence at either side is caught
// immediately by this round-trip test.
func gatewayEncrypt(t *testing.T, hexKey string, plaintext []byte) []byte {
	t.Helper()
	key, err := hex.DecodeString(hexKey)
	if err != nil {
		t.Fatalf("decode key: %v", err)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		t.Fatalf("aes.NewCipher: %v", err)
	}
	gcm, err := cryptocipher.NewGCM(block)
	if err != nil {
		t.Fatalf("cipher.NewGCM: %v", err)
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		t.Fatalf("rand nonce: %v", err)
	}
	return gcm.Seal(nonce, nonce, plaintext, nil)
}

func TestDecryptor_RoundTripFromGatewayCiphertext(t *testing.T) {
	const hexKey = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
	plaintext := []byte(`{"Authorization":"Bearer abc.def.ghi"}`)
	ciphertext := gatewayEncrypt(t, hexKey, plaintext)

	dec, err := NewDecryptor(hexKey)
	if err != nil {
		t.Fatalf("NewDecryptor: %v", err)
	}
	got, err := dec.Decrypt(ciphertext)
	if err != nil {
		t.Fatalf("Decrypt: %v", err)
	}
	if !bytes.Equal(got, plaintext) {
		t.Fatalf("Decrypt = %q, want %q", got, plaintext)
	}
}

func TestDecryptor_RejectsShortCiphertext(t *testing.T) {
	const hexKey = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
	dec, err := NewDecryptor(hexKey)
	if err != nil {
		t.Fatalf("NewDecryptor: %v", err)
	}
	if _, err := dec.Decrypt([]byte{0x01, 0x02}); err == nil {
		t.Fatalf("expected error on short ciphertext, got nil")
	}
}

func TestDecryptor_RejectsBadKey(t *testing.T) {
	if _, err := NewDecryptor("not-hex"); err == nil {
		t.Fatalf("expected error on non-hex key, got nil")
	}
	if _, err := NewDecryptor("aa"); err == nil {
		t.Fatalf("expected error on short key, got nil")
	}
}
