package redisstore

import (
	"context"
	"encoding/json"
	"strings"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/capacityplanning"
	"github.com/redis/go-redis/v9"
)

// RetentionJobPerfMs is 7 days.
const RetentionJobPerfMs = int64(7 * 24 * 60 * 60 * 1000)

// PersistJobPerfSample appends a perf sample to job:perf:<jobId> ZSet.
// Score = ts ms. Auto-prunes entries older than 7 days. Tolerant: errors swallowed.
func (c *Client) PersistJobPerfSample(ctx context.Context, jobID string, ts int64, sample any) {
	if jobID == "" {
		return
	}
	if ts == 0 {
		ts = time.Now().UnixMilli()
	}
	raw, err := json.Marshal(sample)
	if err != nil {
		return
	}
	key := JobPerfPrefix + jobID
	_ = c.rdb.ZAdd(ctx, key, redis.Z{Score: float64(ts), Member: string(raw)}).Err()
	_ = c.rdb.ZRemRangeByScore(ctx, key, "0", formatScore(ts-RetentionJobPerfMs)).Err()
	_ = c.rdb.Expire(ctx, key, time.Duration(RetentionJobPerfMs)*time.Millisecond).Err()
}

// ScanJobPerfByReplica scans every job:perf:* key and groups all samples in
// [now-windowMs, now] per replicaId. Mirrors JS defaultScanJobPerf.
func (c *Client) ScanJobPerfByReplica(ctx context.Context, windowMs int64) (map[string][]capacityplanning.Sample, error) {
	now := time.Now().UnixMilli()
	cutoff := formatScore(now - windowMs)
	out := make(map[string][]capacityplanning.Sample)

	var cursor uint64
	for {
		batch, next, err := c.rdb.Scan(ctx, cursor, JobPerfPrefix+"*", 200).Result()
		if err != nil {
			return nil, err
		}
		for _, key := range batch {
			rawList, err := c.rdb.ZRangeByScore(ctx, key, &redis.ZRangeBy{Min: cutoff, Max: "+inf"}).Result()
			if err != nil {
				continue
			}
			jobID := strings.TrimPrefix(key, JobPerfPrefix)
			for _, s := range rawList {
				var p map[string]any
				if err := json.Unmarshal([]byte(s), &p); err != nil {
					continue
				}
				replicaID, _ := p["replicaId"].(string)
				if replicaID == "" {
					continue
				}
				smp := capacityplanning.Sample{}
				if v, ok := p["ts"].(float64); ok {
					smp.Ts = int64(v)
				}
				if v, ok := p["cpu"].(float64); ok {
					smp.CPU = v
				}
				if v, ok := p["ram"].(float64); ok {
					smp.RAM = v
				}
				if v, ok := p["totalRam"].(float64); ok {
					smp.TotalRAM = v
				}
				if v, ok := p["jobId"].(string); ok && v != "" {
					smp.JobID = v
				} else {
					smp.JobID = jobID
				}
				out[replicaID] = append(out[replicaID], smp)
			}
		}
		cursor = next
		if cursor == 0 {
			break
		}
	}
	return out, nil
}

// ReplicaHistoryAsSamples returns ReadAllReplicasHistory data converted to
// the capacityplanning.Sample shape (used by the 1h fast path).
func (c *Client) ReplicaHistoryAsSamples(ctx context.Context, windowMs int64) (map[string][]capacityplanning.Sample, error) {
	hist, err := c.ReadAllReplicasHistory(ctx, windowMs)
	if err != nil {
		return nil, err
	}
	out := make(map[string][]capacityplanning.Sample, len(hist))
	for id, samples := range hist {
		conv := make([]capacityplanning.Sample, 0, len(samples))
		for _, s := range samples {
			jobID := ""
			if s.JobID != nil {
				jobID = *s.JobID
			}
			conv = append(conv, capacityplanning.Sample{
				Ts:       s.Ts,
				CPU:      s.CPU,
				RAM:      s.RAM,
				TotalRAM: s.TotalRAM,
				JobID:    jobID,
			})
		}
		out[id] = conv
	}
	return out, nil
}
