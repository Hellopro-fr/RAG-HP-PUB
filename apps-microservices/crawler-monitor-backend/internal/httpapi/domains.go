package httpapi

import (
	"net/http"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/domains"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
)

// rawJobsToDomain converts redisstore.RawJob (map[string]any) to domains.RawJob.
func rawJobsToDomain(rawJobs []redisstore.RawJob) []domains.RawJob {
	out := make([]domains.RawJob, 0, len(rawJobs))
	for _, rj := range rawJobs {
		var j domains.RawJob
		if v, ok := rj["id"].(string); ok {
			j.ID = v
		} else if v, ok := rj["_id"].(string); ok {
			j.ID = v
		}
		if v, ok := rj["domain"].(string); ok {
			j.Domain = v
		}
		if v, ok := rj["start_time"].(string); ok {
			j.StartTime = v
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
		if v, ok := rj["previous_crawl_id"].(string); ok {
			j.PreviousCrawlID = v
		}
		out = append(out, j)
	}
	return out
}

// domainsListHandler handles GET /api/domains?window=24h|7d|30d
// Returns aggregated domain summary list sorted by last_run_at desc.
func domainsListHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		windowStr := r.URL.Query().Get("window")
		if windowStr == "" {
			windowStr = "7d"
		}
		windowMs, err := domains.ParseDomainWindow(windowStr)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		rawJobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to load jobs")
			return
		}
		jobs := rawJobsToDomain(rawJobs)
		now := time.Now().UnixMilli()
		result := domains.AggregateDomains(jobs, now, windowMs)
		WriteJSON(w, 200, result)
	}
}

// domainsGetHandler handles GET /api/domains/{domain}?window=24h|7d|30d
// Returns job list + run chain for a single domain.
func domainsGetHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		domain := chi.URLParam(r, "domain")
		windowStr := r.URL.Query().Get("window")
		if windowStr == "" {
			windowStr = "7d"
		}
		windowMs, err := domains.ParseDomainWindow(windowStr)
		if err != nil {
			WriteError(w, 400, err.Error())
			return
		}
		rawJobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to load jobs")
			return
		}
		jobs := rawJobsToDomain(rawJobs)
		now := time.Now().UnixMilli()
		detail := domains.JobsForDomain(jobs, domain, windowMs, now)
		WriteJSON(w, 200, detail)
	}
}
