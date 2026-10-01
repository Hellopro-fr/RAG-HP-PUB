package sso

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"testing"
)

func TestVerifyWebhookSignature(t *testing.T) {
	secret := []byte("client-secret")
	body := []byte(`{"sub":"user-1","sid":"abc","iat":12345}`)

	mac := hmac.New(sha256.New, secret)
	mac.Write(body)
	sig := "hmac-sha256=" + hex.EncodeToString(mac.Sum(nil))

	if err := VerifyWebhookSignature(secret, body, sig); err != nil {
		t.Fatalf("expected ok, got %v", err)
	}
}

func TestVerifyWebhookSignature_Tampered(t *testing.T) {
	secret := []byte("client-secret")
	body := []byte(`{"sub":"user-1"}`)

	mac := hmac.New(sha256.New, secret)
	mac.Write([]byte(`{"sub":"OTHER"}`))
	sig := "hmac-sha256=" + hex.EncodeToString(mac.Sum(nil))

	if err := VerifyWebhookSignature(secret, body, sig); err == nil {
		t.Fatal("expected mismatch")
	}
}

func TestVerifyWebhookSignature_BadFormat(t *testing.T) {
	if err := VerifyWebhookSignature([]byte("k"), []byte("b"), "no-prefix"); err == nil {
		t.Fatal("expected format error")
	}
}
