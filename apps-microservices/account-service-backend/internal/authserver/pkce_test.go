package authserver

import (
	"crypto/sha256"
	"encoding/base64"
	"testing"
)

func makeVerifierAndChallenge() (string, string) {
	verifier := "ZWY1MWQ5ZDQyZjA4MWE0YTI2OTAyZmFlMmM4MWM4MzM"
	sum := sha256.Sum256([]byte(verifier))
	chal := base64.RawURLEncoding.EncodeToString(sum[:])
	return verifier, chal
}

func TestVerifyPKCE_S256_OK(t *testing.T) {
	v, c := makeVerifierAndChallenge()
	if !VerifyPKCES256(v, c) {
		t.Fatal("expected match")
	}
}

func TestVerifyPKCE_S256_Reject(t *testing.T) {
	if VerifyPKCES256("wrong", "definitely-not-the-hash") {
		t.Fatal("expected no match")
	}
}
