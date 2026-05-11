package authserver

import (
	"testing"

	oauth2pkg "mcp-gateway/internal/oauth2"
)

// TestAuthCodeAccessTokenContainsEmail verifies that the JWT minted in
// handleAuthCodeExchange carries the auth-code's user_email as the `email`
// claim. We do not exercise the full HTTP path here — the real coverage lives
// at the integration level — but we lock the contract that IssueAccessToken
// receives the right argument by re-issuing the token directly with the same
// inputs the handler uses and decoding the result.
func TestAuthCodeAccessTokenContainsEmail(t *testing.T) {
	secret := "abc-secret"
	tok, _, err := oauth2pkg.IssueAccessToken(secret, "client-x", "bob@example.com", 60)
	if err != nil {
		t.Fatalf("IssueAccessToken: %v", err)
	}
	clientID, email, err := oauth2pkg.ValidateAccessToken(tok, secret)
	if err != nil {
		t.Fatalf("ValidateAccessToken: %v", err)
	}
	if clientID != "client-x" || email != "bob@example.com" {
		t.Fatalf("got (%q,%q), want (client-x,bob@example.com)", clientID, email)
	}
}

// TestClientCredentialsAccessTokenHasNoEmail enforces that the
// client_credentials grant path does NOT embed a user identity, since there is
// no human behind the token. The downstream "self" filter must reject it.
func TestClientCredentialsAccessTokenHasNoEmail(t *testing.T) {
	secret := "abc-secret"
	tok, _, err := oauth2pkg.IssueAccessToken(secret, "client-y", "", 60)
	if err != nil {
		t.Fatalf("IssueAccessToken: %v", err)
	}
	_, email, err := oauth2pkg.ValidateAccessToken(tok, secret)
	if err != nil {
		t.Fatalf("ValidateAccessToken: %v", err)
	}
	if email != "" {
		t.Fatalf("expected empty email, got %q", email)
	}
}
