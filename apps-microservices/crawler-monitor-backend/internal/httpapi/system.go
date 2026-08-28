package httpapi

import (
	"net/http"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/datetime"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/domain/systemstats"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
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
			j.StartTime = datetime.AnyToISO(rj["start_time"])
			j.EndTime = datetime.AnyToISO(rj["end_time"])
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

// pubsubStaleMs : au-dela de 60s sans message Redis alors que des crawls
// tournent, l'abonnement pub/sub est considere comme mort.
const pubsubStaleMs = int64(60 * 1000)

// systemHealthHandler handles GET /api/system/health
// Retourne la connectivite Redis, le nombre de clients WS, la fraicheur de
// l'abonnement pub/sub et le statut global.
func systemHealthHandler(rs *redisstore.Client, hub *ws.Hub, ps *ws.PubSub) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		redisConnected := rs.Raw().Ping(r.Context()).Err() == nil
		status := "ok"
		if !redisConnected {
			status = "degraded"
		}
		var wsCount int64
		if hub != nil {
			wsCount = hub.Count()
		}
		var lastMessage int64
		if ps != nil {
			lastMessage = ps.LastMessageAt()
		}
		running, _, _ := rs.GetCapacity(r.Context())
		// age = -1 tant qu'aucun message n'est arrive (pub/sub jamais
		// demarre, ou service qui vient de booter) : ce cas n'est pas une
		// panne, alors que lastMessage=0 le faisait passer pour un silence
		// de 57 ans.
		age := int64(-1)
		if lastMessage > 0 {
			age = time.Now().UnixMilli() - lastMessage
		}
		// Silence du pub/sub avec des crawls actifs = plus aucun heartbeat
		// n'arrive : la persistance et la diffusion temps reel sont a l'arret.
		if lastMessage > 0 && running > 0 && age > pubsubStaleMs {
			status = "degraded"
		}
		WriteJSON(w, 200, map[string]any{
			"redis_connected":            redisConnected,
			"ws_clients_count":           wsCount,
			"pubsub_last_message_ms":     lastMessage,
			"pubsub_last_message_age_ms": age,
			"running_count":              running,
			"status":                     status,
		})
	}
}
