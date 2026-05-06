package oauth2

import "testing"

func TestIssueAndValidateAccessToken(t *testing.T) {
	secret := "test-jwt-secret-for-oauth2"
	clientID := "test-client-id-123"
	ttl := 3600

	tokenStr, expiresIn, err := IssueAccessToken(secret, clientID, "", ttl)
	if err != nil {
		t.Fatalf("IssueAccessToken: %v", err)
	}
	if tokenStr == "" {
		t.Fatal("expected non-empty token")
	}
	if expiresIn != ttl {
		t.Fatalf("expected expiresIn=%d, got %d", ttl, expiresIn)
	}

	gotClientID, _, err := ValidateAccessToken(tokenStr, secret)
	if err != nil {
		t.Fatalf("ValidateAccessToken: %v", err)
	}
	if gotClientID != clientID {
		t.Fatalf("expected clientID=%q, got %q", clientID, gotClientID)
	}
}

func TestValidateAccessToken_WrongSecret(t *testing.T) {
	tokenStr, _, _ := IssueAccessToken("secret1", "client-1", "", 3600)
	_, _, err := ValidateAccessToken(tokenStr, "secret2")
	if err == nil {
		t.Fatal("expected error for wrong secret")
	}
}

func TestGenerateCredentials(t *testing.T) {
	clientID, clientSecret, hash, prefix, err := GenerateCredentials()
	if err != nil {
		t.Fatalf("GenerateCredentials: %v", err)
	}
	if clientID == "" || clientSecret == "" || hash == "" || prefix == "" {
		t.Fatal("expected non-empty values")
	}
	if len(prefix) != 16 {
		t.Fatalf("expected prefix length 16, got %d", len(prefix))
	}
	// Verify hash matches
	if HashSecret(clientSecret) != hash {
		t.Fatal("hash mismatch")
	}
}

func TestIssueAndValidateAccessToken_WithEmail(t *testing.T) {
	secret := "test-jwt-secret-for-oauth2"
	clientID := "client-abc"
	email := "alice@example.com"
	ttl := 3600

	tokenStr, expiresIn, err := IssueAccessToken(secret, clientID, email, ttl)
	if err != nil {
		t.Fatalf("IssueAccessToken: %v", err)
	}
	if expiresIn != ttl {
		t.Fatalf("expected expiresIn=%d, got %d", ttl, expiresIn)
	}

	gotClientID, gotEmail, err := ValidateAccessToken(tokenStr, secret)
	if err != nil {
		t.Fatalf("ValidateAccessToken: %v", err)
	}
	if gotClientID != clientID {
		t.Fatalf("expected clientID=%q, got %q", clientID, gotClientID)
	}
	if gotEmail != email {
		t.Fatalf("expected email=%q, got %q", email, gotEmail)
	}
}

func TestIssueAndValidateAccessToken_NoEmail(t *testing.T) {
	secret := "test-jwt-secret-for-oauth2"
	clientID := "client-cc"

	tokenStr, _, err := IssueAccessToken(secret, clientID, "", 3600)
	if err != nil {
		t.Fatalf("IssueAccessToken: %v", err)
	}

	gotClientID, gotEmail, err := ValidateAccessToken(tokenStr, secret)
	if err != nil {
		t.Fatalf("ValidateAccessToken: %v", err)
	}
	if gotClientID != clientID {
		t.Fatalf("expected clientID=%q, got %q", clientID, gotClientID)
	}
	if gotEmail != "" {
		t.Fatalf("expected empty email for client_credentials grant, got %q", gotEmail)
	}
}
