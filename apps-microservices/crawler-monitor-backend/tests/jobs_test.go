package tests

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

func setupJobsTest(t *testing.T) (*httptest.Server, string) {
	t.Helper()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	mr.Set("crawl_job:abc", `{"id":"abc","status":"running","start_time":"2026-04-15T10:00:00Z"}`)
	mr.Set("crawl_job:def", `{"id":"def","status":"finished","start_time":"2026-04-15T11:00:00Z"}`)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	return srv, mintToken("admin", "test-secret")
}

func TestJobs_ListSorted(t *testing.T) {
	srv, tok := setupJobsTest(t)
	resp, err := authedGet(srv.URL+"/api/jobs", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var jobs []map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&jobs)
	if len(jobs) != 2 {
		t.Fatalf("len=%d", len(jobs))
	}
	// def has later start_time so should be first after sort
	if jobs[0]["id"] != "def" {
		t.Errorf("first = %v want def", jobs[0]["id"])
	}
}

func TestJobs_NotFound(t *testing.T) {
	srv, tok := setupJobsTest(t)
	resp, _ := authedGet(srv.URL+"/api/jobs/zzz/details", tok)
	if resp.StatusCode != 404 {
		t.Errorf("status=%d", resp.StatusCode)
	}
}

func TestJobs_NoAuth(t *testing.T) {
	srv, _ := setupJobsTest(t)
	resp, _ := http.Get(srv.URL + "/api/jobs")
	if resp.StatusCode != 401 {
		t.Errorf("status=%d", resp.StatusCode)
	}
}

func TestCapacity_Ok(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	mr.Set(redisstore.RunningCountKey, "5")
	mr.Set(redisstore.MaxGlobalKey, "10")
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	defer srv.Close()
	resp, _ := authedGet(srv.URL+"/api/capacity", mintToken("admin", "test-secret"))
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&body)
	if body["running_jobs"].(float64) != 5 || body["max_global_jobs"].(float64) != 10 {
		t.Errorf("body=%v", body)
	}
	if body["is_full"] != false {
		t.Errorf("is_full=%v", body["is_full"])
	}
}

// TestJobs_WindowKeepsUnparsableStartTime : un start_time illisible n'est pas
// une date ancienne. Avant le correctif, ParseAnyMs retournait -1 et le job
// disparaissait de la liste des qu'un ?window= etait demande.
func TestJobs_WindowKeepsUnparsableStartTime(t *testing.T) {
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	mr.Set("crawl_job:broken", `{"id":"broken","status":"running","start_time":"pas-une-date"}`)
	mr.Set("crawl_job:recent", `{"id":"recent","status":"running","start_time":"`+isoNow()+`"}`)
	mr.Set("crawl_job:old", `{"id":"old","status":"running","start_time":"2020-01-01T00:00:00Z"}`)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)

	resp, err := authedGet(srv.URL+"/api/jobs?window=24h", mintToken("admin", "test-secret"))
	if err != nil {
		t.Fatal(err)
	}
	var jobs []map[string]any
	_ = json.NewDecoder(resp.Body).Decode(&jobs)
	seen := map[string]bool{}
	for _, j := range jobs {
		seen[j["id"].(string)] = true
	}
	if !seen["broken"] {
		t.Error("le job a la date illisible a ete filtre")
	}
	if !seen["recent"] {
		t.Error("le job recent a ete filtre")
	}
	if seen["old"] {
		t.Error("le job de 2020 ne devrait pas passer la fenetre 24h")
	}
}
