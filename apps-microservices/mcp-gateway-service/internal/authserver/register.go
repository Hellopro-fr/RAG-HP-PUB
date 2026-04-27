package authserver

import (
	"encoding/json"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/hellopro/mcp-gateway/internal/db"
	oauth2pkg "github.com/hellopro/mcp-gateway/internal/oauth2"
)

// RegistrationRequest is the RFC 7591 client registration request.
type RegistrationRequest struct {
	ClientName              string   `json:"client_name"`
	RedirectURIs            []string `json:"redirect_uris"`
	GrantTypes              []string `json:"grant_types"`
	ResponseTypes           []string `json:"response_types"`
	TokenEndpointAuthMethod string   `json:"token_endpoint_auth_method"`
}

// RegistrationResponse is the RFC 7591 client registration response.
type RegistrationResponse struct {
	ClientID                string   `json:"client_id"`
	ClientSecret            string   `json:"client_secret,omitempty"`
	ClientName              string   `json:"client_name"`
	RedirectURIs            []string `json:"redirect_uris"`
	GrantTypes              []string `json:"grant_types"`
	TokenEndpointAuthMethod string   `json:"token_endpoint_auth_method"`
	ClientIDIssuedAt        int64    `json:"client_id_issued_at"`
	ClientSecretExpiresAt   int64    `json:"client_secret_expires_at"`
}

// HandleRegister handles POST /register (RFC 7591 Dynamic Client Registration).
func (s *AuthServer) HandleRegister(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeOAuth2Error(w, http.StatusMethodNotAllowed, "invalid_request", "method not allowed")
		return
	}

	var req RegistrationRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_client_metadata", "invalid JSON body")
		return
	}

	if req.ClientName == "" {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_client_metadata", "client_name is required")
		return
	}

	for _, uri := range req.RedirectURIs {
		if !isValidRedirectURI(uri) {
			writeOAuth2Error(w, http.StatusBadRequest, "invalid_redirect_uri", "redirect_uri must be HTTPS or localhost")
			return
		}
	}

	if len(req.GrantTypes) == 0 {
		req.GrantTypes = []string{"authorization_code"}
	}
	if req.TokenEndpointAuthMethod == "" {
		req.TokenEndpointAuthMethod = "client_secret_basic"
	}

	clientID, clientSecret, secretHash, secretPrefix, err := oauth2pkg.GenerateCredentials()
	if err != nil {
		log.Printf("[authserver] failed to generate credentials: %v", err)
		writeOAuth2Error(w, http.StatusInternalServerError, "server_error", "failed to generate credentials")
		return
	}

	redirectURIsStr := jsonMarshalString(req.RedirectURIs)
	grantTypesStr := jsonMarshalString(req.GrantTypes)

	client := db.OAuth2Client{
		ID:                    clientID,
		Name:                  req.ClientName,
		SecretHash:            secretHash,
		SecretPrefix:          secretPrefix,
		EncryptedSecret:       []byte(clientSecret),
		AccessTokenTTL:        3600,
		IsActive:              true,
		RedirectURIs:          &redirectURIsStr,
		GrantTypes:            &grantTypesStr,
		TokenAuthMethod:       req.TokenEndpointAuthMethod,
		DynamicallyRegistered: true,
		CreatedBy:             "",
	}

	if err := s.oauth2Repo.Create(&client); err != nil {
		log.Printf("[authserver] failed to register client: %v", err)
		writeOAuth2Error(w, http.StatusInternalServerError, "server_error", "failed to register client")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(http.StatusCreated)
	json.NewEncoder(w).Encode(RegistrationResponse{
		ClientID:                clientID,
		ClientSecret:            clientSecret,
		ClientName:              req.ClientName,
		RedirectURIs:            req.RedirectURIs,
		GrantTypes:              req.GrantTypes,
		TokenEndpointAuthMethod: req.TokenEndpointAuthMethod,
		ClientIDIssuedAt:        time.Now().Unix(),
		ClientSecretExpiresAt:   0,
	})
}

// isValidRedirectURI checks that URI is HTTPS or localhost.
func isValidRedirectURI(uri string) bool {
	if strings.HasPrefix(uri, "https://") {
		return true
	}
	if strings.HasPrefix(uri, "http://localhost") || strings.HasPrefix(uri, "http://127.0.0.1") || strings.HasPrefix(uri, "http://[::1]") {
		return true
	}
	return false
}

func writeOAuth2Error(w http.ResponseWriter, status int, errCode, description string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]string{
		"error":             errCode,
		"error_description": description,
	})
}

// jsonMarshalString marshals a value to a JSON string.
func jsonMarshalString(v interface{}) string {
	b, _ := json.Marshal(v)
	return string(b)
}

// strPtr returns a pointer to the given string. Returns nil for empty strings.
func strPtr(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

// derefStr safely dereferences a *string, returning "" if nil.
func derefStr(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}
