package gateway

import (
	"testing"

	"mcp-gateway/internal/auth"
)

func TestRegistry_SetMinRole(t *testing.T) {
	r := NewRegistry()
	r.Register(&BackendServer{ID: "srv-1"})

	r.SetMinRole("srv-1", auth.RoleAdmin)
	if got := r.FindByID("srv-1").MinRole; got != auth.RoleAdmin {
		t.Fatalf("MinRole = %q, want %q", got, auth.RoleAdmin)
	}

	r.SetMinRole("srv-1", "")
	if got := r.FindByID("srv-1").MinRole; got != "" {
		t.Fatalf("MinRole = %q, want empty after ungating", got)
	}

	// Must not panic for an unknown id.
	r.SetMinRole("nope", auth.RoleAdmin)
}

// TestRegistry_MinRoleSurvivesRediscovery guards the highest-consequence
// regression in this feature: the health checker rebuilds BackendServer from
// the upstream initialize result every 30 s. If MinRole is not carried over,
// a gated server silently becomes public shortly after boot.
func TestRegistry_MinRoleSurvivesRediscovery(t *testing.T) {
	r := NewRegistry()
	r.Register(&BackendServer{ID: "srv-1", MinRole: auth.RoleAdmin, Name: "old"})

	// Simulate what registerBackend builds from a fresh initialize result:
	// a struct that knows nothing about min_role.
	fresh := &BackendServer{ID: "srv-1", Name: "new"}
	if prev := r.FindByID("srv-1"); prev != nil && fresh.MinRole == "" {
		fresh.MinRole = prev.MinRole
	}
	r.Register(fresh)

	if got := r.FindByID("srv-1").MinRole; got != auth.RoleAdmin {
		t.Fatalf("MinRole = %q after rediscovery, want %q — the gate fell open", got, auth.RoleAdmin)
	}
}
