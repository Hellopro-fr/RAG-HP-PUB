package authserver

import (
	"encoding/base64"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/hellopro/account-service/internal/db"
)

type fakeConsumeAuthCode struct {
	stored *db.OAuth2AuthorizationCode
}

func (f *fakeConsumeAuthCode) ConsumeUnused(hash string) (*db.OAuth2AuthorizationCode, error) {
	if f.stored == nil || f.stored.CodeHash != hash {
		return nil, fakeNotFound{}
	}
	if f.stored.ExpiresAt.Before(time.Now()) {
		return nil, fakeNotFound{}
	}
	return f.stored, nil
}

type fakeNotFound struct{}

func (fakeNotFound) Error() string { return "invalid_grant" }

type fakeRefreshSink struct {
	created *db.OAuth2RefreshToken
}

func (f *fakeRefreshSink) Create(t *db.OAuth2RefreshToken) error {
	f.created = t
	return nil
}

func TestToken_AuthCodeGrant_Success(t *testing.T) {
	verifier, challenge := makeVerifierAndChallenge()
	plainSecret := "client-secret"
	cipher := []byte("ENC:" + plainSecret)

	cli := &db.OAuth2Client{
		ClientID:          "x",
		ClientSecretEnc:   cipher,
		TokenTTLSeconds:   60,
		RefreshTTLSeconds: 86400,
	}
	stored := &db.OAuth2AuthorizationCode{
		CodeHash:      HashAuthCode("rawcode"),
		ClientID:      "x",
		UserEmail:     "alice@example.com",
		RedirectURI:   "https://x/cb",
		CodeChallenge: challenge,
		ExpiresAt:     time.Now().Add(5 * time.Minute),
	}

	te := NewTokenEndpoint(TokenEndpointDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeConsumeAuthCode{stored: stored},
		RefreshRepo:  &fakeRefreshSink{},
		Decrypt:      func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:    "s",
		Issuer:       "https://account.test",
	})

	form := url.Values{
		"grant_type":    {"authorization_code"},
		"code":          {"rawcode"},
		"redirect_uri":  {"https://x/cb"},
		"code_verifier": {verifier},
	}
	r := httptest.NewRequest(http.MethodPost, "/token", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plainSecret)))
	w := httptest.NewRecorder()
	te.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["token_type"] != "Bearer" {
		t.Errorf("token_type=%v", body["token_type"])
	}
	if body["access_token"].(string) == "" {
		t.Error("missing access_token")
	}
	if body["refresh_token"].(string) == "" {
		t.Error("missing refresh_token")
	}
	if body["expires_in"].(float64) != 60 {
		t.Errorf("expires_in=%v", body["expires_in"])
	}
}

func TestToken_AuthCodeGrant_PKCEMismatch(t *testing.T) {
	_, challenge := makeVerifierAndChallenge()
	plainSecret := "s"
	cipher := []byte("ENC:" + plainSecret)
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: cipher, TokenTTLSeconds: 60}
	stored := &db.OAuth2AuthorizationCode{
		CodeHash:      HashAuthCode("rawcode"),
		ClientID:      "x",
		RedirectURI:   "https://x/cb",
		CodeChallenge: challenge,
		ExpiresAt:     time.Now().Add(5 * time.Minute),
	}
	te := NewTokenEndpoint(TokenEndpointDeps{
		ClientRepo:   &fakeClientRepo{c: cli},
		AuthCodeRepo: &fakeConsumeAuthCode{stored: stored},
		RefreshRepo:  &fakeRefreshSink{},
		Decrypt:      func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:    "s",
		Issuer:       "https://account.test",
	})
	form := url.Values{
		"grant_type":    {"authorization_code"},
		"code":          {"rawcode"},
		"redirect_uri":  {"https://x/cb"},
		"code_verifier": {"WRONG-VERIFIER"},
	}
	r := httptest.NewRequest(http.MethodPost, "/token", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plainSecret)))
	w := httptest.NewRecorder()
	te.ServeHTTP(w, r)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("Code=%d", w.Code)
	}
}
