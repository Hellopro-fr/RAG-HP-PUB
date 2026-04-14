package db

import (
	"encoding/json"
	"time"
)

// MCPServer is the GORM model for the mcp_servers table.
type MCPServer struct {
	ID                  string          `gorm:"type:char(36);primaryKey" json:"id"`
	Name                string          `gorm:"type:varchar(255);not null" json:"name"`
	URL                 string          `gorm:"type:varchar(2048);not null;uniqueIndex:uq_url,length:500" json:"url"`
	MessageURL          string          `gorm:"type:varchar(2048)" json:"message_url"`
	TransportType       string          `gorm:"type:varchar(20)" json:"transport_type"`
	ServerName          string          `gorm:"type:varchar(255)" json:"server_name"`
	ServerVersion       string          `gorm:"type:varchar(64)" json:"server_version"`
	AuthHeaders         []byte          `gorm:"type:blob" json:"-"`
	TransportPreference string          `gorm:"type:varchar(20);not null;default:auto" json:"transport_preference"`
	ConnectTimeoutMs    uint            `gorm:"not null;default:10000" json:"connect_timeout_ms"`
	CapabilitiesRaw     json.RawMessage `gorm:"type:json" json:"capabilities_raw,omitempty"`

	// MCP client config fields — used to generate .mcp.json
	MCPTransport string          `gorm:"type:varchar(20);not null;default:http" json:"mcp_transport"`  // "http", "sse", "stdio"
	MCPCommand   string          `gorm:"type:varchar(2048)" json:"mcp_command,omitempty"`              // for stdio: e.g. "npx", "python"
	MCPArgs      json.RawMessage `gorm:"type:json" json:"mcp_args,omitempty"`                          // for stdio: e.g. ["-y", "@mcp/server"]
	MCPEnv       json.RawMessage `gorm:"type:json" json:"mcp_env,omitempty"`                           // for stdio: e.g. {"KEY": "val"}

	// ToolPrefix is an optional alphanumeric prefix prepended to all tool names as {prefix}_{tool_name}.
	ToolPrefix string `gorm:"type:varchar(64);not null;default:''" json:"tool_prefix"`

	// Icon is a URL or path to the server's icon image.
	Icon string `gorm:"type:varchar(512);not null;default:''" json:"icon"`

	// Documentation fields — used by the public /docs pages.
	DocSlug        string          `gorm:"type:varchar(128);uniqueIndex:uq_doc_slug" json:"doc_slug,omitempty"`
	DocDescription string          `gorm:"type:text" json:"doc_description,omitempty"`
	DocConfigGuide json.RawMessage `gorm:"type:json" json:"doc_config_guide,omitempty"`

	IsActive            bool            `gorm:"not null;default:true;index:idx_is_active" json:"is_active"`
	HealthStatus        string          `gorm:"type:varchar(20);not null;default:unknown;index:idx_health_status" json:"health_status"`
	LastHealthCheck     *time.Time      `gorm:"type:datetime(3)" json:"last_health_check,omitempty"`
	LastError           string          `gorm:"type:text" json:"last_error,omitempty"`
	LastDiscoveredAt    *time.Time      `gorm:"type:datetime(3)" json:"last_discovered_at,omitempty"`
	CreatedBy           string          `gorm:"type:varchar(255);not null;default:'';index:idx_created_by" json:"created_by"`
	CreatedAt           time.Time       `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt           time.Time       `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`

	// Associations
	Tools     []ServerTool     `gorm:"foreignKey:ServerID;constraint:OnDelete:CASCADE" json:"tools,omitempty"`
	Resources []ServerResource `gorm:"foreignKey:ServerID;constraint:OnDelete:CASCADE" json:"resources,omitempty"`
	Prompts   []ServerPrompt   `gorm:"foreignKey:ServerID;constraint:OnDelete:CASCADE" json:"prompts,omitempty"`
	Tags      []ServerTag      `gorm:"foreignKey:ServerID;constraint:OnDelete:CASCADE" json:"tags,omitempty"`
}

func (MCPServer) TableName() string { return "mcp_servers" }

// ServerTool is the GORM model for the server_tools table.
type ServerTool struct {
	ID          uint64          `gorm:"primaryKey;autoIncrement" json:"id"`
	ServerID    string          `gorm:"type:char(36);not null;uniqueIndex:uq_server_tool" json:"server_id"`
	Name        string          `gorm:"type:varchar(255);not null;uniqueIndex:uq_server_tool;index:idx_tool_name" json:"name"`
	Description string          `gorm:"type:text" json:"description,omitempty"`
	InputSchema json.RawMessage `gorm:"type:json;not null" json:"input_schema"`
	IsActive    bool            `gorm:"not null;default:true;index:idx_tool_active" json:"is_active"`
}

func (ServerTool) TableName() string { return "server_tools" }

// ServerResource is the GORM model for the server_resources table.
type ServerResource struct {
	ID          uint64 `gorm:"primaryKey;autoIncrement" json:"id"`
	ServerID    string `gorm:"type:char(36);not null;uniqueIndex:uq_server_resource" json:"server_id"`
	URI         string `gorm:"type:varchar(2048);not null;uniqueIndex:uq_server_resource,length:500;index:idx_resource_uri,length:500" json:"uri"`
	Name        string `gorm:"type:varchar(255);not null" json:"name"`
	Description string `gorm:"type:text" json:"description,omitempty"`
	MimeType    string `gorm:"type:varchar(255)" json:"mime_type,omitempty"`
}

func (ServerResource) TableName() string { return "server_resources" }

// ServerPrompt is the GORM model for the server_prompts table.
type ServerPrompt struct {
	ID          uint64           `gorm:"primaryKey;autoIncrement" json:"id"`
	ServerID    string           `gorm:"type:char(36);not null;uniqueIndex:uq_server_prompt" json:"server_id"`
	Name        string           `gorm:"type:varchar(255);not null;uniqueIndex:uq_server_prompt;index:idx_prompt_name" json:"name"`
	Description string           `gorm:"type:text" json:"description,omitempty"`
	Arguments   []PromptArgument `gorm:"foreignKey:PromptID;constraint:OnDelete:CASCADE" json:"arguments,omitempty"`
}

func (ServerPrompt) TableName() string { return "server_prompts" }

// PromptArgument is the GORM model for the prompt_arguments table.
type PromptArgument struct {
	ID          uint64 `gorm:"primaryKey;autoIncrement" json:"id"`
	PromptID    uint64 `gorm:"not null;uniqueIndex:uq_prompt_arg" json:"prompt_id"`
	Name        string `gorm:"type:varchar(255);not null;uniqueIndex:uq_prompt_arg" json:"name"`
	Description string `gorm:"type:text" json:"description,omitempty"`
	IsRequired  bool   `gorm:"not null;default:false" json:"is_required"`
}

func (PromptArgument) TableName() string { return "prompt_arguments" }

// ServerTag is the GORM model for the server_tags table.
type ServerTag struct {
	ServerID string `gorm:"type:char(36);not null;primaryKey" json:"server_id"`
	Tag      string `gorm:"type:varchar(64);not null;primaryKey;index:idx_tag" json:"tag"`
}

func (ServerTag) TableName() string { return "server_tags" }

// ScopeToken is the GORM model for the scope_tokens table.
type ScopeToken struct {
	ID          string     `gorm:"type:char(36);primaryKey" json:"id"`
	Name        string     `gorm:"type:varchar(255);not null" json:"name"`
	Description string     `gorm:"type:text" json:"description,omitempty"`
	TokenHash   string     `gorm:"type:varchar(64);not null;uniqueIndex:uq_token_hash" json:"-"`
	TokenPrefix string     `gorm:"type:varchar(16);not null" json:"token_prefix"`
	CreatedBy   string     `gorm:"type:varchar(255);not null;default:''" json:"created_by"`
	MCPCommand     string     `gorm:"type:varchar(64);not null;default:'npx'" json:"mcp_command"`
	EncryptedToken []byte     `gorm:"type:blob" json:"-"`
	ExpiresAt      *time.Time `gorm:"type:datetime(3)" json:"expires_at,omitempty"`
	IsActive    bool       `gorm:"not null;default:true;index:idx_scope_active" json:"is_active"`
	CreatedAt   time.Time  `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt   time.Time  `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`

	// Leexi ownership scope. When LeexiFilterMode is "none" (default) the
	// token is unrestricted; other modes narrow access to calls whose owner
	// belongs to the configured set:
	//   - "users":   LeexiAllowedUserUUIDs is authoritative.
	//   - "teams":   LeexiAllowedTeamUUIDs is resolved to user UUIDs at
	//                runtime (dynamic — new team members inherit access).
	//   - "creator": LeexiAllowedUserUUIDs holds a single UUID resolved from
	//                the creator's email at token creation time.
	LeexiFilterMode       string          `gorm:"type:varchar(16);not null;default:'none'" json:"leexi_filter_mode"`
	LeexiAllowedUserUUIDs json.RawMessage `gorm:"type:json" json:"leexi_allowed_user_uuids,omitempty"`
	LeexiAllowedTeamUUIDs json.RawMessage `gorm:"type:json" json:"leexi_allowed_team_uuids,omitempty"`

	// Associations
	Servers []ScopeTokenServer `gorm:"foreignKey:TokenID;constraint:OnDelete:CASCADE" json:"servers,omitempty"`
	Tools   []ScopeTokenTool   `gorm:"foreignKey:TokenID;constraint:OnDelete:CASCADE" json:"tools,omitempty"`
}

