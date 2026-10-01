package tests

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/replicahistory"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/alicebob/miniredis/v2"
)

// ---------------------------------------------------------------------------
// Unit tests — pure domain logic (no Redis)
// ---------------------------------------------------------------------------

// TestReplicaWindow_ParseAccepts validates that "15m" and "1h" are accepted.
func TestReplicaWindow_ParseAccepts(t *testing.T) {
	ms15m, err := replicahistory.ParseReplicaWindow("15m")
	if err != nil {
		t.Fatalf("15m: %v", err)
	}
	if ms15m != 15*60*1000 {
		t.Errorf("15m = %d, want %d", ms15m, 15*60*1000)
	}
	ms1h, err := replicahistory.ParseReplicaWindow("1h")
	if err != nil {
		t.Fatalf("1h: %v", err)
	}
	if ms1h != 60*60*1000 {
		t.Errorf("1h = %d, want %d", ms1h, 60*60*1000)
	}
}

// TestReplicaWindow_ParseRejects validates that invalid windows return an error.
func TestReplicaWindow_ParseRejects(t *testing.T) {
	cases := []string{"1d", "", "2h", "30m"}
	for _, tc := range cases {
		_, err := replicahistory.ParseReplicaWindow(tc)
		if err == nil {
			t.Errorf("expected error for %q", tc)
		}
	}
}

// ---------------------------------------------------------------------------
// Integration tests — Redis via miniredis
// ---------------------------------------------------------------------------

func setupReplicaTest(t *testing.T) (*redisstore.Client, *miniredis.Miniredis) {
	t.Helper()
	mr, err := miniredis.Run()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(mr.Close)
	c, err := redisstore.New("redis://" + mr.Addr())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = c.Close() })
	return c, mr
}

// TestReplicaPersistHeartbeat_ZAddsAndRegisters mirrors the JS test:
// "persistHeartbeat ZADDs sample and registers known replica".
func TestReplicaPersistHeartbeat_ZAddsAndRegisters(t *testing.T) {
	c, _ := setupReplicaTest(t)
	ctx := context.Background()
	now := time.Now().UnixMilli()

	jobID := "job-a"
	c.PersistHeartbeat(ctx, "r1", now, 0.42, 1024, 4096, &jobID)

	// Verify the sample is in the sorted set.
	points, err := c.ReadReplicaHistory(ctx, "r1", 60*60*1000)
	if err != nil {
		t.Fatal(err)
	}
	if len(points) != 1 {
		t.Fatalf("len(points) = %d, want 1", len(points))
	}
	if points[0].CPU != 0.42 {
		t.Errorf("cpu = %f, want 0.42", points[0].CPU)
	}
	if points[0].JobID == nil || *points[0].JobID != "job-a" {
		t.Errorf("jobId = %v, want 'job-a'", points[0].JobID)
	}

	// Verify known-set contains r1.
	members, err := c.Raw().SMembers(ctx, redisstore.KnownReplicasKey).Result()
	if err != nil {
		t.Fatal(err)
	}
	found := false
	for _, m := range members {
		if m == "r1" {
			found = true
			break
		}
	}
	if !found {
		t.Error("r1 not found in known-replicas set")
	}
}

// TestReplicaPersistHeartbeat_ToleratesMissing mirrors:
// "persistHeartbeat tolerates missing fields without throwing".
func TestReplicaPersistHeartbeat_ToleratesMissing(t *testing.T) {
	c, _ := setupReplicaTest(t)
	ctx := context.Background()
	// Nil replicaID → no-op.
	c.PersistHeartbeat(ctx, "", 0, 0, 0, 0, nil)
	// Valid one.
	c.PersistHeartbeat(ctx, "r1", 0, 0, 0, 0, nil)
	points, _ := c.ReadReplicaHistory(ctx, "r1", 60*60*1000)
	if len(points) != 1 {
		t.Errorf("len(points) = %d, want 1", len(points))
	}
}

// TestReplicaPersistHeartbeat_TrimsOld mirrors:
// "persistHeartbeat trims samples older than retention".
func TestReplicaPersistHeartbeat_TrimsOld(t *testing.T) {
	c, mr := setupReplicaTest(t)
	ctx := context.Background()
	now := time.Now().UnixMilli()
	oldTs := now - redisstore.RetentionReplicaHistoryMs - 60000

	// Inject an old sample directly via miniredis.
	key := redisstore.ReplicaHistoryPrefix + "r1"
	old := fmt.Sprintf(`{"ts":%d,"cpu":0,"ram":0,"totalRam":0,"jobId":null}`, oldTs)
	mr.ZAdd(key, float64(oldTs), old)

	// Now persist a fresh heartbeat which should trigger trimming.
	c.PersistHeartbeat(ctx, "r1", now, 0.5, 100, 1000, nil)

	points, err := c.ReadReplicaHistory(ctx, "r1", 60*60*1000)
	if err != nil {
		t.Fatal(err)
	}
	// Old sample trimmed, new one kept.
	if len(points) != 1 {
		t.Fatalf("len(points) = %d, want 1", len(points))
	}
	if points[0].CPU != 0.5 {
		t.Errorf("cpu = %f, want 0.5", points[0].CPU)
	}
}

