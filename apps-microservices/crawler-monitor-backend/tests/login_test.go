package tests

import (
	"bytes"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/auth/password"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/golang-jwt/jwt/v5"
)

func newLoginServer(t *testing.T, hash string, audit httpapi.AuditAppender) *httptest.Server {
	t.Helper()
	cfg := &config.Config{
		AdminPasswordHash: hash,
		JWTSecret:         "test-secret",
	}
	r := httpapi.NewRouter(httpapi.Deps{Config: cfg, AuditStore: audit})
	srv := httptest.NewServer(r)
	t.Cleanup(srv.Close)
	return srv
}

func TestLogin_Success(t *testing.T) {
	hash, _ := password.Hash("hunter2")
	audit := &recordingAudit{}
	srv := newLoginServer(t, hash, audit)

	resp, err := srv.Client().Post(srv.URL+"/api/login", "application/json",
		bytes.NewBufferString(`{"password":"hunter2"}`))
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body struct{ Token string `json:"token"` }
	decodeJSON(t, resp.Body, &body)
	if body.Token == "" {
		t.Fatal("empty token")
	}
	parsed, err := jwt.Parse(body.Token, func(t *jwt.Token) (any, error) { return []byte("test-secret"), nil })
	if err != nil || !parsed.Valid {
		t.Fatalf("token invalid: %v", err)
	}
	claims := parsed.Claims.(jwt.MapClaims)
	if claims["role"] != "admin" {
		t.Errorf("role = %v", claims["role"])
	}
	exp := int64(claims["exp"].(float64))
	delta := exp - time.Now().Unix()
	if delta < 23*3600 || delta > 25*3600 {
		t.Errorf("exp delta = %d, want ~24h", delta)
	}
	// Audit
	if len(audit.Entries) != 1 || audit.Entries[0]["action"] != "login_success" {
		t.Errorf("audit entries = %v", audit.Entries)
	}
}

func TestLogin_BadPassword(t *testing.T) {
	hash, _ := password.Hash("hunter2")
	audit := &recordingAudit{}
	srv := newLoginServer(t, hash, audit)
	resp, _ := srv.Client().Post(srv.URL+"/api/login", "application/json",
		bytes.NewBufferString(`{"password":"wrong"}`))
	if resp.StatusCode != 401 {
		t.Errorf("status=%d, want 401", resp.StatusCode)
	}
	bodyContains(t, resp.Body, "Invalid password")
	if len(audit.Entries) != 1 || audit.Entries[0]["action"] != "login_failure" {
		t.Errorf("audit entries = %v", audit.Entries)
	}
}

func TestLogin_MissingPassword(t *testing.T) {
	audit := &recordingAudit{}
	srv := newLoginServer(t, "x", audit)
	resp, _ := srv.Client().Post(srv.URL+"/api/login", "application/json", bytes.NewBufferString(`{}`))
	if resp.StatusCode != 400 {
		t.Errorf("status=%d, want 400", resp.StatusCode)
	}
	bodyContains(t, resp.Body, "Password required")
	if len(audit.Entries) != 1 || audit.Entries[0]["action"] != "login_attempt" {
		t.Errorf("audit entries = %v", audit.Entries)
	}
}

func TestLogin_EmptyBody(t *testing.T) {
	audit := &recordingAudit{}
	srv := newLoginServer(t, "x", audit)
	resp, _ := srv.Client().Post(srv.URL+"/api/login", "application/json", bytes.NewBufferString(""))
	if resp.StatusCode != 400 {
		t.Errorf("status=%d, want 400", resp.StatusCode)
	}
}
