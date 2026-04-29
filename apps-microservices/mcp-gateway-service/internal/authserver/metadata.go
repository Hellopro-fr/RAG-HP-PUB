package authserver

import (
	"encoding/json"
	"net/http"
)

// MetadataResponse is the OAuth2 Authorization Server Metadata (RFC 8414).
type MetadataResponse struct {
	Issuer                            string   `json:"issuer"`
	AuthorizationEndpoint             string   `json:"authorization_endpoint"`
	TokenEndpoint                     string   `json:"token_endpoint"`
	RegistrationEndpoint              string   `json:"registration_endpoint"`
	TokenEndpointAuthMethodsSupported []string `json:"token_endpoint_auth_methods_supported"`
	GrantTypesSupported               []string `json:"grant_types_supported"`
	ResponseTypesSupported            []string `json:"response_types_supported"`
	CodeChallengeMethodsSupported     []string `json:"code_challenge_methods_supported"`
}

// HandleMetadata handles GET /.well-known/oauth-authorization-server (RFC 8414).
func (s *AuthServer) HandleMetadata(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.Header().Set("Allow", "GET")
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}

	issuer := s.publicURL
	if issuer == "" {
		scheme := "http"
		if r.TLS != nil {
			scheme = "https"
		}
		issuer = scheme + "://" + r.Host
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(MetadataResponse{
		Issuer:                            issuer,
		AuthorizationEndpoint:             issuer + "/authorize",
		TokenEndpoint:                     issuer + "/token",
		RegistrationEndpoint:              issuer + "/register",
		TokenEndpointAuthMethodsSupported: []string{"client_secret_basic"},
		GrantTypesSupported:               []string{"authorization_code", "client_credentials"},
		ResponseTypesSupported:            []string{"code"},
		CodeChallengeMethodsSupported:     []string{"S256"},
	})
}
