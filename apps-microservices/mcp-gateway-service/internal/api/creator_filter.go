package api

import (
	"context"
	"net/http"

	"mcp-gateway/internal/auth"
)

// effectiveCreatorFilter returns the created_by value that the calling user is
// allowed to see in list endpoints. Admins get an empty string (no filter, see
// everyone's rows); every other role gets their own email and only sees rows
// they created (plus legacy rows with empty created_by, per the OR clause
// applied in the repository layer).
func effectiveCreatorFilter(ctx context.Context) string {
	if auth.UserRoleFromContext(ctx) == auth.RoleAdmin {
		return ""
	}
	return auth.UserEmailFromContext(ctx)
}

// resolveListServersCreatorFilter is the request-aware variant for
// GET /api/v1/servers. When `?include_all=true` is set on the URL, the
// ownership filter is dropped so the caller (typically a scope-picker in
// the token / OAuth2 creation forms) can see every active server. The DTO
// already redacts secrets, so widening the read leaks nothing. All other
// callers fall back to the role-based filter.
func resolveListServersCreatorFilter(r *http.Request) string {
	if r.URL.Query().Get("include_all") == "true" {
		return ""
	}
	return effectiveCreatorFilter(r.Context())
}
