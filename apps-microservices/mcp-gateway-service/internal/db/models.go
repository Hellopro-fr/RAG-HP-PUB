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

	// TemplateSlug links this server to a template catalog row when the server
	// was created via one of the templates flows (stdio instance or http_batch
	// sheet import). Empty string means "regular server". Used to filter
	// template-origin rows out of the docs list and the docs-admin list.
	TemplateSlug string `gorm:"type:varchar(64);not null;default:'';index:idx_template_slug" json:"template_slug,omitempty"`

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

// LLMInstruction is a reusable "page" of instruction content selected into
// scope tokens or OAuth2 clients. A page contains an ordered list of rows
// (LLMInstructionRow); each row has its own server scope and is rendered as
// a `## <title>\n<body>` block in the MCP `initialize` response when any of
// its linked servers overlap the active token/client's allowed set. The
// page-level fields (title, description) are admin-only and never sent to
// the LLM.
//
// Body is deprecated — retained as an always-empty column for backward
// migration compatibility (MySQL AutoMigrate can't drop NOT NULL columns).
// All instruction content now lives on LLMInstructionRow.
type LLMInstruction struct {
	ID          string    `gorm:"type:char(36);primaryKey" json:"id"`
	Title       string    `gorm:"type:varchar(255);not null" json:"title"`
	// Body is deprecated: the column is kept NOT NULL for backward-compatibility
	// with records created before the row model landed. New code writes an
	// empty string and all content lives on LLMInstructionRow.
	Body        string    `gorm:"type:text;not null" json:"-"`
	Description string    `gorm:"type:varchar(512);not null;default:''" json:"description"`
	CreatedBy   string    `gorm:"type:varchar(255);not null;default:'';index:idx_llm_instruction_created_by" json:"created_by"`
	CreatedAt   time.Time `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt   time.Time `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`

	// Associations
	Rows []LLMInstructionRow `gorm:"foreignKey:InstructionID;constraint:OnDelete:CASCADE" json:"rows,omitempty"`
}

func (LLMInstruction) TableName() string { return "llm_instructions" }

// LLM instruction row kinds. "general" rows are injected on every MCP session
// regardless of server scope — useful for gateway-wide boilerplate (role
// framing, safety guidance). "per_server" rows are injected only when one of
// their linked servers is in the active token/client scope.
const (
	LLMInstructionRowKindPerServer = "per_server"
	LLMInstructionRowKindGeneral   = "general"
)

// LLMInstructionRow is a single block inside an LLMInstruction page. Kind
// decides whether the row is gated by its linked servers ("per_server") or
// always rendered ("general"). DisplayOrder drives the builder's drag-and-drop
// ordering and the composed-output order.
type LLMInstructionRow struct {
	ID            string    `gorm:"type:char(36);primaryKey" json:"id"`
	InstructionID string    `gorm:"type:char(36);not null;index:idx_llm_row_instruction" json:"instruction_id"`
	Kind          string    `gorm:"type:varchar(32);not null;default:'per_server';index:idx_llm_row_kind" json:"kind"`
	Title         string    `gorm:"type:varchar(255);not null;default:''" json:"title"`
	Body          string    `gorm:"type:text;not null" json:"body"`
	DisplayOrder  int       `gorm:"not null;default:0;index:idx_llm_row_order" json:"display_order"`
	CreatedAt     time.Time `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt     time.Time `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`

	// Associations — ignored when Kind == "general".
	Servers []LLMInstructionRowServer `gorm:"foreignKey:RowID;constraint:OnDelete:CASCADE" json:"servers,omitempty"`
}

func (LLMInstructionRow) TableName() string { return "llm_instruction_rows" }

// LLMInstructionRowServer links a single row to the MCP servers it applies to.
type LLMInstructionRowServer struct {
	RowID    string `gorm:"type:char(36);not null;primaryKey" json:"row_id"`
	ServerID string `gorm:"type:char(36);not null;primaryKey;index:idx_llm_row_server" json:"server_id"`
}

func (LLMInstructionRowServer) TableName() string { return "llm_instruction_row_servers" }

