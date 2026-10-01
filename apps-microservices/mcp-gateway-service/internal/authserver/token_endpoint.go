package authserver

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"mcp-gateway/internal/db"
	oauth2pkg "mcp-gateway/internal/oauth2"
)

// TokenResponse is the OAuth2 token response (RFC 6749 Section 5.1).
type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	TokenType    string `json:"token_type"`
	ExpiresIn    int    `json:"expires_in"`
	RefreshToken string `json:"refresh_token,omitempty"`
}

// HandleToken handles POST /token.
func (s *AuthServer) HandleToken(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeOAuth2Error(w, http.StatusMethodNotAllowed, "invalid_request", "method not allowed")
		return
	}

	r.ParseForm()
	grantType := r.FormValue("grant_type")

	switch grantType {
	case "authorization_code":
		s.handleAuthCodeExchange(w, r)
	case "client_credentials":
		s.handleClientCredentials(w, r)
	case "refresh_token":
		s.handleRefreshToken(w, r)
	default:
		writeOAuth2Error(w, http.StatusBadRequest, "unsupported_grant_type", fmt.Sprintf("grant_type '%s' is not supported", grantType))
	}
}

func (s *AuthServer) handleAuthCodeExchange(w http.ResponseWriter, r *http.Request) {
	code := r.FormValue("code")
	codeVerifier := r.FormValue("code_verifier")
	clientID := r.FormValue("client_id")
	redirectURI := r.FormValue("redirect_uri")

	if code == "" || codeVerifier == "" || clientID == "" || redirectURI == "" {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_request", "code, code_verifier, client_id, and redirect_uri are required")
		return
	}

	codeHash := HashAuthCode(code)
	authCode, err := s.authCodeRepo.FindByHash(codeHash)
	if err != nil {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "invalid authorization code")
		return
	}

	if time.Now().After(authCode.ExpiresAt) {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "authorization code has expired")
		return
	}

	// Atomic single-use enforcement: MarkUsed uses WHERE used_at IS NULL + RowsAffected check,
	// preventing TOCTOU race conditions with concurrent requests.
	if err := s.authCodeRepo.MarkUsed(codeHash); err != nil {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "authorization code already used")
		return
	}

	if authCode.ClientID != clientID {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "client_id mismatch")
		return
	}

	if authCode.RedirectURI != redirectURI {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "redirect_uri mismatch")
		return
	}

	if err := VerifyPKCE(authCode.CodeChallenge, codeVerifier); err != nil {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "PKCE verification failed")
		return
	}

	client, err := s.oauth2Repo.GetByID(clientID)
	if err != nil || !client.IsActive {
		writeOAuth2Error(w, http.StatusUnauthorized, "invalid_client", "client not found or inactive")
		return
	}

	accessToken, expiresIn, err := oauth2pkg.IssueAccessToken(s.jwtSecret, clientID, authCode.UserEmail, client.AccessTokenTTL)
	if err != nil {
		writeOAuth2Error(w, http.StatusInternalServerError, "server_error", "failed to issue access token")
		return
	}

	refreshRaw, refreshHash, err := generateRefreshToken()
	if err != nil {
		writeOAuth2Error(w, http.StatusInternalServerError, "server_error", "failed to generate refresh token")
		return
	}

	refreshTTL := s.refreshTTL
	if refreshTTL <= 0 {
		refreshTTL = 30 * 24 * 3600
	}
	if err := s.refreshRepo.Create(&db.OAuth2RefreshToken{
		TokenHash: refreshHash,
		ClientID:  clientID,
		UserEmail: authCode.UserEmail,
		Scope:     authCode.Scope,
		ExpiresAt: time.Now().Add(time.Duration(refreshTTL) * time.Second),
	}); err != nil {
		log.Printf("[authserver] failed to store refresh token: %v", err)
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Pragma", "no-cache")
	json.NewEncoder(w).Encode(TokenResponse{
		AccessToken:  accessToken,
		TokenType:    "Bearer",
		ExpiresIn:    expiresIn,
		RefreshToken: refreshRaw,
	})
}

