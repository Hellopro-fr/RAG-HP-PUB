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
	"github.com/Hellopro-fr/crawler-monitor-backend/internal/ws"
	"github.com/go-chi/chi/v5"
)

type Deps struct {
	Version    string
	Config     *config.Config
	RedisStore *redisstore.Client
	FileStore  *filestore.Storage
	AuditStore AuditAppender
	Hub        *ws.Hub
	PubSub     *ws.PubSub
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

// auditIfSet monte AuditMiddleware quand un magasin d'audit est configure,
// sinon un middleware neutre (les tests instancient le routeur sans audit).
func auditIfSet(store AuditAppender, action string) func(http.Handler) http.Handler {
	if store == nil {
		return func(next http.Handler) http.Handler { return next }
	}
	// id / domain / filename identifient la cible de l'action auditee.
	return mw.AuditMiddleware(store, action, mw.AuditOptions{
		CaptureParams: []string{"id", "domain", "filename"},
	})
}

func NewRouter(d Deps) http.Handler {
	r := chi.NewRouter()
	r.Use(mw.SecurityHeaders)

	// CORS monte inconditionnellement : sans liste configuree, mw.CORS
	// retombe sur "*" — ce qui etait deja le comportement effectif (aucun
	// en-tete CORS = navigateur bloque), mais de facon explicite et loguee
	// au demarrage par config.Load.
	if d.Config != nil {
		r.Use(mw.CORS(d.Config.CorsAllowedOrigins))
	}
	if d.Config != nil && d.Config.RateLimitMax > 0 {
		r.Use(mw.RateLimitByIP(d.Config.RateLimitMax,
			time.Duration(d.Config.RateLimitWindowMs)*time.Millisecond))
	}

	r.Get("/health", healthHandler(d.Version))

	if d.Hub != nil && d.Config != nil {
		r.Get("/", ws.UpgradeHandler(d.Hub, d.Config.JWTSecret, d.Config.CorsAllowedOrigins...))
		r.Get("/api", ws.UpgradeHandler(d.Hub, d.Config.JWTSecret, d.Config.CorsAllowedOrigins...))
	}

	if d.Config != nil {
		// Quota dedie : la connexion est la seule route qui teste un secret.
		r.With(mw.RateLimitLogin()).
			Post("/api/login", loginHandler(d.Config.AdminPasswordHash, d.Config.JWTSecret, d.AuditStore))
	}

	if d.Config != nil && d.RedisStore != nil {
		r.Group(func(rt chi.Router) {
			rt.Use(mw.JWTAuth(d.Config.JWTSecret))

			rt.Route("/api/jobs", func(rt chi.Router) {
				rt.Get("/", jobsListHandler(d.RedisStore))
				rt.Get("/{id}/details", jobsDetailsHandler(d.RedisStore, d.FileStore))
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
					rt.With(auditIfSet(d.AuditStore, "dataset_deduplicate")).
						Post("/{id}/dataset/deduplicate", datasetDeduplicateHandler(d.FileStore))
					rt.Get("/{id}/request-queues", queuesListHandler(d.FileStore))
					// Statiques avant les routes paramétrées pour que chi route correctement
					rt.Get("/{id}/request-queues/analyze", queuesAnalyzeHandler(d.FileStore))
					// Actions destructrices sur les queues : tracees dans l'audit.
					rt.With(auditIfSet(d.AuditStore, "clean_patterns")).
						Post("/{id}/request-queues/clean-patterns", queuesCleanPatternsHandler(d.FileStore))
					rt.With(auditIfSet(d.AuditStore, "repair_queues")).
						Post("/{id}/request-queues/repair", queuesRepairHandler(d.FileStore))
					rt.With(auditIfSet(d.AuditStore, "drop_queues")).
						Post("/{id}/request-queues/drop", queuesDropHandler(d.FileStore))
					rt.Get("/{id}/request-queues/{domain}/{filename}", queuesReadFileHandler(d.FileStore))
					rt.With(auditIfSet(d.AuditStore, "write_queue_file")).
						Post("/{id}/request-queues/{domain}/{filename}", queuesWriteFileHandler(d.FileStore))
				}
			})

			rt.Get("/api/capacity", capacityGetHandler(d.RedisStore))
			rt.Get("/api/capacity/history", capacityHistoryHandler(d.RedisStore))
			rt.Route("/api/capacity-planning", func(rt chi.Router) {
				rt.Get("/ram", capacityPlanningRAMHandler(d.RedisStore))
			})

			rt.Get("/api/replicas/history", replicasHistoryHandler(d.RedisStore))
			rt.Get("/api/replicas/{id}/history", replicaHistoryByIDHandler(d.RedisStore))

			rt.Get("/api/system/stats", systemStatsHandler(d.RedisStore))
			rt.Get("/api/system/health", systemHealthHandler(d.RedisStore, d.Hub, d.PubSub))

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

			rt.Route("/api/albums", func(rt chi.Router) {
				baseURL := ""
				if d.Config != nil {
					// imageproxy will fall back to env IMAGE_DOWNLOAD_SERVICE_URL or default
					baseURL = ""
				}
				MountAlbums(rt, d.AuditStore, baseURL, 10)
			})
		})
	}

	return r
}