func (ScopeToken) TableName() string { return "scope_tokens" }

// ScopeTokenServer is the join table between scope_tokens and mcp_servers.
type ScopeTokenServer struct {
	TokenID  string `gorm:"type:char(36);not null;primaryKey" json:"token_id"`
	ServerID string `gorm:"type:char(36);not null;primaryKey" json:"server_id"`
}

func (ScopeTokenServer) TableName() string { return "scope_token_servers" }

// ScopeTokenTool records which tools are allowed for a token+server pair.
// If no rows exist for a (token_id, server_id), ALL tools of that server are allowed.
type ScopeTokenTool struct {
	TokenID  string `gorm:"type:char(36);not null;primaryKey" json:"token_id"`
	ServerID string `gorm:"type:char(36);not null;primaryKey" json:"server_id"`
	ToolName string `gorm:"type:varchar(255);not null;primaryKey" json:"tool_name"`
}

func (ScopeTokenTool) TableName() string { return "scope_token_tools" }

// OAuth2Client is the GORM model for the oauth2_clients table.
// Supports both Authorization Code (with PKCE) and Client Credentials grants per MCP spec.
type OAuth2Client struct {
	ID              string     `gorm:"type:char(36);primaryKey" json:"id"` // = client_id (UUID)
	Name            string     `gorm:"type:varchar(255);not null" json:"name"`
	Description     string     `gorm:"type:text" json:"description,omitempty"`
	SecretHash      string     `gorm:"type:varchar(64);not null;uniqueIndex:uq_secret_hash" json:"-"`
	SecretPrefix    string     `gorm:"type:varchar(16);not null" json:"secret_prefix"`
	EncryptedSecret []byte     `gorm:"type:blob" json:"-"`
	// OAuth2 registration fields
	RedirectURIs          *string `gorm:"type:json" json:"redirect_uris,omitempty"`                              // JSON array of registered redirect URIs, NULL when unset
	GrantTypes            *string `gorm:"type:json" json:"grant_types,omitempty"`                                // JSON array: ["authorization_code"], ["client_credentials"], or both, NULL when unset
	TokenAuthMethod       string `gorm:"type:varchar(30);not null;default:'client_secret_post'" json:"token_auth_method"`
	DynamicallyRegistered bool   `gorm:"not null;default:false" json:"dynamically_registered"`
	AccessTokenTTL        int    `gorm:"not null;default:3600" json:"access_token_ttl"` // seconds
	ExpiresAt             *time.Time `gorm:"type:datetime(3)" json:"expires_at,omitempty"`
	IsActive              bool       `gorm:"not null;default:true;index:idx_oauth2_active" json:"is_active"`
	CreatedBy             string     `gorm:"type:varchar(255);not null;default:''" json:"created_by"`
	CreatedAt             time.Time  `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt             time.Time  `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`

	// Leexi ownership scope — see ScopeToken for semantics.
	LeexiFilterMode       string          `gorm:"type:varchar(16);not null;default:'none'" json:"leexi_filter_mode"`
	LeexiAllowedUserUUIDs json.RawMessage `gorm:"type:json" json:"leexi_allowed_user_uuids,omitempty"`
	LeexiAllowedTeamUUIDs json.RawMessage `gorm:"type:json" json:"leexi_allowed_team_uuids,omitempty"`

	// Associations
	Servers []OAuth2ClientServer `gorm:"foreignKey:ClientID;constraint:OnDelete:CASCADE" json:"servers,omitempty"`
	Tools   []OAuth2ClientTool   `gorm:"foreignKey:ClientID;constraint:OnDelete:CASCADE" json:"tools,omitempty"`
}

func (OAuth2Client) TableName() string { return "oauth2_clients" }

// OAuth2ClientServer is the join table between oauth2_clients and mcp_servers.
type OAuth2ClientServer struct {
	ClientID string `gorm:"type:char(36);not null;primaryKey" json:"client_id"`
	ServerID string `gorm:"type:char(36);not null;primaryKey" json:"server_id"`
}

func (OAuth2ClientServer) TableName() string { return "oauth2_client_servers" }

// OAuth2ClientTool records which tools are allowed for a client+server pair.
// If no rows exist for a (client_id, server_id), ALL tools of that server are allowed.
type OAuth2ClientTool struct {
	ClientID string `gorm:"type:char(36);not null;primaryKey" json:"client_id"`
	ServerID string `gorm:"type:char(36);not null;primaryKey" json:"server_id"`
	ToolName string `gorm:"type:varchar(255);not null;primaryKey" json:"tool_name"`
}

func (OAuth2ClientTool) TableName() string { return "oauth2_client_tools" }

// OAuth2AuthorizationCode is the GORM model for short-lived authorization codes.
type OAuth2AuthorizationCode struct {
	CodeHash      string     `gorm:"type:varchar(64);primaryKey" json:"-"`
	ClientID      string     `gorm:"type:char(36);not null;index:idx_authcode_client" json:"client_id"`
	UserEmail     string     `gorm:"type:varchar(255);not null" json:"user_email"`
	RedirectURI   string     `gorm:"type:varchar(2048);not null" json:"redirect_uri"`
	CodeChallenge string     `gorm:"type:varchar(128);not null" json:"-"`
	Scope         string     `gorm:"type:json" json:"scope,omitempty"`
	ExpiresAt     time.Time  `gorm:"type:datetime(3);not null" json:"expires_at"`
	UsedAt        *time.Time `gorm:"type:datetime(3)" json:"used_at,omitempty"`
	CreatedAt     time.Time  `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
}

