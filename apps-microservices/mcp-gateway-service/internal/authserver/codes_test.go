package authserver

import "testing"

func TestGenerateAuthCode(t *testing.T) {
	raw, hash, err := GenerateAuthCode()
	if err != nil {
		t.Fatalf("GenerateAuthCode: %v", err)
	}
	if raw == "" || hash == "" {
		t.Fatal("expected non-empty values")
	}
	if HashAuthCode(raw) != hash {
		t.Fatal("hash mismatch")
	}
}
