package transport

import (
	"context"
	"net/http"
	"strconv"
	"strings"
)

// AllowedUserIDsHeader is the HTTP header the gateway sets to restrict a
// request to a specific set of Ringover user IDs. When absent or empty the
// service runs unrestricted (preserving behaviour for direct non-gateway callers).
const AllowedUserIDsHeader = "X-Ringover-Allowed-User-IDs"

// ctxKey is an unexported type for context keys defined in this package so
// collisions with keys defined elsewhere are impossible.
type ctxKey int

const (
	allowedUserIDsKey ctxKey = iota
	restrictedKey
)

// withAllowedUserIDs embeds the parsed allowed-user-id slice in the context.
// The "restricted" flag is stored separately so a deny-all scope (non-empty
// header that parsed to no valid IDs) can be distinguished from an absent one.
func withAllowedUserIDs(ctx context.Context, ids []int, restricted bool) context.Context {
	if !restricted {
		return ctx
	}
	ctx = context.WithValue(ctx, restrictedKey, true)
	if len(ids) > 0 {
		ctx = context.WithValue(ctx, allowedUserIDsKey, ids)
	}
	return ctx
}

// AllowedUserIDsFromContext returns the allowed Ringover user IDs attached to
// ctx by the transport layer. The second return value is false when no
// restriction was declared (unrestricted access). A true value with an empty
// slice means "deny all" (the scope was declared but contained no valid IDs).
func AllowedUserIDsFromContext(ctx context.Context) ([]int, bool) {
	if restricted, _ := ctx.Value(restrictedKey).(bool); !restricted {
		return nil, false
	}
	v, _ := ctx.Value(allowedUserIDsKey).([]int)
	return v, true
}

// parseAllowedUserIDsHeader splits a comma-separated list of integers, trims
// whitespace, and discards empty or unparseable entries.
func parseAllowedUserIDsHeader(h string) []int {
	if h == "" {
		return nil
	}
	parts := strings.Split(h, ",")
	out := make([]int, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		id, err := strconv.Atoi(p)
		if err != nil || id <= 0 {
			continue
		}
		out = append(out, id)
	}
	return out
}

// enrichRequestContext reads the allowed-user-ids header from r and returns a
// new context carrying the parsed slice. Safe to call on every transport entry
// point; does nothing when the header is absent.
func enrichRequestContext(r *http.Request) context.Context {
	raw := r.Header.Get(AllowedUserIDsHeader)
	if raw == "" {
		return r.Context()
	}
	ids := parseAllowedUserIDsHeader(raw)
	return withAllowedUserIDs(r.Context(), ids, true)
}

// WithAllowedUserIDsForTest is exported so tests in sibling packages can build
// a scoped context without constructing an *http.Request.
func WithAllowedUserIDsForTest(ctx context.Context, ids []int, restricted bool) context.Context {
	return withAllowedUserIDs(ctx, ids, restricted)
}
