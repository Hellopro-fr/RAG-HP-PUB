// Server-level user authorizations: grant a specific email full,
// unfiltered access to a single MCP server (bypasses Leexi/Ringover/BDD
// scope filters). JSON keys mirror the Go backend's snake_case tags.

export interface ServerAuthorization {
  server_id: string
  email: string
  created_by?: string
  created_at: string
}

export interface CreateServerAuthorizationRequest {
  server_id: string
  email: string
}
