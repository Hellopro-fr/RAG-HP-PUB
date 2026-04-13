package transport

import (
	"context"
	"net/http"
	"strings"
)

// AllowedOwnersHeader is the HTTP header the gateway sets to restrict a
// request to a specific set of Leexi owner UUIDs. When absent or empty the
// service runs unrestricted (preserving current behaviour for direct callers).
const AllowedOwnersHeader = "X-Leexi-Allowed-Owners"

// ctxKey is an unexported type for context keys defined in this package so
// collisions with keys defined elsewhere are impossible.
type ctxKey int

const (
	allowedOwnersKey ctxKey = iota
)

// withAllowedOwners embeds the parsed allowed-owners slice in the context.
func withAllowedOwners(ctx context.Context, owners []string) context.Context {
	if len(owners) == 0 {
		return ctx
	}
	return context.WithValue(ctx, allowedOwnersKey, owners)
}

// AllowedOwnersFromContext returns the allowed owner UUIDs attached to ctx by
// the transport layer. The second return value is false when no restriction
// was declared (unrestricted access).
func AllowedOwnersFromContext(ctx context.Context) ([]string, bool) {
	v, ok := ctx.Value(allowedOwnersKey).([]string)
	if !ok || len(v) == 0 {
		return nil, false
	}
	return v, true
}

// parseAllowedOwnersHeader splits a comma-separated list, trims whitespace,
// and discards empty entries.
func parseAllowedOwnersHeader(h string) []string {
	if h == "" {
		return nil
	}
	parts := strings.Split(h, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}

// enrichRequestContext reads the allowed-owners header from r and returns a
// new context carrying that slice. Safe to call on every transport entry point.
func enrichRequestContext(r *http.Request) context.Context {
	owners := parseAllowedOwnersHeader(r.Header.Get(AllowedOwnersHeader))
	return withAllowedOwners(r.Context(), owners)
}
