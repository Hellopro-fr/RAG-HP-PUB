// Package jobperf provides per-job CPU/RAM performance history stored in Redis.
//
// Mirrors src/lib/jobPerformance.js:
//   - PerfRetentionMs is the retention window (7 days).
//   - Persist stores a heartbeat sample indexed by jobId.
//   - Read returns chronological points + computed summary stats.
package jobperf

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/redis/go-redis/v9"
)

// PerfRetentionMs is 7 days in milliseconds (mirrors JOB_PERF_RETENTION_MS).
const PerfRetentionMs = int64(7 * 24 * 60 * 60 * 1000)

// Point is a single heartbeat sample stored in the sorted set.
type Point struct {
	Ts        int64   `json:"ts"`
	CPU       float64 `json:"cpu"`
	RAM       float64 `json:"ram"`
	TotalRAM  float64 `json:"totalRam"`
	ReplicaID string  `json:"replicaId"`
}

// Summary holds computed aggregate stats over all points.
type Summary struct {
	Count       int     `json:"count"`
	DurationMs  int64   `json:"duration_ms"`
	PeakCPU     float64 `json:"peak_cpu"`
	PeakCPUAt   *int64  `json:"peak_cpu_at"`
	AvgCPU      float64 `json:"avg_cpu"`
	PeakRAM     float64 `json:"peak_ram"`
	PeakRAMAt   *int64  `json:"peak_ram_at"`
	TotalRAM    float64 `json:"total_ram"`
}

// Result is the full response payload for /api/jobs/:id/performance.
type Result struct {
	JobID   string   `json:"job_id"`
	Points  []Point  `json:"points"`
	Summary *Summary `json:"summary"`
}

// Persist stores a heartbeat sample in the per-job sorted set (fire-and-forget).
// Heartbeat must contain jobId and replicaId fields; other fields default to 0.
// Mirrors persistJobPerf() in JS.
func Persist(ctx context.Context, rdb *redis.Client, jobID, replicaID string, ts int64, cpu, ram, totalRAM float64) {
	if jobID == "" || replicaID == "" {
		return
	}
	sample, err := json.Marshal(Point{
		Ts:        ts,
		CPU:       cpu,
		RAM:       ram,
		TotalRAM:  totalRAM,
		ReplicaID: replicaID,
	})
	if err != nil {
		log.Printf("[jobperf] marshal failed: %v", err)
		return
	}
	key := redisstore.JobPerfPrefix + jobID
	pipe := rdb.Pipeline()
	pipe.ZAdd(ctx, key, redis.Z{Score: float64(ts), Member: string(sample)})
	pipe.ZRemRangeByScore(ctx, key, "0", fmt.Sprintf("%d", ts-PerfRetentionMs))
	pipe.Expire(ctx, key, time.Duration(PerfRetentionMs)*time.Millisecond)
	if _, err := pipe.Exec(ctx); err != nil {
		log.Printf("[jobperf] persist failed: %v", err)
	}
}

// Read returns all performance points for a job, plus computed summary stats.
// Returns empty points and nil summary when the key does not exist.
// Mirrors readJobPerf() in JS.
func Read(ctx context.Context, rdb *redis.Client, jobID string) Result {
	if jobID == "" {
		return Result{JobID: jobID, Points: []Point{}}
	}
	key := redisstore.JobPerfPrefix + jobID
	raw, err := rdb.ZRangeByScore(ctx, key, &redis.ZRangeBy{
		Min: "-inf",
		Max: "+inf",
	}).Result()
	if err != nil || len(raw) == 0 {
		return Result{JobID: jobID, Points: []Point{}}
	}

	points := make([]Point, 0, len(raw))
	for _, s := range raw {
		var p Point
		if err := json.Unmarshal([]byte(s), &p); err != nil {
			continue
		}
		points = append(points, p)
	}
	if len(points) == 0 {
		return Result{JobID: jobID, Points: points}
	}

	// Compute summary stats.
	var peakCPU, peakRAM, cpuSum float64
	var peakCPUAt, peakRAMAt *int64
	for i := range points {
		p := &points[i]
		if p.CPU > peakCPU {
			peakCPU = p.CPU
			ts := p.Ts
			peakCPUAt = &ts
		}
		if p.RAM > peakRAM {
			peakRAM = p.RAM
			ts := p.Ts
			peakRAMAt = &ts
		}
		cpuSum += p.CPU
	}
	n := len(points)
	summary := &Summary{
		Count:      n,
		DurationMs: points[n-1].Ts - points[0].Ts,
		PeakCPU:    peakCPU,
		PeakCPUAt:  peakCPUAt,
		AvgCPU:     cpuSum / float64(n),
		PeakRAM:    peakRAM,
		PeakRAMAt:  peakRAMAt,
		TotalRAM:   points[n-1].TotalRAM,
	}
	return Result{JobID: jobID, Points: points, Summary: summary}
}
