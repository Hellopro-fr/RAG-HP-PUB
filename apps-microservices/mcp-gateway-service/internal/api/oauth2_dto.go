package api

// CreateOAuth2ClientRequest is the body for POST /api/v1/oauth2/clients.
type CreateOAuth2ClientRequest struct {
	Name           string                `json:"name"`
	Description    string                `json:"description,omitempty"`
	ServerIDs      []string              `json:"server_ids"`
	ServerTools    []ServerToolSelection `json:"server_tools,omitempty"` // optional per-server tool selection
	AccessTokenTTL *int                  `json:"access_token_ttl,omitempty"` // seconds, default 3600
	ExpiresAt      *string               `json:"expires_at,omitempty"`       // RFC3339
	RedirectURIs   []string              `json:"redirect_uris,omitempty"`
	GrantTypes     []string              `json:"grant_types,omitempty"`
	LeexiFilter    *LeexiFilterDTO       `json:"leexi_filter,omitempty"` // shares semantics with ScopeToken.LeexiFilter
}

// CreateOAuth2ClientResponse is returned once on creation (includes raw client_secret).
type CreateOAuth2ClientResponse struct {
	ID             string                `json:"id"` // = client_id
	Name           string                `json:"name"`
	Description    string                `json:"description,omitempty"`
	ClientSecret   string                `json:"client_secret"` // shown ONCE
	SecretPrefix   string                `json:"secret_prefix"` // "mcp_oauth_xxxxxx..." for display
	ServerIDs      []string              `json:"server_ids"`
	ServerTools    []ServerToolSelection `json:"server_tools,omitempty"`
	AccessTokenTTL int                   `json:"access_token_ttl"`
	IsActive             bool                  `json:"is_active"`
	CreatedAt            string                `json:"created_at"`
	ExpiresAt            *string               `json:"expires_at,omitempty"`
	RedirectURIs         []string              `json:"redirect_uris,omitempty"`
	GrantTypes           []string              `json:"grant_types,omitempty"`
	DynamicallyRegistered bool                 `json:"dynamically_registered"`
	LeexiFilter          *LeexiFilterDTO       `json:"leexi_filter,omitempty"`
}

// OAuth2ClientResponse is the standard client response (no raw secret).
type OAuth2ClientResponse struct {
	ID             string                `json:"id"` // = client_id
	Name           string                `json:"name"`
	Description    string                `json:"description,omitempty"`
	ClientSecret   string                `json:"client_secret,omitempty"` // decrypted (if available)
	SecretPrefix   string                `json:"secret_prefix"`
	ServerIDs      []string              `json:"server_ids"`
	ServerTools    []ServerToolSelection `json:"server_tools,omitempty"`
	AccessTokenTTL int                   `json:"access_token_ttl"`
	IsActive       bool                  `json:"is_active"`
	CreatedBy      string                `json:"created_by,omitempty"`
	CreatedAt            string                `json:"created_at"`
	UpdatedAt            string                `json:"updated_at"`
	ExpiresAt            *string               `json:"expires_at,omitempty"`
	RedirectURIs         []string              `json:"redirect_uris,omitempty"`
	GrantTypes           []string              `json:"grant_types,omitempty"`
	DynamicallyRegistered bool                 `json:"dynamically_registered"`
	LeexiFilter          *LeexiFilterDTO       `json:"leexi_filter,omitempty"`
}

// UpdateOAuth2ClientRequest is the body for PUT /api/v1/oauth2/clients/{id}.
type UpdateOAuth2ClientRequest struct {
	Name         *string               `json:"name,omitempty"`
	Description  *string               `json:"description,omitempty"`
	ServerIDs    []string              `json:"server_ids,omitempty"`
	ServerTools  []ServerToolSelection `json:"server_tools,omitempty"`
	RedirectURIs []string              `json:"redirect_uris,omitempty"`
	GrantTypes   []string              `json:"grant_types,omitempty"`
	LeexiFilter  *LeexiFilterDTO       `json:"leexi_filter,omitempty"`
}
