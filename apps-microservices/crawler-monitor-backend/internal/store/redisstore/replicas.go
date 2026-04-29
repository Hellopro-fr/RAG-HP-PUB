package redisstore

import (
	"context"
	"encoding/json"
	"strconv"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/replicahistory"
	"github.com/redis/go-redis/v9"
)

// RetentionReplicaHistoryMs is 1 hour, matching JS REPLICA_HISTORY_RETENTION_MS.
const RetentionReplicaHistoryMs = int64(60 * 60 * 1000)

// PersistHeartbeat stores a heartbeat sample into the per-replica sorted set and
// registers the replicaId in the known-replicas set. Tolerant: never returns an error.
// hb fields: ReplicaID, JobID (optional), Timestamp (ms; 0 = now), CPU, RAM, TotalRAM.
func (c *Client) PersistHeartbeat(ctx context.Context, replicaID string, ts int64, cpu, ram, totalRAM float64, jobID *string) {
	if replicaID == "" {
		return
	}
	if ts == 0 {
		ts = time.Now().UnixMilli()
	}
	sample := replicahistory.HeartbeatSample{
		Ts:       ts,
		CPU:      cpu,
		RAM:      ram,
		TotalRAM: totalRAM,
		JobID:    jobID,
	}
	raw, err := json.Marshal(sample)
	if err != nil {
		return
	}
	key := ReplicaHistoryPrefix + replicaID
	_ = c.rdb.ZAdd(ctx, key, redis.Z{Score: float64(ts), Member: string(raw)}).Err()
	_ = c.rdb.ZRemRangeByScore(ctx, key, "0", formatScore(ts-RetentionReplicaHistoryMs)).Err()
	_ = c.rdb.SAdd(ctx, KnownReplicasKey, replicaID).Err()
}

// ReadReplicaHistory returns decoded history points for a single replica within
// [now-windowMs, now].
func (c *Client) ReadReplicaHistory(ctx context.Context, replicaID string, windowMs int64) ([]replicahistory.HeartbeatSample, error) {
	if replicaID == "" {
		return nil, nil
	}
	min := time.Now().UnixMilli() - windowMs
	key := ReplicaHistoryPrefix + replicaID
	strs, err := c.rdb.ZRangeByScore(ctx, key, &redis.ZRangeBy{
		Min: formatScore(min),
		Max: "+inf",
	}).Result()
	if err != nil {
		return nil, err
	}
	out := make([]replicahistory.HeartbeatSample, 0, len(strs))
	for _, s := range strs {
		var p replicahistory.HeartbeatSample
		if err := json.Unmarshal([]byte(s), &p); err != nil {
			continue
		}
		out = append(out, p)
	}
	return out, nil
}

// ReadAllReplicasHistory returns history for all known replicas and prunes orphans
// (replicas with no points in the window).
func (c *Client) ReadAllReplicasHistory(ctx context.Context, windowMs int64) (map[string][]replicahistory.HeartbeatSample, error) {
	ids, err := c.rdb.SMembers(ctx, KnownReplicasKey).Result()
	if err != nil {
		return nil, err
	}
	result := make(map[string][]replicahistory.HeartbeatSample)
	for _, id := range ids {
		points, err := c.ReadReplicaHistory(ctx, id, windowMs)
		if err != nil {
			continue
		}
		if len(points) == 0 {
			// Prune orphan (no data in window).
			_ = c.rdb.SRem(ctx, KnownReplicasKey, id).Err()
			continue
		}
		result[id] = points
	}
	return result, nil
}

// formatScore converts an int64 millisecond timestamp to a string score for ZRangeByScore.
func formatScore(ms int64) string {
	return strconv.FormatInt(ms, 10)
}
