package auth

import (
	"testing"
	"time"
)

func TestSignValidateRoundTrip(t *testing.T) {
	claims := Claims{
		Sub:   "alice@example.com",
		Email: "alice@example.com",
		Name:  "Alice",
		Aud:   "test-aud",
		Iss:   "https://account.test",
		Sid:   "sid-1",
		Iat:   time.Now().Unix(),
		Exp:   time.Now().Add(1 * time.Minute).Unix(),
	}
	tok, err := SignJWT("secret", claims)
	if err != nil {
		t.Fatalf("SignJWT: %v", err)
	}
	got, err := ValidateJWT(tok, "secret", "test-aud")
	if err != nil {
		t.Fatalf("ValidateJWT: %v", err)
	}
	if got.Sub != "alice@example.com" {
		t.Errorf("Sub=%q want alice@example.com", got.Sub)
	}
}

func TestValidateRejectsExpired(t *testing.T) {
	claims := Claims{
		Aud: "x",
		Iat: time.Now().Add(-2 * time.Hour).Unix(),
		Exp: time.Now().Add(-1 * time.Hour).Unix(),
	}
	tok, _ := SignJWT("secret", claims)
	if _, err := ValidateJWT(tok, "secret", "x"); err == nil {
		t.Fatal("expected expired error")
	}
}

func TestValidateRejectsBadSignature(t *testing.T) {
	tok, _ := SignJWT("secret", Claims{Aud: "x", Exp: time.Now().Add(time.Minute).Unix()})
	if _, err := ValidateJWT(tok, "other-secret", "x"); err == nil {
		t.Fatal("expected signature error")
	}
}

func TestValidateRejectsAudienceMismatch(t *testing.T) {
	tok, _ := SignJWT("secret", Claims{Aud: "x", Exp: time.Now().Add(time.Minute).Unix()})
	if _, err := ValidateJWT(tok, "secret", "y"); err == nil {
		t.Fatal("expected audience error")
	}
}
