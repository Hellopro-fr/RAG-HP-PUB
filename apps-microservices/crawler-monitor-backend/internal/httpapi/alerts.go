package httpapi

import (
	"net/http"
	"strings"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/datetime"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/alerts"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/replicahistory"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/systemstats"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

// alertsHandler implements GET /api/alerts.
// Loads jobs, capacity history, replicas history, and failed-callback count from
// Redis, then evaluates the alerts rules and returns the sorted result.
func alertsHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()

		// Load jobs.
		rawJobs, err := rs.ListJobs(ctx)
		if err != nil {
			WriteError(w, 500, "Failed to list jobs")
			return
		}
		jobs := make([]alerts.Job, 0, len(rawJobs))
		for _, rj := range rawJobs {
			jobs = append(jobs, rawJobToAlertJob(rj))
		}

		// Load capacity history (1h window for saturation check).
		capPoints, err := rs.ReadCapacityHistory(ctx, int64(60*60*1000))
		if err != nil {
			capPoints = nil // tolerate
		}
		alertCapPoints := toAlertCapacityPoints(capPoints)

		// Load all replicas history (1h window for CPU check).
		replicasHistory, err := rs.ReadAllReplicasHistory(ctx, int64(60*60*1000))
		if err != nil {
			replicasHistory = nil
		}
		alertReplicasHistory := toAlertReplicasHistory(replicasHistory)

		// Load failed-callback count.
		failedCount := 0
		n, err := rs.Raw().LLen(ctx, redisstore.FailedCallbacksKey).Result()
		if err == nil {
			failedCount = int(n)
		}

		inputs := alerts.Inputs{
			Jobs:                jobs,
			CapacityPoints:      alertCapPoints,
			ReplicasHistory:     alertReplicasHistory,
			FailedCallbackCount: failedCount,
		}

		nowMs := time.Now().UnixMilli()
		thresholds := alerts.DefaultThresholds()
		result := alerts.Evaluate(inputs, nowMs, thresholds)
		if result == nil {
			result = []alerts.Alert{}
		}
		WriteJSON(w, 200, map[string]any{
			"generated_at": time.UnixMilli(nowMs).UTC().Format(time.RFC3339Nano),
			"thresholds":   thresholds,
			"count":        len(result),
			"alerts":       result,
		})
	}
}

// rawJobToAlertJob converts a Redis raw job map to an alerts.Job.
// start_time may be stored as ISO string or Unix-ms number (Python crawler).
func rawJobToAlertJob(rj redisstore.RawJob) alerts.Job {
	startTime := datetime.AnyToISO(rj["start_time"])
	status, _ := rj["status"].(string)
	_ = strings.ToLower // ensure import used
	oom := 0
	switch v := rj["oom_restart_count"].(type) {
	case float64:
		oom = int(v)
	case int:
		oom = v
	case int64:
		oom = int(v)
	}
	return alerts.Job{
		StartTime:       startTime,
		Status:          status,
		OomRestartCount: oom,
	}
}

// toAlertCapacityPoints converts systemstats.CapacityPoint slice to alerts.CapacityPoint slice.
func toAlertCapacityPoints(pts []systemstats.CapacityPoint) []alerts.CapacityPoint {
	out := make([]alerts.CapacityPoint, 0, len(pts))
	for _, p := range pts {
		out = append(out, alerts.CapacityPoint{Ts: p.Ts, Full: p.Full})
	}
	return out
}

// toAlertReplicasHistory converts replicahistory.HeartbeatSample maps to alerts.CpuPoint maps.
func toAlertReplicasHistory(src map[string][]replicahistory.HeartbeatSample) map[string][]alerts.CpuPoint {
	if src == nil {
		return nil
	}
	out := make(map[string][]alerts.CpuPoint, len(src))
	for id, samples := range src {
		pts := make([]alerts.CpuPoint, 0, len(samples))
		for _, s := range samples {
			pts = append(pts, alerts.CpuPoint{Ts: s.Ts, CPU: s.CPU})
		}
		out[id] = pts
	}
	return out
}
