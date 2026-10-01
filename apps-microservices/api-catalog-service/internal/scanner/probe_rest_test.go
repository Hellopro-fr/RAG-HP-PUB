package scanner

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestProbeREST_ParsesPaths(t *testing.T) {
	body := `{
      "paths": {
        "/search": {"get": {"operationId":"do_search","summary":"Search","tags":["s"]}},
        "/health": {"get": {"summary":"H","deprecated": true}}
      }
    }`
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/openapi.json" {
			http.NotFound(w, r)
			return
		}
		_, _ = w.Write([]byte(body))
	}))
	defer srv.Close()

	eps, err := ProbeREST(context.Background(), srv.URL, 1*time.Second)
	if err != nil {
		t.Fatal(err)
	}
	if len(eps) != 2 {
		t.Fatalf("got %d endpoints, want 2", len(eps))
	}
}

func TestProbeREST_404_NoError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(http.NotFound))
	defer srv.Close()
	eps, err := ProbeREST(context.Background(), srv.URL, 1*time.Second)
	if err != nil || len(eps) != 0 {
		t.Fatalf("want 0 eps no err, got %d %v", len(eps), err)
	}
}
