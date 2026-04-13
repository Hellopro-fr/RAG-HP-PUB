package authserver

import "testing"

func TestVerifyPKCE_Valid(t *testing.T) {
	verifier := "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
	challenge := GenerateS256Challenge(verifier)
	if err := VerifyPKCE(challenge, verifier); err != nil {
		t.Fatalf("expected valid PKCE, got: %v", err)
	}
}

func TestVerifyPKCE_Invalid(t *testing.T) {
	challenge := GenerateS256Challenge("correct-verifier")
	if err := VerifyPKCE(challenge, "wrong-verifier"); err == nil {
		t.Fatal("expected PKCE verification to fail")
	}
}

func TestGenerateS256Challenge(t *testing.T) {
	challenge := GenerateS256Challenge("test-verifier")
	if challenge == "" {
		t.Fatal("expected non-empty challenge")
	}
	if len(challenge) < 20 {
		t.Fatal("challenge too short")
	}
}