func (OAuth2AuthorizationCode) TableName() string { return "oauth2_authorization_codes" }

// OAuth2RefreshToken is the GORM model for refresh tokens.
type OAuth2RefreshToken struct {
	TokenHash string     `gorm:"type:varchar(64);primaryKey" json:"-"`
	ClientID  string     `gorm:"type:char(36);not null;index:idx_refresh_client" json:"client_id"`
	UserEmail string     `gorm:"type:varchar(255);not null" json:"user_email"`
	Scope     string     `gorm:"type:json" json:"scope,omitempty"`
	ExpiresAt time.Time  `gorm:"type:datetime(3);not null" json:"expires_at"`
	RevokedAt *time.Time `gorm:"type:datetime(3)" json:"revoked_at,omitempty"`
	CreatedAt time.Time  `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
}

func (OAuth2RefreshToken) TableName() string { return "oauth2_refresh_tokens" }

// OAuth2Consent stores per-client, per-user consent decisions.
type OAuth2Consent struct {
	ID        string    `gorm:"type:char(36);primaryKey" json:"id"`
	ClientID  string    `gorm:"type:char(36);not null;uniqueIndex:uq_consent_client_user" json:"client_id"`
	UserEmail string    `gorm:"type:varchar(255);not null;uniqueIndex:uq_consent_client_user" json:"user_email"`
	Scope     string    `gorm:"type:json" json:"scope,omitempty"`
	CreatedAt time.Time `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt time.Time `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (OAuth2Consent) TableName() string { return "oauth2_consents" }

// GatewayUser is the GORM model for admin UI users with role-based access.
type GatewayUser struct {
	ID          uint64     `gorm:"primaryKey;autoIncrement" json:"id"`
	Email       string     `gorm:"type:varchar(255);not null;uniqueIndex:uq_user_email" json:"email"`
	DisplayName string     `gorm:"type:varchar(255)" json:"display_name"`
	Role        string     `gorm:"type:varchar(20);not null;default:'config-only'" json:"role"`
	LoginCount  int        `gorm:"not null;default:0" json:"login_count"`
	LastLoginAt *time.Time `gorm:"type:datetime(3)" json:"last_login_at,omitempty"`
	CreatedAt   time.Time  `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt   time.Time  `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (GatewayUser) TableName() string { return "gateway_users" }

// AuditLog records API actions for auditing.
type AuditLog struct {
	ID             uint64    `gorm:"primaryKey;autoIncrement" json:"id"`
	UserEmail      string    `gorm:"type:varchar(255);not null;index:idx_audit_user_date" json:"user_email"`
	Action         string    `gorm:"type:varchar(50);not null;index:idx_audit_action" json:"action"`
	ResourceType   string    `gorm:"type:varchar(50)" json:"resource_type"`
	ResourceID     string    `gorm:"type:varchar(255)" json:"resource_id"`
	RequestMethod  string    `gorm:"type:varchar(10)" json:"request_method"`
	RequestPath    string    `gorm:"type:varchar(500)" json:"request_path"`
	RequestBody    string    `gorm:"type:text" json:"request_body,omitempty"`
	ResponseStatus int       `gorm:"not null" json:"response_status"`
	ResponseBody   string    `gorm:"type:text" json:"response_body,omitempty"`
	IPAddress      string    `gorm:"type:varchar(45)" json:"ip_address"`
	CreatedAt      time.Time `gorm:"type:datetime(3);autoCreateTime;index:idx_audit_user_date" json:"created_at"`
}

func (AuditLog) TableName() string { return "audit_logs" }
