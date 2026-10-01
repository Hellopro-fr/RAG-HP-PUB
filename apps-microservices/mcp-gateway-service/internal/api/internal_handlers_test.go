package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/glebarez/sqlite"
	"gorm.io/gorm"

	"mcp-gateway/internal/config"
	"mcp-gateway/internal/repository"
)

// newSyncTestHandler builds a Handler with a SQLite-backed UserRepo and the
// given AccountInternalToken. Same hand-rolled DDL as the repository tests.
func newSyncTestHandler(t *testing.T, token string) *Handler {
	t.Helper()
	gdb, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	const ddl = `
		CREATE TABLE gateway_users (
			id            INTEGER PRIMARY KEY AUTOINCREMENT,
			email         TEXT NOT NULL UNIQUE,
			display_name  TEXT NOT NULL DEFAULT '',
			role          TEXT NOT NULL DEFAULT 'config-only',
			is_allowed    INTEGER NOT NULL DEFAULT 0,
			login_count   INTEGER NOT NULL DEFAULT 0,
			last_login_at datetime,
			created_at    datetime,
			updated_at    datetime
		);`
	if err := gdb.Exec(ddl).Error; err != nil {
		t.Fatalf("create table: %v", err)
	}
	return &Handler{
		userRepo: repository.NewUserRepo(gdb, nil, nil),
		config:   &config.Config{AccountInternalToken: token},
	}
}

func postSync(h *Handler, token, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, "/api/v1/internal/users/sync", strings.NewReader(body))
	if token != "" {
		req.Header.Set("X-Admin-Token", token)
	}
	rec := httptest.NewRecorder()
	h.handleUserSync(rec, req)
	return rec
}

func TestHandleUserSync_NilDeps_Returns503(t *testing.T) {
	h := &Handler{}
	rec := postSync(h, "tok", `{"users":[]}`)
	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("got %d, want 503", rec.Code)
	}
}

func TestHandleUserSync_GetReturns405(t *testing.T) {
	h := newSyncTestHandler(t, "tok")
	req := httptest.NewRequest(http.MethodGet, "/api/v1/internal/users/sync", nil)
	req.Header.Set("X-Admin-Token", "tok")
	rec := httptest.NewRecorder()
	h.handleUserSync(rec, req)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Errorf("got %d, want 405", rec.Code)
	}
	if got := rec.Header().Get("Allow"); got != "POST" {
		t.Errorf("Allow header = %q, want POST", got)
	}
}

func TestHandleUserSync_AuthFailures_Return401(t *testing.T) {
	cases := []struct {
		name, configured, presented string
	}{
		{"missing header", "tok", ""},
		{"wrong token", "tok", "wrong"},
		{"empty configured token", "", "anything"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			h := newSyncTestHandler(t, c.configured)
			rec := postSync(h, c.presented, `{"users":[]}`)
			if rec.Code != http.StatusUnauthorized {
				t.Errorf("got %d, want 401", rec.Code)
			}
		})
	}
}

func TestHandleUserSync_BadBody_Returns400(t *testing.T) {
	h := newSyncTestHandler(t, "tok")
	for _, body := range []string{`not json`, `{"users":[{"email":"  "}]}`} {
		rec := postSync(h, "tok", body)
		if rec.Code != http.StatusBadRequest {
			t.Errorf("body %q: got %d, want 400", body, rec.Code)
		}
	}
}

func TestHandleUserSync_CreatesAndSkips(t *testing.T) {
	h := newSyncTestHandler(t, "tok")

	// First call creates both users.
	rec := postSync(h, "tok", `{"users":[{"email":"A@Hellopro.fr","display_name":"A"},{"email":"b@hellopro.fr","display_name":"B"}]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("got %d body=%s", rec.Code, rec.Body.String())
	}
	var out struct {
		Created []string `json:"created"`
		Skipped []string `json:"skipped"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &out); err != nil {
		t.Fatalf("decode: %v", err)
	}
	// Email normalized: trimmed + lowercased.
	if len(out.Created) != 2 || out.Created[0] != "a@hellopro.fr" {
		t.Fatalf("created = %v, want [a@hellopro.fr b@hellopro.fr]", out.Created)
	}

	// Second call: both already exist -> skipped, created must encode as [].
	rec = postSync(h, "tok", `{"users":[{"email":"a@hellopro.fr","display_name":"A"}]}`)
	if rec.Code != http.StatusOK {
		t.Fatalf("got %d", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"created":[]`) {
		t.Errorf("created not encoded as []: %s", rec.Body.String())
	}
	out = struct {
		Created []string `json:"created"`
		Skipped []string `json:"skipped"`
	}{}
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if len(out.Skipped) != 1 || out.Skipped[0] != "a@hellopro.fr" {
		t.Errorf("skipped = %v, want [a@hellopro.fr]", out.Skipped)
	}
}

func TestHandleRunnerSync_NilDeps_Returns503(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodPost, "/api/v1/internal/runner/sync", nil)
	rec := httptest.NewRecorder()
	h.handleRunnerSync(rec, req)
	if rec.Code != http.StatusServiceUnavailable {
		t.Errorf("got %d", rec.Code)
	}
}

func TestHandleRunnerSync_GetReturns405(t *testing.T) {
	h := &Handler{}
	req := httptest.NewRequest(http.MethodGet, "/api/v1/internal/runner/sync", nil)
	rec := httptest.NewRecorder()
	h.handleRunnerSync(rec, req)
	if rec.Code != http.StatusMethodNotAllowed {
		t.Errorf("got %d, want 405", rec.Code)
	}
	if got := rec.Header().Get("Allow"); got != "POST" {
		t.Errorf("Allow header = %q, want POST", got)
	}
}
