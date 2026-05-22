package api

import (
	"context"

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
