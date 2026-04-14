package transport

import (
	"context"
	"net/http"
	"strings"
)

// AllowedParticipantsHeader is the HTTP header the gateway sets to restrict a
// request to a specific set of Leexi participant UUIDs. When absent or empty
// the service runs unrestricted (preserving current behaviour for direct callers).
const AllowedParticipantsHeader = "X-Leexi-Allowed-Participants"

// ctxKey is an unexported type for context keys defined in this package so
// collisions with keys defined elsewhere are impossible.
type ctxKey int

const (
	allowedParticipantsKey ctxKey = iota
)

// withAllowedParticipants embeds the parsed allowed-participants slice in the context.
func withAllowedParticipants(ctx context.Context, participants []string) context.Context {
	if len(participants) == 0 {
		return ctx
	}
	return context.WithValue(ctx, allowedParticipantsKey, participants)
}

// AllowedParticipantsFromContext returns the allowed participant UUIDs attached
// to ctx by the transport layer. The second return value is false when no
// restriction was declared (unrestricted access).
func AllowedParticipantsFromContext(ctx context.Context) ([]string, bool) {
	v, ok := ctx.Value(allowedParticipantsKey).([]string)
	if !ok || len(v) == 0 {
		return nil, false
	}
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
func enrichRequestContext(r *http.Request) context.Context {
	participants := parseAllowedParticipantsHeader(r.Header.Get(AllowedParticipantsHeader))
	return withAllowedParticipants(r.Context(), participants)
}
