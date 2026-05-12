package transport

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"mcp-zoho-service/internal/db"
	"mcp-zoho-service/internal/routing"
)

// stubRunner satisfies routing.QueryRunner with fixed admin + grant + optional import.
type stubRunner struct {
	adminRow  *db.ServerRow
	granted   bool
	importRow *db.ServerRow
}

func (s stubRunner) FindAdminZohoServer(_ context.Context, _ string) (*db.ServerRow, error) {
	if s.adminRow == nil {
		return nil, sql.ErrNoRows
	}
	return s.adminRow, nil
}

func (s stubRunner) IsAdminGranted(_ context.Context, _ string, _ string) (bool, error) {
	return s.granted, nil
}

func (s stubRunner) FindUserZohoImport(_ context.Context, _, _ string) (*db.ServerRow, error) {
	if s.importRow == nil {
		return nil, sql.ErrNoRows
	}
	return s.importRow, nil
}

type fakeDec struct{}

func (fakeDec) Decrypt(b []byte) ([]byte, error) { return b, nil }

func newServerWith(t *testing.T, runner stubRunner) (*Server, *httptest.Server) {
	t.Helper()
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, _ := io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"jsonrpc":"2.0","result":{"echo":` + string(body) + `},"id":7}`))
	}))
	// Wire the upstream URL into the admin or import row.
	if runner.adminRow != nil && runner.adminRow.URL == "" {
		runner.adminRow.URL = upstream.URL
	}
	if runner.importRow != nil && runner.importRow.URL == "" {
		runner.importRow.URL = upstream.URL
	}
	r := routing.NewResolver(runner, fakeDec{}, time.Minute, "http://self/mcp")
	return &Server{Resolver: r, GatewayToken: "secret", UpstreamTimeout: time.Second}, upstream
}

func TestHandler_MissingEmail400(t *testing.T) {
	s, up := newServerWith(t, stubRunner{adminRow: &db.ServerRow{ID: "admin-1"}})
	defer up.Close()

	req := httptest.NewRequest(http.MethodPost, "/mcp", strings.NewReader(`{}`))
	req.Header.Set("X-Admin-Token", "secret")
	rec := httptest.NewRecorder()
	s.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400 (body=%s)", rec.Code, rec.Body.String())
	}
}

func TestHandler_BadAdminToken401(t *testing.T) {
	s, up := newServerWith(t, stubRunner{adminRow: &db.ServerRow{ID: "admin-1"}})
	defer up.Close()

	req := httptest.NewRequest(http.MethodPost, "/mcp", strings.NewReader(`{}`))
	req.Header.Set("X-Admin-Token", "wrong")
	rec := httptest.NewRecorder()
	s.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want 401", rec.Code)
	}
}

func TestHandler_NoMatchReturnsRPCError(t *testing.T) {
	s, up := newServerWith(t, stubRunner{adminRow: &db.ServerRow{ID: "admin-1"}, granted: false, importRow: nil})
	defer up.Close()

	body := bytes.NewBufferString(`{"jsonrpc":"2.0","method":"tools/list","id":42}`)
	req := httptest.NewRequest(http.MethodPost, "/mcp", body)
	req.Header.Set("X-Admin-Token", "secret")
	req.Header.Set("X-End-User-Email", "charlie@hp.fr")
	req.Header.Set("X-End-User-Login", "charlie")
	rec := httptest.NewRecorder()
	s.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d, want 200 (rpc envelope) body=%s", rec.Code, rec.Body.String())
	}
	var env struct {
		ID    int `json:"id"`
		Error struct {
			Code    int    `json:"code"`
			Message string `json:"message"`
		} `json:"error"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &env); err != nil {
		t.Fatalf("decode: %v body=%s", err, rec.Body.String())
	}
	if env.Error.Code != -32001 {
		t.Fatalf("code = %d, want -32001", env.Error.Code)
	}
	if env.ID != 42 {
		t.Fatalf("id = %d, want 42", env.ID)
	}
	if !strings.Contains(env.Error.Message, "no Zoho server configured") {
		t.Fatalf("message = %q", env.Error.Message)
	}
}

func TestHandler_ProxiesBodyVerbatim(t *testing.T) {
	upstreamHits := 0
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upstreamHits++
		body, _ := io.ReadAll(r.Body)
		if got := string(body); got != `{"jsonrpc":"2.0","method":"tools/list","id":7}` {
			t.Fatalf("upstream body = %q", got)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer admin" {
			t.Fatalf("Authorization = %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"jsonrpc":"2.0","result":{"ok":true},"id":7}`))
	}))
	defer upstream.Close()

	adminRow := &db.ServerRow{ID: "admin-1", URL: upstream.URL, AuthHeaders: []byte(`{"Authorization":"Bearer admin"}`)}
	r := routing.NewResolver(stubRunner{adminRow: adminRow, granted: true}, fakeDec{}, time.Minute, "http://self/mcp")
	s := &Server{Resolver: r, GatewayToken: "secret", UpstreamTimeout: time.Second}

	body := bytes.NewBufferString(`{"jsonrpc":"2.0","method":"tools/list","id":7}`)
	req := httptest.NewRequest(http.MethodPost, "/mcp", body)
	req.Header.Set("X-Admin-Token", "secret")
	req.Header.Set("X-End-User-Email", "alice@hp.fr")
	req.Header.Set("X-End-User-Login", "alice")
	rec := httptest.NewRecorder()
	s.Routes().ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", rec.Code, rec.Body.String())
	}
	if upstreamHits != 1 {
		t.Fatalf("upstreamHits = %d, want 1", upstreamHits)
	}
	var out struct {
		Result struct {
			OK bool `json:"ok"`
		} `json:"result"`
		ID int `json:"id"`
	}
	_ = json.Unmarshal(rec.Body.Bytes(), &out)
	if !out.Result.OK || out.ID != 7 {
		t.Fatalf("response = %s", rec.Body.String())
	}
}
