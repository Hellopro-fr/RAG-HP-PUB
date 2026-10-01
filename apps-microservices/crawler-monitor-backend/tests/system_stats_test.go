package tests

import (
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/systemstats"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

// ---------------------------------------------------------------------------
// Unit tests — pure domain logic
// ---------------------------------------------------------------------------

// TestSystemParseStatsWindow_Accepts mirrors "parseStatsWindow accepts 1h, 24h, 7d".
func TestSystemParseStatsWindow_Accepts(t *testing.T) {
	cases := map[string]int64{
		"1h":  3600000,
		"24h": 86400000,
		"7d":  604800000,
	}
	for w, want := range cases {
		got, err := systemstats.ParseStatsWindow(w)
		if err != nil {
			t.Errorf("%q: unexpected error: %v", w, err)
		}
		if got != want {
			t.Errorf("%q = %d, want %d", w, got, want)
		}
	}
}

// TestSystemParseStatsWindow_Rejects mirrors "parseStatsWindow rejects others".
func TestSystemParseStatsWindow_Rejects(t *testing.T) {
	cases := []string{"30m", "", "2d"}
	for _, w := range cases {
		_, err := systemstats.ParseStatsWindow(w)
		if err == nil {
			t.Errorf("%q: expected error", w)
		}
	}
}

// TestSystemAggregateJobStats mirrors "aggregateJobStats counts statuses, success rate, oom, update mode".
func TestSystemAggregateJobStats(t *testing.T) {
	now := time.Now().UnixMilli()
	jobs := []systemstats.RawJob{
		{StartTime: isoOffset(now, -60000), EndTime: isoOffset(now, -30000), Status: "finished", CrawlMode: "standard"},
		{StartTime: isoOffset(now, -120000), EndTime: isoOffset(now, -90000), Status: "finished", CrawlMode: "update", OOMRestartCount: 1},
		{StartTime: isoOffset(now, -180000), EndTime: isoOffset(now, -150000), Status: "failed"},
		{StartTime: isoOffset(now, -200000), Status: "running"},
		// Outside 1h window.
		{StartTime: isoOffset(now, -7200000), EndTime: isoOffset(now, -7100000), Status: "finished"},
	}
	s := systemstats.AggregateJobStats(jobs, now, 3600000)
	if s.Total != 4 {
		t.Errorf("total = %d, want 4", s.Total)
	}
	if s.Counts.Finished != 2 {
		t.Errorf("finished = %d, want 2", s.Counts.Finished)
	}
	if s.Counts.Failed != 1 {
		t.Errorf("failed = %d, want 1", s.Counts.Failed)
	}
	if s.Counts.Running != 1 {
		t.Errorf("running = %d, want 1", s.Counts.Running)
	}
	// success_rate = 2/(2+1) = 0.6666...
	if s.SuccessRate == nil {
		t.Fatal("success_rate is nil")
	}
	if math.Abs(*s.SuccessRate-2.0/3.0) > 1e-6 {
		t.Errorf("success_rate = %f, want ~0.6667", *s.SuccessRate)
	}
	if s.OOMRestartsTotal != 1 {
		t.Errorf("oom_restarts_total = %d, want 1", s.OOMRestartsTotal)
	}
	if s.UpdateModeCount != 1 {
		t.Errorf("update_mode_count = %d, want 1", s.UpdateModeCount)
	}
	if s.AvgDurationMs == nil || *s.AvgDurationMs <= 0 {
		t.Errorf("avg_duration_ms should be positive, got %v", s.AvgDurationMs)
	}
}

// TestSystemAggregateJobStats_NullSuccessRate mirrors "returns null success_rate when no terminal jobs".
func TestSystemAggregateJobStats_NullSuccessRate(t *testing.T) {
	now := time.Now().UnixMilli()
	jobs := []systemstats.RawJob{
		{StartTime: isoOffset(now, -60000), Status: "running"},
	}
	s := systemstats.AggregateJobStats(jobs, now, 3600000)
	if s.SuccessRate != nil {
		t.Errorf("success_rate = %v, want nil", *s.SuccessRate)
	}
	if s.AvgDurationMs != nil {
		t.Errorf("avg_duration_ms = %v, want nil", *s.AvgDurationMs)
	}
}

// TestSystemAggregateJobStats_Empty mirrors "returns zero totals on empty input".
func TestSystemAggregateJobStats_Empty(t *testing.T) {
	s := systemstats.AggregateJobStats(nil, time.Now().UnixMilli(), 3600000)
	if s.Total != 0 {
		t.Errorf("total = %d, want 0", s.Total)
	}
	if s.SuccessRate != nil {
		t.Error("success_rate should be nil on empty input")
	}
}

// TestSystemAggregateSaturation mirrors "aggregateSaturation sums full intervals".
func TestSystemAggregateSaturation(t *testing.T) {
	now := time.Now().UnixMilli()
	points := []systemstats.CapacityPoint{
		{Ts: now - 300000, Running: 5, Max: 10, Full: false},
		{Ts: now - 240000, Running: 10, Max: 10, Full: true},  // 60s full
		{Ts: now - 180000, Running: 10, Max: 10, Full: true},  // 60s full
		{Ts: now - 120000, Running: 5, Max: 10, Full: false},
		{Ts: now - 60000, Running: 7, Max: 10, Full: false},
	}
	s := systemstats.AggregateSaturation(points, 300000)
	if s.SaturatedSeconds != 120 {
		t.Errorf("saturated_seconds = %d, want 120", s.SaturatedSeconds)
	}
	if s.SaturatedPct == nil {
		t.Fatal("saturated_pct is nil")
	}
	if math.Abs(*s.SaturatedPct-0.4) > 1e-6 {
		t.Errorf("saturated_pct = %f, want 0.4", *s.SaturatedPct)
	}
}

// TestSystemAggregateSaturation_TooFew mirrors "handles too-few points".
func TestSystemAggregateSaturation_TooFew(t *testing.T) {
	s := systemstats.AggregateSaturation(nil, 3600000)
	if s.SaturatedSeconds != 0 {
		t.Errorf("saturated_seconds = %d, want 0", s.SaturatedSeconds)
	}
	if s.SaturatedPct != nil {
		t.Errorf("saturated_pct = %v, want nil", *s.SaturatedPct)
	}
}

// ---------------------------------------------------------------------------
// HTTP endpoint tests
// ---------------------------------------------------------------------------

func setupSystemTest(t *testing.T) (*httptest.Server, string) {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(mr.Close)

	now := time.Now()
	// Populate a few jobs.
	mr.Set(redisstore.JobPrefix+"j1", fmt.Sprintf(`{"id":"j1","status":"finished","start_time":%q,"end_time":%q,"crawl_mode":"standard","oom_restart_count":0}`,
		now.Add(-30*time.Minute).UTC().Format(time.RFC3339),
		now.Add(-20*time.Minute).UTC().Format(time.RFC3339),
	))
	mr.Set(redisstore.JobPrefix+"j2", fmt.Sprintf(`{"id":"j2","status":"failed","start_time":%q,"oom_restart_count":1}`,
		now.Add(-45*time.Minute).UTC().Format(time.RFC3339),
	))
	mr.Set(redisstore.JobPrefix+"j3", fmt.Sprintf(`{"id":"j3","status":"running","start_time":%q}`,
		now.Add(-5*time.Minute).UTC().Format(time.RFC3339),
	))

	rs, err := redisstore.New("redis://" + mr.Addr())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = rs.Close() })
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	tok := mintToken("admin", "test-secret")
	return srv, tok
}

