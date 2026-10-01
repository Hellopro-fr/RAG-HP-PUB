package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"account-service/internal/db"
)

type fakeNameLookup struct {
	c *db.OAuth2Client
}

func (f *fakeNameLookup) GetByName(name string) (*db.OAuth2Client, error) {
	if f.c == nil || f.c.Name != name {
		return nil, errNotFound
	}
	return f.c, nil
}

func TestInternalCredentials_RequiresAdminToken(t *testing.T) {
	h := NewInternalCredentialsHandler(InternalCredentialsDeps{
		Repo:       &fakeNameLookup{c: &db.OAuth2Client{Name: "x"}},
		Decrypt:    func(in []byte) ([]byte, error) { return in, nil },
		AdminToken: "secret",
	})
	r := httptest.NewRequest(http.MethodGet, "/internal/credentials/x", nil)
	r.SetPathValue("name", "x")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusUnauthorized {
		t.Fatalf("Code=%d want 401", w.Code)
	}
}

func TestInternalCredentials_ReturnsDecryptedSecret(t *testing.T) {
	uris := `["http://localhost:8500/auth/callback","https://prod.example/cb"]`
	cli := &db.OAuth2Client{
		Name:            "api-gateway",
		ClientID:        "cli-1",
		ClientSecretEnc: []byte("ENC:plaintext-secret"),
		RedirectURIs:    &uris,
		IsActive:        true,
	}
	h := NewInternalCredentialsHandler(InternalCredentialsDeps{
		Repo: &fakeNameLookup{c: cli},
		Decrypt: func(in []byte) ([]byte, error) {
			return []byte(strings.TrimPrefix(string(in), "ENC:")), nil
		},
		AdminToken: "secret",
	})
	r := httptest.NewRequest(http.MethodGet, "/internal/credentials/api-gateway", nil)
	r.SetPathValue("name", "api-gateway")
	r.Header.Set("X-Admin-Token", "secret")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var got map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &got)
	if got["client_id"] != "cli-1" || got["client_secret"] != "plaintext-secret" {
		t.Fatalf("client fields=%v", got)
	}
	gotURIs, _ := got["redirect_uris"].([]interface{})
	if len(gotURIs) != 2 || gotURIs[0] != "http://localhost:8500/auth/callback" {
		t.Fatalf("redirect_uris=%v", gotURIs)
	}
}

func TestInternalCredentials_404WhenMissing(t *testing.T) {
	h := NewInternalCredentialsHandler(InternalCredentialsDeps{
		Repo:       &fakeNameLookup{},
		Decrypt:    func(in []byte) ([]byte, error) { return in, nil },
		AdminToken: "secret",
	})
	r := httptest.NewRequest(http.MethodGet, "/internal/credentials/nope", nil)
	r.SetPathValue("name", "nope")
	r.Header.Set("X-Admin-Token", "secret")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusNotFound {
		t.Fatalf("Code=%d", w.Code)
	}
}
