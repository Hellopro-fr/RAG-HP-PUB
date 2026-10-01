package tests

import (
	"context"
	"testing"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

// TestReplicaReadAll_ShortWindowDoesNotPrune : une lecture sur fenetre courte
// (15 min) ne doit plus supprimer le replica du registre. Avant le correctif,
// le SREM opportuniste effacait un replica dont le dernier point avait 30 min,
// et la lecture 1h suivante ne le retrouvait plus.
func TestReplicaReadAll_ShortWindowDoesNotPrune(t *testing.T) {
	c, _ := setupReplicaTest(t)
	ctx := context.Background()
	now := time.Now().UnixMilli()

	// Heartbeat vieux de 30 min : hors fenetre 15m, dans la fenetre 1h.
	c.PersistHeartbeat(ctx, "r1", now-30*60*1000, 0.3, 100, 1000, nil)

	short, err := c.ReadAllReplicasHistory(ctx, 15*60*1000)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := short["r1"]; ok {
		t.Error("r1 ne devrait pas avoir de point dans la fenetre 15m")
	}

	long, err := c.ReadAllReplicasHistory(ctx, redisstore.RetentionReplicaHistoryMs)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := long["r1"]; !ok {
		t.Error("r1 perdu apres une lecture sur fenetre courte")
	}
}

// TestReplicaPersistHeartbeat_SetsTTL verifie le TTL 2h pose sur la serie.
func TestReplicaPersistHeartbeat_SetsTTL(t *testing.T) {
	c, mr := setupReplicaTest(t)
	c.PersistHeartbeat(context.Background(), "r1", time.Now().UnixMilli(), 0.1, 1, 2, nil)
	ttl := mr.TTL(redisstore.ReplicaHistoryPrefix + "r1")
	if ttl <= 0 || ttl > redisstore.TTLReplicaHistory {
		t.Errorf("ttl = %v, want 0 < ttl <= %v", ttl, redisstore.TTLReplicaHistory)
	}
}

// TestJobPerf_PersistSetsTTL verifie le TTL 7j sur job:perf:<id>.
func TestJobPerf_PersistSetsTTL(t *testing.T) {
	c, mr := setupReplicaTest(t)
	c.PersistJobPerfSample(context.Background(), "job-1", time.Now().UnixMilli(),
		map[string]any{"ts": time.Now().UnixMilli(), "cpu": 0.1, "replicaId": "r1"})
	ttl := mr.TTL(redisstore.JobPerfPrefix + "job-1")
	// Encadre : un TTL > 0 passait meme si la retention tombait a une seconde.
	wantMax := time.Duration(redisstore.RetentionJobPerfMs) * time.Millisecond
	wantMin := wantMax - 24*time.Hour
	if ttl <= wantMin || ttl > wantMax {
		t.Errorf("ttl = %v, want %v < ttl <= %v", ttl, wantMin, wantMax)
	}
}
