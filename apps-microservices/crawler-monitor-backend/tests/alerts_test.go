package tests

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/alerts"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

// T mirrors the JS threshold fixture used in all unit tests.
var T = alerts.Thresholds{
	ErrorRateThreshold:  0.05,
	ErrorRateMinJobs:    5,
	OomSpikeThreshold:   3,
	ReplicaHighCpu:      0.85,
	ReplicaHighCpuDurMs: 240_000,
	CapacityFullDurMs:   300_000,
	CallbacksFailedMin:  1,
}

/* ---------- evalErrorRate ---------- */

func TestAlerts_EvalErrorRate_TooFewJobs(t *testing.T) {
	now := time.Now().UnixMilli()
	jobs := []alerts.Job{
		{StartTime: msToISOA(now - 60000), Status: "failed"},
		{StartTime: msToISOA(now - 60000), Status: "finished"},
	}
	if alerts.EvalErrorRate(jobs, now, T) != nil {
		t.Error("expected nil when too few jobs")
	}
}

func TestAlerts_EvalErrorRate_FiresWhenExceeded(t *testing.T) {
	now := time.Now().UnixMilli()
	var jobs []alerts.Job
	for i := 0; i < 8; i++ {
		jobs = append(jobs, alerts.Job{StartTime: msToISOA(now - int64(1000*i)), Status: "finished"})
	}
	for i := 0; i < 2; i++ {
		jobs = append(jobs, alerts.Job{StartTime: msToISOA(now - int64(1000*i)), Status: "failed"})
	}
	// 2/10 = 20% > 5%
	a := alerts.EvalErrorRate(jobs, now, T)
	if a == nil {
		t.Fatal("expected alert, got nil")
	}
	if a.Kind != "error_rate_high" {
		t.Errorf("kind=%q, want error_rate_high", a.Kind)
	}
	rate, _ := a.Metadata["rate"].(float64)
	if rate < 0.2 {
		t.Errorf("rate=%v, want >= 0.2", rate)
	}
}

func TestAlerts_EvalErrorRate_IgnoresOutsideWindow(t *testing.T) {
	now := time.Now().UnixMilli()
	var jobs []alerts.Job
	for i := 0; i < 10; i++ {
		jobs = append(jobs, alerts.Job{StartTime: msToISOA(now - 2*60*60*1000), Status: "failed"})
	}
	if alerts.EvalErrorRate(jobs, now, T) != nil {
		t.Error("expected nil for jobs outside window")
	}
}

/* ---------- evalOomSpike ---------- */

func TestAlerts_EvalOomSpike_SumsAcrossWindow(t *testing.T) {
	now := time.Now().UnixMilli()
	jobs := []alerts.Job{
		{StartTime: msToISOA(now - 60000), Status: "finished", OomRestartCount: 2},
		{StartTime: msToISOA(now - 60000), Status: "finished", OomRestartCount: 2},
	}
	a := alerts.EvalOomSpike(jobs, now, T)
	if a == nil {
		t.Fatal("expected alert, got nil")
	}
	if a.Metadata["total"].(int) != 4 {
		t.Errorf("total=%v, want 4", a.Metadata["total"])
	}
	if a.Severity != "critical" {
		t.Errorf("severity=%q, want critical", a.Severity)
	}
}

func TestAlerts_EvalOomSpike_BelowThreshold(t *testing.T) {
	now := time.Now().UnixMilli()
	jobs := []alerts.Job{
		{StartTime: msToISOA(now), Status: "finished", OomRestartCount: 2},
	}
	if alerts.EvalOomSpike(jobs, now, T) != nil {
		t.Error("expected nil below threshold")
	}
}

/* ---------- evalReplicaHighCpu ---------- */

