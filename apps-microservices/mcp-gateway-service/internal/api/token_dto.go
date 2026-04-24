package api

// ServerToolSelection represents which tools are selected for a specific server.
type ServerToolSelection struct {
	ServerID  string   `json:"server_id"`
	ToolNames []string `json:"tool_names"` // empty/nil = all tools allowed
}

// LeexiFilterMode constants — accepted values for LeexiFilterDTO.Mode.
const (
	LeexiFilterModeNone    = "none"
	LeexiFilterModeUsers   = "users"
	LeexiFilterModeTeams   = "teams"
	LeexiFilterModeCreator = "creator"
)

// LeexiFilterDTO carries the per-token Leexi ownership scope from / to the
// frontend. UserUUIDs and TeamUUIDs are mutually exclusive in practice and
// are only meaningful for their corresponding Mode.
type LeexiFilterDTO struct {
	Mode      string   `json:"mode"`                  // none | users | teams | creator
	UserUUIDs []string `json:"user_uuids,omitempty"`  // Mode = users
	TeamUUIDs []string `json:"team_uuids,omitempty"`  // Mode = teams
	// CreatorUUID is set in responses only — it is the resolved UUID of the
	// token creator's email, captured at token creation when Mode = creator.
	CreatorUUID string `json:"creator_uuid,omitempty"`
}

// RingoverFilterMode constants — same set as Leexi; reused so the frontend
// shares the mode enum across providers.
const (
	RingoverFilterModeNone    = "none"
	RingoverFilterModeUsers   = "users"
	RingoverFilterModeTeams   = "teams"
	RingoverFilterModeCreator = "creator"
)

// RingoverFilterDTO carries the per-token Ringover ownership scope from / to
// the frontend. Ringover identifies users with numeric integer IDs, so the
// user/team slices are int rather than UUID-strings.
type RingoverFilterDTO struct {
	Mode    string `json:"mode"`                // none | users | teams | creator
	UserIDs []int  `json:"user_ids,omitempty"`  // Mode = users
	TeamIDs []int  `json:"team_ids,omitempty"`  // Mode = teams
	// CreatorUserID is set in responses only — the resolved user_id of the
	// token creator's email when Mode = creator.
	CreatorUserID int `json:"creator_user_id,omitempty"`
}

// CreateTokenRequest is the body for POST /api/v1/tokens.
type CreateTokenRequest struct {
	Name           string                `json:"name"`
	Description    string                `json:"description,omitempty"`
	ServerIDs      []string              `json:"server_ids"`
	ServerTools    []ServerToolSelection `json:"server_tools,omitempty"`    // optional per-server tool selection
	InstructionIDs []string              `json:"instruction_ids,omitempty"` // LLM instructions injected at MCP initialize
	MCPCommand     string                `json:"mcp_command"`               // npx, bunx, deno, uvx, docker, custom
	ServerName     string                `json:"server_name,omitempty"`     // key used in the generated .mcp.json
	AllowHTTP      bool                  `json:"allow_http,omitempty"`      // include --allow-http in generated mcp.json
	ExpiresAt      *string               `json:"expires_at,omitempty"`      // RFC3339
	LeexiFilter    *LeexiFilterDTO       `json:"leexi_filter,omitempty"`    // nil = unrestricted (mode=none)
	RingoverFilter *RingoverFilterDTO    `json:"ringover_filter,omitempty"` // nil = unrestricted (mode=none)
}

// CreateTokenResponse is returned once on creation (includes raw token).
type CreateTokenResponse struct {
	ID             string                `json:"id"`
	Name           string                `json:"name"`
	Description    string                `json:"description,omitempty"`
	Token          string                `json:"token"`        // raw token, shown ONCE
	TokenPrefix    string                `json:"token_prefix"` // "mcp_xxxx..." for display
	ServerIDs      []string              `json:"server_ids"`
	ServerTools    []ServerToolSelection `json:"server_tools,omitempty"`
	InstructionIDs []string              `json:"instruction_ids,omitempty"`
	MCPCommand     string                `json:"mcp_command"`
	ServerName     string                `json:"server_name,omitempty"`
	AllowHTTP      bool                  `json:"allow_http,omitempty"`
	IsActive       bool                  `json:"is_active"`
	CreatedAt      string                `json:"created_at"`
	ExpiresAt      *string               `json:"expires_at,omitempty"`
	LeexiFilter    *LeexiFilterDTO       `json:"leexi_filter,omitempty"`
	RingoverFilter *RingoverFilterDTO    `json:"ringover_filter,omitempty"`
}

// TokenResponse is the standard token response (no raw token).
type TokenResponse struct {
	ID             string                `json:"id"`
	Name           string                `json:"name"`
	Description    string                `json:"description,omitempty"`
	Token          string                `json:"token,omitempty"` // decrypted token (if available)
	TokenPrefix    string                `json:"token_prefix"`
	ServerIDs      []string              `json:"server_ids"`
	ServerTools    []ServerToolSelection `json:"server_tools,omitempty"`
	InstructionIDs []string              `json:"instruction_ids,omitempty"`
	MCPCommand     string                `json:"mcp_command"`
	ServerName     string                `json:"server_name,omitempty"`
	AllowHTTP      bool                  `json:"allow_http,omitempty"`
	IsActive       bool                  `json:"is_active"`
	CreatedBy      string                `json:"created_by,omitempty"`
	CreatedAt      string                `json:"created_at"`
	UpdatedAt      string                `json:"updated_at"`
	ExpiresAt      *string               `json:"expires_at,omitempty"`
	LeexiFilter    *LeexiFilterDTO       `json:"leexi_filter,omitempty"`
	RingoverFilter *RingoverFilterDTO    `json:"ringover_filter,omitempty"`
}

// UpdateTokenRequest is the body for PUT /api/v1/tokens/{id}.
type UpdateTokenRequest struct {
	Name           *string               `json:"name,omitempty"`
	Description    *string               `json:"description,omitempty"`
	ServerIDs      []string              `json:"server_ids,omitempty"`
	ServerTools    []ServerToolSelection `json:"server_tools,omitempty"`
	InstructionIDs []string              `json:"instruction_ids,omitempty"`
	MCPCommand     *string               `json:"mcp_command,omitempty"`
	ServerName     *string               `json:"server_name,omitempty"`
	AllowHTTP      *bool                 `json:"allow_http,omitempty"`
	LeexiFilter    *LeexiFilterDTO       `json:"leexi_filter,omitempty"`
	RingoverFilter *RingoverFilterDTO    `json:"ringover_filter,omitempty"`
}

// CreateTokenResponse already declared above is extended via leexi_filter in
// the create handler — see token_handlers.go. Adding it here keeps the DTO
// declaration self-contained.
