// Package alerts implements the rules engine for the crawler monitor.
//
// Pure functions — given recent state (jobs, capacity history, replicas history,
// failed callback count), evaluate the configured rules and return a normalized
// list of alerts.
//
// Mirrors src/lib/alerts.js exactly (same IDs, severities, metadata shapes, sort order).
package alerts

import (
	"fmt"
	"math"
	"sort"
	"strings"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/datetime"
)

// Thresholds holds all configurable alert thresholds.
type Thresholds struct {
	ErrorRateThreshold  float64
	ErrorRateMinJobs    int
	OomSpikeThreshold   int
	ReplicaHighCpu      float64
	ReplicaHighCpuDurMs int64
	CapacityFullDurMs   int64
	CallbacksFailedMin  int
}

// DefaultThresholds returns the hardcoded Phase 3 thresholds.
// Mirrors JS DEFAULT_THRESHOLDS (env-resolved values).
func DefaultThresholds() Thresholds {
	return Thresholds{
		ErrorRateThreshold:  0.05,
		ErrorRateMinJobs:    5,
		OomSpikeThreshold:   3,
		ReplicaHighCpu:      0.85,
		ReplicaHighCpuDurMs: 240_000,
		CapacityFullDurMs:   300_000,
		CallbacksFailedMin:  1,
	}
}

const oneHourMs = int64(60 * 60 * 1000)

// Alert is a normalized alert object.
type Alert struct {
	ID       string         `json:"id"`
	Severity string         `json:"severity"`
	Kind     string         `json:"kind"`
	Message  string         `json:"message"`
	Since    *int64         `json:"since"`
	Metadata map[string]any `json:"metadata"`
}

// Job is the minimal job view needed for alert evaluation.
type Job struct {
	StartTime       string
	Status          string
	OomRestartCount int
}

// CapacityPoint is a single capacity history snapshot.
type CapacityPoint struct {
	Ts   int64
	Full bool
}

// CpuPoint is a single CPU history sample for one replica.
type CpuPoint struct {
	Ts  int64
	CPU float64
}

/* ---------- Individual rules ---------- */

// EvalErrorRate evaluates the error_rate_high rule over the last 1h.
// Returns nil if the threshold is not exceeded.
func EvalErrorRate(jobs []Job, nowMs int64, t Thresholds) *Alert {
	cutoff := nowMs - oneHourMs
	var failed, finished int
	for _, j := range jobs {
		ts := parseJobTimeMs(j.StartTime)
		if ts < 0 || ts < cutoff {
			continue
		}
		status := strings.ToLower(j.Status)
		if status == "failed" {
			failed++
		} else if status == "finished" || status == "archived" {
			finished++
		}
	}
	completed := failed + finished
	if completed < t.ErrorRateMinJobs {
		return nil
	}
	rate := float64(failed) / float64(completed)
	if rate < t.ErrorRateThreshold {
		return nil
	}
	return &Alert{
		ID:       "error_rate_high:1h",
		Severity: "warn",
		Kind:     "error_rate_high",
		Message:  fmt.Sprintf("Taux d'erreur %.1f%% sur 1h (%d/%d)", rate*100, failed, completed),
		Since:    nil,
		Metadata: map[string]any{
			"rate":      rate,
			"failed":    failed,
			"completed": completed,
			"window":    "1h",
			"threshold": t.ErrorRateThreshold,
		},
	}
}

// EvalOomSpike evaluates the oom_spike rule: sum of oom_restart_count >= threshold over 1h.
func EvalOomSpike(jobs []Job, nowMs int64, t Thresholds) *Alert {
	cutoff := nowMs - oneHourMs
	var total int
	for _, j := range jobs {
		ts := parseJobTimeMs(j.StartTime)
		if ts < 0 || ts < cutoff {
			continue
		}
		total += j.OomRestartCount
	}
	if total < t.OomSpikeThreshold {
		return nil
	}
	return &Alert{
		ID:       "oom_spike:1h",
		Severity: "critical",
		Kind:     "oom_spike",
		Message:  fmt.Sprintf("%d OOM restarts cumulés sur 1h", total),
		Since:    nil,
		Metadata: map[string]any{
			"total":     total,
			"window":    "1h",
			"threshold": t.OomSpikeThreshold,
		},
	}
}

