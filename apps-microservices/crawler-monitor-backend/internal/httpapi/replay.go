package httpapi

import (
	"errors"
	"net/http"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/queue"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
	"github.com/redis/go-redis/v9"
)

// jobsReplayHandler handles GET /api/jobs/{id}/replay.
// Agrège points de performance, métadonnées Redis, événements dérivés et actions d'audit.
// Mirrors server.js:320-454.
func jobsReplayHandler(rs *redisstore.Client, as *auditstore.Local, cpuThreshold float64) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		result, err := queue.ComputeReplay(r.Context(), rs.Raw(), as, id, cpuThreshold)
		if err != nil {
			if errors.Is(err, redis.Nil) {
				WriteError(w, 404, "Job not found")
				return
			}
			WriteError(w, 500, "Failed to build replay")
			return
		}
		WriteJSON(w, 200, result)
	}
}
