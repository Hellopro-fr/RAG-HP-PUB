package api

import (
	"context"
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
