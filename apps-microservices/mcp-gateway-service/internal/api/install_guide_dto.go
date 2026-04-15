package api

import "encoding/json"

// ── Executor DTOs ──────────────────────────────────────────────────

// CreateExecutorRequest is the request body for creating an executor.
type CreateExecutorRequest struct {
	Slug         string          `json:"slug"`
	Label        string          `json:"label"`
	Sub          string          `json:"sub"`
	Description  string          `json:"description"`
	Intro        string          `json:"intro"`
	Icon         string          `json:"icon"`
	Color        string          `json:"color"`
	Install      json.RawMessage `json:"install"`
	Verify       string          `json:"verify"`
	McpConfig    string          `json:"mcp_config"`
	CliAddCmd    string          `json:"cli_add_cmd"`
	NoteLabel    string          `json:"note_label"`
	NoteText     string          `json:"note_text"`
	NoteClass    string          `json:"note_class"`
	Content      json.RawMessage `json:"content"`
	DisplayOrder int             `json:"display_order"`
	IsActive     *bool           `json:"is_active"`
}

// UpdateExecutorRequest is the request body for updating an executor.
type UpdateExecutorRequest struct {
	Slug         *string          `json:"slug"`
	Label        *string          `json:"label"`
	Sub          *string          `json:"sub"`
	Description  *string          `json:"description"`
	Intro        *string          `json:"intro"`
	Icon         *string          `json:"icon"`
	Color        *string          `json:"color"`
	Install      *json.RawMessage `json:"install"`
	Verify       *string          `json:"verify"`
	McpConfig    *string          `json:"mcp_config"`
	CliAddCmd    *string          `json:"cli_add_cmd"`
	NoteLabel    *string          `json:"note_label"`
	NoteText     *string          `json:"note_text"`
	NoteClass    *string          `json:"note_class"`
	Content      *json.RawMessage `json:"content"`
	DisplayOrder *int             `json:"display_order"`
	IsActive     *bool            `json:"is_active"`
}

// ── Config DTOs ────────────────────────────────────────────────────

// CreateConfigRequest is the request body for creating a config.
type CreateConfigRequest struct {
	Slug         string          `json:"slug"`
	Label        string          `json:"label"`
	Description  string          `json:"description"`
	Icon         string          `json:"icon"`
	Color        string          `json:"color"`
	Content      json.RawMessage `json:"content"`
	DisplayOrder int             `json:"display_order"`
	IsActive     *bool           `json:"is_active"`
}

// UpdateConfigRequest is the request body for updating a config.
type UpdateConfigRequest struct {
	Slug         *string          `json:"slug"`
	Label        *string          `json:"label"`
	Description  *string          `json:"description"`
	Icon         *string          `json:"icon"`
	Color        *string          `json:"color"`
	Content      *json.RawMessage `json:"content"`
	DisplayOrder *int             `json:"display_order"`
	IsActive     *bool            `json:"is_active"`
}
