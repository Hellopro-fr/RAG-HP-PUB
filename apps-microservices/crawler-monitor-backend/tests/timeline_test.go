package tests

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/timeline"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

// ---------- ParseTimelineWindow ----------

func TestTimeline_ParseWindowAcceptsKnown(t *testing.T) {
	cases := []struct {
		key           string
		wantMs        int64
		wantGranMs    int64
	}{
		{"1h", 3600000, 60 * 1000},
		{"6h", 6 * 3600000, 5 * 60 * 1000},
		{"24h", 24 * 3600000, 15 * 60 * 1000},
		{"7d", 7 * 24 * 3600000, 60 * 60 * 1000},
	}
	for _, tc := range cases {
		wms, gms, err := timeline.ParseTimelineWindow(tc.key)
		if err != nil {
			t.Errorf("[%s] unexpected error: %v", tc.key, err)
		}
		if wms != tc.wantMs {
			t.Errorf("[%s] windowMs = %d, want %d", tc.key, wms, tc.wantMs)
		}
		if gms != tc.wantGranMs {
			t.Errorf("[%s] granularityMs = %d, want %d", tc.key, gms, tc.wantGranMs)
		}
	}
}

func TestTimeline_ParseWindowRejectsInvalid(t *testing.T) {
	for _, bad := range []string{"30m", "2h", "", "7D"} {
		_, _, err := timeline.ParseTimelineWindow(bad)
		if err == nil {
			t.Errorf("[%q] expected error, got nil", bad)
		}
	}
}

// ---------- AggregateTimeline ----------

func TestTimeline_FixedWidthEmptySeries(t *testing.T) {
	// Mirrors JS test: now = 1700000400000
	now := int64(1700000400000)
	gran := int64(60 * 1000)
	win := int64(60 * 60 * 1000)

	buckets := timeline.AggregateTimeline(nil, now, win, gran)
	if len(buckets) != 60 {
		t.Fatalf("len=%d, want 60", len(buckets))
	}
	for _, b := range buckets {
		if b.Success != 0 || b.Failure != 0 || b.Running != 0 || b.OomEvents != 0 {
			t.Errorf("expected all zeros, got %+v", b)
		}
	}
	// Last bucket ts must be floor(now/granMs)*granMs
	lastBucketTs := (now / gran) * gran
	if buckets[len(buckets)-1].Ts != lastBucketTs {
		t.Errorf("last bucket ts=%d, want %d", buckets[len(buckets)-1].Ts, lastBucketTs)
	}
	if buckets[0].Ts != lastBucketTs-59*gran {
		t.Errorf("first bucket ts=%d, want %d", buckets[0].Ts, lastBucketTs-59*gran)
	}
}

func TestTimeline_CountsStatusesIntoRightBucket(t *testing.T) {
	now := time.Now().UnixMilli()
	gran := int64(60 * 1000)
	win := int64(60 * 60 * 1000)

	t1 := now - 30*60*1000
	t2 := now - 30*60*1000 + 100
	t3 := now - 5*60*1000
	t4 := now - 2*60*60*1000 // outside window

	jobs := []timeline.Job{
		{StartTime: msToISO(t1), Status: "finished"},
		{StartTime: msToISO(t2), Status: "failed"},
		{StartTime: msToISO(t3), Status: "running", OomRestartCount: 2},
		{StartTime: msToISO(t4), Status: "finished"}, // must be ignored
	}

	buckets := timeline.AggregateTimeline(jobs, now, win, gran)

	var totalSuccess, totalFailure, totalRunning, totalOom int
	for _, b := range buckets {
		totalSuccess += b.Success
		totalFailure += b.Failure
		totalRunning += b.Running
		totalOom += b.OomEvents
	}
	if totalSuccess != 1 {
		t.Errorf("success=%d, want 1", totalSuccess)
	}
	if totalFailure != 1 {
		t.Errorf("failure=%d, want 1", totalFailure)
	}
	if totalRunning != 1 {
		t.Errorf("running=%d, want 1", totalRunning)
	}
	if totalOom != 2 {
		t.Errorf("oom=%d, want 2", totalOom)
	}
}

