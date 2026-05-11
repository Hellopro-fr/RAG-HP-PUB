package sso

import (
	"crypto/sha256"
	"encoding/base64"
	"strings"
	"testing"
)

func TestGenerateVerifier(t *testing.T) {
	v1, err := GenerateVerifier()
	if err != nil {
		t.Fatalf("GenerateVerifier: %v", err)
	}
	v2, err := GenerateVerifier()
	if err != nil {
		t.Fatalf("GenerateVerifier: %v", err)
	}
	if v1 == v2 {
		t.Fatal("verifiers must be unique")
	}
	if len(v1) < 43 {
		t.Fatalf("verifier too short: %d", len(v1))
	}
	if strings.ContainsAny(v1, "+/=") {
		t.Fatalf("verifier must be base64url unpadded: %q", v1)
	}
}

func TestS256Challenge(t *testing.T) {
	verifier := "test-verifier-abc"
	challenge := S256Challenge(verifier)
	sum := sha256.Sum256([]byte(verifier))
	want := base64.RawURLEncoding.EncodeToString(sum[:])
	if challenge != want {
		t.Fatalf("challenge mismatch: got %q want %q", challenge, want)
	}
}
