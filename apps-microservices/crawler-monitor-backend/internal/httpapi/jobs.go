package httpapi

import (
	"errors"
	"net/http"
	"sort"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
	"github.com/redis/go-redis/v9"
)

func jobsListHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		jobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to list jobs")
			return
		}
		sort.SliceStable(jobs, func(i, j int) bool {
			ti, _ := jobs[i]["start_time"].(string)
			tj, _ := jobs[j]["start_time"].(string)
			return ti > tj
		})
		WriteJSON(w, 200, jobs)
	}
}

func jobsDetailsHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := chi.URLParam(r, "id")
		job, err := rs.GetJob(r.Context(), id)
		if errors.Is(err, redis.Nil) {
			WriteError(w, 404, "Job not found")
			return
		}
		if err != nil {
			WriteError(w, 500, "Failed to read job")
			return
		}
		WriteJSON(w, 200, job)
	}
}
