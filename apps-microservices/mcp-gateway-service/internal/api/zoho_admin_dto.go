package api

import (
	"time"

	"mcp-gateway/internal/db"
)

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

// ZohoImportRowDTO is the wire shape of a zoho_imports row. auth_headers
// values are redacted to header key names; the encrypted blob is never
// exposed.
type ZohoImportRowDTO struct {
	ID             string   `json:"id"`
	Name           string   `json:"name"`
	URL            string   `json:"url"`
	IsAdmin        bool     `json:"is_admin"`
	IsActive       bool     `json:"is_active"`
	CreatedBy      string   `json:"created_by"`
	TemplateSlug   string   `json:"template_slug"`
	AuthHeaderKeys []string `json:"auth_header_keys"`
	CreatedAt      string   `json:"created_at"`
	UpdatedAt      string   `json:"updated_at"`
}

// ZohoImportListResponse paginates List results.
type ZohoImportListResponse struct {
	Rows  []ZohoImportRowDTO `json:"rows"`
	Total int64              `json:"total"`
	Page  int                `json:"page"`
	Limit int                `json:"limit"`
}

// ZohoImportUpdateRequest is the body of PATCH /api/v1/zoho-imports/{id}.
// Every field is optional. A non-nil AuthHeaders pointer to an empty map
// clears the encrypted blob; omitting the field entirely leaves it alone.
type ZohoImportUpdateRequest struct {
	Name        *string            `json:"name,omitempty"`
	URL         *string            `json:"url,omitempty"`
	AuthHeaders *map[string]string `json:"auth_headers,omitempty"`
	IsActive    *bool              `json:"is_active,omitempty"`
}

// ZohoImportTestResponse is the result of POST /api/v1/zoho-imports/{id}/test.
type ZohoImportTestResponse struct {
	OK         bool   `json:"ok"`
	StatusCode int    `json:"status_code,omitempty"`
	LatencyMs  int64  `json:"latency_ms"`
	Error      string `json:"error,omitempty"`
}

// ZohoUserCreateRequest is the body of POST /api/v1/zoho-imports. It
// inserts a per-user row (IsAdmin=false). CreatedBy is required. The admin
// singleton is created via POST /api/v1/zoho-imports/admin instead.
type ZohoUserCreateRequest struct {
	Name         string            `json:"name"`
	URL          string            `json:"url"`
	CreatedBy    string            `json:"created_by"`
	AuthHeaders  map[string]string `json:"auth_headers,omitempty"`
	IsActive     *bool             `json:"is_active,omitempty"`
	TemplateSlug string            `json:"template_slug,omitempty"`
}

// ZohoImportToolDTO is one row of the GET /api/v1/zoho-imports/{id}/tools
// response. input_schema is returned as the raw JSON string persisted in
// zoho_import_tools — the client parses it for display.
type ZohoImportToolDTO struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	InputSchema string `json:"input_schema"`
	UpdatedAt   string `json:"updated_at"`
}

// ZohoImportToolsResponse is the wire shape of GET /{id}/tools.
type ZohoImportToolsResponse struct {
	Tools []ZohoImportToolDTO `json:"tools"`
	Total int                 `json:"total"`
}

func zohoImportToolToDTO(t *db.ZohoImportTool) ZohoImportToolDTO {
	return ZohoImportToolDTO{
		Name:        t.Name,
		Description: t.Description,
		InputSchema: string(t.InputSchema),
		UpdatedAt:   t.UpdatedAt.UTC().Format(time.RFC3339),
	}
}
