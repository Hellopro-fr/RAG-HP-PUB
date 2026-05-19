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

	"account-service/internal/auth"
	"account-service/internal/db"
)

type fakeRevoke struct {
	revoked map[string]bool
}

func (f *fakeRevoke) RevokeBySID(sid, reason string) error {
	if f.revoked == nil {
		f.revoked = map[string]bool{}
	}
	f.revoked[sid] = true
	return nil
}

func TestRevoke_RemovesChainBySID(t *testing.T) {
	plain := "s"
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: []byte("ENC:" + plain)}
	row := &db.OAuth2RefreshToken{TokenHash: HashRefreshToken("raw"), SID: "sid1", ClientID: "x"}
	rot := &fakeRotator{rows: map[string]*db.OAuth2RefreshToken{row.TokenHash: row}}
	rev := &fakeRevoke{}

	h := NewRevokeHandler(RevokeDeps{
		ClientRepo: &fakeClientRepo{c: cli},
		Rotator:    rot,
		Revoker:    rev,
		Decrypt:    func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
	})
	form := url.Values{"token": {"raw"}, "token_type_hint": {"refresh_token"}}
	r := httptest.NewRequest(http.MethodPost, "/token/revoke", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plain)))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("Code=%d", w.Code)
	}
	if !rev.revoked["sid1"] {
		t.Fatal("sid1 not revoked")
	}
}

func TestIntrospect_ActiveJWT(t *testing.T) {
	tok, _ := auth.SignJWT("s", auth.Claims{
		Sub: "alice@x", Aud: "x", Iss: "https://account.test", Sid: "sid1",
		Exp: time.Now().Add(60 * time.Second).Unix(), Iat: time.Now().Unix(),
	})
	plain := "secret"
	cli := &db.OAuth2Client{ClientID: "x", ClientSecretEnc: []byte("ENC:" + plain)}
	rot := &fakeRotator{rows: map[string]*db.OAuth2RefreshToken{}}

	h := NewIntrospectHandler(IntrospectDeps{
		ClientRepo: &fakeClientRepo{c: cli},
		Rotator:    rot,
		Decrypt:    func(in []byte) ([]byte, error) { return []byte(strings.TrimPrefix(string(in), "ENC:")), nil },
		JWTSecret:  "s",
		Issuer:     "https://account.test",
		Audience:   "x",
	})
	form := url.Values{"token": {tok}}
	r := httptest.NewRequest(http.MethodPost, "/introspect", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.Header.Set("Authorization", "Basic "+base64.StdEncoding.EncodeToString([]byte("x:"+plain)))
	w := httptest.NewRecorder()
	h.ServeHTTP(w, r)

	var body map[string]interface{}
	_ = json.Unmarshal(w.Body.Bytes(), &body)
	if body["active"] != true {
		t.Fatalf("active=%v body=%v", body["active"], body)
	}
}
