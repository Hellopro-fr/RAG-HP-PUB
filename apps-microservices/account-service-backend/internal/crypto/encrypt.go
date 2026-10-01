package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
)

type Cipher struct {
	gcm cipher.AEAD
}

func New(hexKey string) (*Cipher, error) {
	if len(hexKey) != 64 {
		return nil, fmt.Errorf("key must be 32 bytes hex (got %d chars)", len(hexKey))
	}
	key, err := hex.DecodeString(hexKey)
	if err != nil {
		return nil, fmt.Errorf("decode key: %w", err)
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	return &Cipher{gcm: gcm}, nil
}

func (c *Cipher) Encrypt(plain []byte) ([]byte, error) {
	nonce := make([]byte, c.gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, err
	}
	out := c.gcm.Seal(nonce, nonce, plain, nil)
	return out, nil
}

func (c *Cipher) Decrypt(cipherBytes []byte) ([]byte, error) {
	ns := c.gcm.NonceSize()
	if len(cipherBytes) < ns {
		return nil, fmt.Errorf("ciphertext too short")
	}
	nonce, ct := cipherBytes[:ns], cipherBytes[ns:]
	return c.gcm.Open(nil, nonce, ct, nil)
}