func TestAlerts_EvalReplicaHighCpu_FiresWhenSustained(t *testing.T) {
	now := time.Now().UnixMilli()
	points := []alerts.CpuPoint{
		{Ts: now - 5*60000, CPU: 0.5},
		{Ts: now - 4*60000, CPU: 0.9},
		{Ts: now - 3*60000, CPU: 0.91},
		{Ts: now - 2*60000, CPU: 0.92},
		{Ts: now - 1*60000, CPU: 0.93},
		{Ts: now, CPU: 0.94},
	}
	a := alerts.EvalReplicaHighCpu("r1", points, now, T)
	if a == nil {
		t.Fatal("expected alert, got nil")
	}
	if a.Kind != "replica_high_cpu_sustained" {
		t.Errorf("kind=%q", a.Kind)
	}
	durMs, _ := a.Metadata["duration_ms"].(int64)
	if durMs < 240_000 {
		t.Errorf("duration_ms=%d, want >= 240000", durMs)
	}
}

func TestAlerts_EvalReplicaHighCpu_NoFireAfterDip(t *testing.T) {
	now := time.Now().UnixMilli()
	points := []alerts.CpuPoint{
		{Ts: now - 4*60000, CPU: 0.95},
		{Ts: now - 3*60000, CPU: 0.5}, // dip
		{Ts: now - 2*60000, CPU: 0.95},
		{Ts: now - 1*60000, CPU: 0.95},
		{Ts: now, CPU: 0.95},
	}
	// Streak after dip = 3 min < 4 min threshold
	if alerts.EvalReplicaHighCpu("r1", points, now, T) != nil {
		t.Error("expected nil after dip")
	}
}

func TestAlerts_EvalReplicaHighCpu_NilWhenLowCpu(t *testing.T) {
	now := time.Now().UnixMilli()
	points := []alerts.CpuPoint{{Ts: now, CPU: 0.5}}
	if alerts.EvalReplicaHighCpu("r1", points, now, T) != nil {
		t.Error("expected nil when cpu below threshold")
	}
}

/* ---------- evalCapacitySaturation ---------- */

func TestAlerts_EvalCapacitySaturation_FiresAfterSustained(t *testing.T) {
	now := time.Now().UnixMilli()
	points := []alerts.CapacityPoint{
		{Ts: now - 7*60000, Full: false},
		{Ts: now - 6*60000, Full: true},
		{Ts: now - 5*60000, Full: true},
		{Ts: now - 4*60000, Full: true},
		{Ts: now - 3*60000, Full: true},
		{Ts: now - 2*60000, Full: true},
		{Ts: now - 1*60000, Full: true},
		{Ts: now, Full: true},
	}
	a := alerts.EvalCapacitySaturation(points, now, T)
	if a == nil {
		t.Fatal("expected alert, got nil")
	}
	if a.Kind != "capacity_full_sustained" {
		t.Errorf("kind=%q", a.Kind)
	}
	if a.Severity != "critical" {
		t.Errorf("severity=%q", a.Severity)
	}
}

func TestAlerts_EvalCapacitySaturation_NoFireShortDuration(t *testing.T) {
	now := time.Now().UnixMilli()
	points := []alerts.CapacityPoint{
		{Ts: now - 60000, Full: true},
		{Ts: now, Full: true},
	}
	// Only 1 min < 5 min threshold
	if alerts.EvalCapacitySaturation(points, now, T) != nil {
		t.Error("expected nil for short duration")
	}
}

/* ---------- evalCallbacksFailing ---------- */

func TestAlerts_EvalCallbacksFailing_FiresAboveMin(t *testing.T) {
	a := alerts.EvalCallbacksFailing(3, T)
	if a == nil {
		t.Fatal("expected alert, got nil")
	}
	cnt, _ := a.Metadata["count"].(int)
	if cnt != 3 {
		t.Errorf("count=%d, want 3", cnt)
	}
}

func TestAlerts_EvalCallbacksFailing_NilWhenZero(t *testing.T) {
	if alerts.EvalCallbacksFailing(0, T) != nil {
		t.Error("expected nil when 0 callbacks")
	}
}

/* ---------- Evaluate aggregator ---------- */

