package tests

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

// TestWSPubSub_HeartbeatPersistsSeries verifie que le pub/sub ecrit bien les
// series replica:history et job:perf (regression prod : la diffusion WS
// continuait alors que la persistance avait cesse).
func TestWSPubSub_HeartbeatPersistsSeries(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rdb := redis.NewClient(&redis.Options{Addr: mr.Addr()})
	defer rdb.Close()
	rs, _ := redisstore.New("redis://" + mr.Addr())
	defer rs.Close()

	hub := ws.NewHub()
	defer hub.Close()
	c := ws.NewClientForTest()
	hub.Register(c)
	ps := ws.NewPubSub(rs, hub, "crawler:heartbeat")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go ps.Run(ctx)
	waitSubscribed(t, mr, "crawler:heartbeat")

	now := time.Now().UnixMilli()
	payload := fmt.Sprintf(
		`{"type":"heartbeat","replicaId":"r1","jobId":"job-1","domain":"example.com","cpu":0.42,"ram":1024,"totalRam":4096,"timestamp":%d,"status":"running"}`,
		now)
	rdb.Publish(context.Background(), "crawler:heartbeat", payload)

	// Le heartbeat doit atteindre le hub…
	select {
	case raw := <-c.SendForTest():
		var msg map[string]any
		if err := json.Unmarshal(raw, &msg); err != nil {
			t.Fatalf("invalid JSON: %v", err)
		}
		if msg["type"] != "replica_heartbeat" {
			t.Errorf("type = %v, want replica_heartbeat", msg["type"])
		}
	case <-time.After(3 * time.Second):
		t.Fatal("no broadcast received")
	}

	// …et avoir ete persiste dans les deux series.
	deadline := time.Now().Add(3 * time.Second)
	for {
		points, _ := rs.ReadReplicaHistory(context.Background(), "r1", 60*60*1000)
		perf, _ := rs.ScanJobPerfByReplica(context.Background(), 60*60*1000)
		if len(points) == 1 && len(perf["r1"]) == 1 {
			if points[0].CPU != 0.42 {
				t.Errorf("cpu = %v, want 0.42", points[0].CPU)
			}
			if perf["r1"][0].JobID != "job-1" {
				t.Errorf("jobId = %q, want job-1", perf["r1"][0].JobID)
			}
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("series non persistees: replica=%d jobperf=%d", len(points), len(perf["r1"]))
		}
		time.Sleep(20 * time.Millisecond)
	}

	// crawl_job:<id> ne doit PAS avoir ete creee par le monitor : cette cle
	// appartient a crawler-service.
	if mr.Exists("crawl_job:job-1") {
		t.Error("crawl_job:job-1 ecrite par le monitor")
	}

	if last := ps.LastMessageAt(); last <= 0 {
		t.Errorf("LastMessageAt = %d, want > 0", last)
	}
}

// TestWSPubSub_LastMessageAtZeroBeforeAnyMessage verifie l'etat initial.
func TestWSPubSub_LastMessageAtZeroBeforeAnyMessage(t *testing.T) {
	mr, _ := miniredis.Run()
	defer mr.Close()
	rs, _ := redisstore.New("redis://" + mr.Addr())
	defer rs.Close()
	ps := ws.NewPubSub(rs, ws.NewHub(), "crawl_updates")
	if got := ps.LastMessageAt(); got != 0 {
		t.Errorf("LastMessageAt = %d, want 0", got)
	}
}
