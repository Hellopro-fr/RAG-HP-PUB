package api

// ── Google Sheets Import DTOs ───────────────────────────────────────────────

// SheetInfoRequest is the request body for POST /api/v1/google/sheets/info.
type SheetInfoRequest struct {
	SpreadsheetURL string `json:"spreadsheet_url"`
}

// SheetInfoResponse is the response for POST /api/v1/google/sheets/info.
type SheetInfoResponse struct {
	SpreadsheetID string   `json:"spreadsheet_id"`
	Title         string   `json:"title"`
	Sheets        []string `json:"sheets"`
}

// SheetPreviewRequest is the request body for POST /api/v1/google/sheets/preview.
type SheetPreviewRequest struct {
	SpreadsheetID string `json:"spreadsheet_id"`
	SheetName     string `json:"sheet_name"`
}

// SheetPreviewResponse is the response for POST /api/v1/google/sheets/preview.
type SheetPreviewResponse struct {
	Headers   []string   `json:"headers"`
	Rows      [][]string `json:"rows"`
	TotalRows int        `json:"total_rows"`
}

// ColumnMapping maps spreadsheet column headers to MCP server fields.
type ColumnMapping struct {
	Name                string `json:"name"`                   // Required
	URL                 string `json:"url"`                    // Required
	AuthHeaders         string `json:"auth_headers,omitempty"` // JSON string
	Tags                string `json:"tags,omitempty"`         // Comma-separated
	TransportPreference string `json:"transport_preference,omitempty"`
	ConnectTimeoutMs    string `json:"connect_timeout_ms,omitempty"`
	ToolPrefix          string `json:"tool_prefix,omitempty"`
	Icon                string `json:"icon,omitempty"`
	MCPTransport        string `json:"mcp_transport,omitempty"`
	MCPCommand          string `json:"mcp_command,omitempty"`
	MCPArgs             string `json:"mcp_args,omitempty"` // JSON array string
	MCPEnv              string `json:"mcp_env,omitempty"`  // JSON object string
	DocSlug             string `json:"doc_slug,omitempty"`
	DocDescription      string `json:"doc_description,omitempty"`
	CreatedBy           string `json:"created_by,omitempty"` // Optional — sheet column whose cell value sets mcp_servers.created_by; empty/missing falls back to connected user
}

// SheetImportRequest is the request body for POST /api/v1/google/sheets/import.
type SheetImportRequest struct {
	SpreadsheetID string        `json:"spreadsheet_id"`
	SheetName     string        `json:"sheet_name"`
	ColumnMapping ColumnMapping `json:"column_mapping"`
	AutoDiscover  bool          `json:"auto_discover"`
	// Override fields — applied to all imported servers (take precedence over column mapping).
	NamePrefix           string `json:"name_prefix,omitempty"`           // Prepended to every server name
	FixedTags            string `json:"fixed_tags,omitempty"`            // Comma-separated tags applied to all servers (merged with sheet column)
	FixedToolPrefix      string `json:"fixed_tool_prefix,omitempty"`     // Tool prefix applied to all servers (overrides sheet column)
	FixedIcon            string `json:"fixed_icon,omitempty"`            // Icon applied to all servers (overrides sheet column)
	DisableDocumentation bool   `json:"disable_documentation,omitempty"` // When true, imported servers have no documentation page
	// TemplateSlug is set when the import was launched from the templates
	// catalog (e.g. custom-http). Empty for regular server imports from
	// /servers/import-google. Stamped on every created mcp_servers row so the
	// docs / docs-admin filters can exclude these rows uniformly.
	TemplateSlug string `json:"template_slug,omitempty"`
}

// SheetImportResultEntry represents the import status of a single row.
type SheetImportResultEntry struct {
	Row     int    `json:"row"`
	Name    string `json:"name"`
	Status  string `json:"status"` // "imported", "skipped", "error"
	Message string `json:"message,omitempty"`
}

// InstanceSheetImportRequest is the request body for
// POST /api/v1/google/sheets/import-instances. Mirrors the server-import shape
// (SheetImportRequest) but scoped to a single template: every row becomes one
// template instance (with its own credentials + extra_env).
type InstanceSheetImportRequest struct {
	SpreadsheetID string `json:"spreadsheet_id"`
	SheetName     string `json:"sheet_name"`
	TemplateSlug  string `json:"template_slug"`
	// Column mapping — all required, all non-empty for the import to proceed.
	NameColumn        string `json:"name_column"`
	CredentialsColumn string `json:"credentials_column"`
	// ExtraEnvColumns maps a template's required_extra_env key to the sheet
	// column header that holds its value. One entry per schema field; the
	// handler validates that every required key has a non-empty mapping.
	ExtraEnvColumns map[string]string `json:"extra_env_columns,omitempty"`
	// Optional overrides applied to EVERY row (mirror server-import semantics).
	AutoDiscover    bool   `json:"auto_discover,omitempty"`
	FixedTags       string `json:"fixed_tags,omitempty"` // comma-separated
	FixedToolPrefix string `json:"fixed_tool_prefix,omitempty"`
	FixedIcon       string `json:"fixed_icon,omitempty"`
	NamePrefix      string `json:"name_prefix,omitempty"`
	// Optional — when set, each row's cell at this column populates
	// template_instances.created_by (and the linked mcp_servers row).
	// Empty header or empty cell falls back to the connected user.
	CreatedByColumn string `json:"created_by_column,omitempty"`
}

// SheetImportResponse is the response for POST /api/v1/google/sheets/import.
type SheetImportResponse struct {
	Total    int                      `json:"total"`
	Imported int                      `json:"imported"`
	Skipped  int                      `json:"skipped"`
	Errors   int                      `json:"errors"`
	Results  []SheetImportResultEntry `json:"results"`
}

// GoogleStatusResponse is the response for GET /api/v1/google/status.
type GoogleStatusResponse struct {
	Connected bool   `json:"connected"`
	Email     string `json:"email,omitempty"`
}

// SpreadsheetListItemResponse represents a spreadsheet in the list response.
type SpreadsheetListItemResponse struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	ModifiedTime string `json:"modified_time"`
	WebViewLink  string `json:"web_view_link"`
}

// SpreadsheetListResponse is the response for GET /api/v1/google/spreadsheets.
type SpreadsheetListResponse struct {
	Spreadsheets []SpreadsheetListItemResponse `json:"spreadsheets"`
}
