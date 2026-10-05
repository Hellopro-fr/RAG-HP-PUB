package api

import (
	"context"
	"log"

	"mcp-gateway/internal/auth"
	"mcp-gateway/internal/gateway"
	"mcp-gateway/internal/mcp"
	"mcp-gateway/internal/transport"
)

// hellodataToolPrefix mirrors the unexported constant of the same name in
// internal/gateway/scoped_gateway.go. Both MUST stay in sync.
const hellodataToolPrefix = "hellodata"

// hellodataToolLister fetches a backend's tools/list with the given headers.
// A field on Handler (see hellodataLister) so tests can stub the network.
type hellodataToolLister func(ctx context.Context, messageURL string, headers map[string]string) ([]mcp.Tool, error)

func liveHellodataToolLister(ctx context.Context, messageURL string, headers map[string]string) ([]mcp.Tool, error) {
	return transport.NewBackendClientWithEndpoint(messageURL, headers).ListTools(ctx)
}

// hellodataToolsToPersist decides which tools are saved for a hellodata
// backend. ok=false means "not hellodata": the caller keeps backend.Tools.
//
// Why: mcp-hellodata-service lists its tools only to an admin or a grant
// holder, and DiscoverAndRegister asks anonymously, so backend.Tools is
// always empty and /servers showed 0 tools even to an admin. When the admin
// API is driven by an admin, the list is fetched again with that admin's
// identity and THAT is what gets saved to the DB.
//
// The registry is deliberately left untouched: ScopedGateway never reads
// hellodata tools from it (fetchHellodataTools live-fetches per caller), and
// the health checker would rewrite it anonymously within 30s anyway.
//
// Any other caller (non-admin owner, auth disabled, fetch failure, empty
// answer) keeps the tools already in the DB instead of wiping them, so a
// refresh by someone who cannot see the catalog never erases it — and never
// fires a spurious ToolsRegression alert.
func (h *Handler) hellodataToolsToPersist(ctx context.Context, id string, backend *gateway.BackendServer) ([]mcp.Tool, bool) {
	prefix := backend.ToolPrefix
	var stored []mcp.Tool
	if srv, err := h.repo.GetByID(id); err == nil {
		// The DB row is authoritative: some re-discover paths (bulk
		// rediscover) do not push ToolPrefix back into the registry.
		if srv.ToolPrefix != "" {
			prefix = srv.ToolPrefix
		}
		for _, t := range srv.Tools {
			stored = append(stored, mcp.Tool{Name: t.Name, Description: t.Description, InputSchema: t.InputSchema})
		}
	}
	if prefix != hellodataToolPrefix {
		return nil, false
	}

	email := auth.UserEmailFromContext(ctx)
	if email == "" || auth.UserRoleFromContext(ctx) != auth.RoleAdmin {
		log.Printf("[api] hellodata %s: caller is not an admin — keeping the %d stored tool(s)", id, len(stored))
		return stored, true
	}

	headers := make(map[string]string, len(backend.AuthHeaders)+2)
	for k, v := range backend.AuthHeaders {
		headers[k] = v
	}
	headers[gateway.EndUserEmailHeader] = email
	headers[gateway.EndUserRoleHeader] = auth.RoleAdmin

	lister := h.hellodataLister
	if lister == nil {
		lister = liveHellodataToolLister
	}
	tools, err := lister(ctx, backend.MessageURL, headers)
	if err != nil || len(tools) == 0 {
		log.Printf("[api] hellodata %s: admin tools/list failed (err=%v, count=%d) — keeping the %d stored tool(s)", id, err, len(tools), len(stored))
		return stored, true
	}
	return tools, true
}
