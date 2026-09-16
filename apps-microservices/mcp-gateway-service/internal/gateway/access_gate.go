package gateway

import (
	"context"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/db"
	"mcp-gateway/internal/scopetoken"
)

// gatewayUserRole resolves email to its gateway_users role.
//
// The bool reports whether the lookup produced a usable answer: false covers
// an unwired repository, a repository error, and an email with no row. It is
// deliberately distinct from "role is low" so callers can fail closed on
// uncertainty rather than treating an outage as a valid low-privilege answer.
func gatewayUserRole(users gatewayUserFinder, email string) (string, bool) {
	if users == nil || email == "" {
		return "", false
	}
	u, err := users.GetByEmail(email)
	if err != nil || u == nil {
		return "", false
	}
	return u.Role, true
}

// GateAllowsEmail reports whether the gateway user identified by email may
// see and reach a server whose mcp_servers.min_role is minRole.
//
// Fail-closed: an empty minRole is the only path that allows without a
// successful role resolution. Everything uncertain — no repository, no email,
// unknown email, repository error — denies.
func GateAllowsEmail(minRole, email string, users gatewayUserFinder) bool {
	if minRole == "" {
		return true // public: the value every pre-existing server carries
	}
	if auth.RoleLevelFor(minRole) == 0 {
		// RoleLevelFor returns 0 for any unrecognised string, same as its
		// "lowest defined role" default. If min_role ever holds something
		// unrecognised (miscased via direct SQL, a backup restore, or a
		// future import path), a required level of 0 would let EVERY user
		// with a gateway_users row through — including one whose own role
		// is also unrecognised (0 >= 0). Deny instead: an unrecognised gate
		// value must fail closed, not silently disable the gate.
		return false
	}
	role, ok := gatewayUserRole(users, email)
	if !ok {
		return false
	}
	return auth.RoleLevelFor(role) >= auth.RoleLevelFor(minRole)
}

// GateAllows is the MCP-runtime form of GateAllowsEmail. It reads the
// end-user email from ctx, which is set in exactly one place —
// internal/oauth2/middleware.go, on the OAuth2 bearer path, and only when the
// access token carries a non-empty email claim.
//
// That single fact is what makes this function reject `mcp_…` scope tokens
// and client_credentials grants on a gated server: neither ever puts an email
// on the context. The invariant is pinned by
// TestScopeTokenPathLeavesEndUserEmailUnset — if that test ever fails, this
// gate has silently opened.
func GateAllows(minRole string, ctx context.Context, users gatewayUserFinder) bool {
	if minRole == "" {
		return true
	}
	email, ok := scopetoken.EndUserEmailFromContext(ctx)
	if !ok {
		return false
	}
	return GateAllowsEmail(minRole, email, users)
}

// FilterServersByGate returns the subset of servers that email may see.
// Pure: no receiver, no I/O beyond the injected finder, so the consent-screen
// call sites stay unit-testable without any AuthServer plumbing — the same
// discipline as applyZohoUserState.
func FilterServersByGate(servers []db.MCPServer, email string, users gatewayUserFinder) []db.MCPServer {
	out := make([]db.MCPServer, 0, len(servers))
	for _, s := range servers {
		if GateAllowsEmail(s.MinRole, email, users) {
			out = append(out, s)
		}
	}
	return out
}