func (s *AuthServer) handleClientCredentials(w http.ResponseWriter, r *http.Request) {
	clientID, clientSecret, ok := extractClientCredentials(r)
	if !ok {
		writeOAuth2Error(w, http.StatusUnauthorized, "invalid_client", "missing client credentials")
		return
	}

	hash := oauth2pkg.HashSecret(clientSecret)
	client, err := s.oauth2Repo.FindBySecretHash(hash)
	if err != nil {
		writeOAuth2Error(w, http.StatusUnauthorized, "invalid_client", "invalid client credentials")
		return
	}
	if client.ID != clientID {
		writeOAuth2Error(w, http.StatusUnauthorized, "invalid_client", "client_id mismatch")
		return
	}
	if !client.IsActive {
		writeOAuth2Error(w, http.StatusUnauthorized, "invalid_client", "client is revoked")
		return
	}
	if client.ExpiresAt != nil && client.ExpiresAt.Before(time.Now()) {
		writeOAuth2Error(w, http.StatusUnauthorized, "invalid_client", "client has expired")
		return
	}

	// client_credentials carries no end-user identity — pass "" so downstream
	// "self"-mode filters fail closed instead of leaking another user's data.
	accessToken, expiresIn, err := oauth2pkg.IssueAccessToken(s.jwtSecret, client.ID, "", client.AccessTokenTTL)
	if err != nil {
		writeOAuth2Error(w, http.StatusInternalServerError, "server_error", "failed to issue access token")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Pragma", "no-cache")
	json.NewEncoder(w).Encode(TokenResponse{
		AccessToken: accessToken,
		TokenType:   "Bearer",
		ExpiresIn:   expiresIn,
	})
}

func (s *AuthServer) handleRefreshToken(w http.ResponseWriter, r *http.Request) {
	refreshToken := r.FormValue("refresh_token")
	clientID := r.FormValue("client_id")
	if refreshToken == "" || clientID == "" {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_request", "refresh_token and client_id are required")
		return
	}

	hash := hashRefreshToken(refreshToken)
	stored, err := s.refreshRepo.FindByHash(hash)
	if err != nil {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "invalid refresh token")
		return
	}
	if stored.ClientID != clientID {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "client_id mismatch")
		return
	}
	if stored.RevokedAt != nil {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "refresh token has been revoked")
		return
	}
	if time.Now().After(stored.ExpiresAt) {
		writeOAuth2Error(w, http.StatusBadRequest, "invalid_grant", "refresh token has expired")
		return
	}

	// Rotation: revoke old token before issuing new one.
	s.refreshRepo.Revoke(hash)

	client, err := s.oauth2Repo.GetByID(clientID)
	if err != nil || !client.IsActive {
		writeOAuth2Error(w, http.StatusUnauthorized, "invalid_client", "client not found or inactive")
		return
	}

	accessToken, expiresIn, err := oauth2pkg.IssueAccessToken(s.jwtSecret, clientID, stored.UserEmail, client.AccessTokenTTL)
	if err != nil {
		writeOAuth2Error(w, http.StatusInternalServerError, "server_error", "failed to issue access token")
		return
	}

	newRefreshRaw, newRefreshHash, err := generateRefreshToken()
	if err != nil {
		writeOAuth2Error(w, http.StatusInternalServerError, "server_error", "failed to generate refresh token")
		return
	}

	refreshTTL := s.refreshTTL
	if refreshTTL <= 0 {
		refreshTTL = 30 * 24 * 3600
	}
	s.refreshRepo.Create(&db.OAuth2RefreshToken{
		TokenHash: newRefreshHash,
		ClientID:  clientID,
		UserEmail: stored.UserEmail,
		Scope:     stored.Scope,
		ExpiresAt: time.Now().Add(time.Duration(refreshTTL) * time.Second),
	})

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Pragma", "no-cache")
	json.NewEncoder(w).Encode(TokenResponse{
		AccessToken:  accessToken,
		TokenType:    "Bearer",
		ExpiresIn:    expiresIn,
		RefreshToken: newRefreshRaw,
	})
}

// extractClientCredentials tries Basic auth first, then form params.
func extractClientCredentials(r *http.Request) (clientID, clientSecret string, ok bool) {
	authHeader := r.Header.Get("Authorization")
	if strings.HasPrefix(authHeader, "Basic ") {
		decoded, err := base64.StdEncoding.DecodeString(authHeader[6:])
		if err == nil {
			parts := strings.SplitN(string(decoded), ":", 2)
			if len(parts) == 2 && parts[0] != "" && parts[1] != "" {
				return parts[0], parts[1], true
			}
		}
	}
	clientID = r.FormValue("client_id")
	clientSecret = r.FormValue("client_secret")
	if clientID != "" && clientSecret != "" {
		return clientID, clientSecret, true
	}
	return "", "", false
}

func generateRefreshToken() (raw, hash string, err error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", "", err
	}
	raw = hex.EncodeToString(b)
	h := sha256.Sum256([]byte(raw))
	return raw, hex.EncodeToString(h[:]), nil
}

func hashRefreshToken(raw string) string {
	h := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(h[:])
}
