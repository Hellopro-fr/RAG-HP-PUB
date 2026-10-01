package tests

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/jobperf"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

func setupJobPerfServer(t *testing.T) (*httptest.Server, *redisstore.Client, string) {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(mr.Close)
	rs, err := redisstore.New("redis://" + mr.Addr())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { rs.Close() })
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	return srv, rs, mintToken("admin", "test-secret")
}

// TestJobPerf_NoData verifies that querying a non-existent job returns 200 with empty points and null summary.
func TestJobPerf_NoData(t *testing.T) {
	srv, _, tok := setupJobPerfServer(t)
	resp, err := authedGet(srv.URL+"/api/jobs/nonexistent/performance", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["job_id"] != "nonexistent" {
		t.Errorf("job_id=%v want nonexistent", body["job_id"])
	}
	pts, ok := body["points"].([]any)
	if !ok || len(pts) != 0 {
		t.Errorf("expected empty points, got %v", body["points"])
	}
	if body["summary"] != nil {
		t.Errorf("expected null summary for empty job, got %v", body["summary"])
	}
}

// TestJobPerf_PersistAndRead verifies that persisted points are returned and summary is computed.
func TestJobPerf_PersistAndRead(t *testing.T) {
	srv, rs, tok := setupJobPerfServer(t)
	ctx := t.Context()
	now := time.Now().UnixMilli()

	// Persist two samples.
	jobperf.Persist(ctx, rs.Raw(), "job-perf-1", "replica-A", now, 0.4, 512, 2048)
	jobperf.Persist(ctx, rs.Raw(), "job-perf-1", "replica-A", now+1000, 0.9, 768, 2048)

	resp, err := authedGet(srv.URL+"/api/jobs/job-perf-1/performance", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body struct {
		JobID   string           `json:"job_id"`
		Points  []map[string]any `json:"points"`
		Summary map[string]any   `json:"summary"`
	}
	decodeJSON(t, resp.Body, &body)

	if body.JobID != "job-perf-1" {
		t.Errorf("job_id=%v", body.JobID)
	}
	if len(body.Points) != 2 {
		t.Errorf("expected 2 points, got %d", len(body.Points))
	}
	if body.Summary == nil {
		t.Fatal("expected non-nil summary")
	}
	if cnt, _ := body.Summary["count"].(float64); int(cnt) != 2 {
		t.Errorf("summary.count=%v want 2", body.Summary["count"])
	}
	// peak CPU should be 0.9
	if pc, _ := body.Summary["peak_cpu"].(float64); pc != 0.9 {
		t.Errorf("peak_cpu=%v want 0.9", pc)
	}
}

// TestJobPerf_Format verifies the JSON shape of the response.
func TestJobPerf_Format(t *testing.T) {
	srv, rs, tok := setupJobPerfServer(t)
	ctx := t.Context()
	now := time.Now().UnixMilli()
	jobperf.Persist(ctx, rs.Raw(), "job-fmt", "replica-B", now, 0.5, 300, 1024)

	resp, _ := authedGet(srv.URL+"/api/jobs/job-fmt/performance", tok)
	var body map[string]any
	decodeJSON(t, resp.Body, &body)

	// Verify required top-level keys.
	for _, key := range []string{"job_id", "points", "summary"} {
		if _, ok := body[key]; !ok {
			t.Errorf("missing key %q in response", key)
		}
	}

	pts, _ := body["points"].([]any)
	if len(pts) != 1 {
		t.Fatalf("expected 1 point, got %d", len(pts))
	}
	pt, _ := pts[0].(map[string]any)
	for _, field := range []string{"ts", "cpu", "ram", "totalRam", "replicaId"} {
		if _, ok := pt[field]; !ok {
			t.Errorf("point missing field %q", field)
		}
	}

	// Verify summary fields.
	b, _ := json.Marshal(body["summary"])
	var sum map[string]any
	json.Unmarshal(b, &sum)
	for _, field := range []string{"count", "duration_ms", "peak_cpu", "avg_cpu", "peak_ram", "total_ram"} {
		if _, ok := sum[field]; !ok {
			t.Errorf("summary missing field %q", field)
		}
	}
}

// TestJobPerf_NoAuth verifies unauthenticated requests are rejected.
func TestJobPerf_NoAuth(t *testing.T) {
	srv, _, _ := setupJobPerfServer(t)
	resp, _ := http.Get(srv.URL + "/api/jobs/somejob/performance")
	if resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", resp.StatusCode)
	}
}
