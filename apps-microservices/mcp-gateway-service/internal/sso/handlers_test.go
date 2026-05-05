package sso

import "testing"

// Compile-only smoke test — full integration coverage lives in cmd/server e2e.
func TestNewHandlers(t *testing.T) {
	h := NewHandlers(nil, nil, nil, nil, false)
	if h == nil {
		t.Fatal("expected non-nil handlers")
	}
}

func TestParseJWTSubAndEmail(t *testing.T) {
	// {"sub":"user-123","email":"alice@example.com"}
	tok := "header." +
		"eyJzdWIiOiJ1c2VyLTEyMyIsImVtYWlsIjoiYWxpY2VAZXhhbXBsZS5jb20ifQ" +
		".sig"
	sub, email, name, err := ParseAccessTokenIdentity(tok)
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if sub != "user-123" || email != "alice@example.com" {
		t.Fatalf("got sub=%q email=%q", sub, email)
	}
	_ = name
}
