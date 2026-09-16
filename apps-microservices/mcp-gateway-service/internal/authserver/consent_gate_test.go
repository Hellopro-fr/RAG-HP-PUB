package authserver

import (
	"testing"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
)

type fakeUsers map[string]string

func (f fakeUsers) GetByEmail(email string) (*db.GatewayUser, error) {
	role, ok := f[email]
	if !ok {
		return nil, nil
	}
	return &db.GatewayUser{Email: email, Role: role}, nil
}

// TestConsentFilterSeam proves the property both consent builders rely on:
// filtering the ListActive() slice removes a gated server from the map the
// pre-configured-scope branch resolves through, so that branch needs no
// filtering of its own.
func TestConsentFilterSeam(t *testing.T) {
	users := fakeUsers{
		"admin@hellopro.fr": auth.RoleAdmin,
		"ro@hellopro.fr":    auth.RoleReadOnly,
	}
	servers := []db.MCPServer{
		{ID: "pub-1", Name: "Public"},
		{ID: "gated-1", Name: "Gated", MinRole: auth.RoleAdmin},
	}

	buildMap := func(email string) map[string]db.MCPServer {
		filtered := gateway.FilterServersByGate(servers, email, users)
		m := make(map[string]db.MCPServer, len(filtered))
		for _, s := range filtered {
			m[s.ID] = s
		}
		return m
	}

	adminMap := buildMap("admin@hellopro.fr")
	if _, ok := adminMap["gated-1"]; !ok {
		t.Fatal("admin lost the gated server from serverMap")
	}

	roMap := buildMap("ro@hellopro.fr")
	if _, ok := roMap["gated-1"]; ok {
		t.Fatal("read-only viewer kept the gated server in serverMap")
	}
	if _, ok := roMap["pub-1"]; !ok {
		t.Fatal("read-only viewer lost the public server")
	}

	// An anonymous viewer (empty email) must see only public servers.
	anonMap := buildMap("")
	if _, ok := anonMap["gated-1"]; ok {
		t.Fatal("anonymous viewer kept the gated server")
	}
	if len(anonMap) != 1 {
		t.Fatalf("anonymous viewer sees %d servers, want 1", len(anonMap))
	}
}
