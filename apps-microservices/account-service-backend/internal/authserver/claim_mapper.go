package authserver

import "encoding/json"

type UserClaimSource struct {
	Email       string
	DisplayName string
	IsAdmin     bool
}

// ApplyClaimMappings produces a map suitable for auth.Claims.Custom. It always
// emits sub/email/name defaults. Custom mapping is JSON {user_field: jwt_claim}.
func ApplyClaimMappings(rawMapping string, src UserClaimSource) map[string]interface{} {
	out := map[string]interface{}{
		"sub":   src.Email,
		"email": src.Email,
		"name":  src.DisplayName,
	}
	if rawMapping == "" {
		return out
	}
	var mapping map[string]string
	if err := json.Unmarshal([]byte(rawMapping), &mapping); err != nil {
		return out
	}
	for userField, claim := range mapping {
		switch userField {
		case "email":
			out[claim] = src.Email
		case "display_name":
			out[claim] = src.DisplayName
		case "is_admin":
			out[claim] = src.IsAdmin
		}
	}
	return out
}
