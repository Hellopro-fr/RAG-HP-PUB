package api

import (
	"encoding/json"
	"time"
)

// ── Request DTOs ────────────────────────────────────────────────────────────────

type CreateServerRequest struct {
	Name                string            `json:"name"`
	URL                 string            `json:"url"`
	AuthHeaders         map[string]string `json:"auth_headers,omitempty"`
	TransportPreference string            `json:"transport_preference,omitempty"`
	ConnectTimeoutMs    *uint             `json:"connect_timeout_ms,omitempty"`
	Tags                []string          `json:"tags,omitempty"`
	AutoDiscover        bool              `json:"auto_discover"`
	ToolPrefix          string            `json:"tool_prefix,omitempty"` // alphanumeric prefix for tool names: {prefix}_{tool_name}
	Icon                string            `json:"icon,omitempty"`        // URL or path to the server icon
	// MCP client config
	MCPTransport string            `json:"mcp_transport,omitempty"` // "http", "sse", "stdio"
	MCPCommand   string            `json:"mcp_command,omitempty"`   // stdio: command to run
	MCPArgs      []string          `json:"mcp_args,omitempty"`      // stdio: command arguments
	MCPEnv       map[string]string `json:"mcp_env,omitempty"`       // stdio: environment variables
}

type UpdateServerRequest struct {
	Name                *string           `json:"name,omitempty"`
	URL                 *string           `json:"url,omitempty"`
	AuthHeaders         map[string]string `json:"auth_headers,omitempty"`
	TransportPreference *string           `json:"transport_preference,omitempty"`
	ConnectTimeoutMs    *uint             `json:"connect_timeout_ms,omitempty"`
	Tags                *[]string         `json:"tags,omitempty"`
	ToolPrefix          *string           `json:"tool_prefix,omitempty"` // alphanumeric prefix for tool names
	Icon                *string           `json:"icon,omitempty"`        // URL or path to the server icon
	// Documentation fields
	DocSlug        *string          `json:"doc_slug,omitempty"`
	DocDescription *string          `json:"doc_description,omitempty"`
	DocConfigGuide *json.RawMessage `json:"doc_config_guide,omitempty"`
	// MCP client config
	MCPTransport *string           `json:"mcp_transport,omitempty"`
	MCPCommand   *string           `json:"mcp_command,omitempty"`
	MCPArgs      *[]string         `json:"mcp_args,omitempty"`
	MCPEnv       map[string]string `json:"mcp_env,omitempty"`
}

// ── Response DTOs ───────────────────────────────────────────────────────────────

// ToolSummary is a lightweight tool reference (name + description) for list views.
type ToolSummary struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	IsActive    bool   `json:"is_active"`
}

type ServerResponse struct {
	ID                  string     `json:"id"`
	Name                string     `json:"name"`
	URL                 string     `json:"url"`
	MessageURL          string     `json:"message_url,omitempty"`
	TransportType       string     `json:"transport_type,omitempty"`
	ServerName          string     `json:"server_name,omitempty"`
	ServerVersion       string     `json:"server_version,omitempty"`
	TransportPreference string     `json:"transport_preference"`
	ConnectTimeoutMs    uint       `json:"connect_timeout_ms"`
	IsActive            bool       `json:"is_active"`
	HealthStatus        string     `json:"health_status"`
	LastHealthCheck     *time.Time `json:"last_health_check,omitempty"`
	LastError           string     `json:"last_error,omitempty"`
	LastDiscoveredAt    *time.Time `json:"last_discovered_at,omitempty"`
	ToolPrefix          string            `json:"tool_prefix"`
	Icon                string            `json:"icon,omitempty"`
	ToolsCount          int               `json:"tools_count"`
	ToolNames           []ToolSummary     `json:"tool_names"`
	ResourcesCount      int               `json:"resources_count"`
	PromptsCount        int               `json:"prompts_count"`
	Tags                []string          `json:"tags"`
	MCPTransport        string            `json:"mcp_transport"`
	MCPCommand          string            `json:"mcp_command,omitempty"`
	MCPArgs             []string          `json:"mcp_args,omitempty"`
	MCPEnv              map[string]string `json:"mcp_env,omitempty"`
	HasAuthHeaders      bool              `json:"has_auth_headers"`
	// Documentation fields
	DocSlug        string          `json:"doc_slug,omitempty"`
	DocDescription string          `json:"doc_description,omitempty"`
	DocConfigGuide json.RawMessage `json:"doc_config_guide,omitempty"`
	CreatedBy           string            `json:"created_by,omitempty"`
	CreatedAt           time.Time         `json:"created_at"`
	UpdatedAt           time.Time         `json:"updated_at"`
}

type ServerDetailResponse struct {
	ServerResponse
	Tools     []ToolResponse     `json:"tools"`
	Resources []ResourceResponse `json:"resources"`
	Prompts   []PromptResponse   `json:"prompts"`
}

type ToolResponse struct {
	Name        string          `json:"name"`
	Description string          `json:"description,omitempty"`
	InputSchema json.RawMessage `json:"input_schema"`
	IsActive    bool            `json:"is_active"`
}

type ResourceResponse struct {
	URI         string `json:"uri"`
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	MimeType    string `json:"mime_type,omitempty"`
}

type PromptResponse struct {
	Name        string                   `json:"name"`
	Description string                   `json:"description,omitempty"`
	Arguments   []PromptArgumentResponse `json:"arguments,omitempty"`
}

type PromptArgumentResponse struct {
	Name        string `json:"name"`
	Description string `json:"description,omitempty"`
	IsRequired  bool   `json:"is_required"`
}

type ListServersResponse struct {
	Servers []ServerResponse `json:"servers"`
	Total   int              `json:"total"`
}

type ErrorResponse struct {
	Error string `json:"error"`
}

// ── Public Docs DTOs ─────────────────────────────────────────────────────────

type DocsServerSummary struct {
	Slug        string `json:"slug"`
	Name        string `json:"name"`
	Description string `json:"description"`
	Icon        string `json:"icon,omitempty"`
	ToolsCount  int    `json:"tools_count"`
}

type DocsServerDetail struct {
	DocsServerSummary
	Tools       []ToolResponse  `json:"tools"`
	ConfigGuide json.RawMessage `json:"config_guide,omitempty"`
}
