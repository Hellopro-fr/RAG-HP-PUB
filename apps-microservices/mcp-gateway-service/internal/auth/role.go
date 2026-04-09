package auth

import (
	"context"
	"encoding/json"
	"net/http"
)

// Role constants.
const (
	RoleAdmin      = "admin"
	RoleReadOnly   = "read-only"
	RoleConfigOnly = "config-only"
)

// ContextKeyUserRole is the context key for the authenticated user's role.
const ContextKeyUserRole contextKey = "user_role"

// UserRoleFromContext extracts the authenticated user's role from the request context.
// Returns empty string if not set.
func UserRoleFromContext(ctx context.Context) string {
	if v, ok := ctx.Value(ContextKeyUserRole).(string); ok {
		return v
	}
	return ""
}

// RoleLevelFor returns a numeric level for a role: admin=3, read-only=2, config-only=1, default=0.
func RoleLevelFor(role string) int {
	switch role {
	case RoleAdmin:
		return 3
	case RoleReadOnly:
		return 2
	case RoleConfigOnly:
		return 1
	default:
		return 0
	}
}

// RequireRole returns a middleware that enforces a minimum role level.
// If the user's role level is below minRole, it responds with 403 JSON.
func RequireRole(minRole string) func(http.Handler) http.Handler {
	minLevel := RoleLevelFor(minRole)
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			role := UserRoleFromContext(r.Context())
			if RoleLevelFor(role) < minLevel {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusForbidden)
				json.NewEncoder(w).Encode(map[string]string{"error": "insufficient permissions"})
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

// RequireAdmin is a shortcut for RequireRole(RoleAdmin).
func RequireAdmin() func(http.Handler) http.Handler {
	return RequireRole(RoleAdmin)
}

// RequireReadOnly is a shortcut for RequireRole(RoleReadOnly).
func RequireReadOnly() func(http.Handler) http.Handler {
	return RequireRole(RoleReadOnly)
}

// RequireConfigOnly is a shortcut for RequireRole(RoleConfigOnly).
func RequireConfigOnly() func(http.Handler) http.Handler {
	return RequireRole(RoleConfigOnly)
}
