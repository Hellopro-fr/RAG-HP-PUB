package authserver

import (
	"context"
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

// fakeServerLister satisfies serverLister without GORM.
type fakeServerLister []db.MCPServer

func (f fakeServerLister) ListActive() ([]db.MCPServer, error) {
	return []db.MCPServer(f), nil
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

// TestBuildServerList_HidesGatedServersByRole exercises the real seam:
// AuthServer.buildServerList itself, not gateway.FilterServersByGate in
// isolation. It fails if the FilterServersByGate call is ever removed from
// buildServerList, in both the show-all branch (no client.Servers) and the
// pre-configured-scope branch (admin-assigned client.Servers), since a gated
// server must drop out of serverMap for a non-admin viewer either way.
func TestBuildServerList_HidesGatedServersByRole(t *testing.T) {
	servers := fakeServerLister{
		{ID: "pub-1", Name: "Public"},
		{ID: "gated-1", Name: "Gated", MinRole: auth.RoleAdmin},
	}
	users := fakeUsers{
		"admin@hellopro.fr": auth.RoleAdmin,
		"ro@hellopro.fr":    auth.RoleReadOnly,
	}

	newServer := func() *AuthServer {
		return &AuthServer{
			serverRepo: servers,
			userRepo:   users,
		}
	}

	hasID := func(list []authorizeServerDTO, id string) bool {
		for _, s := range list {
			if s.ID == id {
				return true
			}
		}
		return false
	}

	ctx := context.Background()

	t.Run("show-all branch", func(t *testing.T) {
		s := newServer()
		client := &db.OAuth2Client{ID: "client-1"} // no pre-configured scope

		adminList := s.buildServerList(ctx, client, "admin@hellopro.fr")
		if !hasID(adminList, "gated-1") {
			t.Fatal("admin should see the gated server")
		}
		if !hasID(adminList, "pub-1") {
			t.Fatal("admin should see the public server")
		}

		roList := s.buildServerList(ctx, client, "ro@hellopro.fr")
		if hasID(roList, "gated-1") {
			t.Fatal("read-only viewer should NOT see the gated server")
		}
		if !hasID(roList, "pub-1") {
			t.Fatal("read-only viewer should still see the public server")
		}

		anonList := s.buildServerList(ctx, client, "")
		if hasID(anonList, "gated-1") {
			t.Fatal("anonymous viewer should NOT see the gated server")
		}
	})

	t.Run("pre-configured-scope branch", func(t *testing.T) {
		s := newServer()
		client := &db.OAuth2Client{
			ID: "client-2",
			Servers: []db.OAuth2ClientServer{
				{ClientID: "client-2", ServerID: "pub-1"},
				{ClientID: "client-2", ServerID: "gated-1"},
			},
		}

		adminList := s.buildServerList(ctx, client, "admin@hellopro.fr")
		if !hasID(adminList, "gated-1") {
			t.Fatal("admin should see the pre-configured gated server")
		}

		roList := s.buildServerList(ctx, client, "ro@hellopro.fr")
		if hasID(roList, "gated-1") {
			t.Fatal("read-only viewer should NOT see the pre-configured gated server")
		}
		if !hasID(roList, "pub-1") {
			t.Fatal("read-only viewer should still see the pre-configured public server")
		}
	})
}
