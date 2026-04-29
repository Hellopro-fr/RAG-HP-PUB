package httpapi

import (
	"net/http"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/jobperf"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
)

// jobsPerformanceHandler handles GET /api/jobs/{id}/performance.
// Returns per-job CPU/RAM performance history stored in Redis sorted-set job:perf:<jobId>.
// Mirrors the Node endpoint at server.js:314.
func jobsPerformanceHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		result := jobperf.Read(r.Context(), rs.Raw(), id)
		WriteJSON(w, 200, result)
	}
}