// ScopeTokenInstruction records which LLM instructions a scope token carries.
// CASCADE on both ends: token deletion removes the rows; instruction deletion
// removes the association (the token itself survives).
type ScopeTokenInstruction struct {
	TokenID       string `gorm:"type:char(36);not null;primaryKey" json:"token_id"`
	InstructionID string `gorm:"type:char(36);not null;primaryKey" json:"instruction_id"`
}

func (ScopeTokenInstruction) TableName() string { return "scope_token_instructions" }

// OAuth2ClientInstruction is the symmetric join for OAuth2 clients.
type OAuth2ClientInstruction struct {
	ClientID      string `gorm:"type:char(36);not null;primaryKey" json:"client_id"`
	InstructionID string `gorm:"type:char(36);not null;primaryKey" json:"instruction_id"`
}

func (OAuth2ClientInstruction) TableName() string { return "oauth2_client_instructions" }

// ScopeToken is the GORM model for the scope_tokens table.
type ScopeToken struct {
	ID          string     `gorm:"type:char(36);primaryKey" json:"id"`
	Name        string     `gorm:"type:varchar(255);not null" json:"name"`
	Description string     `gorm:"type:text" json:"description,omitempty"`
	TokenHash   string     `gorm:"type:varchar(64);not null;uniqueIndex:uq_token_hash" json:"-"`
	TokenPrefix string     `gorm:"type:varchar(16);not null" json:"token_prefix"`
	CreatedBy   string     `gorm:"type:varchar(255);not null;default:''" json:"created_by"`
	MCPCommand     string     `gorm:"type:varchar(64);not null;default:'npx'" json:"mcp_command"`
	ServerName     string     `gorm:"type:varchar(255);not null;default:''" json:"server_name"`
	AllowHTTP      bool       `gorm:"not null;default:false" json:"allow_http"`
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

	// Ringover ownership scope — same semantics as the Leexi filter above, but
	// Ringover identifies users with numeric integer IDs (not UUIDs), so the
	// JSON columns hold int arrays instead of UUID strings.
	RingoverFilterMode     string          `gorm:"type:varchar(16);not null;default:'none'" json:"ringover_filter_mode"`
	RingoverAllowedUserIDs json.RawMessage `gorm:"type:json" json:"ringover_allowed_user_ids,omitempty"`
	RingoverAllowedTeamIDs json.RawMessage `gorm:"type:json" json:"ringover_allowed_team_ids,omitempty"`

	// Zoho ownership scope — see ZohoFilterMode constants in api/token_dto.go.
	// "users":   ZohoAllowedEmails is authoritative (JSON array of email strings).
	// "creator": resolved single email from the token's CreatedBy at write time.
	// "none":    no filter (default).
	ZohoFilterMode    string          `gorm:"type:varchar(16);not null;default:'none'" json:"zoho_filter_mode"`
	ZohoAllowedEmails json.RawMessage `gorm:"type:json" json:"zoho_allowed_emails,omitempty"`

	// Associations
	Servers      []ScopeTokenServer      `gorm:"foreignKey:TokenID;constraint:OnDelete:CASCADE" json:"servers,omitempty"`
	Tools        []ScopeTokenTool        `gorm:"foreignKey:TokenID;constraint:OnDelete:CASCADE" json:"tools,omitempty"`
	Instructions []ScopeTokenInstruction `gorm:"foreignKey:TokenID;constraint:OnDelete:CASCADE" json:"instructions,omitempty"`
	BDDTables    []ScopeTokenBDDTable    `gorm:"foreignKey:TokenID;references:ID;constraint:OnDelete:CASCADE" json:"bdd_tables,omitempty"`
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

	// Ringover ownership scope — see ScopeToken for semantics; int arrays.
	RingoverFilterMode     string          `gorm:"type:varchar(16);not null;default:'none'" json:"ringover_filter_mode"`
	RingoverAllowedUserIDs json.RawMessage `gorm:"type:json" json:"ringover_allowed_user_ids,omitempty"`
	RingoverAllowedTeamIDs json.RawMessage `gorm:"type:json" json:"ringover_allowed_team_ids,omitempty"`

	// Zoho ownership scope — same semantics as ScopeToken.ZohoFilterMode.
	ZohoFilterMode    string          `gorm:"type:varchar(16);not null;default:'none'" json:"zoho_filter_mode"`
	ZohoAllowedEmails json.RawMessage `gorm:"type:json" json:"zoho_allowed_emails,omitempty"`

	// Associations
	Servers      []OAuth2ClientServer      `gorm:"foreignKey:ClientID;constraint:OnDelete:CASCADE" json:"servers,omitempty"`
	Tools        []OAuth2ClientTool        `gorm:"foreignKey:ClientID;constraint:OnDelete:CASCADE" json:"tools,omitempty"`
	Instructions []OAuth2ClientInstruction `gorm:"foreignKey:ClientID;constraint:OnDelete:CASCADE" json:"instructions,omitempty"`
	BDDTables    []OAuth2ClientBDDTable    `gorm:"foreignKey:ClientID;references:ID;constraint:OnDelete:CASCADE" json:"bdd_tables,omitempty"`
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
	IsAllowed   bool       `gorm:"not null;default:false" json:"is_allowed"`
	LoginCount  int        `gorm:"not null;default:0" json:"login_count"`
	LastLoginAt *time.Time `gorm:"type:datetime(3)" json:"last_login_at,omitempty"`
	CreatedAt   time.Time  `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt   time.Time  `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (GatewayUser) TableName() string { return "gateway_users" }

// SSOSession persists per-browser admin-UI sessions backed by an account-service
// OAuth2 access+refresh token pair. The opaque session ID lives in the HttpOnly
// gw_session cookie; access_token and refresh_token are AES-256-GCM ciphertext
// (encrypted with ENCRYPTION_KEY in internal/sso, never stored in plaintext).
type SSOSession struct {
	ID            string    `gorm:"type:varchar(64);primaryKey" json:"id"`
	UserID        uint64    `gorm:"not null;index:idx_sso_user" json:"user_id"`
	Sub           string    `gorm:"type:varchar(255);not null;index:idx_sso_sub" json:"sub"`
	Email         string    `gorm:"type:varchar(255);not null" json:"email"`
	AccessToken   []byte    `gorm:"type:varbinary(2048);not null" json:"-"`
	RefreshToken  []byte    `gorm:"type:varbinary(512);not null" json:"-"`
	AccessExp     time.Time `gorm:"type:datetime(3);not null" json:"access_exp"`
	RefreshExp    time.Time `gorm:"type:datetime(3);not null;index:idx_sso_refresh_exp" json:"refresh_exp"`
	CreatedAt     time.Time `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	LastSeenAt    time.Time `gorm:"type:datetime(3);not null" json:"last_seen_at"`
	UserAgent     string    `gorm:"type:varchar(255)" json:"user_agent,omitempty"`
	ClientIP      string    `gorm:"type:varchar(45)" json:"client_ip,omitempty"`
}

func (SSOSession) TableName() string { return "sso_sessions" }

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

// ── Install Guide Models ───────────────────────────────────────────

// InstallExecutor represents a package executor (npx, bunx, deno, uvx, docker).
type InstallExecutor struct {
	ID           uint64          `gorm:"primaryKey;autoIncrement" json:"id"`
	Slug         string          `gorm:"type:varchar(64);not null;uniqueIndex:uq_executor_slug" json:"slug"`
	Label        string          `gorm:"type:varchar(64);not null" json:"label"`
	Sub          string          `gorm:"type:varchar(64)" json:"sub"`
	Description  string          `gorm:"type:varchar(512)" json:"description"`
	Intro        string          `gorm:"type:text" json:"intro"`
	Icon         string          `gorm:"type:varchar(64)" json:"icon"`
	Color        string          `gorm:"type:varchar(255)" json:"color"`
	Install      json.RawMessage `gorm:"type:json" json:"install"`
	Verify       string          `gorm:"type:text" json:"verify"`
	McpConfig    string          `gorm:"type:text" json:"mcp_config"`
	CliAddCmd    string          `gorm:"type:text" json:"cli_add_cmd"`
	NoteLabel    string          `gorm:"type:varchar(64)" json:"note_label"`
	NoteText     string          `gorm:"type:text" json:"note_text"`
	NoteClass    string          `gorm:"type:varchar(255)" json:"note_class"`
	Content      json.RawMessage `gorm:"type:json" json:"content"`
	DisplayOrder int             `gorm:"not null;default:0;index:idx_executor_order" json:"display_order"`
	IsActive     bool            `gorm:"not null;default:true" json:"is_active"`
	CreatedAt    time.Time       `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt    time.Time       `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (InstallExecutor) TableName() string { return "install_executors" }

// InstallConfig represents an MCP configuration page (Claude Code, Claude Desktop, etc.).
type InstallConfig struct {
	ID           uint64          `gorm:"primaryKey;autoIncrement" json:"id"`
	Slug         string          `gorm:"type:varchar(64);not null;uniqueIndex:uq_config_slug" json:"slug"`
	Label        string          `gorm:"type:varchar(128);not null" json:"label"`
	Description  string          `gorm:"type:text" json:"description"`
	Icon         string          `gorm:"type:varchar(64)" json:"icon"`
	Color        string          `gorm:"type:varchar(255)" json:"color"`
	Content      json.RawMessage `gorm:"type:json" json:"content"`
	DisplayOrder int             `gorm:"not null;default:0;index:idx_config_order" json:"display_order"`
	IsActive     bool            `gorm:"not null;default:true" json:"is_active"`
	CreatedAt    time.Time       `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt    time.Time       `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (InstallConfig) TableName() string { return "install_configs" }

// UserGoogleToken stores per-admin Google OAuth2 tokens for Sheets API access.
type UserGoogleToken struct {
	ID           string     `gorm:"type:char(36);primaryKey" json:"id"`
	UserID       uint64     `gorm:"not null;uniqueIndex:uq_user_google" json:"user_id"`
	Email        string     `gorm:"type:varchar(255);not null" json:"email"` // Google account email
	AccessToken  []byte     `gorm:"type:blob;not null" json:"-"`            // Encrypted
	RefreshToken []byte     `gorm:"type:blob;not null" json:"-"`            // Encrypted
	TokenExpiry  *time.Time `gorm:"type:datetime(3)" json:"token_expiry,omitempty"`
	CreatedAt    time.Time  `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt    time.Time  `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (UserGoogleToken) TableName() string { return "user_google_tokens" }

// Template is the GORM model for the templates catalog (seed data).
// Rows are managed via migration, never via user input.
type Template struct {
	Slug             string          `gorm:"type:varchar(32);primaryKey" json:"slug"`
	Name             string          `gorm:"type:varchar(128);not null" json:"name"`
	Description      string          `gorm:"type:text" json:"description"`
	Icon             string          `gorm:"type:varchar(512);not null;default:''" json:"icon"`
	StdioCommand     string          `gorm:"type:varchar(256);not null" json:"stdio_command"`
	StdioArgs        json.RawMessage `gorm:"type:json" json:"stdio_args"`
	DefaultEnv       json.RawMessage `gorm:"type:json" json:"default_env"`
	RequiredExtraEnv json.RawMessage `gorm:"type:json" json:"required_extra_env"`
	ToolPrefix       string          `gorm:"type:varchar(64);not null;default:''" json:"tool_prefix"`
	Tags             json.RawMessage `gorm:"type:json" json:"tags"`
	IsActive         bool            `gorm:"not null;default:true;index:idx_template_active" json:"is_active"`
	// Kind distinguishes template categories:
	//   "stdio"      — spawns a subprocess via mcp-google-templates-runner (ga, gsc, ...)
	//   "http_batch" — batch-creates full HTTP mcp_servers via Google Sheets import
	// Frontend uses this to route clicks differently on the templates catalog.
	Kind string `gorm:"type:varchar(16);not null;default:'stdio';index:idx_template_kind" json:"kind"`
	CreatedAt        time.Time       `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt        time.Time       `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (Template) TableName() string { return "templates" }

// TemplateInstance is one admin-uploaded service-account JSON. Each row backs
// exactly one running mcp-proxy subprocess in the runner.
type TemplateInstance struct {
	ID                   string     `gorm:"type:char(36);primaryKey" json:"id"`
	TemplateSlug         string     `gorm:"type:varchar(32);not null;index:idx_instance_template" json:"template_slug"`
	// Template is the associated catalog row. The FK (on TemplateSlug →
	// templates.slug) is declared here so AutoMigrate emits it; the field itself
	// is not preloaded by default and not exposed in JSON.
	Template *Template `gorm:"foreignKey:TemplateSlug;references:Slug;constraint:OnDelete:RESTRICT" json:"-"`
	Name                 string     `gorm:"type:varchar(255);not null" json:"name"`
	EncryptedCredentials []byte     `gorm:"type:blob;not null" json:"-"`
	// CredentialsHash is SHA-256(plaintext) used by the runner to detect
	// credential changes during reconcile. Not unique — multiple instances may
	// share the same SA JSON under different names.
	CredentialsHash string          `gorm:"type:char(64);not null" json:"-"`
	ExtraEnv        json.RawMessage `gorm:"type:json" json:"extra_env,omitempty"`
	RunnerPort      *int            `gorm:"type:int" json:"runner_port,omitempty"`
	RunnerStatus    string          `gorm:"type:varchar(16);not null;default:'pending';index:idx_instance_status" json:"runner_status"`
	RunnerLastError string          `gorm:"type:text" json:"runner_last_error,omitempty"`
	// MCPServerID links to mcp_servers.id. No DB FK / cascade by design — delete
	// order is enforced in the repository so the runner-kill step cannot be skipped.
	MCPServerID string `gorm:"type:char(36);not null;uniqueIndex:uq_instance_mcp_server" json:"mcp_server_id"`
	CreatedBy            string     `gorm:"type:varchar(255);not null;default:''" json:"created_by"`
	CreatedAt            time.Time  `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt            time.Time  `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (TemplateInstance) TableName() string { return "template_instances" }

// ── Hellopro BDD "Used Tables" Models ──────────────────────────────
//
// These models drive the "Hellopro BDD tables" admin onglet. They store
// the subset of upstream catalog tables/fields that the gateway has been
// configured to surface to scope tokens and OAuth2 clients. The upstream
// catalog (see internal/bddcatalog) remains the source of truth for
// schema metadata; these tables only record what is in scope locally.

// BDDUsedTable is one row per (database, table) pair that has been
// activated for use through the gateway. UpstreamTableID mirrors the ID
// returned by the upstream catalog so we can refresh metadata.
type BDDUsedTable struct {
	ID              string          `gorm:"type:char(36);primaryKey"`
	DatabaseID      int             `gorm:"not null;index;uniqueIndex:uniq_db_table"`
	Name            string          `gorm:"column:table_name;type:varchar(128);not null;uniqueIndex:uniq_db_table"`
	UpstreamTableID int             `gorm:"index"`
	Description     string          `gorm:"type:text"`
	Rows            *int64          `gorm:"type:bigint"`
	PrimaryKey      string          `gorm:"type:varchar(255);not null;default:''"`
	DefaultOrderBy  string          `gorm:"type:varchar(255);not null;default:''"`
	Relations       json.RawMessage `gorm:"type:json"`
	Notes           string          `gorm:"type:text"`
	IsActive        bool            `gorm:"not null;default:true;index"`
	CreatedBy       string          `gorm:"type:varchar(255);not null;default:''"`
	CreatedAt       time.Time       `gorm:"type:datetime(3);autoCreateTime"`
	UpdatedAt       time.Time       `gorm:"type:datetime(3);autoUpdateTime"`
	Fields          []BDDUsedField  `gorm:"foreignKey:UsedTableID;constraint:OnDelete:CASCADE"`
}

func (BDDUsedTable) TableName() string { return "bdd_used_tables" }

// BDDUsedField is one row per (used_table, field) pair. Cascading delete
// from BDDUsedTable keeps the join consistent.
type BDDUsedField struct {
	ID              string    `gorm:"type:char(36);primaryKey"`
	UsedTableID     string    `gorm:"type:char(36);not null;uniqueIndex:uniq_table_field;index"`
	FieldName       string    `gorm:"type:varchar(128);not null;uniqueIndex:uniq_table_field"`
	UpstreamFieldID int       `gorm:"index"`
	FieldType       string    `gorm:"type:varchar(128);not null;default:''"`
	Description     string    `gorm:"type:text"`
	CreatedAt       time.Time `gorm:"type:datetime(3);autoCreateTime"`
	UpdatedAt       time.Time `gorm:"type:datetime(3);autoUpdateTime"`
}

func (BDDUsedField) TableName() string { return "bdd_used_fields" }

// BDDMeta is the singleton metadata header surfaced through /api/v1/bdd/used/meta
// and folded into the doc payload's _meta block. Always row id = 1.
type BDDMeta struct {
	ID          int       `gorm:"primaryKey;autoIncrement:false"`
	Description string    `gorm:"type:text"`
	Usage       string    `gorm:"type:text"`
	UpdatedAt   time.Time `gorm:"type:datetime(3);autoUpdateTime"`
	UpdatedBy   string    `gorm:"type:varchar(255);not null;default:''"`
}

func (BDDMeta) TableName() string { return "bdd_meta" }

// ScopeTokenBDDTable is the join table between scope_tokens and BDD used
// tables, mirroring the shape of ScopeTokenServer.
type ScopeTokenBDDTable struct {
	TokenID     string `gorm:"type:char(36);primaryKey"`
	UsedTableID string `gorm:"type:char(36);primaryKey"`
}

func (ScopeTokenBDDTable) TableName() string { return "scope_token_bdd_tables" }

// OAuth2ClientBDDTable is the equivalent join for OAuth2 clients.
type OAuth2ClientBDDTable struct {
	ClientID    string `gorm:"type:char(36);primaryKey"`
	UsedTableID string `gorm:"type:char(36);primaryKey"`
}

func (OAuth2ClientBDDTable) TableName() string { return "oauth2_client_bdd_tables" }

// ServerAuthorization grants a specific end-user (by email) full unfiltered
// access to a specific MCP server. When a row exists for (server_id, email),
// the gateway skips all filter-header injection (Leexi/Ringover/BDD) on
// outbound requests targeting that server — the backend receives only the
// static auth headers and treats the call as unrestricted.
//
// Primary key is (server_id, email). Insert/delete is the admin-side API.
type ServerAuthorization struct {
	ServerID  string    `gorm:"type:char(36);primaryKey" json:"server_id"`
	Email     string    `gorm:"type:varchar(255);primaryKey" json:"email"`
	CreatedBy string    `gorm:"type:varchar(255);not null;default:''" json:"created_by"`
	CreatedAt time.Time `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
}

func (ServerAuthorization) TableName() string { return "server_authorizations" }

// ZohoImport stores per-user and admin Zoho upstream URLs used by
// mcp-zoho-service for per-call routing. Rows are written by the gateway
// (sheet-import handler + admin REST endpoint) and read by the service.
//
// At most one row may have isAdmin=true AND isActive=true (enforced by the
// repo layer). Admin rows MUST have empty createdBy.
type ZohoImport struct {
	ID           string    `gorm:"type:char(36);primaryKey" json:"id"`
	Name         string    `gorm:"type:varchar(255);not null;default:''" json:"name"`
	URL          string    `gorm:"type:varchar(2048);not null" json:"url"`
	AuthHeaders  []byte    `gorm:"type:blob" json:"-"`
	CreatedBy    string    `gorm:"type:varchar(255);not null;default:'';index:idx_zoho_created_by" json:"created_by"`
	IsAdmin      bool      `gorm:"not null;default:false;index:idx_zoho_admin_active,priority:1" json:"is_admin"`
	IsActive     bool      `gorm:"not null;default:true;index:idx_zoho_admin_active,priority:2;index:idx_zoho_active" json:"is_active"`
	TemplateSlug string    `gorm:"type:varchar(64);not null;default:''" json:"template_slug"`
	CreatedAt    time.Time `gorm:"type:datetime(3);autoCreateTime" json:"created_at"`
	UpdatedAt    time.Time `gorm:"type:datetime(3);autoUpdateTime" json:"updated_at"`
}

func (ZohoImport) TableName() string { return "zoho_imports" }
