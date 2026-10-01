// Package systemstats provides aggregated system metric helpers for time windows.
//
// Sources:
//   - Jobs: Redis MGET on crawl_job:* keys (filter by start_time)
//   - Capacity: optional, from capacity:history:zset
package systemstats

import (
	"errors"
	"math"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/datetime"
)

// WINDOW_MAP mirrors the JS WINDOW_MAP for system stats.
var windowMap = map[string]int64{
	"1h":  3600000,
	"24h": 86400000,
	"7d":  604800000,
}

// ParseStatsWindow parses "1h", "24h" or "7d" and returns the duration in ms.
func ParseStatsWindow(input string) (int64, error) {
	ms, ok := windowMap[input]
	if !ok {
		return 0, errors.New("Invalid window. Use '1h', '24h' or '7d'.")
	}
	return ms, nil
}

// StatusCounts mirrors the counts object in aggregateJobStats.
type StatusCounts struct {
	Finished      int `json:"finished"`
	Failed        int `json:"failed"`
	Running       int `json:"running"`
	Archived      int `json:"archived"`
	RestartingOOM int `json:"restarting_oom"`
	Stopping      int `json:"stopping"`
	Other         int `json:"other"`
}

// JobStats is the output of AggregateJobStats.
type JobStats struct {
	Total           int          `json:"total"`
	Counts          StatusCounts `json:"counts"`
	SuccessRate     *float64     `json:"success_rate"`      // 0..1 or null
	AvgDurationMs   *int64       `json:"avg_duration_ms"`   // null if no finished jobs
	OOMRestartsTotal int         `json:"oom_restarts_total"`
	UpdateModeCount int          `json:"update_mode_count"`
}

// RawJob is a minimal view of a crawl job used for aggregation.
// Fields match Redis job JSON keys (snake_case).
type RawJob struct {
	StartTime       string  `json:"start_time"`
	EndTime         string  `json:"end_time"`
	Status          string  `json:"status"`
	CrawlMode       string  `json:"crawl_mode"`
	OOMRestartCount int     `json:"oom_restart_count"`
}

// AggregateJobStats aggregates metrics from a list of jobs that started within windowMs.
// Pure function — no side effects.
func AggregateJobStats(jobs []RawJob, nowMs, windowMs int64) JobStats {
	cutoff := nowMs - windowMs

	var inWindow []RawJob
	for _, j := range jobs {
		tMs := datetime.ParseStringMs(j.StartTime)
		if tMs < 0 {
			continue
		}
		if tMs >= cutoff {
			inWindow = append(inWindow, j)
		}
	}

	counts := StatusCounts{}
	oomTotal := 0
	updateMode := 0
	var durationsMs []int64

	for _, j := range inWindow {
		status := j.Status
		if status == "" {
			status = "other"
		}
		switch status {
		case "finished":
			counts.Finished++
		case "failed":
			counts.Failed++
		case "running":
			counts.Running++
		case "archived":
			counts.Archived++
		case "restarting_oom":
			counts.RestartingOOM++
		case "stopping":
			counts.Stopping++
		default:
			counts.Other++
		}
		oomTotal += j.OOMRestartCount
		if j.CrawlMode == "update" {
			updateMode++
		}
		if status == "finished" && j.StartTime != "" && j.EndTime != "" {
			stMs := datetime.ParseStringMs(j.StartTime)
			etMs := datetime.ParseStringMs(j.EndTime)
			if stMs >= 0 && etMs >= 0 {
				d := etMs - stMs
				if d >= 0 {
					durationsMs = append(durationsMs, d)
				}
			}
		}
	}

	total := len(inWindow)
	completed := counts.Finished + counts.Failed
	var successRate *float64
	if completed > 0 {
		sr := float64(counts.Finished) / float64(completed)
		successRate = &sr
	}
	var avgDurationMs *int64
	if len(durationsMs) > 0 {
		sum := int64(0)
		for _, d := range durationsMs {
			sum += d
		}
		avg := int64(math.Round(float64(sum) / float64(len(durationsMs))))
		avgDurationMs = &avg
	}

	return JobStats{
		Total:            total,
		Counts:           counts,
		SuccessRate:      successRate,
		AvgDurationMs:    avgDurationMs,
		OOMRestartsTotal: oomTotal,
		UpdateModeCount:  updateMode,
	}
}

// CapacityPoint is a single capacity history snapshot.
type CapacityPoint struct {
	Ts      int64 `json:"ts"`
	Running int   `json:"running"`
	Max     int   `json:"max"`
	Full    bool  `json:"full"`
}

// SaturationStats is the output of AggregateSaturation.
type SaturationStats struct {
	SaturatedSeconds int      `json:"saturated_seconds"`
	SaturatedPct     *float64 `json:"saturated_pct"` // null if windowMs == 0
}

// AggregateSaturation sums intervals where full=true.
// Mirrors JS aggregateSaturation exactly.
func AggregateSaturation(points []CapacityPoint, windowMs int64) SaturationStats {
	if len(points) < 2 {
		return SaturationStats{SaturatedSeconds: 0, SaturatedPct: nil}
	}
	var saturatedMs int64
	for i := 1; i < len(points); i++ {
		prev := points[i-1]
		curr := points[i]
		if prev.Full {
			dt := curr.Ts - prev.Ts
			if dt > 0 {
				saturatedMs += dt
			}
		}
	}
	secs := int(math.Round(float64(saturatedMs) / 1000.0))
	var pct *float64
	if windowMs > 0 {
		p := float64(saturatedMs) / float64(windowMs)
		pct = &p
	}
	return SaturationStats{
		SaturatedSeconds: secs,
		SaturatedPct:     pct,
	}
}

// SystemStatsResult is the combined output for /api/system/stats.
type SystemStatsResult struct {
	Jobs     JobStats        `json:"jobs"`
	Capacity SaturationStats `json:"capacity"`
}
