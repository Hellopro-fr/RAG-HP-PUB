package api

// CreateTokenRequest is the body for POST /api/v1/tokens.
type CreateTokenRequest struct {
	Name        string   `json:"name"`
	Description string   `json:"description,omitempty"`
	ServerIDs   []string `json:"server_ids"`
	ExpiresAt   *string  `json:"expires_at,omitempty"` // RFC3339
}

// CreateTokenResponse is returned once on creation (includes raw token).
type CreateTokenResponse struct {
	ID          string   `json:"id"`
	Name        string   `json:"name"`
	Description string   `json:"description,omitempty"`
	Token       string   `json:"token"`        // raw token, shown ONCE
	TokenPrefix string   `json:"token_prefix"`  // "mcp_xxxx..." for display
	ServerIDs   []string `json:"server_ids"`
	IsActive    bool     `json:"is_active"`
	CreatedAt   string   `json:"created_at"`
	ExpiresAt   *string  `json:"expires_at,omitempty"`
}

// TokenResponse is the standard token response (no raw token).
type TokenResponse struct {
	ID          string   `json:"id"`
	Name        string   `json:"name"`
	Description string   `json:"description,omitempty"`
	TokenPrefix string   `json:"token_prefix"`
	ServerIDs   []string `json:"server_ids"`
	IsActive    bool     `json:"is_active"`
	CreatedBy   string   `json:"created_by,omitempty"`
	CreatedAt   string   `json:"created_at"`
	UpdatedAt   string   `json:"updated_at"`
	ExpiresAt   *string  `json:"expires_at,omitempty"`
}

// UpdateTokenRequest is the body for PUT /api/v1/tokens/{id}.
type UpdateTokenRequest struct {
	Name        *string  `json:"name,omitempty"`
	Description *string  `json:"description,omitempty"`
	ServerIDs   []string `json:"server_ids,omitempty"`
}

