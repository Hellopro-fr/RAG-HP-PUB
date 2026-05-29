package api

import (
	"context"
	"net/http/httptest"
	"testing"

	"mcp-gateway/internal/auth"
)

func TestEffectiveCreatorFilter_AdminBypassesFilter(t *testing.T) {
	ctx := context.WithValue(context.Background(), auth.ContextKeyUserRole, auth.RoleAdmin)
	ctx = context.WithValue(ctx, auth.ContextKeyUserEmail, "admin@example.com")

	got := effectiveCreatorFilter(ctx)
	if got != "" {
		t.Fatalf("admin should bypass filter (empty string), got %q", got)
	}
}

func TestEffectiveCreatorFilter_NonAdminUsesEmail(t *testing.T) {
	cases := []struct {
		name string
		role string
	}{
		{"read-only", auth.RoleReadOnly},
		{"config-only", auth.RoleConfigOnly},
		{"empty-role", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			ctx := context.WithValue(context.Background(), auth.ContextKeyUserRole, tc.role)
			ctx = context.WithValue(ctx, auth.ContextKeyUserEmail, "alice@example.com")

			got := effectiveCreatorFilter(ctx)
			if got != "alice@example.com" {
				t.Fatalf("role=%q should filter by email, got %q", tc.role, got)
			}
		})
	}
}

func TestEffectiveCreatorFilter_NoContextValues(t *testing.T) {
	got := effectiveCreatorFilter(context.Background())
	if got != "" {
		t.Fatalf("empty context should return empty string, got %q", got)
	}
}

func TestResolveListServersCreatorFilter_IncludeAllOverridesNonAdmin(t *testing.T) {
	req := httptest.NewRequest("GET", "/api/v1/servers?include_all=true", nil)
	ctx := context.WithValue(req.Context(), auth.ContextKeyUserRole, auth.RoleConfigOnly)
	ctx = context.WithValue(ctx, auth.ContextKeyUserEmail, "alice@example.com")
	req = req.WithContext(ctx)

	got := resolveListServersCreatorFilter(req)
	if got != "" {
		t.Fatalf("include_all=true should drop the creator filter, got %q", got)
	}
}

func TestResolveListServersCreatorFilter_DefaultUsesRoleFilter(t *testing.T) {
	req := httptest.NewRequest("GET", "/api/v1/servers", nil)
	ctx := context.WithValue(req.Context(), auth.ContextKeyUserRole, auth.RoleConfigOnly)
	ctx = context.WithValue(ctx, auth.ContextKeyUserEmail, "alice@example.com")
	req = req.WithContext(ctx)

	got := resolveListServersCreatorFilter(req)
	if got != "alice@example.com" {
		t.Fatalf("default request should apply the role-based filter, got %q", got)
	}
}

func TestResolveListServersCreatorFilter_AdminUnaffectedByFlag(t *testing.T) {
	req := httptest.NewRequest("GET", "/api/v1/servers?include_all=false", nil)
	ctx := context.WithValue(req.Context(), auth.ContextKeyUserRole, auth.RoleAdmin)
	ctx = context.WithValue(ctx, auth.ContextKeyUserEmail, "admin@example.com")
	req = req.WithContext(ctx)

	got := resolveListServersCreatorFilter(req)
	if got != "" {
		t.Fatalf("admin should keep the empty filter regardless of flag, got %q", got)
	}
}
