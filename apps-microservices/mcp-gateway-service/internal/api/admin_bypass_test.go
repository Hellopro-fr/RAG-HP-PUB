package api

import (
	"context"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
)

func ctxWith(role, email string) context.Context {
	ctx := context.Background()
	if role != "" {
		ctx = context.WithValue(ctx, auth.ContextKeyUserRole, role)
	}
	if email != "" {
		ctx = context.WithValue(ctx, auth.ContextKeyUserEmail, email)
	}
	return ctx
}

func TestIsTokenOwner_AdminBypass(t *testing.T) {
	h := &Handler{}
	tok := &db.ScopeToken{CreatedBy: "alice@example.com"}

	r := httptest.NewRequest("GET", "/api/v1/tokens/x", nil)
	r = r.WithContext(ctxWith(auth.RoleAdmin, "admin@example.com"))

	if !h.isTokenOwner(r, tok) {
		t.Fatal("admin must be allowed to mutate any token, got false")
	}
}

func TestIsTokenOwner_NonAdminBlocked(t *testing.T) {
	h := &Handler{}
	tok := &db.ScopeToken{CreatedBy: "alice@example.com"}

	r := httptest.NewRequest("GET", "/api/v1/tokens/x", nil)
	r = r.WithContext(ctxWith(auth.RoleReadOnly, "bob@example.com"))

	if h.isTokenOwner(r, tok) {
		t.Fatal("non-admin foreign user must be blocked, got true")
	}
}

func TestIsTokenOwner_LegacyNoOwner(t *testing.T) {
	h := &Handler{}
	tok := &db.ScopeToken{CreatedBy: ""}

	r := httptest.NewRequest("GET", "/api/v1/tokens/x", nil)
	r = r.WithContext(ctxWith(auth.RoleReadOnly, "bob@example.com"))

	if !h.isTokenOwner(r, tok) {
		t.Fatal("legacy token with empty CreatedBy must remain world-accessible")
	}
}

func TestIsOAuth2ClientOwner_AdminBypass(t *testing.T) {
	h := &Handler{}
	c := &db.OAuth2Client{CreatedBy: "alice@example.com"}

	r := httptest.NewRequest("GET", "/api/v1/oauth2/clients/x", nil)
	r = r.WithContext(ctxWith(auth.RoleAdmin, "admin@example.com"))

	if !h.isOAuth2ClientOwner(r, c) {
		t.Fatal("admin must be allowed to mutate any OAuth2 client, got false")
	}
}

func TestIsOAuth2ClientOwner_NonAdminBlocked(t *testing.T) {
	h := &Handler{}
	c := &db.OAuth2Client{CreatedBy: "alice@example.com"}

	r := httptest.NewRequest("GET", "/api/v1/oauth2/clients/x", nil)
	r = r.WithContext(ctxWith(auth.RoleReadOnly, "bob@example.com"))

	if h.isOAuth2ClientOwner(r, c) {
		t.Fatal("non-admin foreign user must be blocked, got true")
	}
}

func TestCheckOwnership_AdminBypass(t *testing.T) {
	srv := &db.MCPServer{CreatedBy: "alice@example.com"}
	r := httptest.NewRequest("GET", "/api/v1/servers/x", nil)
	r = r.WithContext(ctxWith(auth.RoleAdmin, "admin@example.com"))
	w := httptest.NewRecorder()

	if !checkOwnership(r, srv, w) {
		t.Fatal("admin must bypass server ownership gate")
	}
	if w.Code != 200 {
		t.Fatalf("admin path must not write a 403, got code=%d", w.Code)
	}
}

func TestCheckOwnership_NonAdminBlocked(t *testing.T) {
	srv := &db.MCPServer{CreatedBy: "alice@example.com"}
	r := httptest.NewRequest("GET", "/api/v1/servers/x", nil)
	r = r.WithContext(ctxWith(auth.RoleReadOnly, "bob@example.com"))
	w := httptest.NewRecorder()

	if checkOwnership(r, srv, w) {
		t.Fatal("non-admin foreign user must be blocked")
	}
	if w.Code != 403 {
		t.Fatalf("expected 403 forbidden, got code=%d", w.Code)
	}
}

func TestCheckOwnership_AuthDisabled(t *testing.T) {
	srv := &db.MCPServer{CreatedBy: "alice@example.com"}
	r := httptest.NewRequest("GET", "/api/v1/servers/x", nil) // no email in ctx
	w := httptest.NewRecorder()

	if !checkOwnership(r, srv, w) {
		t.Fatal("auth-disabled path must short-circuit to true")
	}
}
