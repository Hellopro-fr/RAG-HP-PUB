package gateway

import "mcp-gateway/internal/mcp"

// ZohoCatalogState is what a ZohoUserCatalog implementation returns for a
// single viewer email. Configured == true iff the viewer's resolved
// zoho_imports row exists AND has at least one tool. Tools is non-empty
// only when Configured == true.
type ZohoCatalogState struct {
	Tools      []mcp.Tool
	Configured bool
}

// ZohoServerState is the per-Zoho-backend view rendered on the consent
// screen. Mirrors ZohoCatalogState but keyed by mcp_servers.id in the
// gateway's FetchZohoStateForUser response.
type ZohoServerState struct {
	Tools      []mcp.Tool
	Configured bool
}
