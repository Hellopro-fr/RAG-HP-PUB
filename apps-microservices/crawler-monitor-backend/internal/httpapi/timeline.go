package httpapi

import (
	"net/http"
	"strings"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/timeline"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
)

// timelineHandler implements GET /api/timeline.
// Query params:
//
//	window — preset key: '1h' (default), '6h', '24h', '7d'
//	from, to — ISO dates for a custom range (overrides window)
func timelineHandler(rs *redisstore.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		windowKey := q.Get("window")
		if windowKey == "" {
			windowKey = "1h"
		}
		opts := timeline.ComputeOptions{
			From: q.Get("from"),
			To:   q.Get("to"),
		}

		rawJobs, err := rs.ListJobs(r.Context())
		if err != nil {
			WriteError(w, 500, "Failed to list jobs")
			return
		}

		jobs := make([]timeline.Job, 0, len(rawJobs))
		for _, rj := range rawJobs {
			j := rawJobToTimelineJob(rj)
			jobs = append(jobs, j)
		}

		result, err := timeline.ComputeTimeline(jobs, windowKey, opts)
		if err != nil {
			msg := err.Error()
			if strings.Contains(msg, "Invalid window") || strings.Contains(msg, "Invalid 'from'") {
				WriteError(w, 400, msg)
			} else {
				WriteError(w, 500, msg)
			}
			return
		}

		WriteJSON(w, 200, result)
	}
}

// rawJobToTimelineJob converts a Redis raw job map to a timeline.Job.
func rawJobToTimelineJob(rj redisstore.RawJob) timeline.Job {
	startTime, _ := rj["start_time"].(string)
	status, _ := rj["status"].(string)
	oom := 0
	switch v := rj["oom_restart_count"].(type) {
	case float64:
		oom = int(v)
	case int:
		oom = v
	case int64:
		oom = int(v)
	}
	return timeline.Job{
		StartTime:       startTime,
		Status:          status,
		OomRestartCount: oom,
	}
}
