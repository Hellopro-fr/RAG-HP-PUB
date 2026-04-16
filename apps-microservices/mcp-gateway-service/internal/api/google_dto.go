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
	Name                string `json:"name"`                           // Required
	URL                 string `json:"url"`                            // Required
	AuthHeaders         string `json:"auth_headers,omitempty"`         // JSON string
	Tags                string `json:"tags,omitempty"`                 // Comma-separated
	TransportPreference string `json:"transport_preference,omitempty"`
	ConnectTimeoutMs    string `json:"connect_timeout_ms,omitempty"`
	ToolPrefix          string `json:"tool_prefix,omitempty"`
	Icon                string `json:"icon,omitempty"`
	MCPTransport        string `json:"mcp_transport,omitempty"`
	MCPCommand          string `json:"mcp_command,omitempty"`
	MCPArgs             string `json:"mcp_args,omitempty"`    // JSON array string
	MCPEnv              string `json:"mcp_env,omitempty"`     // JSON object string
	DocSlug             string `json:"doc_slug,omitempty"`
	DocDescription      string `json:"doc_description,omitempty"`
}

// SheetImportRequest is the request body for POST /api/v1/google/sheets/import.
type SheetImportRequest struct {
	SpreadsheetID string        `json:"spreadsheet_id"`
	SheetName     string        `json:"sheet_name"`
	ColumnMapping ColumnMapping `json:"column_mapping"`
	AutoDiscover  bool          `json:"auto_discover"`
	// Override fields — applied to all imported servers (take precedence over column mapping).
	NamePrefix     string `json:"name_prefix,omitempty"`      // Prepended to every server name
	FixedTags      string `json:"fixed_tags,omitempty"`       // Comma-separated tags applied to all servers (merged with sheet column)
	FixedToolPrefix string `json:"fixed_tool_prefix,omitempty"` // Tool prefix applied to all servers (overrides sheet column)
	FixedIcon            string `json:"fixed_icon,omitempty"`             // Icon applied to all servers (overrides sheet column)
	DisableDocumentation bool   `json:"disable_documentation,omitempty"` // When true, imported servers have no documentation page
}

// SheetImportResultEntry represents the import status of a single row.
type SheetImportResultEntry struct {
	Row     int    `json:"row"`
	Name    string `json:"name"`
	Status  string `json:"status"` // "imported", "skipped", "error"
	Message string `json:"message,omitempty"`
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
