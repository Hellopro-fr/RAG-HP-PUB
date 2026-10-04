package authserver

import (
	"log"

	"mcp-gateway/internal/db"
	"mcp-gateway/internal/gateway"
)

// ServerAccessPolicy decides whether a consent-screen viewer may see (and
// consent to) a server. templateSlug is the server's
// mcp_servers.template_slug when known, "" to let the policy resolve it.
// *gateway.Neo4jAccess satisfies it.
type ServerAccessPolicy interface {
	AllowsEmail(email, serverID, templateSlug string) bool
}

var _ ServerAccessPolicy = (*gateway.Neo4jAccess)(nil)

// SetServerAccess wires the service-level access policy applied to the
// consent screens (HTML + JSON) and to the consent submissions. nil (the
// default) shows every active server, as before the policy existed.
func (s *AuthServer) SetServerAccess(p ServerAccessPolicy) {
	s.serverAccess = p
}

// visibleServers returns the servers the viewer may see, preserving order.
func visibleServers(servers []db.MCPServer, policy ServerAccessPolicy, email string) []db.MCPServer {
	if policy == nil {
		return servers
	}
	out := make([]db.MCPServer, 0, len(servers))
	for _, srv := range servers {
		if policy.AllowsEmail(email, srv.ID, srv.TemplateSlug) {
			out = append(out, srv)
		}
	}
	return out
}

// filterScopeForViewer drops from a consent scope every server — and every
// per-server tool selection — the viewer may not see, so a hand-crafted
// submission can never store a hidden server.
func filterScopeForViewer(scope ConsentScope, policy ServerAccessPolicy, email string) ConsentScope {
	if policy == nil {
		return scope
	}
	var out ConsentScope
	for _, id := range scope.ServerIDs {
		if policy.AllowsEmail(email, id, "") {
			out.ServerIDs = append(out.ServerIDs, id)
		} else {
			log.Printf("[authserver] consent: dropped server %s not visible to %q", id, email)
		}
	}
	for _, sel := range scope.ServerTools {
		if policy.AllowsEmail(email, sel.ServerID, "") {
			out.ServerTools = append(out.ServerTools, sel)
		}
	}
	return out
}