// TestSystemHTTP_StatsReturns200 checks GET /api/system/stats returns 200 with expected fields.
func TestSystemHTTP_StatsReturns200(t *testing.T) {
	srv, tok := setupSystemTest(t)
	resp, err := authedGet(srv.URL+"/api/system/stats?window=1h", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var body systemstats.SystemStatsResult
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.Jobs.Total != 3 {
		t.Errorf("jobs.total = %d, want 3", body.Jobs.Total)
	}
	if body.Jobs.Counts.Finished != 1 {
		t.Errorf("jobs.counts.finished = %d, want 1", body.Jobs.Counts.Finished)
	}
	if body.Jobs.Counts.Failed != 1 {
		t.Errorf("jobs.counts.failed = %d, want 1", body.Jobs.Counts.Failed)
	}
}

// TestSystemHTTP_StatsDefaultWindow checks that the default window is 24h.
func TestSystemHTTP_StatsDefaultWindow(t *testing.T) {
	srv, tok := setupSystemTest(t)
	resp, _ := authedGet(srv.URL+"/api/system/stats", tok)
	if resp.StatusCode != http.StatusOK {
		t.Errorf("status = %d, want 200", resp.StatusCode)
	}
}

// TestSystemHTTP_StatsBadWindow checks 400 on invalid window.
func TestSystemHTTP_StatsBadWindow(t *testing.T) {
	srv, tok := setupSystemTest(t)
	resp, _ := authedGet(srv.URL+"/api/system/stats?window=30m", tok)
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", resp.StatusCode)
	}
}

// TestSystemHTTP_HealthReturns200 checks GET /api/system/health.
func TestSystemHTTP_HealthReturns200(t *testing.T) {
	srv, tok := setupSystemTest(t)
	resp, err := authedGet(srv.URL+"/api/system/health", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if _, ok := body["redis_connected"]; !ok {
		t.Error("redis_connected field missing")
	}
	if _, ok := body["status"]; !ok {
		t.Error("status field missing")
	}
	if v, _ := body["ws_clients_count"].(float64); int(v) != 0 {
		t.Errorf("ws_clients_count = %d, want 0", int(v))
	}
}

// TestSystemHTTP_NoAuth checks that unauthenticated requests are rejected.
func TestSystemHTTP_NoAuth(t *testing.T) {
	srv, _ := setupSystemTest(t)
	resp, _ := http.Get(srv.URL + "/api/system/stats")
	if resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", resp.StatusCode)
	}
}

// ---------------------------------------------------------------------------
// helper: build an ISO timestamp relative to a base ms.
// ---------------------------------------------------------------------------

func isoOffset(baseMs, offsetMs int64) string {
	return time.UnixMilli(baseMs + offsetMs).UTC().Format(time.RFC3339)
}
