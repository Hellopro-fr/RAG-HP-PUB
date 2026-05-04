package authserver

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"time"

	"github.com/google/uuid"
	"github.com/hellopro/account-service/internal/auth"
	"github.com/hellopro/account-service/internal/db"
)

type AuthCodeConsumer interface {
	ConsumeUnused(hash string) (*db.OAuth2AuthorizationCode, error)
}

type RefreshSink interface {
	Create(t *db.OAuth2RefreshToken) error
}

type RefreshRotator interface {
	Rotate(oldHash, newHash string) (*db.OAuth2RefreshToken, error)
	FindByHash(hash string) (*db.OAuth2RefreshToken, error)
}

type DecryptFunc func([]byte) ([]byte, error)

type TokenEndpointDeps struct {
	ClientRepo     ClientRepo
	AuthCodeRepo   AuthCodeConsumer
	RefreshRepo    RefreshSink
	RefreshRotator RefreshRotator
	Decrypt        DecryptFunc
	JWTSecret      string
	Issuer         string
}

type TokenEndpoint struct {
	deps TokenEndpointDeps
}

func NewTokenEndpoint(d TokenEndpointDeps) *TokenEndpoint {
	return &TokenEndpoint{deps: d}
}

func (t *TokenEndpoint) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	_ = r.ParseForm()
	switch r.FormValue("grant_type") {
	case "authorization_code":
		t.handleAuthCode(w, r)
	case "refresh_token":
		t.handleRefresh(w, r)
	default:
		writeOAuthErr(w, http.StatusBadRequest, "unsupported_grant_type", "")
	}
}

func (t *TokenEndpoint) handleAuthCode(w http.ResponseWriter, r *http.Request) {
	clientID, secret, ok := extractClientAuth(r)
	if !ok {
		writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "missing client credentials")
		return
	}
	cli, err := t.deps.ClientRepo.GetByClientID(clientID)
	if err != nil || !t.checkSecret(cli, secret) {
		writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "bad credentials")
		return
	}

	rawCode := r.FormValue("code")
	verifier := r.FormValue("code_verifier")
	redirect := r.FormValue("redirect_uri")
	if rawCode == "" || verifier == "" {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "missing fields")
		return
	}
	stored, err := t.deps.AuthCodeRepo.ConsumeUnused(HashAuthCode(rawCode))
	if err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "code invalid or used")
		return
	}
	if stored.ClientID != clientID {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "client mismatch")
		return
	}
	if stored.RedirectURI != redirect {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "redirect_uri mismatch")
		return
	}
	if !VerifyPKCES256(verifier, stored.CodeChallenge) {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "PKCE mismatch")
		return
	}

	sid := uuid.New().String()
	mappings := ""
	if cli.ClaimMappings != nil {
		mappings = *cli.ClaimMappings
	}
	custom := ApplyClaimMappings(mappings, UserClaimSource{
		Email: stored.UserEmail,
	})

	tokenTTL := cli.TokenTTLSeconds
	if tokenTTL <= 0 {
		tokenTTL = 60
	}
	refreshTTL := cli.RefreshTTLSeconds
	if refreshTTL <= 0 {
		refreshTTL = 2592000
	}

	claims := auth.Claims{
		Sub:    stored.UserEmail,
		Email:  stored.UserEmail,
		Aud:    cli.ClientID,
		Iss:    t.deps.Issuer,
		Sid:    sid,
		Iat:    time.Now().Unix(),
		Exp:    time.Now().Add(time.Duration(tokenTTL) * time.Second).Unix(),
		Custom: custom,
	}
	access, err := auth.SignJWT(t.deps.JWTSecret, claims)
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "sign failed")
		return
	}

	rawRef, _, err := GenerateAuthCode()
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "rand failed")
		return
	}
	refHash := HashRefreshToken(rawRef)
	if err := t.deps.RefreshRepo.Create(&db.OAuth2RefreshToken{
		ID:        uuid.New().String(),
		TokenHash: refHash,
		SID:       sid,
		ClientID:  cli.ClientID,
		UserEmail: stored.UserEmail,
		ExpiresAt: time.Now().Add(time.Duration(refreshTTL) * time.Second),
	}); err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "refresh persist failed")
		return
	}

	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"access_token":  access,
		"token_type":    "Bearer",
		"expires_in":    tokenTTL,
		"refresh_token": rawRef,
		"scope":         stored.Scope,
	})
}

func (t *TokenEndpoint) handleRefresh(w http.ResponseWriter, r *http.Request) {
	clientID, secret, ok := extractClientAuth(r)
	if !ok {
		writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "missing client credentials")
		return
	}
	cli, err := t.deps.ClientRepo.GetByClientID(clientID)
	if err != nil || !t.checkSecret(cli, secret) {
		writeOAuthErr(w, http.StatusUnauthorized, "invalid_client", "bad credentials")
		return
	}
	raw := r.FormValue("refresh_token")
	if raw == "" {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_request", "missing refresh_token")
		return
	}
	oldHash := HashRefreshToken(raw)
	newRaw, _, err := GenerateAuthCode()
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "rand failed")
		return
	}
	newHash := HashRefreshToken(newRaw)
	rotated, err := t.deps.RefreshRotator.Rotate(oldHash, newHash)
	if err != nil {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "refresh invalid")
		return
	}
	if rotated.ClientID != clientID {
		writeOAuthErr(w, http.StatusBadRequest, "invalid_grant", "client mismatch")
		return
	}
	tokenTTL := cli.TokenTTLSeconds
	if tokenTTL <= 0 {
		tokenTTL = 60
	}
	mappings := ""
	if cli.ClaimMappings != nil {
		mappings = *cli.ClaimMappings
	}
	custom := ApplyClaimMappings(mappings, UserClaimSource{Email: rotated.UserEmail})
	claims := auth.Claims{
		Sub:    rotated.UserEmail,
		Email:  rotated.UserEmail,
		Aud:    cli.ClientID,
		Iss:    t.deps.Issuer,
		Sid:    rotated.SID,
		Iat:    time.Now().Unix(),
		Exp:    time.Now().Add(time.Duration(tokenTTL) * time.Second).Unix(),
		Custom: custom,
	}
	access, err := auth.SignJWT(t.deps.JWTSecret, claims)
	if err != nil {
		writeOAuthErr(w, http.StatusInternalServerError, "server_error", "sign failed")
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]interface{}{
		"access_token":  access,
		"token_type":    "Bearer",
		"expires_in":    tokenTTL,
		"refresh_token": newRaw,
	})
}

func (t *TokenEndpoint) checkSecret(c *db.OAuth2Client, presented string) bool {
	if c == nil || t.deps.Decrypt == nil {
		return false
	}
	plain, err := t.deps.Decrypt(c.ClientSecretEnc)
	if err != nil {
		return false
	}
	return subtle.ConstantTimeCompare(plain, []byte(presented)) == 1
}

func extractClientAuth(r *http.Request) (clientID, secret string, ok bool) {
	if user, pass, basicOK := r.BasicAuth(); basicOK {
		return user, pass, true
	}
	id := r.FormValue("client_id")
	sec := r.FormValue("client_secret")
	if id == "" || sec == "" {
		return "", "", false
	}
	return id, sec, true
}

// HashRefreshToken is the canonical hash for refresh tokens, used by both the
// repo and the introspection endpoint.
func HashRefreshToken(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}
