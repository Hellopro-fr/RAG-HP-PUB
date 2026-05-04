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

type fakeRotator struct {
	rows  map[string]*db.OAuth2RefreshToken
	calls int
}

func (f *fakeRotator) FindByHash(h string) (*db.OAuth2RefreshToken, error) {
	if r, ok := f.rows[h]; ok {
		return r, nil
	}
	return nil, fakeNotFound{}
}

func (f *fakeRotator) Rotate(oldHash, newHash string) (*db.OAuth2RefreshToken, error) {
	f.calls++
	old, ok := f.rows[oldHash]
	if !ok {
		return nil, fakeNotFound{}
	}
	if old.Revoked {
		for _, r := range f.rows {
			if r.SID == old.SID {
				r.Revoked = true
			}
		}
		return nil, fakeNotFound{}
	}
	old.Revoked = true
	newRow := &db.OAuth2RefreshToken{
		TokenHash: newHash,
		SID:       old.SID,
		ClientID:  old.ClientID,
		UserEmail: old.UserEmail,
		ExpiresAt: old.ExpiresAt,
	}
	f.rows[newHash] = newRow
	return newRow, nil
}

func TestToken_Refresh_Success(t *testing.T) {
	plain := "s"
	cipher := []byte("ENC:" + plain)
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: cipher, TokenTTLSeconds: 60}

	old := &db.OAuth2RefreshToken{
		TokenHash: HashRefreshToken("oldraw"),
		SID:       "sid1",
		ClientID:  "x",
		UserEmail: "a@x",
		ExpiresAt: time.Now().Add(time.Hour),
	}
	rot := &fakeRotator{rows: map[string]*db.OAuth2RefreshToken{old.TokenHash: old}}

	te := NewTokenEndpoint(TokenEndpointDeps{
		ClientRepo:     &fakeClientRepo{c: cli},
		RefreshRepo:    &fakeRefreshSink{},
		RefreshRotator: rot,
		Decrypt:        func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:      "s",
		Issuer:         "https://account.test",
	})

	form := url.Values{
		"grant_type":    {"refresh_token"},
		"refresh_token": {"oldraw"},
	}
	r := httptest.NewRequest(http.MethodPost, "/token", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plain)))
	w := httptest.NewRecorder()
	te.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d body=%s", w.Code, w.Body.String())
	}
	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["refresh_token"].(string) == "oldraw" {
		t.Fatal("refresh did not rotate")
	}
	if rot.calls != 1 {
		t.Fatalf("rotator calls=%d", rot.calls)
	}
}

func TestToken_Refresh_ReuseAttack(t *testing.T) {
	plain := "s"
	cipher := []byte("ENC:" + plain)
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: cipher, TokenTTLSeconds: 60}
	old := &db.OAuth2RefreshToken{
		TokenHash: HashRefreshToken("raw"),
		SID:       "sid1",
		ClientID:  "x",
		UserEmail: "a@x",
		ExpiresAt: time.Now().Add(time.Hour),
		Revoked:   true,
	}
	rot := &fakeRotator{rows: map[string]*db.OAuth2RefreshToken{old.TokenHash: old}}

	te := NewTokenEndpoint(TokenEndpointDeps{
		ClientRepo:     &fakeClientRepo{c: cli},
		RefreshRepo:    &fakeRefreshSink{},
		RefreshRotator: rot,
		Decrypt:        func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:      "s",
		Issuer:         "https://account.test",
	})
	form := url.Values{"grant_type": {"refresh_token"}, "refresh_token": {"raw"}}
	r := httptest.NewRequest(http.MethodPost, "/token", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plain)))
	w := httptest.NewRecorder()
	te.ServeHTTP(w, r)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("Code=%d", w.Code)
	}
}
