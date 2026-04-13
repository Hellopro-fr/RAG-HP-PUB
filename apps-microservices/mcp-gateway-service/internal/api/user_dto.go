package api

// UpdateUserRoleRequest is the request body for updating a user's role.
type UpdateUserRoleRequest struct {
	Role string `json:"role"`
}

// UserResponse is the JSON representation of a GatewayUser.
type UserResponse struct {
	ID          uint64  `json:"id"`
	Email       string  `json:"email"`
	DisplayName string  `json:"display_name"`
	Role        string  `json:"role"`
	LoginCount  int     `json:"login_count"`
	LastLoginAt *string `json:"last_login_at,omitempty"`
	CreatedAt   string  `json:"created_at"`
}
