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
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/jobperf"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

func setupReplayServer(t *testing.T) (*httptest.Server, *miniredis.Miniredis, *redisstore.Client, string) {
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
	cfg := &config.Config{
		JWTSecret:     "test-secret",
		ReplayHighCPU: 0.85,
	}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config:     cfg,
		RedisStore: rs,
		AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	return srv, mr, rs, mintToken("admin", "test-secret")
}

// seedReplayJob insère un job Redis minimal pour les tests.
func seedReplayJob(t *testing.T, mr *miniredis.Miniredis, jobID string) {
	t.Helper()
	payload := fmt.Sprintf(
		`{"crawl_id":%q,"domain":"example.com","status":"running","start_time":"2026-04-29T10:00:00Z","crawl_mode":"full","oom_restart_count":0}`,
		jobID,
	)
	mr.Set("crawl_job:"+jobID, payload)
}

// TestReplay_NotFound vérifie qu'un job inexistant retourne 404.
func TestReplay_NotFound(t *testing.T) {
	srv, _, _, tok := setupReplayServer(t)
	resp, err := authedGet(srv.URL+"/api/jobs/nonexistent-replay-job/replay", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusNotFound {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("expected 404, got %d body=%s", resp.StatusCode, b)
	}
}

// TestReplay_WithPerfPoints vérifie qu'un job avec des points de perf retourne 200
// avec urls_processed > 0 (points non vides).
func TestReplay_WithPerfPoints(t *testing.T) {
	srv, mr, rs, tok := setupReplayServer(t)
	jobID := "replay-with-perf"
	seedReplayJob(t, mr, jobID)

	ctx := t.Context()
	now := time.Now().UnixMilli()
	jobperf.Persist(ctx, rs.Raw(), jobID, "replica-1", now, 0.3, 512, 2048)
	jobperf.Persist(ctx, rs.Raw(), jobID, "replica-1", now+1000, 0.5, 600, 2048)
	jobperf.Persist(ctx, rs.Raw(), jobID, "replica-1", now+2000, 0.7, 700, 2048)

	resp, err := authedGet(srv.URL+"/api/jobs/"+jobID+"/replay", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("expected 200, got %d body=%s", resp.StatusCode, b)
	}

	var body map[string]any
	decodeJSON(t, resp.Body, &body)

	if body["job_id"] != jobID {
		t.Errorf("job_id=%v want %s", body["job_id"], jobID)
	}

	pts, ok := body["points"].([]any)
	if !ok || len(pts) != 3 {
		t.Errorf("expected 3 points, got %v", body["points"])
	}

	if body["summary"] == nil {
		t.Error("expected non-nil summary")
	}
}

// TestReplay_CPUHighMarksHotZone vérifie que des points CPU > threshold génèrent
// un hot_zone et l'événement hot_cpu_zone.
func TestReplay_CPUHighMarksHotZone(t *testing.T) {
	srv, mr, rs, tok := setupReplayServer(t)
	jobID := "replay-cpu-high"
	seedReplayJob(t, mr, jobID)

	ctx := t.Context()
	now := time.Now().UnixMilli()
	// 2 points sous le seuil + 3 points au-dessus (> 0.85) + 1 point de retour
	jobperf.Persist(ctx, rs.Raw(), jobID, "r1", now, 0.2, 200, 1024)
	jobperf.Persist(ctx, rs.Raw(), jobID, "r1", now+1000, 0.9, 900, 1024) // > 0.85
	jobperf.Persist(ctx, rs.Raw(), jobID, "r1", now+2000, 0.95, 950, 1024) // > 0.85
	jobperf.Persist(ctx, rs.Raw(), jobID, "r1", now+3000, 0.3, 300, 1024)

	resp, err := authedGet(srv.URL+"/api/jobs/"+jobID+"/replay", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}

	var body map[string]any
	decodeJSON(t, resp.Body, &body)

	zones, ok := body["hot_zones"].([]any)
	if !ok || len(zones) == 0 {
		t.Errorf("expected at least 1 hot_zone, got %v", body["hot_zones"])
	}

	// Vérifie qu'au moins un événement hot_cpu_zone est présent
	events, _ := body["events"].([]any)
	found := false
	for _, ev := range events {
		if m, ok := ev.(map[string]any); ok {
			if m["kind"] == "hot_cpu_zone" {
				found = true
				if m["severity"] != "warn" {
					t.Errorf("hot_cpu_zone severity=%v want warn", m["severity"])
				}
				break
			}
		}
	}
	if !found {
		t.Errorf("no hot_cpu_zone event found in events=%v", events)
	}
}

// TestReplay_ResponseShape vérifie la présence de tous les champs attendus dans la réponse.
func TestReplay_ResponseShape(t *testing.T) {
	srv, mr, rs, tok := setupReplayServer(t)
	jobID := "replay-shape"
	seedReplayJob(t, mr, jobID)

	ctx := t.Context()
	now := time.Now().UnixMilli()
	jobperf.Persist(ctx, rs.Raw(), jobID, "r1", now, 0.4, 512, 2048)

	resp, err := authedGet(srv.URL+"/api/jobs/"+jobID+"/replay", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		b, _ := io.ReadAll(resp.Body)
		t.Fatalf("status=%d body=%s", resp.StatusCode, b)
	}

	b, _ := io.ReadAll(resp.Body)
	var body map[string]any
	if err := json.Unmarshal(b, &body); err != nil {
		t.Fatal(err)
	}

	// Vérifie les champs obligatoires du payload (mirrors server.js:442-450)
	for _, field := range []string{"job_id", "job", "points", "summary", "events", "hot_zones", "generated_at"} {
		if _, ok := body[field]; !ok {
			t.Errorf("missing field %q in replay response", field)
		}
	}

	// Vérifie la forme du champ job
	jobField, ok := body["job"].(map[string]any)
	if !ok {
		t.Fatalf("job field should be an object, got %T", body["job"])
	}
	for _, key := range []string{"id", "oom_restart_count"} {
		if _, ok := jobField[key]; !ok {
			t.Errorf("job missing field %q", key)
		}
	}

	// generated_at doit être une chaîne RFC3339
	ga, ok := body["generated_at"].(string)
	if !ok || ga == "" {
		t.Errorf("generated_at=%v want RFC3339 string", body["generated_at"])
	}
}

// TestReplay_NoAuth vérifie que les requêtes non authentifiées sont rejetées.
func TestReplay_NoAuth(t *testing.T) {
	srv, mr, _, _ := setupReplayServer(t)
	seedReplayJob(t, mr, "replay-noauth")
	resp, _ := http.Get(srv.URL + "/api/jobs/replay-noauth/replay")
	if resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", resp.StatusCode)
	}
}
