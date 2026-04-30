package httpapi

import (
	"context"
	"errors"
	"io/fs"
	"net/http"
	"sort"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/joblog"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
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

// jobsDetailsHandler returns the job document merged with crawler.log parse
// results (stats / errors / warnings / rawContent / hasStats) when the log
// file exists. Mirrors server.js:462-501.
func jobsDetailsHandler(rs *redisstore.Client, fileStore *filestore.Storage) http.HandlerFunc {
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
		mergeJobLog(r.Context(), fileStore, id, job)
		WriteJSON(w, 200, job)
	}
}

// mergeJobLog reads <id>/crawler.log via the FileStore and, if found, merges
// the parsed payload into job. Missing log file is non-fatal — defaults are
// injected so the frontend always finds the expected fields.
func mergeJobLog(ctx context.Context, fileStore *filestore.Storage, id string, job redisstore.RawJob) {
	defaults := func() {
		if _, ok := job["stats"]; !ok {
			job["stats"] = nil
		}
		if _, ok := job["errors"]; !ok {
			job["errors"] = []string{}
		}
		if _, ok := job["warnings"]; !ok {
			job["warnings"] = []string{}
		}
		if _, ok := job["rawContent"]; !ok {
			job["rawContent"] = ""
		}
		if _, ok := job["hasStats"]; !ok {
			job["hasStats"] = false
		}
	}
	if fileStore == nil {
		defaults()
		return
	}
	raw, err := fileStore.Read(ctx, id, "crawler.log")
	if err != nil {
		if !errors.Is(err, fs.ErrNotExist) {
			defaults()
			return
		}
		defaults()
		return
	}
	parsed := joblog.Parse(string(raw))
	job["stats"] = parsed.Stats
	job["errors"] = parsed.Errors
	job["warnings"] = parsed.Warnings
	job["rawContent"] = parsed.RawContent
	job["hasStats"] = parsed.HasStats
}