// EvalReplicaHighCpu evaluates sustained high CPU for a single replica.
// points must be in chronological order (oldest first).
func EvalReplicaHighCpu(replicaID string, points []CpuPoint, nowMs int64, t Thresholds) *Alert {
	if len(points) == 0 {
		return nil
	}
	last := points[len(points)-1]
	if last.CPU <= t.ReplicaHighCpu {
		return nil
	}
	// Walk back to find streak start.
	streakStart := last.Ts
	for i := len(points) - 2; i >= 0; i-- {
		if points[i].CPU > t.ReplicaHighCpu {
			streakStart = points[i].Ts
		} else {
			break
		}
	}
	dur := last.Ts - streakStart
	if dur < t.ReplicaHighCpuDurMs {
		return nil
	}
	// Slice replicaID to 12 chars for the message, matching JS slice(0,12).
	shortID := replicaID
	if len(shortID) > 12 {
		shortID = shortID[:12]
	}
	cpuPct := math.Round(t.ReplicaHighCpu * 100)
	durMin := int(math.Floor(float64(dur) / 60000))
	since := streakStart
	return &Alert{
		ID:       fmt.Sprintf("replica_high_cpu:%s", replicaID),
		Severity: "warn",
		Kind:     "replica_high_cpu_sustained",
		Message:  fmt.Sprintf("Replica %s : CPU > %.0f%% depuis %d min", shortID, cpuPct, durMin),
		Since:    &since,
		Metadata: map[string]any{
			"replicaId":   replicaID,
			"current_cpu": last.CPU,
			"duration_ms": dur,
			"threshold":   t.ReplicaHighCpu,
		},
	}
}

// EvalCapacitySaturation evaluates sustained capacity saturation.
// points must be in chronological order (oldest first).
func EvalCapacitySaturation(points []CapacityPoint, nowMs int64, t Thresholds) *Alert {
	if len(points) == 0 {
		return nil
	}
	last := points[len(points)-1]
	if !last.Full {
		return nil
	}
	streakStart := last.Ts
	for i := len(points) - 2; i >= 0; i-- {
		if points[i].Full {
			streakStart = points[i].Ts
		} else {
			break
		}
	}
	dur := last.Ts - streakStart
	if dur < t.CapacityFullDurMs {
		return nil
	}
	durMin := int(math.Floor(float64(dur) / 60000))
	since := streakStart
	return &Alert{
		ID:       "capacity_full",
		Severity: "critical",
		Kind:     "capacity_full_sustained",
		Message:  fmt.Sprintf("Capacité saturée depuis %d min", durMin),
		Since:    &since,
		Metadata: map[string]any{
			"duration_ms":  dur,
			"threshold_ms": t.CapacityFullDurMs,
		},
	}
}

// EvalCallbacksFailing evaluates whether the failed-callback count meets the minimum.
func EvalCallbacksFailing(failedCallbackCount int, t Thresholds) *Alert {
	if failedCallbackCount < t.CallbacksFailedMin {
		return nil
	}
	suffix := ""
	if failedCallbackCount > 1 {
		suffix = "s"
	}
	return &Alert{
		ID:       "callbacks_failing",
		Severity: "critical",
		Kind:     "callbacks_failing",
		Message:  fmt.Sprintf("%d callback%s en échec à rejouer", failedCallbackCount, suffix),
		Since:    nil,
		Metadata: map[string]any{
			"count": failedCallbackCount,
		},
	}
}

/* ---------- Aggregator ---------- */

// Inputs holds all the data needed by Evaluate.
type Inputs struct {
	Jobs                []Job
	CapacityPoints      []CapacityPoint
	ReplicasHistory     map[string][]CpuPoint // replicaID -> chronological CPU points
	FailedCallbackCount int
}

// Evaluate runs every rule and returns the non-nil alerts, sorted critical-first
// then by kind (lexicographic). Mirrors JS evaluateAlerts.
func Evaluate(inputs Inputs, nowMs int64, t Thresholds) []Alert {
	var out []Alert

	if a := EvalErrorRate(inputs.Jobs, nowMs, t); a != nil {
		out = append(out, *a)
	}
	if a := EvalOomSpike(inputs.Jobs, nowMs, t); a != nil {
		out = append(out, *a)
	}
	if a := EvalCapacitySaturation(inputs.CapacityPoints, nowMs, t); a != nil {
		out = append(out, *a)
	}
	if a := EvalCallbacksFailing(inputs.FailedCallbackCount, t); a != nil {
		out = append(out, *a)
	}
	for id, points := range inputs.ReplicasHistory {
		if a := EvalReplicaHighCpu(id, points, nowMs, t); a != nil {
			out = append(out, *a)
		}
	}

	sevWeight := map[string]int{"critical": 0, "warn": 1, "info": 2}
	sort.SliceStable(out, func(i, j int) bool {
		wi := sevWeight[out[i].Severity]
		wj := sevWeight[out[j].Severity]
		if wi != wj {
			return wi < wj
		}
		return strings.Compare(out[i].Kind, out[j].Kind) < 0
	})

	if out == nil {
		out = []Alert{}
	}
	return out
}

/* ---------- helpers ---------- */

// parseJobTimeMs parses an ISO timestamp string and returns UnixMilli, or -1.
func parseJobTimeMs(s string) int64 {
	return datetime.ParseStringMs(s)
}
