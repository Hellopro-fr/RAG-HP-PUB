package httpapi

import (
	"net/http"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/systemstats"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

// systemStatsHandler handles GET /api/system/stats?window=1h|24h|7d
// Aggregates job stats and capacity saturation for the given window.
func systemStatsHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		windowStr := r.URL.Query().Get("window")
		if windowStr == "" {
			windowStr = "24h"
		}
		windowMs, err := systemstats.ParseStatsWindow(windowStr)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}

		// Load all jobs.
		rawJobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to load jobs")
			return
		}

		// Convert redisstore.RawJob (map[string]any) → systemstats.RawJob.
		jobs := make([]systemstats.RawJob, 0, len(rawJobs))
		for _, rj := range rawJobs {
			var j systemstats.RawJob
			if v, ok := rj["start_time"].(string); ok {
				j.StartTime = v
			}
			if v, ok := rj["end_time"].(string); ok {
				j.EndTime = v
			}
			if v, ok := rj["status"].(string); ok {
				j.Status = v
			}
			if v, ok := rj["crawl_mode"].(string); ok {
				j.CrawlMode = v
			}
			if v, ok := rj["oom_restart_count"].(float64); ok {
				j.OOMRestartCount = int(v)
			}
			jobs = append(jobs, j)
		}

		now := time.Now().UnixMilli()
		jobStats := systemstats.AggregateJobStats(jobs, now, windowMs)

		// Capacity saturation — best effort.
		var satStats systemstats.SaturationStats
		if points, err := rs.ReadCapacityHistory(r.Context(), windowMs); err == nil {
			satStats = systemstats.AggregateSaturation(points, windowMs)
		}

		WriteJSON(w, 200, systemstats.SystemStatsResult{
			Jobs:     jobStats,
			Capacity: satStats,
		})
	}
}

// systemHealthHandler handles GET /api/system/health
// Returns Redis connectivity, ws_clients_count (0 for now), and overall status.
func systemHealthHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		redisConnected := rs.Raw().Ping(r.Context()).Err() == nil
		status := "ok"
		if !redisConnected {
			status = "degraded"
		}
		WriteJSON(w, 200, map[string]any{
			"redis_connected":  redisConnected,
			"ws_clients_count": 0, // Phase 5 will add WebSocket hub
			"status":           status,
		})
	}
}