func TestTimeline_AlignsLastBucketAndCountsBuckets(t *testing.T) {
	now := time.Now().UnixMilli()
	gran := int64(5 * 60 * 1000)
	win := int64(60 * 60 * 1000) // 12 buckets of 5 min
	buckets := timeline.AggregateTimeline(nil, now, win, gran)
	if len(buckets) != 12 {
		t.Fatalf("len=%d, want 12", len(buckets))
	}
	last := buckets[len(buckets)-1]
	if last.Ts%gran != 0 {
		t.Errorf("last bucket ts %d not aligned to granularity %d", last.Ts, gran)
	}
}

func TestTimeline_IgnoresInvalidStartTime(t *testing.T) {
	now := time.Now().UnixMilli()
	jobs := []timeline.Job{
		{StartTime: "not-a-date", Status: "finished"},
		{StartTime: "", Status: "failed"},
		{Status: "finished"},
	}
	buckets := timeline.AggregateTimeline(jobs, now, 3600000, 60000)
	var total int
	for _, b := range buckets {
		total += b.Success + b.Failure + b.Running
	}
	if total != 0 {
		t.Errorf("total=%d, want 0", total)
	}
}

// ---------- HTTP endpoint /api/timeline ----------

func setupTimelineServer(t *testing.T, jobs []string) (*httptest.Server, string) {
	t.Helper()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	for i, j := range jobs {
		mr.Set(fmt.Sprintf("crawl_job:job%d", i), j)
	}
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	return srv, mintToken("admin", "test-secret")
}

func TestTimeline_EndpointDefaultWindow(t *testing.T) {
	srv, tok := setupTimelineServer(t, nil)
	resp, err := authedGet(srv.URL+"/api/timeline", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["window"] != "1h" {
		t.Errorf("window=%v, want 1h", body["window"])
	}
	buckets, ok := body["buckets"].([]any)
	if !ok || len(buckets) != 60 {
		t.Errorf("buckets len=%d, want 60", len(buckets))
	}
}

func TestTimeline_EndpointBadWindow(t *testing.T) {
	srv, tok := setupTimelineServer(t, nil)
	resp, _ := authedGet(srv.URL+"/api/timeline?window=30m", tok)
	if resp.StatusCode != 400 {
		t.Errorf("status=%d, want 400", resp.StatusCode)
	}
}

func TestTimeline_EndpointNoAuth(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{Config: cfg, RedisStore: rs, AuditStore: &noopAudit{}}))
	defer srv.Close()
	resp, _ := autoGet(srv.URL + "/api/timeline")
	if resp.StatusCode != 401 {
		t.Errorf("status=%d, want 401", resp.StatusCode)
	}
}

func TestTimeline_EndpointWithJobs(t *testing.T) {
	now := time.Now()
	job1 := fmt.Sprintf(`{"start_time":%q,"status":"finished","oom_restart_count":0}`, now.Add(-5*time.Minute).UTC().Format(time.RFC3339))
	job2 := fmt.Sprintf(`{"start_time":%q,"status":"failed","oom_restart_count":0}`, now.Add(-10*time.Minute).UTC().Format(time.RFC3339))
	srv, tok := setupTimelineServer(t, []string{job1, job2})
	resp, err := authedGet(srv.URL+"/api/timeline?window=1h", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	buckets := body["buckets"].([]any)
	var totalSuccess, totalFailure float64
	for _, bRaw := range buckets {
		b := bRaw.(map[string]any)
		totalSuccess += b["success"].(float64)
		totalFailure += b["failure"].(float64)
	}
	if totalSuccess != 1 || totalFailure != 1 {
		t.Errorf("success=%v failure=%v, want 1 1", totalSuccess, totalFailure)
	}
}

func TestTimeline_EndpointCustomRange(t *testing.T) {
	from := "2026-01-01T00:00:00Z"
	to := "2026-01-01T06:00:00Z"
	srv, tok := setupTimelineServer(t, nil)
	resp, err := authedGet(srv.URL+"/api/timeline?from="+from+"&to="+to, tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body map[string]any
	decodeJSON(t, resp.Body, &body)
	if body["window"] != "custom" {
		t.Errorf("window=%v, want custom", body["window"])
	}
}

// helpers

func msToISO(ms int64) string {
	return time.UnixMilli(ms).UTC().Format(time.RFC3339)
}

func autoGet(url string) (*http.Response, error) {
	return http.Get(url)
}
