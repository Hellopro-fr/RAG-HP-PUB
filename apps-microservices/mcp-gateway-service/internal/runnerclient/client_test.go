package runnerclient

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSpawn_OK(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Admin-Token") != "t" {
			w.WriteHeader(http.StatusUnauthorized)
			return
		}
		if r.Method != http.MethodPost || r.URL.Path != "/admin/instances" {
			http.NotFound(w, r)
			return
		}
		_ = json.NewEncoder(w).Encode(SpawnResponse{Port: 15000, PID: 42})
	}))
	defer srv.Close()

	c := New(srv.URL, "t")
	out, err := c.Spawn(context.Background(), SpawnRequest{InstanceID: "x", TemplateSlug: "ga", StdioCommand: "analytics-mcp"})
	if err != nil {
		t.Fatalf("err: %v", err)
	}
	if out.Port != 15000 || out.PID != 42 {
		t.Errorf("got %+v", out)
	}
}

func TestSpawn_BadToken(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
	}))
	defer srv.Close()

	c := New(srv.URL, "wrong")
	_, err := c.Spawn(context.Background(), SpawnRequest{InstanceID: "x"})
	if err == nil {
		t.Fatal("want error")
	}
}

func TestSpawn_UnprocessableReturnsStatusErrorWithDetail(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnprocessableEntity)
		_, _ = w.Write([]byte(`{"detail":{"code":"neo4j_auth_failed","message":"Neo4j rejected the username or password"}}`))
	}))
	defer srv.Close()

	_, err := New(srv.URL, "tok").Spawn(context.Background(), SpawnRequest{InstanceID: "i1"})
	var se *StatusError
	if !errors.As(err, &se) {
		t.Fatalf("want *StatusError, got %T %v", err, err)
	}
	if se.StatusCode != http.StatusUnprocessableEntity {
		t.Errorf("status = %d", se.StatusCode)
	}
	code, msg := se.Detail()
	if code != "neo4j_auth_failed" || msg != "Neo4j rejected the username or password" {
		t.Errorf("detail = %q / %q", code, msg)
	}
	if !strings.Contains(err.Error(), "runner POST /admin/instances: status 422") {
		t.Errorf("error text changed: %v", err)
	}
}

func TestStatusError_DetailIgnoresNonObjectDetail(t *testing.T) {
	// FastAPI request-validation 422s carry a list in "detail".
	se := &StatusError{StatusCode: 422, Body: map[string]any{"detail": []any{"x"}}}
	if code, msg := se.Detail(); code != "" || msg != "" {
		t.Errorf("got %q / %q, want empty", code, msg)
	}
}
