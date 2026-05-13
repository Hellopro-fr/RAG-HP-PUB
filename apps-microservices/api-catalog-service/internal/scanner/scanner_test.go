package scanner

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"

	"api-catalog-service/internal/db"
	"api-catalog-service/internal/repository"
)

func TestMergeTargets_EnvOverridesDB(t *testing.T) {
	seeds := map[string]string{"svc-a": "http://a", "svc-b": "http://b"}
	rows := []DBRow{
		{Name: "svc-a", BaseURL: "http://old-a", Source: "manual"},
		{Name: "svc-c", BaseURL: "http://c", Source: "manual"},
	}
	targets := MergeTargets(seeds, rows)
	byName := map[string]Target{}
	for _, t := range targets {
		byName[t.Name] = t
	}
	if byName["svc-a"].BaseURL != "http://a" || byName["svc-a"].Source != "env" {
		t.Fatalf("env should override manual for svc-a, got %+v", byName["svc-a"])
	}
	if byName["svc-c"].BaseURL != "http://c" {
		t.Fatalf("manual-only svc-c should be present, got %+v", byName["svc-c"])
	}
	if len(targets) != 3 {
		t.Fatalf("expected 3 targets, got %d: %+v", len(targets), targets)
	}
}

func newTestDB(t *testing.T) *gorm.DB {
	t.Helper()
	g, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatal(err)
	}
	if err := db.AutoMigrate(g); err != nil {
		t.Fatal(err)
	}
	return g
}

func TestScanner_RunUpsertsServiceAndReplacesEndpoints(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/openapi.json" {
			_, _ = w.Write([]byte(`{"paths":{"/x":{"get":{"summary":"x"}}}}`))
			return
		}
		if r.URL.Path == "/api-info" {
			_ = json.NewEncoder(w).Encode(map[string]any{})
			return
		}
		http.NotFound(w, r)
	}))
	defer srv.Close()

	g := newTestDB(t)
	s := New(Deps{
		Services:    repository.NewServiceRepo(g),
		Endpoints:   repository.NewEndpointRepo(g),
		Concurrency: 4,
		Timeout:     1 * time.Second,
	})
	rep := s.Run(context.Background(), map[string]string{"foo-service": srv.URL})
	if rep.ServicesScanned != 1 || rep.ServicesOK != 1 {
		t.Fatalf("report = %+v", rep)
	}
	items, _, _ := repository.NewServiceRepo(g).List(10, 0, "")
	if len(items) != 1 || items[0].Name != "foo-service" {
		t.Fatalf("services = %+v", items)
	}
	eps, _ := repository.NewEndpointRepo(g).ListForService(items[0].ID, "")
	if len(eps) != 1 || eps[0].Path != "/x" {
		t.Fatalf("eps = %+v", eps)
	}
}
