package crypto

import (
	"strings"
	"testing"
)

const testKey = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

func TestRoundTrip(t *testing.T) {
	c, err := New(testKey)
	if err != nil {
		t.Fatalf("New: %v", err)
	}
	plain := "super-secret-client-secret"
	cipher, err := c.Encrypt([]byte(plain))
	if err != nil {
		t.Fatalf("Encrypt: %v", err)
	}
	if strings.Contains(string(cipher), plain) {
		t.Fatal("ciphertext should not contain plaintext")
	}
	got, err := c.Decrypt(cipher)
	if err != nil {
		t.Fatalf("Decrypt: %v", err)
	}
	if string(got) != plain {
		t.Fatalf("Decrypt got=%q want=%q", string(got), plain)
	}
}

func TestDecryptRejectsTampered(t *testing.T) {
	c, err := New(testKey)
	if err != nil {
		t.Fatal(err)
	}
	cipher, _ := c.Encrypt([]byte("hello"))
	cipher[len(cipher)-1] ^= 0x01
	if _, err := c.Decrypt(cipher); err == nil {
		t.Fatal("expected auth error for tampered ciphertext")
	}
}

func TestNewRejectsBadKeyLen(t *testing.T) {
	if _, err := New("deadbeef"); err == nil {
		t.Fatal("expected error for short key")
	}
}