func TestAlerts_Evaluate_AggregatesAndSortsCriticalFirst(t *testing.T) {
	now := time.Now().UnixMilli()
	var jobs []alerts.Job
	for i := 0; i < 10; i++ {
		status := "finished"
		if i >= 8 {
			status = "failed"
		}
		jobs = append(jobs, alerts.Job{
			StartTime:       msToISOA(now),
			Status:          status,
			OomRestartCount: 1,
		})
	}
	inputs := alerts.Inputs{
		Jobs:                jobs,
		CapacityPoints:      nil,
		ReplicasHistory:     map[string][]alerts.CpuPoint{},
		FailedCallbackCount: 2,
	}
	result := alerts.Evaluate(inputs, now, T)
	// 3 alerts: error_rate_high (warn) + oom_spike (critical, 10*1=10) + callbacks_failing (critical)
	if len(result) != 3 {
		t.Fatalf("len=%d, want 3: %+v", len(result), result)
	}
	if result[0].Severity != "critical" {
		t.Errorf("first severity=%q, want critical", result[0].Severity)
	}
	if result[len(result)-1].Severity != "warn" {
		t.Errorf("last severity=%q, want warn", result[len(result)-1].Severity)
	}
}

func TestAlerts_Evaluate_EmptyOnQuietSystem(t *testing.T) {
	inputs := alerts.Inputs{
		Jobs: nil, CapacityPoints: nil,
		ReplicasHistory: map[string][]alerts.CpuPoint{}, FailedCallbackCount: 0,
	}
	result := alerts.Evaluate(inputs, time.Now().UnixMilli(), T)
	if len(result) != 0 {
		t.Errorf("expected empty, got %+v", result)
	}
}

func TestAlerts_DefaultThresholds_Exposed(t *testing.T) {
	dt := alerts.DefaultThresholds()
	if dt.ErrorRateThreshold <= 0 {
		t.Errorf("ErrorRateThreshold=%v", dt.ErrorRateThreshold)
	}
}

/* ---------- HTTP endpoint /api/alerts ---------- */

func setupAlertsServer(t *testing.T) (*httptest.Server, string) {
	t.Helper()
	mr, _ := miniredis.Run()
	t.Cleanup(mr.Close)
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	return srv, mintToken("admin", "test-secret")
}

func TestAlerts_Endpoint_ReturnsArray(t *testing.T) {
	srv, tok := setupAlertsServer(t)
	resp, err := authedGet(srv.URL+"/api/alerts", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}
	var body []any
	decodeJSON(t, resp.Body, &body)
	// Empty system → no alerts (but must be an array, not null).
	if body == nil {
		t.Error("expected non-nil array")
	}
}

func TestAlerts_Endpoint_NoAuth(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{Config: cfg, RedisStore: rs, AuditStore: &noopAudit{}}))
	defer srv.Close()
	resp, _ := http.Get(srv.URL + "/api/alerts")
	if resp.StatusCode != 401 {
		t.Errorf("status=%d, want 401", resp.StatusCode)
	}
}

func TestAlerts_Endpoint_WithFailedCallbacks(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	// Push items onto the failed_callbacks list.
	for i := 0; i < 3; i++ {
		mr.Lpush(redisstore.FailedCallbacksKey, fmt.Sprintf(`{"id":%d}`, i))
	}
	rs, _ := redisstore.New("redis://" + mr.Addr())
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{Config: cfg, RedisStore: rs, AuditStore: &noopAudit{}}))
	defer srv.Close()
	tok := mintToken("admin", "test-secret")
	resp, err := authedGet(srv.URL+"/api/alerts", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("status=%d", resp.StatusCode)
	}
	var body []map[string]any
	decodeJSON(t, resp.Body, &body)
	found := false
	for _, a := range body {
		if a["id"] == "callbacks_failing" {
			found = true
		}
	}
	if !found {
		t.Errorf("expected callbacks_failing alert, got %+v", body)
	}
}

// helpers

func msToISOA(ms int64) string {
	return time.UnixMilli(ms).UTC().Format(time.RFC3339)
}

var _ = json.Marshal
