package authserver

import (
	"testing"
)

func TestGenerateCSRFToken(t *testing.T) {
	token, err := generateCSRFToken()
	if err != nil {
		t.Fatalf("generateCSRFToken: %v", err)
	}
	if len(token) < 32 {
		t.Fatal("CSRF token too short")
	}
}

func TestConsentScopeJSON(t *testing.T) {
	scope := ConsentScope{
		ServerIDs: []string{"srv-1", "srv-2"},
	}
	j := scope.ToJSON()
	if j == "" {
		t.Fatal("expected non-empty JSON")
	}
	parsed, err := ParseConsentScope(j)
	if err != nil {
		t.Fatalf("ParseConsentScope: %v", err)
	}
	if len(parsed.ServerIDs) != 2 {
		t.Fatalf("expected 2 server IDs, got %d", len(parsed.ServerIDs))
	}
}
