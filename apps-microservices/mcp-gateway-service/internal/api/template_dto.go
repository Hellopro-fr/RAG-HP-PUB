package api

import (
	"encoding/json"
	"time"
)

type TemplateResponse struct {
	Slug             string          `json:"slug"`
	Name             string          `json:"name"`
	Description      string          `json:"description"`
	Icon             string          `json:"icon"`
	StdioCommand     string          `json:"stdio_command"`
	StdioArgs        json.RawMessage `json:"stdio_args"`
	DefaultEnv       json.RawMessage `json:"default_env"`
	RequiredExtraEnv json.RawMessage `json:"required_extra_env"`
	ToolPrefix       string          `json:"tool_prefix"`
	Tags             json.RawMessage `json:"tags"`
	InstanceCount    int             `json:"instance_count"`
}

type TemplateInstanceResponse struct {
	ID              string          `json:"id"`
	TemplateSlug    string          `json:"template_slug"`
	Name            string          `json:"name"`
	ExtraEnv        json.RawMessage `json:"extra_env,omitempty"`
	RunnerPort      *int            `json:"runner_port,omitempty"`
	RunnerStatus    string          `json:"runner_status"`
	RunnerLastError string          `json:"runner_last_error,omitempty"`
	MCPServerID     string          `json:"mcp_server_id"`
	URL             string          `json:"url,omitempty"`
	CreatedBy       string          `json:"created_by"`
	CreatedAt       time.Time       `json:"created_at"`
	UpdatedAt       time.Time       `json:"updated_at"`
	// Filled by GetByID only:
	StderrTail string `json:"stderr_tail,omitempty"`
}

type CreateInstanceRequest struct {
	TemplateSlug string            `json:"template_slug"`
	Name         string            `json:"name"`
	ExtraEnv     map[string]string `json:"extra_env,omitempty"`
	// Credentials come via multipart file part "credentials", not JSON body.
}

// TemplateExportRow is the decoded shape of a template in the export/import
// JSON payload. Unlike TemplateResponse, JSON-encoded fields (stdio_args,
// default_env, required_extra_env, tags) are decoded to their native Go types
// so the wire form is human-editable instead of nested escaped strings.
type TemplateExportRow struct {
	Slug             string                   `json:"slug"`
	Name             string                   `json:"name"`
	Description      string                   `json:"description"`
	Icon             string                   `json:"icon"`
	StdioCommand     string                   `json:"stdio_command"`
	StdioArgs        []string                 `json:"stdio_args"`
	DefaultEnv       map[string]string        `json:"default_env"`
	RequiredExtraEnv []map[string]interface{} `json:"required_extra_env"`
	ToolPrefix       string                   `json:"tool_prefix"`
	Tags             []string                 `json:"tags"`
	IsActive         bool                     `json:"is_active"`
}

// TemplateExportPayload is the top-level import/export envelope. "version"
// lets us evolve the format without breaking older dumps; unknown top-level
// fields are ignored at import time for forward compatibility.
type TemplateExportPayload struct {
	Version    int                 `json:"version"`
	ExportedAt time.Time           `json:"exported_at"`
	Templates  []TemplateExportRow `json:"templates"`
}
