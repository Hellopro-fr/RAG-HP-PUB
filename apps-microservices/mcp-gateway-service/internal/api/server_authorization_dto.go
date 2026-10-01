package api

// CreateServerAuthorizationRequest is the body for POST /api/v1/server-authorizations.
type CreateServerAuthorizationRequest struct {
	ServerID string `json:"server_id"`
	Email    string `json:"email"`
}

// ServerAuthorizationResponse is the wire shape returned by GET / POST.
type ServerAuthorizationResponse struct {
	ServerID  string `json:"server_id"`
	Email     string `json:"email"`
	CreatedBy string `json:"created_by,omitempty"`
	CreatedAt string `json:"created_at"`
}
