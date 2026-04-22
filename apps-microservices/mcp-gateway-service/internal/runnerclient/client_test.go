package runnerclient

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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