// TestReplicaReadHistory_ReturnsRecentPoints mirrors:
// "readReplicaHistory returns recent points".
func TestReplicaReadHistory_ReturnsRecentPoints(t *testing.T) {
	c, _ := setupReplicaTest(t)
	ctx := context.Background()
	now := time.Now().UnixMilli()

	c.PersistHeartbeat(ctx, "r1", now-1000, 0.1, 10, 1000, nil)
	c.PersistHeartbeat(ctx, "r1", now, 0.2, 20, 1000, nil)

	points, err := c.ReadReplicaHistory(ctx, "r1", 60*60*1000)
	if err != nil {
		t.Fatal(err)
	}
	if len(points) != 2 {
		t.Fatalf("len(points) = %d, want 2", len(points))
	}
	if points[0].CPU != 0.1 {
		t.Errorf("points[0].cpu = %f, want 0.1", points[0].CPU)
	}
	if points[1].CPU != 0.2 {
		t.Errorf("points[1].cpu = %f, want 0.2", points[1].CPU)
	}
}

// TestReplicaReadAll_ReturnsMapAndDropsOrphans mirrors:
// "readAllReplicasHistory returns map of replicaId -> points and drops orphans".
func TestReplicaReadAll_ReturnsMapAndDropsOrphans(t *testing.T) {
	c, _ := setupReplicaTest(t)
	ctx := context.Background()
	now := time.Now().UnixMilli()

	// Persist a real replica.
	c.PersistHeartbeat(ctx, "r1", now, 0.1, 10, 1000, nil)

	// Inject a ghost replica with no recent data into known-set.
	_ = c.Raw().SAdd(ctx, redisstore.KnownReplicasKey, "r-ghost").Err()

	all, err := c.ReadAllReplicasHistory(ctx, 60*60*1000)
	if err != nil {
		t.Fatal(err)
	}
	if len(all) != 1 {
		t.Errorf("len(all) = %d, want 1", len(all))
	}
	if _, ok := all["r1"]; !ok {
		t.Error("r1 missing from result")
	}
	if _, ok := all["r-ghost"]; ok {
		t.Error("r-ghost should be absent from result")
	}

	// Ghost should have been removed from the known-set.
	members, _ := c.Raw().SMembers(ctx, redisstore.KnownReplicasKey).Result()
	for _, m := range members {
		if m == "r-ghost" {
			t.Error("r-ghost still in known-replicas set")
		}
	}
}

// ---------------------------------------------------------------------------
// HTTP endpoint tests
// ---------------------------------------------------------------------------

func setupReplicaHTTPTest(t *testing.T) (*httptest.Server, string, *redisstore.Client) {
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
	t.Cleanup(func() { _ = rs.Close() })
	cfg := &config.Config{JWTSecret: "test-secret"}
	srv := httptest.NewServer(httpapi.NewRouter(httpapi.Deps{
		Config: cfg, RedisStore: rs, AuditStore: &noopAudit{},
	}))
	t.Cleanup(srv.Close)
	tok := mintToken("admin", "test-secret")
	return srv, tok, rs
}

// TestReplicaHTTP_AllHistory checks GET /api/replicas/history returns 200 with map.
func TestReplicaHTTP_AllHistory(t *testing.T) {
	srv, tok, rs := setupReplicaHTTPTest(t)
	ctx := context.Background()
	now := time.Now().UnixMilli()
	rs.PersistHeartbeat(ctx, "r1", now, 0.5, 512, 2048, nil)

	resp, err := authedGet(srv.URL+"/api/replicas/history?window=1h", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var body struct {
		Window   string                   `json:"window"`
		Replicas map[string][]any         `json:"replicas"`
	}
	decodeJSON(t, resp.Body, &body)
	if _, ok := body.Replicas["r1"]; !ok {
		t.Errorf("r1 missing from response: %+v", body)
	}
}

// TestReplicaHTTP_SingleHistory checks GET /api/replicas/{id}/history.
func TestReplicaHTTP_SingleHistory(t *testing.T) {
	srv, tok, rs := setupReplicaHTTPTest(t)
	ctx := context.Background()
	now := time.Now().UnixMilli()
	rs.PersistHeartbeat(ctx, "r1", now, 0.3, 200, 1000, nil)

	resp, err := authedGet(srv.URL+"/api/replicas/r1/history?window=15m", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusOK {
		t.Fatalf("status = %d, want 200", resp.StatusCode)
	}
	var body struct {
		ReplicaID string                          `json:"replica_id"`
		Points    []replicahistory.HeartbeatSample `json:"points"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		t.Fatal(err)
	}
	if body.ReplicaID != "r1" {
		t.Errorf("replica_id = %q, want r1", body.ReplicaID)
	}
	if len(body.Points) != 1 {
		t.Errorf("len(points) = %d, want 1", len(body.Points))
	}
}

// TestReplicaHTTP_InvalidWindow checks GET /api/replicas/history with bad window.
func TestReplicaHTTP_InvalidWindow(t *testing.T) {
	srv, tok, _ := setupReplicaHTTPTest(t)
	resp, err := authedGet(srv.URL+"/api/replicas/history?window=1d", tok)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusBadRequest {
		t.Errorf("status = %d, want 400", resp.StatusCode)
	}
}

// TestReplicaHTTP_NoAuth checks that unauthenticated requests are rejected.
func TestReplicaHTTP_NoAuth(t *testing.T) {
	srv, _, _ := setupReplicaHTTPTest(t)
	resp, err := http.Get(srv.URL + "/api/replicas/history")
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != http.StatusUnauthorized {
		t.Errorf("status = %d, want 401", resp.StatusCode)
	}
}
