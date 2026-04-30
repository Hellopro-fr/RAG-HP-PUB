package httpapi

import (
	"net/http"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/replicahistory"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
)

// replicasHistoryHandler handles GET /api/replicas/history?window=15m|1h
// Returns history for ALL known replicas.
func replicasHistoryHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		windowStr := r.URL.Query().Get("window")
		if windowStr == "" {
			windowStr = "1h"
		}
		windowMs, err := replicahistory.ParseReplicaWindow(windowStr)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		all, err := rs.ReadAllReplicasHistory(r.Context(), windowMs)
		if err != nil {
			WriteError(w, 500, "Failed to read replicas history")
			return
		}
		if all == nil {
			all = map[string][]replicahistory.HeartbeatSample{}
		}
		WriteJSON(w, 200, map[string]any{
			"window":   windowStr,
			"replicas": all,
		})
	}
}

// replicaHistoryByIDHandler handles GET /api/replicas/{id}/history?window=15m|1h
// Returns history for a single replica.
func replicaHistoryByIDHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		windowStr := r.URL.Query().Get("window")
		if windowStr == "" {
			windowStr = "1h"
		}
		windowMs, err := replicahistory.ParseReplicaWindow(windowStr)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		points, err := rs.ReadReplicaHistory(r.Context(), id, windowMs)
		if err != nil {
			WriteError(w, 500, "Failed to read replica history")
			return
		}
		WriteJSON(w, 200, map[string]any{
			"replica_id": id,
			"points":     points,
		})
	}
}
