package transport

import (
	"context"
	"net/http"
	"strings"
)

// AllowedParticipantsHeader is the HTTP header the gateway sets to restrict a
// request to a specific set of Leexi participant UUIDs. When absent the service
// runs unrestricted (preserving current behaviour for direct callers).
//
// A non-empty header that parsed to zero valid UUIDs is treated as "deny-all"
// (not "unrestricted") — the gateway relies on this to signal an empty scope
// safely without ambiguity.
const AllowedParticipantsHeader = "X-Leexi-Allowed-Participants"

// ctxKey is an unexported type for context keys defined in this package so
// collisions with keys defined elsewhere are impossible.
type ctxKey int

const (
	allowedParticipantsKey ctxKey = iota
	restrictedKey
)

// withAllowedParticipants embeds the parsed allowed-participants slice in the
// context. The "restricted" flag is stored separately so a deny-all scope
// (non-empty header that parsed to no valid UUIDs) can be distinguished from
// an absent header.
func withAllowedParticipants(ctx context.Context, participants []string, restricted bool) context.Context {
	if !restricted {
		return ctx
	}
	ctx = context.WithValue(ctx, restrictedKey, true)
	if len(participants) > 0 {
		ctx = context.WithValue(ctx, allowedParticipantsKey, participants)
	}
	return ctx
}

// AllowedParticipantsFromContext returns the allowed participant UUIDs attached
// to ctx by the transport layer. The second return value is false when no
// restriction was declared (unrestricted access). A true value with an empty
// slice means "deny all" (the scope was declared but contained no valid UUIDs).
func AllowedParticipantsFromContext(ctx context.Context) ([]string, bool) {
	if restricted, _ := ctx.Value(restrictedKey).(bool); !restricted {
		return nil, false
	}
	v, _ := ctx.Value(allowedParticipantsKey).([]string)
	return v, true
}

// parseAllowedParticipantsHeader splits a comma-separated list, trims
// whitespace, and discards empty entries.
func parseAllowedParticipantsHeader(h string) []string {
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

// enrichRequestContext reads the allowed-participants header from r and returns
// a new context carrying that slice. Safe to call on every transport entry point.
// When the header is absent the context is returned unchanged (unrestricted).
// When the header is present (even if it parsed to zero valid UUIDs) the
// context is flagged as restricted — preserving fail-closed semantics.
func enrichRequestContext(r *http.Request) context.Context {
	raw := r.Header.Get(AllowedParticipantsHeader)
	if raw == "" {
		return r.Context()
	}
	participants := parseAllowedParticipantsHeader(raw)
	return withAllowedParticipants(r.Context(), participants, true)
}

// WithAllowedParticipantsForTest is exported so tests in sibling packages can
// build a scoped context without constructing an *http.Request.
func WithAllowedParticipantsForTest(ctx context.Context, participants []string, restricted bool) context.Context {
	return withAllowedParticipants(ctx, participants, restricted)
}
