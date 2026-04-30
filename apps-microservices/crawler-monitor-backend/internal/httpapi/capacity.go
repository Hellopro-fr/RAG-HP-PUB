package httpapi

import (
	"net/http"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/capacityplanning"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/systemstats"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

// capacityWindowMap maps frontend window strings to milliseconds.
// Mirrors JS parseCapacityWindow.
var capacityWindowMap = map[string]int64{
	"15m": 15 * 60 * 1000,
	"1h":  60 * 60 * 1000,
	"6h":  6 * 60 * 60 * 1000,
	"24h": 24 * 60 * 60 * 1000,
}

func parseCapacityWindow(s string) (int64, string) {
	if s == "" {
		s = "1h"
	}
	ms, ok := capacityWindowMap[s]
	if !ok {
		return 60 * 60 * 1000, "1h"
	}
	return ms, s
}

func capacityGetHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		running, max, err := rs.GetCapacity(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to read capacity")
			return
		}
		WriteJSON(w, 200, map[string]any{
			"running_jobs":    running,
			"max_global_jobs": max,
			"is_full":         max > 0 && running >= max,
		})
	}
}

// capacityHistoryHandler returns capacity snapshots over the requested window.
// Response: { window, count, points: [{ts, running, max, full}, …] }
func capacityHistoryHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		windowMs, windowStr := parseCapacityWindow(r.URL.Query().Get("window"))
		points, err := rs.ReadCapacityHistory(r.Context(), windowMs)
		if err != nil {
			WriteError(w, 500, "Failed to read capacity history")
			return
		}
		if points == nil {
			points = []systemstats.CapacityPoint{}
		}
		WriteJSON(w, http.StatusOK, map[string]any{
			"window": windowStr,
			"count":  len(points),
			"points": points,
		})
	}
}

// capacityPlanningRAMHandler aggregates per-replica RAM usage over the requested
// window. Window=1h reads replica:history; window=24h|7d scans job:perf:*.
// Response: { window, window_ms, generated_at, replicas:[…], totals:{…} }
func capacityPlanningRAMHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		windowKey := r.URL.Query().Get("window")
		if windowKey == "" {
			windowKey = "1h"
		}
		windowMs, err := capacityplanning.ParseWindow(windowKey)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		ctx := r.Context()
		var pointsByReplica map[string][]capacityplanning.Sample
		if windowKey == "1h" {
			pointsByReplica, err = rs.ReplicaHistoryAsSamples(ctx, windowMs)
		} else {
			pointsByReplica, err = rs.ScanJobPerfByReplica(ctx, windowMs)
		}
		if err != nil {
			WriteError(w, 500, "Failed to load capacity planning data")
			return
		}
		replicas := capacityplanning.AggregateByReplica(pointsByReplica)
		totals := capacityplanning.ComputeTotals(replicas)
		WriteJSON(w, http.StatusOK, map[string]any{
			"window":       windowKey,
			"window_ms":    windowMs,
			"generated_at": time.Now().UTC().Format(time.RFC3339Nano),
			"replicas":     replicas,
			"totals":       totals,
		})
	}
}
