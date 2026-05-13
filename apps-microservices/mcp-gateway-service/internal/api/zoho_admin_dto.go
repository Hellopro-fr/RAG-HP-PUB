package api

// ZohoAdminCreateRequest is the body of POST /api/v1/zoho-imports/admin.
type ZohoAdminCreateRequest struct {
	Name        string            `json:"name"`
	URL         string            `json:"url"`
	AuthHeaders map[string]string `json:"auth_headers,omitempty"`
}

// ZohoAdminResponse is returned by GET and POST. AuthHeaderKeys lists the
// header names present (values are redacted; same pattern as mcp_servers GET).
type ZohoAdminResponse struct {
	ID             string   `json:"id"`
	Name           string   `json:"name"`
	URL            string   `json:"url"`
	IsActive       bool     `json:"is_active"`
	AuthHeaderKeys []string `json:"auth_header_keys"`
	CreatedAt      string   `json:"created_at"`
	UpdatedAt      string   `json:"updated_at"`
}
