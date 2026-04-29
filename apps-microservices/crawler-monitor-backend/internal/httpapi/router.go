package httpapi

import (
	"context"
	"net/http"
	"time"

	"github.com/Hellopro-fr/crawler-monitor-backend/internal/config"
	mw "github.com/Hellopro-fr/crawler-monitor-backend/internal/httpapi/middleware"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/auditstore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/filestore"
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/store/redisstore"
	"github.com/go-chi/chi/v5"
)

type Deps struct {
	Version    string
	Config     *config.Config
	RedisStore *redisstore.Client
	FileStore  *filestore.Storage
	AuditStore AuditAppender
}

// auditStoreAdapter adapts *auditstore.Local to AuditAppender.
type auditStoreAdapter struct{ s *auditstore.Local }

func (a *auditStoreAdapter) Append(ctx context.Context, e map[string]any) error {
	return a.s.Append(ctx, e)
}

// WrapAuditStore wraps an *auditstore.Local as an AuditAppender.
func WrapAuditStore(s *auditstore.Local) AuditAppender {
	return &auditStoreAdapter{s: s}
}

func NewRouter(d Deps) http.Handler {
	r := chi.NewRouter()
	r.Use(mw.SecurityHeaders)

	if d.Config != nil && len(d.Config.CorsAllowedOrigins) > 0 {
		r.Use(mw.CORS(d.Config.CorsAllowedOrigins))
	}
	if d.Config != nil && d.Config.RateLimitMax > 0 {
		r.Use(mw.RateLimitByIP(d.Config.RateLimitMax,
			time.Duration(d.Config.RateLimitWindowMs)*time.Millisecond))
	}

	r.Get("/health", healthHandler(d.Version))

	if d.Config != nil {
		r.Post("/api/login", loginHandler(d.Config.AdminPasswordHash, d.Config.JWTSecret, d.AuditStore))
	}

	if d.Config != nil && d.RedisStore != nil {
		r.Group(func(rt chi.Router) {
			rt.Use(mw.JWTAuth(d.Config.JWTSecret))

			rt.Route("/api/jobs", func(rt chi.Router) {
				rt.Get("/", jobsListHandler(d.RedisStore))
				rt.Get("/{id}/details", jobsDetailsHandler(d.RedisStore))
				rt.Get("/{id}/performance", jobsPerformanceHandler(d.RedisStore))
				// Replay : best-effort audit (nil auditstore is tolerated)
				var replayCPU float64 = 0.85
				if d.Config != nil {
					replayCPU = d.Config.ReplayHighCPU
				}
				if adapted, ok := d.AuditStore.(*auditStoreAdapter); ok {
					rt.Get("/{id}/replay", jobsReplayHandler(d.RedisStore, adapted.s, replayCPU))
				} else {
					rt.Get("/{id}/replay", jobsReplayHandler(d.RedisStore, nil, replayCPU))
				}
				if d.FileStore != nil {
					rt.Get("/{id}/dataset/counts", datasetCountsHandler(d.FileStore))
					rt.Get("/{id}/dataset/urls", datasetURLsHandler(d.FileStore))
					rt.Get("/{id}/dataset/analyze", datasetAnalyzeHandler(d.FileStore))
					rt.Post("/{id}/dataset/deduplicate", datasetDeduplicateHandler(d.FileStore))
					rt.Get("/{id}/request-queues", queuesListHandler(d.FileStore))
					// Statiques avant les routes paramétrées pour que chi route correctement
					rt.Get("/{id}/request-queues/analyze", queuesAnalyzeHandler(d.FileStore))
					rt.Post("/{id}/request-queues/clean-patterns", queuesCleanPatternsHandler(d.FileStore))
					rt.Post("/{id}/request-queues/repair", queuesRepairHandler(d.FileStore))
					rt.Post("/{id}/request-queues/drop", queuesDropHandler(d.FileStore))
					rt.Get("/{id}/request-queues/{domain}/{filename}", queuesReadFileHandler(d.FileStore))
					rt.Post("/{id}/request-queues/{domain}/{filename}", queuesWriteFileHandler(d.FileStore))
				}
			})

			rt.Get("/api/capacity", capacityGetHandler(d.RedisStore))

			rt.Get("/api/replicas/history", replicasHistoryHandler(d.RedisStore))
			rt.Get("/api/replicas/{id}/history", replicaHistoryByIDHandler(d.RedisStore))

			rt.Get("/api/system/stats", systemStatsHandler(d.RedisStore))
			rt.Get("/api/system/health", systemHealthHandler(d.RedisStore))

			rt.Get("/api/domains", domainsListHandler(d.RedisStore))
			rt.Get("/api/domains/{domain}", domainsGetHandler(d.RedisStore))

			rt.Get("/api/timeline", timelineHandler(d.RedisStore))
			rt.Get("/api/alerts", alertsHandler(d.RedisStore))

			rt.Get("/api/callbacks", callbacksListHandler(d.RedisStore))
			rt.Post("/api/callbacks/clear", callbacksClearHandler(d.RedisStore, d.AuditStore))
			rt.Post("/api/callbacks/{idx}/retry", callbacksRetryHandler(d.RedisStore, d.AuditStore))
			rt.Delete("/api/callbacks/{idx}", callbacksDeleteHandler(d.RedisStore, d.AuditStore))

			if d.AuditStore != nil {
				if adapted, ok := d.AuditStore.(*auditStoreAdapter); ok {
					rt.Get("/api/audit", auditListHandler(adapted.s))
				}
			}
		})
	}

	return r
}
